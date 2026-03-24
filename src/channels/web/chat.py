"""Records router — chat endpoint uses ADR 0012 UEC runtime; utility endpoints unchanged."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Literal, Optional

from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from domain.records.structuring import structure_medical_record
from infra.llm.vision import extract_text_from_image
from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from agent import handle_turn
from agent.actions import Action
from channels.web.deps import get_doctor_id
from messages import M
from utils.log import log

from constants import SUPPORTED_IMAGE_TYPES

router = APIRouter(prefix="/api/records", tags=["records"])

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Pydantic models ───────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    """Single turn in client-supplied history (accepted but not used by runtime)."""
    role: Literal["user", "assistant"] = Field(..., description="Must be 'user' or 'assistant'")
    content: str = Field(..., max_length=16000)


class ChatInput(BaseModel):
    """Input for the /chat endpoint."""
    text: str = Field(..., max_length=8000)
    history: List[HistoryMessage] = Field(default_factory=list)
    doctor_id: str = ""
    action_hint: Optional[Action] = None

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return value or ""

    @field_validator("history")
    @classmethod
    def _validate_history(cls, value: List[HistoryMessage]) -> List[HistoryMessage]:
        if len(value) > 100:
            raise ValueError("history exceeds max length (100)")
        return value


class TextInput(BaseModel):
    """Input for /from-text endpoint."""
    text: str = Field(..., max_length=16000)


class ChatResponse(BaseModel):
    """Output for the /chat endpoint."""
    reply: str
    record: Optional[MedicalRecord] = None
    record_id: Optional[int] = None
    view_payload: Optional[Dict[str, Any]] = None  # structured data for web rendering (ADR 0012 §14)
    switch_notification: Optional[str] = None  # patient-switch system message


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





# ── Chat endpoint ──────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatInput,
    authorization: Optional[str] = Header(default=None),
):
    """Doctor chat — UEC pipeline runtime (ADR 0012)."""
    doctor_id = resolve_doctor_id_from_auth_or_fallback(
        body.doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")

    enforce_doctor_rate_limit(doctor_id, scope="records.chat")

    result = await handle_turn(text, "doctor", doctor_id, action_hint=body.action_hint)
    return ChatResponse(reply=result.reply, view_payload=result.data)


# ── Utility endpoints (unchanged) ───────────────────────────────────────────

@router.post("/from-text", response_model=MedicalRecord)
async def create_record_from_text(
    body: TextInput,
    doctor_id: str = "",
    authorization: Optional[str] = Header(default=None),
):
    """Structure raw text into a medical record."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )
    enforce_doctor_rate_limit(resolved, scope="records.from_text")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    try:
        return await structure_medical_record(body.text)
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
    from channels.wechat.wechat_import import handle_import_history
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




