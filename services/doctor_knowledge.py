from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

from db.crud import add_doctor_knowledge_item, list_doctor_knowledge_items
from db.models import DoctorKnowledgeItem
from utils.log import log

_ADD_TO_KNOWLEDGE_RE = re.compile(
    r"^\s*(?:add_to_knowledge_base|add\s+to\s+knowledge\s+base|添加(?:到)?知识库|保存知识)(?:[\s:：]+(.*))?\s*$",
    flags=re.IGNORECASE,
)


_KNOWLEDGE_PAYLOAD_VERSION = 1
_AUTO_KNOWLEDGE_HINTS = (
    "建议", "优先", "先", "再", "需要", "应", "避免", "禁忌",
    "随访", "复查", "流程", "规范", "用药", "剂量", "观察",
)


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_text(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _encode_knowledge_payload(text: str, source: str, confidence: float) -> str:
    payload = {
        "v": _KNOWLEDGE_PAYLOAD_VERSION,
        "text": _normalize_text(text),
        "source": source,
        "confidence": max(0.0, min(1.0, float(confidence))),
    }
    return json.dumps(payload, ensure_ascii=False)


def _decode_knowledge_payload(raw: str) -> Tuple[str, str, float]:
    content = (raw or "").strip()
    if not content:
        return "", "doctor", 1.0
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
                return text, source, max(0.0, min(1.0, confidence))
        except Exception:
            pass
    return _normalize_text(content), "doctor", 1.0


def _source_weight(source: str) -> float:
    return 0.5 if source == "doctor" else 0.2


def _extract_auto_candidates(text: str, structured_fields: Optional[Dict[str, str]]) -> List[str]:
    content = _normalize_text(text)
    if not content:
        return []
    min_chars = _int_env("KNOWLEDGE_AUTO_MIN_TEXT_CHARS", 8, 4)
    candidates: List[str] = []

    if len(content) >= min_chars and any(h in content for h in _AUTO_KNOWLEDGE_HINTS):
        candidates.append(content[: _int_env("KNOWLEDGE_MAX_ITEM_CHARS", 320, 80)])

    fields = structured_fields or {}
    diagnosis = _normalize_text(str(fields.get("diagnosis") or ""))
    treatment = _normalize_text(str(fields.get("treatment_plan") or ""))
    follow_up = _normalize_text(str(fields.get("follow_up_plan") or ""))
    if diagnosis and treatment:
        candidates.append("临床处理经验：{0}；治疗建议：{1}".format(diagnosis, treatment))
    if follow_up:
        candidates.append("随访要点：{0}".format(follow_up))
    # Dedup while preserving order
    out: List[str] = []
    seen = set()
    for c in candidates:
        normalized = _normalize_text(c)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def parse_add_to_knowledge_command(text: str) -> Optional[str]:
    """Return payload when message is an add-to-knowledge command."""
    matched = _ADD_TO_KNOWLEDGE_RE.match((text or "").strip())
    if not matched:
        return None
    payload = (matched.group(1) or "").strip()
    return payload



def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", text or "") if tok]



def _score_item(query: str, item_content: str) -> int:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0
    haystack = (item_content or "").lower()
    score = 0
    for tok in query_tokens:
        if tok in haystack:
            score += 2
    return score



def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)



def knowledge_limits() -> dict:
    return {
        "candidate_limit": _int_env("KNOWLEDGE_CANDIDATE_LIMIT", 30, 1),
        "max_items": _int_env("KNOWLEDGE_MAX_ITEMS", 3, 1),
        "max_chars": _int_env("KNOWLEDGE_MAX_CHARS", 1200, 200),
        "max_item_chars": _int_env("KNOWLEDGE_MAX_ITEM_CHARS", 320, 80),
        "auto_max_new_per_turn": _int_env("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", 1, 1),
    }



def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"



def render_knowledge_context(query: str, items: Sequence[DoctorKnowledgeItem]) -> str:
    if not items:
        return ""

    limits = knowledge_limits()
    scored = []
    for idx, item in enumerate(items):
        text, source, confidence = _decode_knowledge_payload(item.content)
        if not text:
            continue
        score = _score_item(query, text)
        weighted = float(score) + _source_weight(source) + float(confidence)
        # Prefer relevant items, then fresher order by index (earlier = newer in query result).
        scored.append((weighted, -idx, item, text))

    scored.sort(reverse=True)
    selected: List[DoctorKnowledgeItem] = []
    selected_texts: List[str] = []
    for score, _ord, item, text in scored:
        if len(selected) >= limits["max_items"]:
            break
        # Always allow at least one newest item, even if score=0
        if score <= 0 and selected:
            continue
        selected.append(item)
        selected_texts.append(text)

    if not selected:
        selected = [items[0]]
        first_text, _source, _confidence = _decode_knowledge_payload(items[0].content)
        selected_texts = [first_text]

    lines: List[str] = []
    total = len("【医生知识库（仅作背景约束）】\n")
    for index, snippet_raw in enumerate(selected_texts, 1):
        snippet = _truncate_text((snippet_raw or "").strip(), limits["max_item_chars"])
        if not snippet:
            continue
        line = "{0}. {1}".format(index, snippet)
        projected = total + len(line) + 1
        if projected > limits["max_chars"]:
            break
        lines.append(line)
        total = projected

    if not lines:
        return ""

    return "【医生知识库（仅作背景约束）】\n" + "\n".join(lines)


async def load_knowledge_context_for_prompt(session, doctor_id: str, query: str) -> str:
    limits = knowledge_limits()
    items = await list_doctor_knowledge_items(
        session,
        doctor_id,
        limit=limits["candidate_limit"],
    )
    return render_knowledge_context(query=query, items=items)


async def save_knowledge_item(
    session,
    doctor_id: str,
    text: str,
    source: str = "doctor",
    confidence: float = 1.0,
) -> Optional[DoctorKnowledgeItem]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return None
    limits = knowledge_limits()
    cleaned = cleaned[: limits["max_item_chars"]]

    existing = await list_doctor_knowledge_items(
        session,
        doctor_id,
        limit=max(5, limits["candidate_limit"]),
    )
    normalized_new = _normalize_text(cleaned)
    for row in existing:
        row_text, _row_source, _row_conf = _decode_knowledge_payload(row.content)
        if _normalize_text(row_text) == normalized_new:
            return row

    payload = _encode_knowledge_payload(cleaned, source=source, confidence=confidence)
    return await add_doctor_knowledge_item(session, doctor_id, payload)


async def maybe_auto_learn_knowledge(
    session,
    doctor_id: str,
    user_text: str,
    structured_fields: Optional[Dict[str, str]] = None,
) -> int:
    if not _bool_env("KNOWLEDGE_AUTO_LEARN_ENABLED", True):
        return 0
    limits = knowledge_limits()
    candidates = _extract_auto_candidates(user_text, structured_fields)
    if not candidates:
        return 0
    inserted = 0
    for candidate in candidates[: limits["auto_max_new_per_turn"]]:
        try:
            row = await save_knowledge_item(
                session,
                doctor_id,
                candidate,
                source="agent_auto",
                confidence=0.6,
            )
        except Exception as exc:
            log(
                "[Knowledge] auto learn save failed doctor={0} candidate={1}: {2}".format(
                    doctor_id,
                    candidate[:80],
                    exc,
                )
            )
            continue
        if row is not None:
            inserted += 1
    return inserted
