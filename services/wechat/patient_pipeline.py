"""
Patient-facing WeChat message pipeline.

Non-doctor senders receive a helpful health Q&A response instead of a static
rejection.  No access to medical records.  Emergency keywords route to 120
guidance immediately, bypassing the LLM.
"""
from __future__ import annotations

import logging
import os

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
# LLM client
# ---------------------------------------------------------------------------

_PATIENT_SYSTEM_PROMPT = """你是一个友善的医疗健康助手，帮助患者解答基本健康问题和就医建议。

重要规则：
- 你无法访问患者的个人病历或私人医疗信息
- 不做具体诊断，不给出处方建议
- 若患者描述急重症状（胸痛、呼吸困难、意识丧失、大出血等），建议立即拨打 120
- 用友善、通俗的语言回答，复杂情况建议前往医院就诊
- 回复简洁，不超过 200 字"""

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return (client, model). Singleton per base_url+model, bypassed in tests."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError("patient pipeline LLM not available in test context")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = (
        os.environ.get("PATIENT_LLM_MODEL")
        or os.environ.get("STRUCTURING_LLM_MODEL", "qwen2.5:14b")
    )
    cache_key = f"{base_url}:{model}"
    if cache_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[cache_key] = AsyncOpenAI(base_url=base_url, api_key="ollama")
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

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _PATIENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return reply or "感谢您的留言，如有需要请前往医院就诊。"
    except Exception:
        log.exception("[patient] LLM call failed open_id=%s", open_id[:8])
        return "您好！目前系统繁忙，如有紧急情况请拨打 120 或前往医院就诊。"
