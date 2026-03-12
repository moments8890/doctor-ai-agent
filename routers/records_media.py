"""
病历媒体端点：处理文本、图片、音频文件上传及 OCR/转录。

ADR 0009: image/PDF uploads default to import_history after extraction.
Extraction-only helpers (/ocr, /extract-file, /transcribe) are unchanged.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Header
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from routers.records import SUPPORTED_AUDIO_TYPES, SUPPORTED_IMAGE_TYPES, TextInput
from services.ai.intent import IntentResult, Intent
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from services.ai.vision import extract_text_from_image
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.knowledge.pdf_extract_llm import extract_text_from_pdf_llm
from utils.log import log

router = APIRouter(prefix="/api/records", tags=["records"])


@router.post("/from-text", response_model=MedicalRecord)
async def create_record_from_text(body: TextInput):
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


class ImportMediaResponse(BaseModel):
    """Response for media import endpoints (ADR 0009)."""
    reply: str
    source: str
    extracted_text: Optional[str] = None


@router.post("/from-image", response_model=ImportMediaResponse)
async def import_from_image(
    image: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """OCR an image then import via import_history (ADR 0009).

    Previously returned a single MedicalRecord from direct structuring.
    Now extracts text and dispatches to the import workflow for chunking,
    dedup, and persistence.
    """
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {image.content_type}. Supported: jpeg, png, webp, gif.",
        )
    try:
        image_bytes = await image.read()
        text = await extract_text_from_image(image_bytes, image.content_type)
    except Exception as e:
        log(f"[Records] from-image OCR failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")

    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="OCR 未能从图片中提取文字")

    reply = await _import_extracted_text(text, resolved_doctor_id, source="image")
    return ImportMediaResponse(reply=reply, source="image", extracted_text=text)


@router.post("/from-audio")
async def import_from_audio(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Transcribe audio then import via import_history (ADR 0009).

    Previously returned a single MedicalRecord from direct structuring.
    Now transcribes and dispatches to the import workflow.
    """
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
    except Exception as e:
        log(f"[Records] from-audio transcription failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcript or not transcript.strip():
        raise HTTPException(status_code=422, detail="转录未产生有效文本")

    reply = await _import_extracted_text(transcript, resolved_doctor_id, source="voice")
    return ImportMediaResponse(reply=reply, source="voice", extracted_text=transcript)


@router.post("/transcribe")
async def transcribe_audio_only(audio: UploadFile = File(...)):
    """Transcribe audio to text without creating a medical record."""
    content_type = (audio.content_type or "").split(";")[0].strip()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        if not content_type.startswith("audio/"):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {content_type}. Upload an audio file.",
            )
    try:
        audio_bytes = await audio.read()
        text = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
        return {"text": text}
    except Exception as e:
        log(f"[Records] transcribe failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")


@router.post("/ocr")
async def ocr_image_only(image: UploadFile = File(...)):
    """Extract text from an image without creating a medical record."""
    content_type = (image.content_type or "").split(";")[0].strip()
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {content_type}. Upload a JPEG, PNG, or WebP image.",
        )
    try:
        image_bytes = await image.read()
        text = await extract_text_from_image(image_bytes, content_type)
        return {"text": text}
    except Exception as e:
        log(f"[Records] ocr failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")


@router.post("/extract-file")
async def extract_file_for_chat(file: UploadFile = File(...)):
    """Extract text from a PDF or image for the chat input."""
    content_type = (file.content_type or "").split(";")[0].strip()
    filename = file.filename or ""
    MAX_BYTES = 20 * 1024 * 1024  # 20 MB
    try:
        raw = await file.read()
        if len(raw) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            text = await extract_text_from_pdf_llm(raw)
            if text is None:
                import asyncio as _asyncio
                text = await _asyncio.get_event_loop().run_in_executor(
                    None, extract_text_from_pdf, raw
                )
        elif content_type in SUPPORTED_IMAGE_TYPES:
            text = await extract_text_from_image(raw, content_type)
        else:
            raise HTTPException(
                status_code=422,
                detail="不支持的文件格式，请上传 PDF 或图片（JPG/PNG）",
            )
        return {"text": text, "filename": filename}
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] extract-file failed: {e}")
        raise HTTPException(status_code=500, detail="文件解析失败，请重试")


async def _import_extracted_text(text: str, doctor_id: str, *, source: str) -> str:
    """Dispatch extracted text to import_history with source metadata."""
    from services.wechat.wechat_import import handle_import_history

    intent_result = IntentResult(
        intent=Intent.import_history,
        extra_data={"source": source},
    )
    try:
        return await handle_import_history(text, doctor_id, intent_result)
    except Exception as e:
        log(f"[Records] import failed source={source} doctor={doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="导入处理失败，请重试")


@router.get("/{record_id}/history")
async def record_history(
    record_id: int,
    doctor_id: str = "test_doctor",
    authorization: Optional[str] = Header(default=None),
):
    """Return the correction history (versions) for a record, oldest first."""
    from db.crud import get_record_versions
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select as _select
        from db.models import MedicalRecordDB as _MRD
        rec = (await db.execute(
            _select(_MRD).where(_MRD.id == record_id, _MRD.doctor_id == resolved_doctor_id)
        )).scalar_one_or_none()
        if rec is None:
            raise HTTPException(status_code=404, detail="Record not found")
        versions = await get_record_versions(db, record_id, resolved_doctor_id)
    return {
        "record_id": record_id,
        "versions": [
            {
                "id": v.id,
                "old_content": v.old_content,
                "old_tags": v.old_tags,
                "old_record_type": v.old_record_type,
                "changed_at": v.changed_at.isoformat() if v.changed_at else None,
            }
            for v in versions
        ],
    }
