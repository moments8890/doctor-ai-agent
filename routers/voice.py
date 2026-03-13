"""
语音录入路由：接收音频上传并通过 Whisper 转录后经 5-layer 工作流结构化为病历。

Voice chat routes through the shared 5-layer intent workflow and draft-first
safety model, matching the behaviour of Web and WeChat channels.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from db.models.medical_record import MedicalRecord
from services.domain.chat_constants import SUPPORTED_AUDIO_TYPES
from services.ai.intent import Intent, IntentResult
from services.session import (
    push_and_flush_turn as _push_and_flush_turn,
    set_blocked_write_context as _set_blocked_write_context,
)
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
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

_ROUTING_HISTORY_MAX_MESSAGES = max(0, int(os.environ.get("ROUTING_HISTORY_MAX_MESSAGES", "2")))
_MAX_TRANSCRIPT_LENGTH = 8000  # match web channel limit
_WORKFLOW_TIMEOUT = float(os.environ.get("VOICE_WORKFLOW_TIMEOUT", "30"))


# ── Response models ────────────────────────────────────────────────────────


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None  # ISO-8601 UTC
    switch_notification: Optional[str] = None


# ── Transcription ──────────────────────────────────────────────────────────


async def _transcribe_upload(
    audio: UploadFile,
    doctor_id: str,
    *,
    consultation_mode: bool = False,
) -> tuple[bytes, str]:
    """读取上传文件并转录，返回 (audio_bytes, transcript)；失败时抛 HTTPException。"""
    _MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
    try:
        transcript = await transcribe_audio(
            audio_bytes, audio.filename or "audio.wav",
            consultation_mode=consultation_mode,
        )
    except Exception as e:
        log(f"[VoiceChat] transcription FAILED doctor={doctor_id} file={audio.filename}: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcription produced empty text.")
    if len(transcript) > _MAX_TRANSCRIPT_LENGTH:
        log(f"[VoiceChat] transcript too long ({len(transcript)} chars) doctor={doctor_id}, truncating")
        transcript = transcript[:_MAX_TRANSCRIPT_LENGTH]
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
) -> VoiceChatResponse:
    """Route resolved intent to shared domain handlers and convert to VoiceChatResponse."""
    from services.domain.intent_handlers import dispatch_intent

    # Channel-specific overrides
    if intent_result.intent == Intent.help:
        return VoiceChatResponse(
            transcript=transcript,
            reply="您好！我可以帮您：建档、记录病历、查询患者、安排随访。\n发「帮助」可查看完整功能列表。",
        )

    hr = await dispatch_intent(
        transcript, doctor_id, history_list, intent_result,
        original_text=transcript,
    )
    return _handler_result_to_voice(transcript, hr)


# ── Main voice chat flow ──────────────────────────────────────────────────


async def _voice_chat_for_doctor(
    audio: UploadFile,
    doctor_id: str,
    history: Optional[str] = None,
    *,
    consultation_mode: bool = False,
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
            raise HTTPException(status_code=422, detail="Malformed history: expected a JSON array")

    _audio_bytes, transcript = await _transcribe_upload(
        audio, doctor_id, consultation_mode=consultation_mode,
    )

    # Hydrate session state before workflow (same as WeChat path)
    await hydrate_session_state(doctor_id, write_intent=True)

    # ── Shared stateful prechecks ─────────────────────────────────────────
    from services.intent_workflow.precheck import PrecheckContext, run_stateful_prechecks

    _pctx = PrecheckContext(
        doctor_id=doctor_id, text=transcript, original_text=transcript,
        history=history_list, channel="voice",
    )
    _precheck = await run_stateful_prechecks(_pctx)
    if _precheck.handled:
        _resp = _handler_result_to_voice(transcript, _precheck.handler_result)
        await _push_and_flush_turn(doctor_id, transcript, _resp.reply)
        return _resp

    # Run the shared 5-layer intent workflow pipeline
    from services.intent_workflow import run as workflow_run
    from services.ai.turn_context import assemble_turn_context
    turn_ctx = await assemble_turn_context(doctor_id)
    if _precheck.knowledge_context:
        turn_ctx.advisory.knowledge_snippet = _precheck.knowledge_context

    # Trim history to match Web channel limits
    _routing_history = history_list[-_ROUTING_HISTORY_MAX_MESSAGES:] if _ROUTING_HISTORY_MAX_MESSAGES > 0 else []

    # Prepend compressed long-term memory to history (same as WeChat path)
    if turn_ctx.advisory.context_message:
        _routing_history = [turn_ctx.advisory.context_message] + _routing_history

    try:
        result = await asyncio.wait_for(
            workflow_run(
                transcript, doctor_id, _routing_history,
                knowledge_context=_precheck.knowledge_context or "",
                channel="voice",
                turn_context=turn_ctx,
            ),
            timeout=_WORKFLOW_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log(f"[VoiceChat] workflow TIMEOUT after {_WORKFLOW_TIMEOUT}s doctor={doctor_id}")
        raise HTTPException(status_code=504, detail="Processing timed out, please try again")
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
            )
            log(f"[VoiceChat] blocked write stored doctor={doctor_id} text={transcript[:60]!r}")
        _gate_reply = result.gate.clarification_message or "没太理解您的意思，能说得更具体一些吗？"
        _gate_resp = VoiceChatResponse(transcript=transcript, reply=_gate_reply)
        await _push_and_flush_turn(doctor_id, transcript, _gate_reply)
        return _gate_resp

    intent_result = result.to_intent_result()

    resp = await _dispatch_voice_intent(
        transcript, doctor_id, intent_result, history_list,
    )

    # Prepend abandon notice if a pending draft was discarded
    if _precheck.abandon_notice:
        resp.reply = f"{_precheck.abandon_notice}\n\n{resp.reply}"

    await _push_and_flush_turn(doctor_id, transcript, resp.reply)
    return resp


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


# ── Consultation endpoint (ADR 0009: transcribe + workflow, no direct save) ─


@router.post("/consultation", response_model=VoiceChatResponse)
async def voice_consultation(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    history: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> VoiceChatResponse:
    """Doctor uploads an ambient consultation recording; transcribed with
    dialogue-aware prompt then routed through the 5-layer intent workflow.

    Previously this endpoint structured and saved directly. Per ADR 0009 it
    now shares the same routing, gating, and draft-first safety as voice_chat.
    The only difference is consultation_mode=True for the transcription step.
    """
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="VOICE_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _voice_chat_for_doctor(
        audio, resolved_doctor_id, history=history,
        consultation_mode=True,
    )
