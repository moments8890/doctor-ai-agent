"""Records router — utility endpoints for text extraction and import."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field
from typing import Optional

from infra.llm.vision import extract_text_from_image
from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from utils.log import log

from constants import SUPPORTED_IMAGE_TYPES

router = APIRouter(prefix="/api/records", tags=["records"])

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Pydantic models ───────────────────────────────────────────────────────────

class TextInput(BaseModel):
    """Input for /from-text endpoint."""
    text: str = Field(..., max_length=16000)


class ExtractedTextResponse(BaseModel):
    """Output for /from-image, /from-audio."""
    reply: str
    source: str
    extracted_text: str


class TextOnlyResponse(BaseModel):
    """Output for /transcribe, /ocr."""
    text: str


class FileExtractResponse(BaseModel):
    """Output for /extract-file."""
    text: Optional[str] = None
    filename: str



# ── Utility endpoints ────────────────────────────────────────────────────────

@router.post("/from-text")
async def create_record_from_text(
    body: TextInput,
    doctor_id: str = "",
    patient_id: Optional[int] = None,
    authorization: Optional[str] = Header(default=None),
):
    """Extract fields from text → create intake session for doctor review."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    enforce_doctor_rate_limit(resolved, scope="records.from_text")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    try:
        from domain.records.structuring import text_to_intake
        return await text_to_intake(body.text, doctor_id=resolved, patient_id=patient_id)
    except ValueError as e:
        log(f"[Records] from-text validation failed: {e}")
        raise HTTPException(status_code=422, detail="Invalid medical record content")
    except Exception as e:
        log(f"[Records] from-text failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/from-image", response_model=ExtractedTextResponse)
async def create_record_from_image(
    image: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """OCR an image then import."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    enforce_doctor_rate_limit(resolved, scope="records.from_image")
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported: {image.content_type}")
    try:
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
        text = await extract_text_from_image(image_bytes, image.content_type)
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] from-image OCR failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="OCR extracted no text")
    reply = await _import_extracted_text(text, resolved, source="image")
    return {"reply": reply, "source": "image", "extracted_text": text}


async def _import_extracted_text(text: str, doctor_id: str, *, source: str) -> str:
    """Dispatch extracted text to import_history."""
    from types import SimpleNamespace
    from domain.records.import_history import handle_import_history
    intent_result = SimpleNamespace(patient_name=None, extra_data={"source": source})
    try:
        return await handle_import_history(text, doctor_id, intent_result)
    except Exception as e:
        log(f"[Records] import failed source={source} doctor={doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="Import failed")


@router.post("/ocr", response_model=TextOnlyResponse)
async def ocr_image_only(
    image: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from an image without creating a record."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    enforce_doctor_rate_limit(resolved, scope="records.ocr")
    content_type = (image.content_type or "").split(";")[0].strip()
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported: {content_type}")
    try:
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
        return {"text": await extract_text_from_image(image_bytes, content_type)}
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] ocr failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")


@router.post("/extract-file", response_model=FileExtractResponse)
async def extract_file_for_chat(
    file: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from a PDF or image for the chat input."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    enforce_doctor_rate_limit(resolved, scope="records.extract_file")
    content_type = (file.content_type or "").split(";")[0].strip()
    filename = file.filename or ""
    try:
        raw = await file.read()
        if len(raw) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            text = await extract_text_from_pdf_smart(raw)
        elif content_type in SUPPORTED_IMAGE_TYPES:
            text = await extract_text_from_image(raw, content_type)
        else:
            raise HTTPException(status_code=422, detail="Unsupported format (PDF or image only)")
        return {"text": text, "filename": filename}
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] extract-file failed: {e}")
        raise HTTPException(status_code=500, detail="File extraction failed")




