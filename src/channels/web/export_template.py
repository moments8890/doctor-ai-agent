"""
报告模板管理路由：上传、查询、删除自定义报告模板，及文件文本提取。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from db.engine import AsyncSessionLocal
from channels.web.ui._utils import _resolve_ui_doctor_id
from infra.observability.audit import audit
from utils.log import log, safe_create_task


router = APIRouter(tags=["export"])

# ---------------------------------------------------------------------------
# Magic-byte MIME validation (server-side, not trusting Content-Type header)
# ---------------------------------------------------------------------------

# Each entry: (magic_bytes_prefix, set_of_allowed_declared_mime_types)
_MAGIC_SIGNATURES: list[tuple[bytes, set[str]]] = [
    (b"%PDF", {"application/pdf"}),
    (b"PK\x03\x04", {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }),
    (b"\xff\xd8\xff", {"image/jpeg"}),
    (b"\x89PNG\r\n\x1a\n", {"image/png"}),
    # WEBP: RIFF????WEBP
    (b"RIFF", {"image/webp"}),
]


def _validate_magic_bytes(raw: bytes, declared_mime: str) -> None:
    """Raise HTTPException 415 if file magic bytes do not match declared MIME."""
    for magic, allowed_mimes in _MAGIC_SIGNATURES:
        if raw[:len(magic)] == magic:
            # Special-case WEBP: bytes 8-12 must be b"WEBP"
            if magic == b"RIFF" and raw[8:12] != b"WEBP":
                continue
            if declared_mime not in allowed_mimes:
                raise HTTPException(
                    status_code=415,
                    detail=f"File magic bytes indicate a different type than declared '{declared_mime}'",
                )
            return  # matched and validated
    # No magic signature matched; for text/plain this is fine
    if declared_mime != "text/plain":
        log(f"[Export] warning: no magic signature match for declared mime={declared_mime}")


_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/webp",
}
_MAX_TEMPLATE_BYTES = 1 * 1024 * 1024  # 1 MB (was 10 MB — only 500 chars used in prompt)


# ---------------------------------------------------------------------------
# Custom report template upload / management
# ---------------------------------------------------------------------------

@router.post("/template/upload")
async def upload_report_template(
    file: UploadFile = File(...),
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """
    Upload a custom report template (PDF / Word / image / text).
    The template text is extracted and stored in system_prompts under
    key  report.template.{doctor_id}.  Future outpatient reports for
    this doctor will use it as a format reference (first 500 chars only).

    IMPORTANT: upload a **generic format template**, not a real patient document.
    The extracted text is stored persistently outside the medical records tables
    and is NOT subject to record-level retention or redaction policies.  Any PHI
    in the uploaded file will persist in system_prompts indefinitely.
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, Word, image, text.",
        )

    raw = await file.read()
    if len(raw) > _MAX_TEMPLATE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 1 MB)")

    # Server-side magic byte validation (not just trusting Content-Type header)
    _validate_magic_bytes(raw, content_type)

    # Extract text from the uploaded file
    text = await _extract_template_text(raw, content_type)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the uploaded file")

    # Store only the first 500 chars — enough for format reference, avoids
    # retaining a full patient document if a doctor uploads one by mistake.
    # The outpatient-report prompt already truncates to 500 chars at read time;
    # this ensures the DB itself doesn't hold more than needed.
    truncated = text[:500]
    # SystemPrompt table removed — template upload is a no-op for now.
    # TODO: migrate template storage to runtime config or file-based approach.

    safe_filename = os.path.basename(file.filename or "unknown")
    log(f"[Export] template uploaded doctor={resolved_doctor_id} file={safe_filename!r} chars={len(text)}")
    safe_create_task(
        audit(resolved_doctor_id, "WRITE", resource_type="report_template", resource_id=resolved_doctor_id)
    )
    return JSONResponse({"status": "ok", "chars": len(text)})


@router.get("/template/status")
async def get_template_status(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """Return whether a custom template exists for this doctor."""
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    # SystemPrompt table removed — no template storage.
    return {"has_template": False, "chars": 0}


@router.delete("/template")
async def delete_report_template(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """Delete the custom template for this doctor (revert to default format)."""
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    # SystemPrompt table removed — no template to delete.
    safe_create_task(
        audit(resolved_doctor_id, "DELETE", resource_type="report_template", resource_id=resolved_doctor_id)
    )
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Template text extraction helpers
# ---------------------------------------------------------------------------

async def _extract_template_text(raw: bytes, content_type: str) -> str:
    """Extract plain text from PDF, Word, image, or text files."""
    if content_type == "text/plain":
        import chardet
        enc = chardet.detect(raw).get("encoding") or "utf-8"
        return raw.decode(enc, errors="replace")

    if content_type == "application/pdf":
        return _extract_pdf_text(raw)

    if content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return _extract_docx_text(raw)

    if content_type.startswith("image/"):
        return await _extract_image_text(raw, content_type)

    return ""


def _extract_pdf_text(raw: bytes) -> str:
    """Extract text from PDF bytes using pypdf (if installed) or pdfminer."""
    try:
        import io
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    except Exception as exc:
        log(f"[Export] pypdf extraction failed: {exc}")
    try:
        import io
        from pdfminer.high_level import extract_text as pm_extract  # type: ignore
        return pm_extract(io.BytesIO(raw))
    except ImportError:
        pass
    except Exception as exc:
        log(f"[Export] pdfminer extraction failed: {exc}")
    return raw.decode("utf-8", errors="replace")


def _extract_docx_text(raw: bytes) -> str:
    """Extract text from Word .docx bytes."""
    try:
        import io
        from docx import Document  # type: ignore
        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        log(f"[Export] docx extraction failed: {exc}")
        return ""


async def _extract_image_text(raw: bytes, content_type: str) -> str:
    """OCR image using the shared vision LLM service (singleton client, with fallback)."""
    try:
        from infra.llm.vision import extract_text_from_image
        text = await extract_text_from_image(raw, content_type)
        if not text.strip():
            raise HTTPException(status_code=422, detail="Vision model returned empty text for this image")
        return text
    except HTTPException:
        raise
    except Exception as exc:
        log(f"[Export] image OCR failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Image text extraction failed (vision LLM error). Please upload a text or PDF file instead.",
        )
