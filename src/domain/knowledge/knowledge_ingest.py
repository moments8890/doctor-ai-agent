"""
Knowledge ingest: extract text from uploaded files, LLM-process, and save.
"""

from __future__ import annotations

import pathlib
from typing import Dict, List, Optional

from domain.knowledge.knowledge_crud import (
    _AUTO_KNOWLEDGE_HINTS,
    _encode_knowledge_payload,
    _int_env,
    _normalize_text,
    extract_title_from_text,
    invalidate_knowledge_cache,
    knowledge_limits,
)
from db.models.doctor import KnowledgeCategory
from utils.log import log


# ── Auto-candidate extraction (used by WeChat auto-learn) ──────────

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


# ── LLM processing ─────────────────────────────────────────────────

async def _llm_process_knowledge(raw_text: str) -> Optional[str]:
    """Use LLM to clean/structure raw document text into a knowledge item."""
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


# ── Document extraction ────────────────────────────────────────────

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


async def save_uploaded_knowledge(doctor_id: str, text: str, source_filename: str, category: str = KnowledgeCategory.custom) -> dict:
    """Save doctor-approved text as a knowledge item."""
    from db.engine import AsyncSessionLocal
    from db.crud import add_doctor_knowledge_item

    if not text or not text.strip():
        raise ValueError("内容不能为空")
    if len(text) > 3000:
        raise ValueError("内容过长（超过3000字）")

    payload = _encode_knowledge_payload(text.strip(), source="upload:{0}".format(source_filename), confidence=1.0)

    async with AsyncSessionLocal() as session:
        item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
        # Note: add_doctor_knowledge_item already commits
        if item:
            item.title = extract_title_from_text(text.strip())
            await session.commit()

    # Invalidate cache
    invalidate_knowledge_cache(doctor_id)

    return {"id": item.id, "text_preview": text[:100]}
