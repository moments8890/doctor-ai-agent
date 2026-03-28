"""
医生个人知识库管理：添加、检索和自动学习医学知识条目。
"""

from __future__ import annotations

import json
import os
import re
import time as _time
from typing import Dict, List, Optional, Sequence, Tuple

from db.crud import add_doctor_knowledge_item, list_doctor_knowledge_items
from db.models import DoctorKnowledgeItem
from utils.log import log

_KNOWLEDGE_ITEMS_CACHE: dict[str, tuple[float, list]] = {}  # doctor_id → (timestamp, raw items)
_KNOWLEDGE_CACHE_TTL = 300  # 5 minutes

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
        except Exception as exc:
            log(
                "[Knowledge] decode payload failed; falling back to raw text payload_prefix={0!r} err={1}".format(
                    content[:80],
                    exc,
                )
            )
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
        "max_chars": _int_env("KNOWLEDGE_MAX_CHARS", 6000, 200),
        "auto_max_new_per_turn": _int_env("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", 1, 1),
    }



def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


# ── Prompt injection sanitization ─────────────────────────────────
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


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


def render_knowledge_context(
    query: str,
    items: Sequence[DoctorKnowledgeItem],
    patient_context: str = "",
) -> str:
    if not items:
        return ""

    limits = knowledge_limits()
    # Expand scoring query with patient fields for better relevance
    scoring_query = query
    if patient_context:
        scoring_query = "{0} {1}".format(query, patient_context)

    scored = []
    for idx, item in enumerate(items):
        text, source, confidence = _decode_knowledge_payload(item.content)
        if not text:
            continue
        relevance = _score_item(scoring_query, text)
        weighted = float(relevance) + _source_weight(source) + float(confidence)
        scored.append((weighted, relevance, -idx, item, text))

    scored.sort(reverse=True)

    # Include ALL items up to max_chars soft cap (no max_items hard cap)
    header = "【医生知识库】\n"
    lines: List[str] = []
    total = len(header)
    for weighted, relevance, _ord, item, text in scored:
        snippet = _sanitize_for_prompt((text or "").strip())
        if not snippet:
            continue
        line = "[KB-{0}] {1}".format(item.id, snippet)
        projected = total + len(line) + 1
        if projected > limits["max_chars"]:
            break
        lines.append(line)
        total = projected

    if not lines:
        return ""

    return header + "\n".join(lines)


async def load_knowledge(
    doctor_id: str,
    query: str = "",
    patient_context: str = "",
) -> str:
    """Load all knowledge items for a doctor, scored against query."""
    from db.engine import AsyncSessionLocal

    if not doctor_id:
        return ""

    limits = knowledge_limits()
    async with AsyncSessionLocal() as session:
        items = await list_doctor_knowledge_items(
            session, doctor_id, limit=limits["candidate_limit"],
        )
    if not items:
        return ""

    return render_knowledge_context(query=query, items=items, patient_context=patient_context)


async def load_knowledge_context_for_prompt(session, doctor_id: str, query: str) -> str:
    """Load knowledge items (cached by doctor_id) and render per-query.

    Raw items are cached by doctor_id with a 5-minute TTL to avoid repeated DB reads.
    Rendering (scoring/ranking against the query) is always done fresh so that
    different queries surface the most relevant items.
    """
    now = _time.time()
    cached = _KNOWLEDGE_ITEMS_CACHE.get(doctor_id)
    if cached and now - cached[0] < _KNOWLEDGE_CACHE_TTL:
        items = cached[1]
    else:
        limits = knowledge_limits()
        items = await list_doctor_knowledge_items(
            session,
            doctor_id,
            limit=limits["candidate_limit"],
        )
        _KNOWLEDGE_ITEMS_CACHE[doctor_id] = (now, list(items))
    return render_knowledge_context(query=query, items=items)


def invalidate_knowledge_cache(doctor_id: str) -> None:
    """Clear cached knowledge items for a doctor (call after add/delete)."""
    _KNOWLEDGE_ITEMS_CACHE.pop(doctor_id, None)


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
    return await add_doctor_knowledge_item(session, doctor_id, payload, category="custom")


async def extract_and_process_document(file_bytes: bytes, filename: str) -> dict:
    """Extract text from uploaded file, LLM-process if long."""
    # 1. Detect format from extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # 2. Extract raw text
    if ext == "pdf":
        from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
        raw_text = await extract_text_from_pdf_smart(file_bytes)
    elif ext in ("docx", "doc"):
        from domain.knowledge.word_extract import extract_text_from_docx
        raw_text = extract_text_from_docx(file_bytes)
    elif ext == "txt":
        # Try UTF-8, fallback to chardet
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                import chardet
                detected = chardet.detect(file_bytes)
                raw_text = file_bytes.decode(detected.get("encoding", "gbk"))
            except Exception:
                raw_text = file_bytes.decode("gbk", errors="replace")
    else:
        raise ValueError("不支持的文件格式: .{0}".format(ext))

    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("文件内容为空")

    # 3. LLM process if text > 500 chars
    llm_processed = False
    if len(raw_text) > 500:
        processed = await _llm_process_knowledge(raw_text)
        if processed:
            raw_text = processed
            llm_processed = True

    return {
        "extracted_text": raw_text,
        "source_filename": filename,
        "char_count": len(raw_text),
        "llm_processed": llm_processed,
    }


async def _llm_process_knowledge(raw_text: str) -> Optional[str]:
    """Use LLM to clean/structure raw document text into a knowledge item."""
    import pathlib
    prompt_path = pathlib.Path(__file__).resolve().parent.parent / "agent" / "prompts" / "knowledge_ingest.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_message = system_prompt.replace("{{document_text}}", raw_text[:8000])  # cap input

    from agent.llm import llm_call
    try:
        result = await llm_call(
            messages=[{"role": "user", "content": user_message}],
            op_name="knowledge_ingest",
            max_tokens=2000,
            temperature=0.1,
        )
        text = result.strip() if result else None
        if text and text != "未提取到可用的临床知识内容":
            return text
        return None
    except Exception as e:
        log("[Knowledge] LLM processing failed: {0}".format(e))
        return None  # fallback to raw text


async def process_knowledge_text(raw_text: str) -> dict:
    """Process manual text input through LLM if >=500 chars.

    Returns dict with processed_text, original_length, processed_length, llm_processed.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("内容不能为空")

    original_length = len(text)
    llm_processed = False

    if original_length >= 500:
        processed = await _llm_process_knowledge(text)
        if processed:
            text = processed
            llm_processed = True

    return {
        "processed_text": text,
        "original_length": original_length,
        "processed_length": len(text),
        "llm_processed": llm_processed,
    }


async def save_uploaded_knowledge(doctor_id: str, text: str, source_filename: str) -> dict:
    """Save doctor-approved text as a knowledge item."""
    from db.engine import AsyncSessionLocal

    if not text or not text.strip():
        raise ValueError("内容不能为空")
    if len(text) > 3000:
        raise ValueError("内容过长（超过3000字）")

    payload = _encode_knowledge_payload(text.strip(), source="upload:{0}".format(source_filename), confidence=1.0)

    async with AsyncSessionLocal() as session:
        item = await add_doctor_knowledge_item(session, doctor_id, payload, category="custom")
        # Note: add_doctor_knowledge_item already commits

    # Invalidate cache
    invalidate_knowledge_cache(doctor_id)

    return {"id": item.id, "text_preview": text[:100]}


async def maybe_auto_learn_knowledge(
    session,
    doctor_id: str,
    user_text: str,
    structured_fields: Optional[Dict[str, str]] = None,
) -> int:
    # Auto-learn disabled to prevent self-reinforcing hallucination loop.
    # Doctor-curated items only. See D6.4 spec.
    return 0
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
