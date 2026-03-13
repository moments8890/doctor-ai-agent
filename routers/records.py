"""
病历管理路由：提供病历的创建、查询、更新和语音/图片录入 API 端点。
"""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional

from db.crud import (
    get_all_patients,
    get_record_versions,
    upsert_doctor_context,
)
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.session import (
    clear_pending_record_id,
)
from db.crud.pending import get_pending_record, abandon_pending_record
from services.knowledge.doctor_knowledge import (
    load_knowledge_context_for_prompt,
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from services.ai.intent import Intent, IntentResult
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from services.ai.vision import extract_text_from_image
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.knowledge.pdf_extract_llm import extract_text_from_pdf_llm
from services.observability.observability import trace_block
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from utils.log import log

# ── Re-export constants and utilities from domain modules ─────────────────────
from services.domain.chat_constants import (
    COMPLETE_RE as _COMPLETE_RE,
    DELETE_BY_ID_RE as _DELETE_BY_ID_RE,
    DELETE_PATIENT_RE as _DELETE_PATIENT_RE,
    GREETING_RE as _GREETING_RE,
    MENU_NUMBER_RE as _MENU_NUMBER_RE,
    PATIENT_COUNT_RE as _PATIENT_COUNT_RE,
    CONTEXT_SAVE_RE as _CONTEXT_SAVE_RE,
    SCHEDULE_APPOINTMENT_RE as _SCHEDULE_APPOINTMENT_RE,
    VOICE_TRANSCRIPTION_PREFIX_RE as _VOICE_TRANSCRIPTION_PREFIX_RE,
    CN_ORDINAL as _CN_ORDINAL,
    UNCLEAR_INTENT_REPLY as _UNCLEAR_INTENT_REPLY,
    HELP_REPLY as _HELP_REPLY,
    WARM_GREETING_REPLY as _WARM_GREETING_REPLY,
    MENU_PROMPTS as _MENU_PROMPTS,
    parse_delete_patient_target as _parse_delete_patient_target,
    normalize_human_datetime as _normalize_human_datetime,
    TREATMENT_HINTS as _TREATMENT_HINTS,
    REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE,
    CREATE_PREAMBLE_RE as _CREATE_PREAMBLE_RE,
    SUPPORTED_AUDIO_TYPES,
    SUPPORTED_IMAGE_TYPES,
)
from services.domain.chat_handlers import (
    handle_notify_control_command as _handle_notify_control_command,
    fastpath_complete_task as _fastpath_complete_task,
    fastpath_delete_patient_by_id as _fastpath_delete_patient_by_id,
    fastpath_save_context as _fastpath_save_context,
)
from services.domain.adapters.web_adapter import WebAdapter as _WebAdapter
from services.domain.intent_handlers import (
    HandlerResult as _HandlerResult,
    handle_add_record as shared_handle_add_record,
    handle_create_patient as shared_handle_create_patient,
    handle_query_records as shared_handle_query_records,
    handle_list_patients as shared_handle_list_patients,
    handle_delete_patient as shared_handle_delete_patient,
    handle_list_tasks as shared_handle_list_tasks,
    handle_complete_task as shared_handle_complete_task,
    handle_schedule_appointment as shared_handle_schedule_appointment,
    handle_update_patient as shared_handle_update_patient,
    handle_update_record as shared_handle_update_record,
)
from services.domain.name_utils import (
    is_valid_patient_name as _is_valid_patient_name,
    last_assistant_was_unclear_menu as _last_assistant_was_unclear_menu,
)
from services.session import (
    push_and_flush_turn as _push_and_flush_turn,
    set_blocked_write_context as _set_blocked_write_context,
)

# ── Unclear-intent reply builder ──────────────────────────────────────────────

_UNCLEAR_PREVIEW_MAX = 40  # chars shown from the user's own message as fallback

# LLM generic defaults — zero-signal, skip as summary source.
_GENERIC_LLM_REPLIES: frozenset[str] = frozenset({
    "您好！有什么可以帮您？",
    "您好，有什么可以帮您的吗？",
    "您好！请问有什么需要帮助的？",
    "您好！",
    "好的。",
})


def _build_unclear_reply(user_text: str, chat_reply: Optional[str] = None) -> str:
    """Build the fallback reply for unknown intent with a tentative summary.

    Pattern:
        我理解到您可能是在说：{summary}
        没太理解您的意思，能说得更具体一些吗？发送「帮助」可查看完整功能列表。

    Summary source priority:
    1. LLM chat_reply — if short, non-generic, and ends with a sentence break
       (the LLM provides a more natural paraphrase than a raw echo)
    2. First ~40 chars of the user's own message — reliable fallback when the
       LLM produced nothing useful (e.g. Ollama no-tool path)
    3. Plain _UNCLEAR_INTENT_REPLY when neither source is informative
    """
    # ── 1. Try LLM chat_reply ──────────────────────────────────────────────
    if chat_reply:
        llm_summary = chat_reply.strip()
        if llm_summary not in _GENERIC_LLM_REPLIES:
            for punct in ("。", "？", "！"):
                idx = llm_summary.find(punct)
                if 0 < idx < 50:
                    llm_summary = llm_summary[: idx + 1]
                    break
            else:
                llm_summary = ""  # no sentence break within 50 chars → too verbose
            if len(llm_summary) >= 6:
                return f"我理解到您可能是在说：{llm_summary}\n{_UNCLEAR_INTENT_REPLY}"

    # ── 2. Fall back to first ~40 chars of user's own message ─────────────
    preview = " ".join(user_text.strip().split())  # collapse newlines
    if len(preview) < 8:
        return _UNCLEAR_INTENT_REPLY
    if len(preview) > _UNCLEAR_PREVIEW_MAX:
        preview = preview[:_UNCLEAR_PREVIEW_MAX] + "…"
    return f"我理解到您可能是在说：{preview}\n{_UNCLEAR_INTENT_REPLY}"


router = APIRouter(prefix="/api/records", tags=["records"])

_ROUTING_HISTORY_MAX_MESSAGES = max(0, int(os.environ.get("ROUTING_HISTORY_MAX_MESSAGES", "2")))
_WORKFLOW_TIMEOUT = float(os.environ.get("WEB_CHAT_WORKFLOW_TIMEOUT", "30"))
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — matches /extract-file limit


# ── Pydantic models ───────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Must be 'user' or 'assistant'")
    content: str = Field(..., max_length=16000)


class ChatInput(BaseModel):
    text: str = Field(..., max_length=8000)
    history: List[HistoryMessage] = Field(default_factory=list)
    doctor_id: str = ""

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
    text: str = Field(..., max_length=16000)


class ChatResponse(BaseModel):
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None  # ISO-8601 UTC


# ── Infrastructure helpers ────────────────────────────────────────────────────

def _trim_history_for_routing(history: List[dict]) -> List[dict]:
    if _ROUTING_HISTORY_MAX_MESSAGES <= 0:
        return []
    if len(history) <= _ROUTING_HISTORY_MAX_MESSAGES:
        return history
    return history[-_ROUTING_HISTORY_MAX_MESSAGES:]


def _contains_clinical_content(text: str) -> bool:
    from services.domain.compound_normalizer import has_residual_clinical_content
    has_content, _ = has_residual_clinical_content(text or "")
    return has_content



def _contains_treatment_signal(text: str) -> bool:
    content = text or ""
    content_lower = content.lower()
    for hint in _TREATMENT_HINTS:
        if hint in content or hint.lower() in content_lower:
            return True
    return False


def _parse_schedule_appointment_target(text: str) -> tuple[Optional[str], Optional[str]]:
    """Parse schedule appointment command into (patient_name, normalized_time)."""
    m = _SCHEDULE_APPOINTMENT_RE.match((text or "").strip())
    if not m:
        return None, None
    patient_name = m.group(1).strip()
    raw_time = m.group(2).strip()
    return patient_name, _normalize_human_datetime(raw_time)


def _resolve_doctor_id(body: ChatInput, authorization: Optional[str]) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        body.doctor_id,
        authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )


def _enforce_rate_limit(doctor_id: str) -> None:
    enforce_doctor_rate_limit(doctor_id, scope="records.chat")


# ── Adapter and HandlerResult → ChatResponse conversion ──────────────────────

_web_adapter = _WebAdapter()


async def _handler_result_to_chat(hr: _HandlerResult) -> ChatResponse:
    """Convert a shared-layer HandlerResult to web ChatResponse via adapter."""
    d = await _web_adapter.format_reply(hr)
    return ChatResponse(**d)


# ── Dispatch table ────────────────────────────────────────────────────────────

async def _dispatch_intent(
    text: str, original_text: str, doctor_id: str, history: list,
    intent_result: IntentResult,
) -> ChatResponse:
    """Route resolved intent to the shared domain handlers and convert to ChatResponse."""
    from services.domain.intent_handlers import dispatch_intent

    # Channel-specific overrides
    if intent_result.intent == Intent.help:
        return ChatResponse(reply=_HELP_REPLY)

    hr = await dispatch_intent(
        text, doctor_id, history, intent_result, original_text=original_text,
    )

    # Unknown intent: enrich with contextual summary
    if intent_result.intent == Intent.unknown:
        return ChatResponse(reply=_build_unclear_reply(original_text, intent_result.chat_reply))

    return await _handler_result_to_chat(hr)


async def _try_fast_paths(
    text: str, doctor_id: str, history: list,
) -> Optional[ChatResponse]:
    """Check deterministic fast paths before routing. Returns response or None."""
    if _PATIENT_COUNT_RE.search(text):
        with trace_block("router", "records.chat.patient_count.fastpath", {"doctor_id": doctor_id}):
            async with AsyncSessionLocal() as db:
                patients = await get_all_patients(db, doctor_id)
        count = len(patients)
        if count == 0:
            return ChatResponse(reply="👥 当前您管理的患者数量：0。")
        return ChatResponse(reply="👥 当前您管理的患者数量：{0}。可发送「所有患者」查看名单。".format(count))

    resp = await _fastpath_delete_patient_by_id(doctor_id, text, _parse_delete_patient_target)
    if resp is not None:
        return resp

    resp = await _fastpath_save_context(doctor_id, text, history, _CONTEXT_SAVE_RE, upsert_doctor_context)
    if resp is not None:
        return resp

    knowledge_payload = parse_add_to_knowledge_command(text)
    if knowledge_payload is not None:
        if not knowledge_payload:
            return ChatResponse(reply="⚠️ 请在命令后补充知识内容，例如：add_to_knowledge_base 高危胸痛需先排除ACS。")
        async with AsyncSessionLocal() as db:
            item = await save_knowledge_item(db, doctor_id, knowledge_payload, source="doctor", confidence=1.0)
        if item is None:
            return ChatResponse(reply="⚠️ 知识内容为空，未保存。")
        return ChatResponse(reply=f"✅ 已加入医生知识库（#{item.id}）：{knowledge_payload}")

    return None


# ── Main chat orchestrator ────────────────────────────────────────────────────

async def chat_core(
    text: str,
    doctor_id: str,
    history: list,
    *,
    original_text: Optional[str] = None,
    effective_intent: Optional[IntentResult] = None,
) -> ChatResponse:
    """Channel-agnostic intent routing and execution.

    Uses the intent workflow pipeline (classify -> extract -> bind -> plan -> gate)
    to produce a structured WorkflowResult, then dispatches to the appropriate handler.

    Args:
        text: Processed message text (e.g. transcription prefix stripped).
        doctor_id: The resolved doctor identifier.
        history: Conversation history as [{"role": "user"/"assistant", "content": str}].
        original_text: Raw text before processing (defaults to text). Used for
            reminder detection and record correction re-structuring.
        effective_intent: Pre-resolved intent (e.g. from menu shortcuts).

    Returns:
        ChatResponse with reply text, optional record, and optional pending draft
        metadata.  Channel formatters are responsible for serialising this to
        their wire format (JSON for web, plain text for WeChat).
    """
    original_text = original_text or text
    from services.session import (
        hydrate_session_state as _hydrate_session_state,
        get_session_lock as _get_session_lock,
    )

    # Serialize the full turn under the per-doctor session lock — same as
    # WeChat — to prevent concurrent requests from interleaving prechecks,
    # patient attribution, and session mutations.
    async with _get_session_lock(doctor_id):
        await _hydrate_session_state(doctor_id, write_intent=True)
        history_for_routing = _trim_history_for_routing(history)

        fast_resp = await _try_fast_paths(original_text, doctor_id, history)
        if fast_resp is not None:
            await _push_and_flush_turn(doctor_id, original_text, fast_resp.reply)
            return fast_resp

        # ── Shared stateful prechecks (pending record / create / blocked-write / knowledge) ──
        from services.intent_workflow.precheck import PrecheckContext, run_stateful_prechecks

        _pctx = PrecheckContext(
            doctor_id=doctor_id, text=text, original_text=original_text,
            history=history, channel="web",
        )
        _precheck = await run_stateful_prechecks(_pctx)
        if _precheck.handled:
            _resp = await _handler_result_to_chat(_precheck.handler_result)
            await _push_and_flush_turn(doctor_id, original_text, _resp.reply)
            return _resp

        knowledge_context = _precheck.knowledge_context

        # Assemble per-turn context (snapshot session state + advisory)
        from services.ai.turn_context import assemble_turn_context
        turn_ctx = await assemble_turn_context(doctor_id)
        if knowledge_context:
            turn_ctx.advisory.knowledge_snippet = knowledge_context

        # Run the 5-layer intent workflow pipeline
        from services.intent_workflow import run as workflow_run

        # Prepend compressed long-term memory to history (same as WeChat path)
        _routing_history = history_for_routing
        if turn_ctx.advisory.context_message:
            _routing_history = [turn_ctx.advisory.context_message] + _routing_history

        try:
            result = await asyncio.wait_for(
                workflow_run(
                    text, doctor_id, _routing_history,
                    original_text=original_text,
                    effective_intent=effective_intent,
                    knowledge_context=knowledge_context,
                    channel="web",
                    turn_context=turn_ctx,
                ),
                timeout=_WORKFLOW_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log(f"[Chat] workflow TIMEOUT after {_WORKFLOW_TIMEOUT}s doctor={doctor_id} len={len(text)}")
            raise HTTPException(status_code=504, detail="Processing timed out, please try again")
        except Exception as e:
            msg = str(e)
            status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
            log(
                f"[Chat] workflow FAILED doctor={doctor_id} status={status} "
                f"len={len(text)} err={msg}"
            )
            detail = "rate_limit_exceeded" if status == 429 else "Service temporarily unavailable"
            raise HTTPException(status_code=status, detail=detail)

        # Gate check: block unsafe operations before dispatching
        if not result.gate.approved:
            # Store blocked write context when add_record is gated for missing patient
            if (
                result.gate.reason == "no_patient_name"
                and result.decision.intent == Intent.add_record
            ):
                _set_blocked_write_context(
                    doctor_id,
                    intent="add_record",
                    clinical_text=text,
                    original_text=original_text,
                )
                log(
                    f"[Chat] blocked write stored doctor={doctor_id} "
                    f"len={len(text)}"
                )
            _gate_reply = result.gate.clarification_message or _UNCLEAR_INTENT_REPLY
            await _push_and_flush_turn(doctor_id, original_text, _gate_reply)
            return ChatResponse(reply=_gate_reply)

        intent_result = result.to_intent_result()

        resp = await _dispatch_intent(text, original_text, doctor_id, history, intent_result)
        await _push_and_flush_turn(doctor_id, original_text, resp.reply)
        return resp


async def _chat_for_doctor(body: ChatInput, doctor_id: str) -> ChatResponse:
    """Main entry point for web doctor chat — thin wrapper around chat_core."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")

    # Normalize input via adapter (voice prefix strip, history conversion)
    msg = await _web_adapter.parse_inbound(body)
    history = msg.history
    _enforce_rate_limit(doctor_id)

    notify_reply = await _handle_notify_control_command(doctor_id, body.text)
    if notify_reply is not None:
        return ChatResponse(reply=notify_reply)

    body_text = msg.text or body.text  # fallback to original if empty after strip

    if _GREETING_RE.match(body_text.strip()):
        return ChatResponse(reply=_WARM_GREETING_REPLY)

    effective_intent: Optional[IntentResult] = None
    _menu_match = _MENU_NUMBER_RE.match(body.text)
    if _menu_match and _last_assistant_was_unclear_menu(history):
        _digit = _menu_match.group(1)
        if _digit in _MENU_PROMPTS:
            return ChatResponse(reply=_MENU_PROMPTS[_digit])
        if _digit == "4":
            effective_intent = IntentResult(intent=Intent.list_patients)
        elif _digit == "6":
            effective_intent = IntentResult(intent=Intent.list_tasks)

    complete_resp = await _fastpath_complete_task(body.text, doctor_id, _COMPLETE_RE)
    if complete_resp is not None:
        return complete_resp

    return await chat_core(
        body_text, doctor_id, history,
        original_text=body.text,
        effective_intent=effective_intent,
    )


# ── FastAPI endpoints ─────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatInput,
    authorization: Optional[str] = Header(default=None),
):
    """General-purpose agent endpoint: dispatches via LLM and executes business logic."""
    doctor_id = _resolve_doctor_id(body, authorization)
    return await _chat_for_doctor(body, doctor_id)


@router.post("/from-text", response_model=MedicalRecord)
async def create_record_from_text(
    body: TextInput,
    doctor_id: str = "",
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.from_text")
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


@router.post("/from-image")
async def create_record_from_image(
    image: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """OCR an image then import via import_history (ADR 0009)."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.from_image")
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {image.content_type}. Supported: jpeg, png, webp, gif.",
        )
    try:
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
        text = await extract_text_from_image(image_bytes, image.content_type)
    except Exception as e:
        log(f"[Records] from-image OCR failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")

    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="OCR 未能从图片中提取文字")

    reply = await _import_extracted_text(text, resolved_doctor_id, source="image")
    return {"reply": reply, "source": "image", "extracted_text": text}


@router.post("/from-audio")
async def create_record_from_audio(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Transcribe audio then import via import_history (ADR 0009)."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.from_audio")
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )
    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
    except Exception as e:
        log(f"[Records] from-audio transcription failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcript or not transcript.strip():
        raise HTTPException(status_code=422, detail="转录未产生有效文本")

    reply = await _import_extracted_text(transcript, resolved_doctor_id, source="voice")
    return {"reply": reply, "source": "voice", "extracted_text": transcript}


async def _import_extracted_text(text: str, doctor_id: str, *, source: str) -> str:
    """Dispatch extracted text to import_history with source metadata."""
    from services.ai.intent import IntentResult as _IR, Intent as _I
    from services.wechat.wechat_import import handle_import_history

    intent_result = _IR(intent=_I.import_history, extra_data={"source": source})
    try:
        return await handle_import_history(text, doctor_id, intent_result)
    except Exception as e:
        log(f"[Records] import failed source={source} doctor={doctor_id}: {e}")
        raise HTTPException(status_code=500, detail="导入处理失败，请重试")


@router.post("/transcribe")
async def transcribe_audio_only(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Transcribe audio to text without creating a medical record."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.transcribe")
    content_type = (audio.content_type or "").split(";")[0].strip()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        if not content_type.startswith("audio/"):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {content_type}. Upload an audio file.",
            )
    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
        text = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] transcribe failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")


@router.post("/ocr")
async def ocr_image_only(
    image: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from an image without creating a medical record."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.ocr")
    content_type = (image.content_type or "").split(";")[0].strip()
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {content_type}. Upload a JPEG, PNG, or WebP image.",
        )
    try:
        image_bytes = await image.read()
        if len(image_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件过大，请上传 20 MB 以内的文件")
        text = await extract_text_from_image(image_bytes, content_type)
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        log(f"[Records] ocr failed: {e}")
        raise HTTPException(status_code=500, detail="OCR failed")


@router.post("/extract-file")
async def extract_file_for_chat(
    file: UploadFile = File(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from a PDF or image for the chat input."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="records.extract_file")
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


@router.get("/{record_id}/history")
async def record_history(
    record_id: int,
    doctor_id: str = "test_doctor",
    authorization: Optional[str] = Header(default=None),
):
    """Return the correction history (versions) for a record, oldest first."""
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


@router.post("/pending/{pending_id}/confirm")
async def confirm_pending(
    pending_id: str,
    doctor_id: str = "test_doctor",
    authorization: Optional[str] = Header(default=None),
):
    """确认待审草稿，将记录保存至 medical_records。"""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    async with AsyncSessionLocal() as db:
        pending = await get_pending_record(db, pending_id, resolved_doctor_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="草稿不存在或已过期")

    from services.domain.intent_handlers import save_pending_record
    result = await save_pending_record(resolved_doctor_id, pending)
    if result is None:
        raise HTTPException(status_code=500, detail="保存失败，请重试")

    patient_name, record_id = result
    clear_pending_record_id(resolved_doctor_id, expected_id=pending_id)
    return {"ok": True, "record_id": record_id, "patient_name": patient_name}


@router.post("/pending/{pending_id}/abandon")
async def abandon_pending(
    pending_id: str,
    doctor_id: str = "test_doctor",
    authorization: Optional[str] = Header(default=None),
):
    """取消待审草稿，不保存记录。"""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    async with AsyncSessionLocal() as db:
        ok = await abandon_pending_record(db, pending_id, resolved_doctor_id)
    if not ok:
        raise HTTPException(status_code=404, detail="草稿不存在或已过期")
    clear_pending_record_id(resolved_doctor_id, expected_id=pending_id)
    return {"ok": True}
