"""面向患者的微信消息处理流水线：健康问答、急症关键词检测与会话管理。

Patient-facing WeChat message pipeline.

Non-doctor senders receive a helpful health Q&A response instead of a static
rejection.  No access to medical records.  Emergency keywords route to 120
guidance immediately, bypassing the LLM.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import List

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emergency detection
# ---------------------------------------------------------------------------

_EMERGENCY_KEYWORDS = frozenset(
    {
        "胸痛", "胸闷", "心梗", "心脏骤停", "心脏病发", "中风", "脑卒中",
        "呼吸困难", "喘不过气", "晕倒", "意识丧失", "意识不清", "昏迷",
        "大出血", "严重出血", "骨折", "溺水", "触电", "急救", "救命",
        "休克", "脑出血", "急性腹痛",
    }
)

_EMERGENCY_REPLY = (
    "⚠️ 您描述的症状可能是急症，请立即拨打 120 急救电话！\n\n"
    "等待救护车期间：\n"
    "• 保持冷静，不要独自行动\n"
    "• 告知家人或周围人\n"
    "• 如有需要，可拨打 110 或 119 配合救援"
)

_NON_TEXT_REPLY = (
    "您好！\n"
    "此频道目前支持文字消息。\n"
    "如需就医咨询，请直接发送文字提问；\n"
    "如有紧急情况，请拨打 120。"
)

# ---------------------------------------------------------------------------
# Per-patient session memory (in-process, 2-turn window, 30-min TTL)
# ---------------------------------------------------------------------------

_SESSION_TTL = 30 * 60  # 30 minutes
_SESSION_MAX_TURNS = 2   # keep last N user+assistant pairs


@dataclass
class _PatientSession:
    history: List[dict] = field(default_factory=list)
    last_active: float = field(default_factory=time.monotonic)


_patient_sessions: dict[str, _PatientSession] = {}


def _get_patient_session(open_id: str) -> _PatientSession:
    now = time.monotonic()
    sess = _patient_sessions.get(open_id)
    if sess is None or (now - sess.last_active) > _SESSION_TTL:
        sess = _PatientSession()
        _patient_sessions[open_id] = sess
    sess.last_active = now
    return sess


def _trim_history(history: List[dict]) -> List[dict]:
    """Keep at most _SESSION_MAX_TURNS user+assistant pairs (2*N messages)."""
    max_msgs = _SESSION_MAX_TURNS * 2
    return history[-max_msgs:] if len(history) > max_msgs else history


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

from services.patient import PATIENT_SYSTEM_PROMPT as _PATIENT_SYSTEM_PROMPT

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return (client, model). Uses the shared provider registry to stay aligned
    with the main routing stack's configuration. Singleton per base_url+model,
    bypassed in tests."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError("patient pipeline LLM not available in test context")
    from services.ai.llm_client import _PROVIDERS
    provider_name = os.environ.get("STRUCTURING_LLM", "ollama")
    # PHI egress gate: patient chat carries clinical history.
    from services.ai.egress_policy import is_local_provider, check_cloud_egress
    if not is_local_provider(provider_name):
        check_cloud_egress(provider_name, "patient_pipeline")
    provider = _PROVIDERS.get(provider_name) or _PROVIDERS.get("ollama", {})
    base_url = os.environ.get("OLLAMA_BASE_URL") or provider.get("base_url") or "http://192.168.0.123:11434/v1"
    model = (
        os.environ.get("PATIENT_LLM_MODEL")
        or os.environ.get("STRUCTURING_LLM_MODEL")
        or provider.get("model", "qwen2.5:14b")
    )
    api_key = os.environ.get(provider.get("api_key_env", "OLLAMA_API_KEY"), "ollama")
    cache_key = f"{base_url}:{model}"
    if cache_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[cache_key] = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return _CLIENT_CACHE[cache_key], model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_emergency_keyword(text: str) -> bool:
    return any(kw in text for kw in _EMERGENCY_KEYWORDS)


async def handle_patient_message(text: str, open_id: str) -> str:
    """Process a text message from a non-doctor (patient) sender.

    Returns the reply string to deliver back.  Never raises — falls back to a
    safe static message on any failure.
    """
    if has_emergency_keyword(text):
        log.info("[patient] emergency keyword detected open_id=%s", open_id[:8])
        return _EMERGENCY_REPLY

    try:
        client, model = _get_llm_client()
    except RuntimeError:
        return "您好！如需就医请联系主治医生或前往医院就诊。如有紧急情况请拨打 120。"

    from utils.prompt_loader import get_prompt
    patient_prompt = await get_prompt("patient.chat", _PATIENT_SYSTEM_PROMPT)
    sess = _get_patient_session(open_id)
    sess.history = _trim_history(sess.history)
    messages = [{"role": "system", "content": patient_prompt}]
    messages.extend(sess.history)
    messages.append({"role": "user", "content": text})

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=400,
            temperature=0.3,
        )
        reply = (resp.choices[0].message.content or "").strip()
        reply = reply or "感谢您的留言，如有需要请前往医院就诊。"
        # Persist turn in session history
        sess.history.append({"role": "user", "content": text})
        sess.history.append({"role": "assistant", "content": reply})
        sess.history = _trim_history(sess.history)
        return reply
    except Exception:
        log.exception("[patient] LLM call failed open_id=%s", open_id[:8])
        return "您好！目前系统繁忙，如有紧急情况请拨打 120 或前往医院就诊。"
