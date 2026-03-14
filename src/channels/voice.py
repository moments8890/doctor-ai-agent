"""Voice channel — transcribe audio then route through ADR 0011 runtime."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from db.models.medical_record import MedicalRecord
from constants import SUPPORTED_AUDIO_TYPES
from services.ai.transcription import transcribe_audio
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.runtime import TurnEnvelope, process_turn
from utils.log import log

router = APIRouter(prefix="/api/voice", tags=["voice"])

_MAX_TRANSCRIPT_LENGTH = 8000
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class VoiceChatResponse(BaseModel):
    """Voice chat response with transcript and runtime result."""
    transcript: str
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None
    switch_notification: Optional[str] = None


async def _transcribe_upload(
    audio: UploadFile, doctor_id: str, *, consultation_mode: bool = False,
) -> str:
    """Read upload, transcribe, return transcript text."""
    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
    try:
        transcript = await transcribe_audio(
            audio_bytes, audio.filename or "audio.wav",
            consultation_mode=consultation_mode,
        )
    except Exception as e:
        log(f"[Voice] transcription FAILED doctor={doctor_id}: {e}", level="error", exc_info=True)
        raise HTTPException(status_code=500, detail="Transcription failed")
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")
    if len(transcript) > _MAX_TRANSCRIPT_LENGTH:
        transcript = transcript[:_MAX_TRANSCRIPT_LENGTH]
    return transcript


async def _voice_chat(
    audio: UploadFile, doctor_id: str, *, consultation_mode: bool = False,
) -> VoiceChatResponse:
    """Transcribe audio then route through ADR 0011 runtime."""
    enforce_doctor_rate_limit(doctor_id, scope="voice.chat")
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported: {audio.content_type}")

    transcript = await _transcribe_upload(audio, doctor_id, consultation_mode=consultation_mode)
    result = await process_turn(TurnEnvelope(
        doctor_id=doctor_id,
        text=transcript,
        channel="voice",
        modality="voice",
    ))

    return VoiceChatResponse(
        transcript=transcript,
        reply=result.reply,
        pending_id=result.pending_id,
        pending_patient_name=result.pending_patient_name,
        pending_expires_at=result.pending_expires_at,
    )


@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    history: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> VoiceChatResponse:
    """Transcribe audio and route through conversation runtime."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_chat(audio, resolved)


@router.post("/consultation", response_model=VoiceChatResponse)
async def voice_consultation(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    history: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> VoiceChatResponse:
    """Transcribe consultation audio (dialogue-aware) and route through runtime."""
    resolved = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_chat(audio, resolved, consultation_mode=True)
