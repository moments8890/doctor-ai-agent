"""
Knowledge CRUD helpers: encode/decode payloads, save/invalidate, parse commands.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Tuple

from db.crud import add_doctor_knowledge_item, list_doctor_knowledge_items
from db.models import DoctorKnowledgeItem
from db.models.doctor import KnowledgeCategory
from utils.log import log

# ── Regex & constants ──────────────────────────────────────────────

_ADD_TO_KNOWLEDGE_RE = re.compile(
    r"^\s*(?:add_to_knowledge_base|add\s+to\s+knowledge\s+base|添加(?:到)?知识库|保存知识)(?:[\s:：]+(.*))?\s*$",
    flags=re.IGNORECASE,
)

_KNOWLEDGE_PAYLOAD_VERSION = 1
_AUTO_KNOWLEDGE_HINTS = (
    "建议", "优先", "先", "再", "需要", "应", "避免", "禁忌",
    "随访", "复查", "流程", "规范", "用药", "剂量", "观察",
)

# ── Prompt injection sanitization ─────────────────────────────────
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


# ── Env helpers ────────────────────────────────────────────────────

def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


# ── Text helpers ───────────────────────────────────────────────────

def _normalize_text(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _sanitize_for_prompt(text: str) -> str:
    """Sanitize user-authored KB text before injecting into LLM prompts.

    - Escape XML/HTML angle brackets to fullwidth equivalents
    - Escape [KB- patterns to prevent spoofed citation markers
    - Strip control chars U+0000-U+001F except \\n (0x0A) and \\t (0x09)
    """
    out = text.replace("<", "\uff1c").replace(">", "\uff1e")
    out = out.replace("[KB-", "\\[KB-")
    out = _CONTROL_CHAR_RE.sub("", out)
    return out


# ── Payload encode/decode ──────────────────────────────────────────

def _encode_knowledge_payload(
    text: str,
    source: str,
    confidence: float,
    source_url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    payload = {
        "v": _KNOWLEDGE_PAYLOAD_VERSION,
        "text": _normalize_text(text),
        "source": source,
        "confidence": max(0.0, min(1.0, float(confidence))),
    }
    if source_url is not None:
        payload["source_url"] = source_url
    if file_path is not None:
        payload["file_path"] = file_path
    return json.dumps(payload, ensure_ascii=False)


def _decode_knowledge_payload(raw: str) -> Tuple[str, str, float, Optional[str], Optional[str]]:
    """Decode a knowledge payload JSON string.

    Returns (text, source, confidence, source_url, file_path).
    """
    content = (raw or "").strip()
    if not content:
        return "", "doctor", 1.0, None, None
    if content.startswith("{") and '"text"' in content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                text = _normalize_text(str(parsed.get("text") or ""))
                source = str(parsed.get("source") or "doctor")
                try:
                    confidence = float(parsed.get("confidence", 1.0))
                except (TypeError, ValueError):
                    confidence = 1.0
                source_url = parsed.get("source_url") or None
                file_path = parsed.get("file_path") or None
                return text, source, max(0.0, min(1.0, confidence)), source_url, file_path
        except Exception as exc:
            log(
                "[Knowledge] decode payload failed; falling back to raw text payload_prefix={0!r} err={1}".format(
                    content[:80],
                    exc,
                )
            )
    return _normalize_text(content), "doctor", 1.0, None, None


# ── Limits ─────────────────────────────────────────────────────────

def knowledge_limits() -> dict:
    return {
        "candidate_limit": _int_env("KNOWLEDGE_CANDIDATE_LIMIT", 30, 1),
        "max_chars": _int_env("KNOWLEDGE_MAX_CHARS", 6000, 200),
        "auto_max_new_per_turn": _int_env("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", 1, 1),
    }


# ── Command parser ─────────────────────────────────────────────────

def parse_add_to_knowledge_command(text: str) -> Optional[str]:
    """Return payload when message is an add-to-knowledge command."""
    matched = _ADD_TO_KNOWLEDGE_RE.match((text or "").strip())
    if not matched:
        return None
    payload = (matched.group(1) or "").strip()
    return payload


# ── Cache invalidation ─────────────────────────────────────────────

def invalidate_knowledge_cache(doctor_id: str) -> None:
    """Clear cached knowledge items for a doctor (call after add/delete).

    The cache itself lives in knowledge_context; this function is imported
    there and re-exported here so callers only need one import location.
    """
    # Import from context module to avoid duplicating the cache dict.
    from domain.knowledge.knowledge_context import _invalidate_cache
    _invalidate_cache(doctor_id)


# ── Title extraction ──────────────────────────────────────────────

def extract_title_from_text(text: str, max_len: int = 20) -> str:
    """Extract a SHORT title from knowledge text.

    Strategy: prefer the shortest meaningful split.
    1. Split on newline -> take first line
    2. Try colon first (strongest title delimiter): ： or :
    3. Then period: 。
    4. Truncate to max_len (default 20 chars for CJK)
    """
    if not text:
        return ""
    first_line = text.split("\n")[0].strip()
    # Try colon first — "蛛网膜下腔出血（SAH）：..." -> "蛛网膜下腔出血（SAH）"
    for sep in ("：", ":"):
        if sep in first_line:
            candidate = first_line.split(sep)[0].strip()
            if candidate:
                first_line = candidate
                break
    else:
        # No colon found — try period
        if "。" in first_line:
            first_line = first_line.split("。")[0].strip()
    if len(first_line) > max_len:
        first_line = first_line[:max_len] + "…"
    return first_line


# ── DB write ───────────────────────────────────────────────────────

async def save_knowledge_item(
    session,
    doctor_id: str,
    text: str,
    source: str = "doctor",
    confidence: float = 1.0,
    category: str = KnowledgeCategory.custom,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    source_url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> Optional[DoctorKnowledgeItem]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return None
    limits = knowledge_limits()

    existing = await list_doctor_knowledge_items(
        session,
        doctor_id,
        limit=max(5, limits["candidate_limit"]),
    )
    normalized_new = _normalize_text(cleaned)
    for row in existing:
        row_text, _row_source, _row_conf, _row_url, _row_fp = _decode_knowledge_payload(row.content)
        if _normalize_text(row_text) == normalized_new:
            return row

    payload = _encode_knowledge_payload(cleaned, source=source, confidence=confidence, source_url=source_url)
    item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
    item.title = title or extract_title_from_text((text or "").strip())
    item.summary = summary
    await session.commit()
    await session.refresh(item)
    return item
