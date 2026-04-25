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
    """Use LLM to clean/structure raw document text into a knowledge item.

    Document text comes from PDF / DOCX / image uploads. Even when the
    doctor uploaded the file, its content is upstream-of-us and can
    contain prompt-injection payloads. Wrap in a trust boundary before
    substituting so embedded "ignore prior" instructions stay data.
    """
    from agent.prompt_safety import wrap_untrusted

    prompt_path = pathlib.Path(__file__).resolve().parent.parent / "agent" / "prompts" / "knowledge_ingest.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_message = system_prompt.replace(
        "{{document_text}}",
        wrap_untrusted("document_text", raw_text[:8000]),
    )

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
    elif ext in ("jpg", "jpeg", "png", "webp"):
        _MIME_MAP = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
        from infra.llm.vision import extract_text_from_image
        raw_text = await extract_text_from_image(file_bytes, _MIME_MAP.get(ext, "image/jpeg"))
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


async def extract_text_from_url(url: str) -> dict:
    """Fetch a URL, strip HTML tags, LLM-process the text content."""
    import re
    from html.parser import HTMLParser
    import httpx

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, trust_env=False) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 DoctorAI/1.0"})
        resp.raise_for_status()
        html = resp.text

    # Extract text from HTML
    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: List[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "svg", "head", "nav", "footer", "header"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "svg", "head", "nav", "footer", "header"):
                self._skip = False
            if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "article", "section"):
                self._parts.append("\n")

        def handle_data(self, data):
            if not self._skip:
                self._parts.append(data)

    parser = _TextExtractor()
    parser.feed(html)
    raw_text = "".join(parser._parts)
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    raw_text = re.sub(r"[ \t]+", " ", raw_text).strip()

    if not raw_text:
        raise ValueError("页面内容为空")

    # LLM process if text > 500 chars
    llm_processed = False
    if len(raw_text) > 500:
        processed = await _llm_process_knowledge(raw_text)
        if processed:
            raw_text = processed
            llm_processed = True

    return {
        "extracted_text": raw_text,
        "source_url": url,
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


async def save_uploaded_knowledge(
    doctor_id: str,
    text: str,
    source_filename: str,
    category: str = KnowledgeCategory.custom,
    source_url: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    """Save doctor-approved text as a knowledge item."""
    from db.engine import AsyncSessionLocal
    from db.crud import add_doctor_knowledge_item

    if not text or not text.strip():
        raise ValueError("内容不能为空")
    if len(text) > 3000:
        raise ValueError("内容过长（超过3000字）")

    if source_url:
        source_label = "url:{0}".format(source_url)
    else:
        source_label = "upload:{0}".format(source_filename)
    payload = _encode_knowledge_payload(
        text.strip(),
        source=source_label,
        confidence=1.0,
        source_url=source_url,
        file_path=file_path,
    )

    async with AsyncSessionLocal() as session:
        item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
        # Note: add_doctor_knowledge_item already commits
        if item:
            item.title = extract_title_from_text(text.strip())
            await session.commit()

    # Invalidate cache
    invalidate_knowledge_cache(doctor_id)

    return {"id": item.id, "text_preview": text[:100]}
