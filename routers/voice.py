from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from db.crud import create_patient as db_create_patient, find_patient_by_name, save_record
from db.engine import AsyncSessionLocal
from models.medical_record import MedicalRecord
from routers.records import (
    SUPPORTED_AUDIO_TYPES,
    _assistant_asked_for_name,
    _is_valid_patient_name,
    _name_only_text,
)
from services.agent import dispatch as agent_dispatch
from services.intent import Intent
from services.structuring import structure_medical_record
from services.transcription import transcribe_audio
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
) -> VoiceChatResponse:
    """Doctor speaks a command or dictates a record; audio is transcribed then
    routed through the full agent dispatch pipeline."""
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )

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
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")

    asked_name_in_last_turn = _assistant_asked_for_name(history_list)
    followup_name = _name_only_text(transcript) if asked_name_in_last_turn else None

    try:
        intent_result = await agent_dispatch(transcript, history=history_list)
    except Exception as e:
        msg = str(e)
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        raise HTTPException(status_code=status, detail=msg)

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
            patient = await db_create_patient(
                db, doctor_id, name, intent_result.gender, intent_result.age
            )
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
            if not fields.get("chief_complaint"):
                fields["chief_complaint"] = "门诊就诊"
            record = MedicalRecord(**{k: fields.get(k) for k in MedicalRecord.model_fields})
        else:
            doctor_ctx = [m["content"] for m in history_list[-10:] if m.get("role") == "user"]
            if not (followup_name and transcript.strip() == followup_name):
                doctor_ctx.append(transcript)
            if not doctor_ctx:
                doctor_ctx.append(transcript)
            try:
                record = await structure_medical_record("\n".join(doctor_ctx))
            except Exception as e:
                return VoiceChatResponse(transcript=transcript, reply=f"病历生成失败：{e}")

        patient_id = None
        patient_name = intent_result.patient_name
        patient_created = False
        async with AsyncSessionLocal() as db:
            if patient_name:
                patient = await find_patient_by_name(db, doctor_id, patient_name)
                if not patient:
                    patient = await db_create_patient(
                        db, doctor_id, patient_name,
                        intent_result.gender, intent_result.age,
                    )
                    patient_created = True
                patient_id = patient.id
            await save_record(db, doctor_id, record, patient_id)

        reply = intent_result.chat_reply
        if not reply:
            if patient_name:
                reply = "✅ 已为【" + patient_name + "】" + ("新建档并" if patient_created else "") + "保存病历。"
            else:
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
) -> ConsultationResponse:
    """Doctor uploads an ambient consultation recording; transcribed with
    dialogue-aware prompt then structured into a MedicalRecord."""
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )

    audio_bytes = await audio.read()

    try:
        transcript = await transcribe_audio(
            audio_bytes, audio.filename or "audio.wav", consultation_mode=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")

    try:
        record = await structure_medical_record(transcript, consultation_mode=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structuring failed: {e}")

    saved_patient_id: Optional[int] = None
    if save:
        async with AsyncSessionLocal() as db:
            if patient_name:
                patient = await find_patient_by_name(db, doctor_id, patient_name)
                if not patient:
                    patient = await db_create_patient(db, doctor_id, patient_name)
                saved_patient_id = patient.id
            await save_record(db, doctor_id, record, saved_patient_id)
        log(f"[VoiceConsultation] saved record patient={patient_name} doctor={doctor_id}")

    return ConsultationResponse(
        transcript=transcript,
        record=record,
        patient_id=saved_patient_id,
    )
