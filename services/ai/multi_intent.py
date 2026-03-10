"""多意图消息拆分：检测含 2 个以上独立意图的消息，并拆分为可独立处理的子消息。"""

from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from utils.log import log

# ── Pre-check regex signals ──────────────────────────────────────────────────
# "先...再..." with 4+ chars in each part
_XIAN_ZAI_RE = re.compile(r"先.{4,}再.{4,}")

# "...。另外..." or "...，另外..."
_LINGWAI_RE = re.compile(r"[。，].{0,2}另外")

# "...。然后..." or "...，然后..." when followed by action verb
_RANHOU_RE = re.compile(r"[。，].{0,2}然后.{0,3}[记查建设安排删]")

_MIN_LEN = 20  # minimum total message length to avoid false positives


def _might_be_multi_intent(text: str) -> bool:
    """Fast regex pre-check: returns True if message may contain multiple intents."""
    if len(text) < _MIN_LEN:
        return False
    if _XIAN_ZAI_RE.search(text):
        return True
    if _LINGWAI_RE.search(text):
        return True
    if _RANHOU_RE.search(text):
        return True
    return False


_SPLIT_PROMPT = (
    "你是消息拆分助手。将以下医生消息拆分为多个独立意图的子消息（每个可单独执行）。\n"
    "只返回JSON数组，不要其他内容。若是单一意图，返回单元素数组。最多5个子消息。\n"
    "每个子消息保留完整上下文（包含患者姓名）。\n"
    "消息：{text}\n"
    "示例：[\"先记赵峰头痛2天\", \"记施铭胸闷3天\", \"查询赵峰历史病历\"]"
)


def _resolve_provider(provider_name: str, provider: dict) -> dict:
    """Apply env-var overrides to a provider config dict (returns a copy)."""
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "openai":
        provider["base_url"] = os.environ.get("OPENAI_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("OPENAI_MODEL", provider["model"])
    return provider


def _parse_segments(raw: str) -> Optional[List[str]]:
    """Extract and validate a JSON array of segment strings from a raw LLM response."""
    json_start = raw.find("[")
    json_end = raw.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        log(f"[MultiIntent] no JSON array in LLM response: {raw[:100]}")
        return None
    segments = json.loads(raw[json_start:json_end])
    if not isinstance(segments, list):
        log(f"[MultiIntent] LLM returned non-list: {raw[:100]}")
        return None
    segments = [s for s in segments if isinstance(s, str) and len(s) >= 3]
    return segments if len(segments) >= 2 else None


async def split_multi_intent(
    text: str,
    doctor_id: str,
    history: Optional[List[dict]] = None,
) -> Optional[List[str]]:
    """
    Detect and split a multi-intent message into individual sub-messages.

    Returns a list of 2+ segment strings if multi-intent is detected,
    or None if the message is single-intent (or splitting failed).
    """
    if not _might_be_multi_intent(text):
        return None

    # Import provider infrastructure from agent.py
    from services.ai.agent import _get_client
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("ROUTING_LLM") or os.environ.get("STRUCTURING_LLM", "deepseek")
    provider_cfg = _PROVIDERS.get(provider_name)
    if provider_cfg is None:
        log(f"[MultiIntent] provider {provider_name!r} not found, skipping split")
        return None

    provider = _resolve_provider(provider_name, provider_cfg)
    prompt = _SPLIT_PROMPT.format(text=text)
    try:
        client = _get_client(provider_name, provider)
        completion = await client.chat.completions.create(
            model=provider["model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip()
        segments = _parse_segments(raw)
        if segments is None:
            return None
        log(f"[MultiIntent] split into {len(segments)} segments doctor={doctor_id}")
        return segments
    except Exception as e:
        log(f"[MultiIntent] LLM split failed doctor={doctor_id}: {e}")
        return None
