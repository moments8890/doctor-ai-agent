"""
语音录入路由：接收音频上传并通过 Whisper 转录后结构化为病历。
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from db.crud import create_patient as db_create_patient, find_patient_by_name, save_record
from db.engine import AsyncSessionLocal
from models.medical_record import MedicalRecord
from routers.records import SUPPORTED_AUDIO_TYPES
from routers.records import _assistant_asked_for_name
from routers.records import _is_valid_patient_name
from routers.records import _name_only_text
from services.ai.agent import dispatch as agent_dispatch
from utils.errors import InvalidMedicalRecordError
from services.ai.intent import Intent
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from utils.log import log

router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    record: Optional[MedicalRecord] = None


class ConsultationResponse(BaseModel):
    transcript: str
    record: MedicalRecord
    patient_id: Optional[int] = None


@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    history: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> VoiceChatResponse:
    """Doctor speaks a command or dictates a record; audio is transcribed then
    routed through the full agent dispatch pipeline."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_chat_for_doctor(audio, resolved_doctor_id, history=history)


async def _voice_chat_for_doctor(
    audio: UploadFile,
    doctor_id: str,
    history: Optional[str] = None,
) -> VoiceChatResponse:
    enforce_doctor_rate_limit(doctor_id, scope="voice.chat")

    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.")  # noqa: E501

    # Parse history JSON string
    history_list: List[dict] = []
    if history:
        try:
            history_list = json.loads(history)
            if not isinstance(history_list, list):
                raise ValueError("history must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Malformed history: {e}")

    audio_bytes = await audio.read()

    try:
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
    except Exception as e:
        log(f"[VoiceChat] transcription FAILED doctor={doctor_id} file={audio.filename}: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")

    asked_name_in_last_turn = _assistant_asked_for_name(history_list)
    followup_name = _name_only_text(transcript) if asked_name_in_last_turn else None

    try:
        intent_result = await agent_dispatch(transcript, history=history_list)
    except Exception as e:
        msg = str(e)
        log(f"[VoiceChat] dispatch FAILED doctor={doctor_id} msg={transcript[:80]!r}: {msg}")
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        detail = "rate_limit_exceeded" if status == 429 else "Service temporarily unavailable"
        raise HTTPException(status_code=status, detail=detail)

    # Two-turn name followup: assistant asked for name -> doctor replies with name only
    if followup_name:
        intent_result.intent = Intent.add_record
        intent_result.patient_name = followup_name

    reply: str = ""
    record: Optional[MedicalRecord] = None

    # ── create_patient ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.create_patient:
        name = intent_result.patient_name
        if not name:
            return VoiceChatResponse(transcript=transcript, reply="好的，请告诉我患者的姓名。")
        async with AsyncSessionLocal() as db:
            try:
                patient = await db_create_patient(
                    db, doctor_id, name, intent_result.gender, intent_result.age
                )
            except InvalidMedicalRecordError:
                return VoiceChatResponse(transcript=transcript, reply="⚠️ 患者姓名格式无效，请更正后重试。")
        parts = "、".join(filter(None, [
            intent_result.gender,
            f"{intent_result.age}岁" if intent_result.age else None,
        ]))
        reply = f"✅ 已为患者【{patient.name}】建档" + (f"（{parts}）" if parts else "") + "。"
        log(f"[VoiceChat] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
        return VoiceChatResponse(transcript=transcript, reply=reply)

    # ── add_record ─────────────────────────────────────────────────────────────
    if intent_result.intent == Intent.add_record:
        if not intent_result.patient_name or not _is_valid_patient_name(intent_result.patient_name):
            return VoiceChatResponse(transcript=transcript, reply="请问这位患者叫什么名字？")

        if intent_result.structured_fields:
            fields = dict(intent_result.structured_fields)
            if not fields.get("content"):
                fields["content"] = "门诊就诊"
            record = MedicalRecord(**{k: v for k, v in fields.items() if k in MedicalRecord.model_fields and v is not None})
        else:
            doctor_ctx = [m["content"] for m in history_list[-10:] if m.get("role") == "user"]
            if not (followup_name and transcript.strip() == followup_name):
                doctor_ctx.append(transcript)
            if not doctor_ctx:
                doctor_ctx.append(transcript)
            try:
                record = await structure_medical_record("\n".join(doctor_ctx))
            except Exception as e:
                log(f"[VoiceChat] structuring FAILED doctor={doctor_id} patient={intent_result.patient_name}: {e}")
                return VoiceChatResponse(transcript=transcript, reply="病历生成失败，请稍后重试。")

        patient_id = None
        patient_name = intent_result.patient_name
        patient_created = False
        async with AsyncSessionLocal() as db:
            if patient_name:
                patient = await find_patient_by_name(db, doctor_id, patient_name)
                if not patient:
                    try:
                        patient = await db_create_patient(
                            db, doctor_id, patient_name,
                            intent_result.gender, intent_result.age,
                        )
                    except InvalidMedicalRecordError:
                        return VoiceChatResponse(transcript=transcript, reply="⚠️ 患者姓名格式无效，请更正后重试。")
                    patient_created = True
                patient_id = patient.id
            await save_record(db, doctor_id, record, patient_id)

        reply = intent_result.chat_reply
        if not reply:
            if patient_name:
                reply = "✅ 已为【" + patient_name + "】" + ("新建档并" if patient_created else "") + "保存病历。"
            else:  # pragma: no cover
                reply = "✅ 病历已保存。"
        log(f"[VoiceChat] saved record patient={patient_name} doctor={doctor_id}")
        return VoiceChatResponse(transcript=transcript, reply=reply, record=record)

    # ── unknown / conversational ───────────────────────────────────────────────
    return VoiceChatResponse(
        transcript=transcript,
        reply=intent_result.chat_reply or "您好！有什么可以帮您？",
    )


@router.post("/consultation", response_model=ConsultationResponse)
async def voice_consultation(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    patient_name: Optional[str] = Form(default=None),
    save: bool = Form(default=False),
    authorization: Optional[str] = Header(default=None),
) -> ConsultationResponse:
    """Doctor uploads an ambient consultation recording; transcribed with
    dialogue-aware prompt then structured into a MedicalRecord."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_consultation_for_doctor(
        audio,
        resolved_doctor_id,
        patient_name=patient_name,
        save=save,
    )


async def _voice_consultation_for_doctor(
    audio: UploadFile,
    doctor_id: str,
    *,
    patient_name: Optional[str] = None,
    save: bool = False,
) -> ConsultationResponse:
    enforce_doctor_rate_limit(doctor_id, scope="voice.consultation")

    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.")  # noqa: E501

    audio_bytes = await audio.read()

    try:
        transcript = await transcribe_audio(
            audio_bytes, audio.filename or "audio.wav", consultation_mode=True
        )
    except Exception as e:
        log(f"[VoiceConsultation] transcription FAILED doctor={doctor_id} file={audio.filename}: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")

    try:
        record = await structure_medical_record(transcript, consultation_mode=True)
    except Exception as e:
        log(f"[VoiceConsultation] structuring FAILED doctor={doctor_id} patient={patient_name}: {e}")
        raise HTTPException(status_code=500, detail="Structuring failed")

    saved_patient_id: Optional[int] = None
    if save:
        async with AsyncSessionLocal() as db:
            if patient_name:
                patient = await find_patient_by_name(db, doctor_id, patient_name)
                if not patient:
                    try:
                        patient = await db_create_patient(db, doctor_id, patient_name)
                    except InvalidMedicalRecordError:
                        raise HTTPException(status_code=422, detail="Invalid patient name")
                saved_patient_id = patient.id
            await save_record(db, doctor_id, record, saved_patient_id)
        log(f"[VoiceConsultation] saved record patient={patient_name} doctor={doctor_id}")

    return ConsultationResponse(
        transcript=transcript,
        record=record,
        patient_id=saved_patient_id,
    )
