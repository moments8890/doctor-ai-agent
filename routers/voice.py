"""
语音录入路由：接收音频上传并通过 Whisper 转录后经 5-layer 工作流结构化为病历。

Voice chat routes through the shared 5-layer intent workflow and draft-first
safety model, matching the behaviour of Web and WeChat channels.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from db.models.medical_record import MedicalRecord
from services.domain.chat_constants import SUPPORTED_AUDIO_TYPES
from services.domain.name_utils import (
    assistant_asked_for_name as _assistant_asked_for_name,
    is_blocked_write_cancel as _is_blocked_write_cancel,
    name_only_text as _name_only_text,
)
from services.ai.intent import Intent, IntentResult
from services.intent_workflow.precheck import (
    precheck_blocked_write as _precheck_blocked_write,
    is_blocked_write_cancel_reply as _is_blocked_write_cancel_reply,
)
from services.session import (
    set_blocked_write_context as _set_blocked_write_context,
    clear_blocked_write_context as _clear_blocked_write_context,
)
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from services.domain.intent_handlers import (
    HandlerResult,
    handle_add_record as shared_handle_add_record,
    handle_cancel_task as shared_handle_cancel_task,
    handle_complete_task as shared_handle_complete_task,
    handle_create_patient as shared_handle_create_patient,
    handle_delete_patient as shared_handle_delete_patient,
    handle_list_patients as shared_handle_list_patients,
    handle_list_tasks as shared_handle_list_tasks,
    handle_postpone_task as shared_handle_postpone_task,
    handle_query_records as shared_handle_query_records,
    handle_schedule_appointment as shared_handle_schedule_appointment,
    handle_schedule_follow_up as shared_handle_schedule_follow_up,
    handle_update_patient as shared_handle_update_patient,
    handle_update_record as shared_handle_update_record,
)
from services.session import hydrate_session_state
from utils.log import log

router = APIRouter(prefix="/api/voice", tags=["voice"])


# ── Response models ────────────────────────────────────────────────────────


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None  # ISO-8601 UTC
    switch_notification: Optional[str] = None


class ConsultationResponse(BaseModel):
    transcript: str
    record: MedicalRecord
    patient_id: Optional[int] = None


# ── Transcription ──────────────────────────────────────────────────────────


async def _transcribe_upload(
    audio: UploadFile,
    doctor_id: str,
) -> tuple[bytes, str]:
    """读取上传文件并转录，返回 (audio_bytes, transcript)；失败时抛 HTTPException。"""
    audio_bytes = await audio.read()
    try:
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
    except Exception as e:
        log(f"[VoiceChat] transcription FAILED doctor={doctor_id} file={audio.filename}: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")
    return audio_bytes, transcript


# ── HandlerResult → VoiceChatResponse conversion ──────────────────────────


def _handler_result_to_voice(transcript: str, hr: HandlerResult) -> VoiceChatResponse:
    """Convert a shared-layer HandlerResult to VoiceChatResponse."""
    return VoiceChatResponse(
        transcript=transcript,
        reply=hr.reply,
        record=hr.record,
        pending_id=hr.pending_id,
        pending_patient_name=hr.pending_patient_name,
        pending_expires_at=hr.pending_expires_at,
        switch_notification=hr.switch_notification,
    )


# ── Intent dispatch via shared handlers ───────────────────────────────────


async def _dispatch_voice_intent(
    transcript: str,
    doctor_id: str,
    intent_result: IntentResult,
    history_list: list,
    followup_name: Optional[str],
) -> VoiceChatResponse:
    """Route resolved intent to shared domain handlers and convert to VoiceChatResponse."""
    intent = intent_result.intent

    if intent == Intent.create_patient:
        hr = await shared_handle_create_patient(
            doctor_id, intent_result, body_text=transcript, original_text=transcript,
        )
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.add_record:
        hr = await shared_handle_add_record(
            transcript, doctor_id, history_list, intent_result,
            followup_name=followup_name,
        )
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.query_records:
        hr = await shared_handle_query_records(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.list_patients:
        hr = await shared_handle_list_patients(doctor_id)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.delete_patient:
        hr = await shared_handle_delete_patient(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.list_tasks:
        hr = await shared_handle_list_tasks(doctor_id)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.complete_task:
        hr = await shared_handle_complete_task(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.schedule_appointment:
        hr = await shared_handle_schedule_appointment(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.update_patient:
        hr = await shared_handle_update_patient(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.update_record:
        hr = await shared_handle_update_record(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.postpone_task:
        hr = await shared_handle_postpone_task(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.cancel_task:
        hr = await shared_handle_cancel_task(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.schedule_follow_up:
        hr = await shared_handle_schedule_follow_up(doctor_id, intent_result)
        return _handler_result_to_voice(transcript, hr)

    if intent == Intent.help:
        return VoiceChatResponse(
            transcript=transcript,
            reply="您好！我可以帮您：建档、记录病历、查询患者、安排随访。\n发「帮助」可查看完整功能列表。",
        )

    # unknown / fallback
    return VoiceChatResponse(
        transcript=transcript,
        reply=intent_result.chat_reply or "您好！有什么可以帮您？",
    )


# ── Main voice chat flow ──────────────────────────────────────────────────


async def _voice_chat_for_doctor(
    audio: UploadFile,
    doctor_id: str,
    history: Optional[str] = None,
) -> VoiceChatResponse:
    """转录音频，经 5-layer 工作流路由意图，分发至共享处理函数，返回结构化回复。"""
    enforce_doctor_rate_limit(doctor_id, scope="voice.chat")

    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.")  # noqa: E501

    history_list: List[dict] = []
    if history:
        try:
            history_list = json.loads(history)
            if not isinstance(history_list, list):
                raise ValueError("history must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Malformed history: {e}")

    _audio_bytes, transcript = await _transcribe_upload(audio, doctor_id)

    asked_name_in_last_turn = _assistant_asked_for_name(history_list)
    followup_name = _name_only_text(transcript) if asked_name_in_last_turn else None

    # Hydrate session state before workflow (same as WeChat path)
    await hydrate_session_state(doctor_id)

    # ── Blocked-write precheck (ADR 0007) ─────────────────────────────────
    if _is_blocked_write_cancel_reply(doctor_id, transcript):
        _clear_blocked_write_context(doctor_id)
        return VoiceChatResponse(transcript=transcript, reply="好的，已取消。")

    continuation = _precheck_blocked_write(doctor_id, transcript)
    if continuation is not None:
        _ir = IntentResult(
            intent=Intent.add_record,
            patient_name=continuation.patient_name,
        )
        hr = await shared_handle_add_record(
            continuation.clinical_text, doctor_id,
            continuation.history_snapshot,
            _ir, followup_name=continuation.patient_name,
        )
        return _handler_result_to_voice(transcript, hr)

    # Run the shared 5-layer intent workflow pipeline
    from services.intent_workflow import run as workflow_run

    try:
        result = await workflow_run(
            transcript, doctor_id, history_list,
            followup_name=followup_name,
            channel="voice",
        )
    except Exception as e:
        msg = str(e)
        log(f"[VoiceChat] workflow FAILED doctor={doctor_id} msg={transcript[:80]!r}: {msg}")
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        detail = "rate_limit_exceeded" if status == 429 else "Service temporarily unavailable"
        raise HTTPException(status_code=status, detail=detail)

    # Gate check: block unsafe operations before dispatching
    if not result.gate.approved:
        if (
            result.gate.reason == "no_patient_name"
            and result.decision.intent == Intent.add_record
        ):
            _set_blocked_write_context(
                doctor_id,
                intent="add_record",
                clinical_text=transcript,
                original_text=transcript,
                history_snapshot=list(history_list),
            )
            log(f"[VoiceChat] blocked write stored doctor={doctor_id} text={transcript[:60]!r}")
        if result.gate.reason != "no_patient_name":
            return VoiceChatResponse(
                transcript=transcript,
                reply=result.gate.clarification_message or "没太理解您的意思，能说得更具体一些吗？",
            )

    intent_result = result.to_intent_result()

    # Followup-name override: when the assistant asked for a patient name and
    # the user replied with just a name, always treat as add_record using
    # clinical content from history (regardless of what the LLM classified).
    if followup_name and intent_result.intent != Intent.add_record:
        intent_result = IntentResult(
            intent=Intent.add_record,
            patient_name=followup_name,
            gender=intent_result.gender,
            age=intent_result.age,
            extra_data=intent_result.extra_data,
        )

    return await _dispatch_voice_intent(
        transcript, doctor_id, intent_result, history_list, followup_name,
    )


# ── Endpoint ───────────────────────────────────────────────────────────────


@router.post("/chat", response_model=VoiceChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    history: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> VoiceChatResponse:
    """Doctor speaks a command or dictates a record; audio is transcribed then
    routed through the 5-layer intent workflow pipeline."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_chat_for_doctor(audio, resolved_doctor_id, history=history)


# ── Consultation endpoint (unchanged — transcribe + structure, no workflow) ─


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
        from db.crud import create_patient as db_create_patient, find_patient_by_name, save_record
        from db.engine import AsyncSessionLocal
        from utils.errors import InvalidMedicalRecordError

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
