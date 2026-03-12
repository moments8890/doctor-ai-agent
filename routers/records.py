"""
病历管理路由：提供病历的创建、查询、更新和语音/图片录入 API 端点。
"""

from __future__ import annotations

import os
import time
from collections import deque
from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

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
    CLINICAL_CONTENT_HINTS as _CLINICAL_CONTENT_HINTS,
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
    is_blocked_write_cancel as _is_blocked_write_cancel,
    last_assistant_was_unclear_menu as _last_assistant_was_unclear_menu,
)
from services.intent_workflow.precheck import (
    precheck_blocked_write as _precheck_blocked_write,
    is_blocked_write_cancel_reply as _is_blocked_write_cancel_reply,
)
from services.session import (
    set_blocked_write_context as _set_blocked_write_context,
    clear_blocked_write_context as _clear_blocked_write_context,
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
_REQUESTS_PER_MINUTE = max(1, int(os.environ.get("RECORDS_CHAT_RATE_LIMIT_PER_MINUTE", "100")))
_RATE_WINDOWS: dict[str, deque] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatInput(BaseModel):
    text: str = Field(..., max_length=8000)
    history: List[HistoryMessage] = Field(default_factory=list)
    doctor_id: str = "test_doctor"

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
    text: str


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
    return any(hint in (text or "") for hint in _CLINICAL_CONTENT_HINTS)


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
    now = time.time()
    window_start = now - 60.0
    q = _RATE_WINDOWS.setdefault(doctor_id, deque())
    while q and q[0] < window_start:
        q.popleft()
    if len(q) >= _REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    q.append(now)


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
    intent = intent_result.intent

    if intent == Intent.create_patient:
        hr = await shared_handle_create_patient(
            doctor_id, intent_result, body_text=text, original_text=original_text,
        )
        return await _handler_result_to_chat(hr)

    if intent == Intent.add_record:
        hr = await shared_handle_add_record(
            text, doctor_id, history, intent_result,
        )
        return await _handler_result_to_chat(hr)

    if intent == Intent.query_records:
        hr = await shared_handle_query_records(doctor_id, intent_result)
        return await _handler_result_to_chat(hr)

    if intent == Intent.list_patients:
        hr = await shared_handle_list_patients(doctor_id)
        return await _handler_result_to_chat(hr)

    if intent == Intent.delete_patient:
        hr = await shared_handle_delete_patient(doctor_id, intent_result)
        return await _handler_result_to_chat(hr)

    if intent == Intent.list_tasks:
        hr = await shared_handle_list_tasks(doctor_id, intent_result)
        return await _handler_result_to_chat(hr)

    if intent == Intent.complete_task:
        hr = await shared_handle_complete_task(
            doctor_id, intent_result, text=original_text,
        )
        return await _handler_result_to_chat(hr)

    if intent == Intent.schedule_appointment:
        hr = await shared_handle_schedule_appointment(doctor_id, intent_result)
        return await _handler_result_to_chat(hr)

    if intent == Intent.update_patient:
        hr = await shared_handle_update_patient(doctor_id, intent_result)
        return await _handler_result_to_chat(hr)

    if intent == Intent.update_record:
        hr = await shared_handle_update_record(
            doctor_id, intent_result, text=original_text,
        )
        return await _handler_result_to_chat(hr)

    if intent == Intent.help:
        return ChatResponse(reply=_HELP_REPLY)

    return ChatResponse(reply=_build_unclear_reply(original_text, intent_result.chat_reply))


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
    history_for_routing = _trim_history_for_routing(history)

    fast_resp = await _try_fast_paths(original_text, doctor_id, history)
    if fast_resp is not None:
        return fast_resp

    # ── Blocked-write precheck (ADR 0007) ─────────────────────────────────
    # Check for cancel BEFORE precheck to return a user-facing reply.
    if _is_blocked_write_cancel_reply(doctor_id, text):
        _clear_blocked_write_context(doctor_id)
        return ChatResponse(reply="好的，已取消。")

    continuation = _precheck_blocked_write(doctor_id, text)
    if continuation is not None:
        # Resume blocked write with stored clinical text and resolved name.
        _ir = IntentResult(
            intent=Intent.add_record,
            patient_name=continuation.patient_name,
        )
        hr = await shared_handle_add_record(
            continuation.clinical_text, doctor_id,
            continuation.history_snapshot, _ir,
        )
        return await _handler_result_to_chat(hr)

    # Assemble per-turn context (snapshot session state + advisory)
    from services.ai.turn_context import assemble_turn_context
    turn_ctx = await assemble_turn_context(doctor_id)

    # Load knowledge context for LLM dispatch
    knowledge_context = ""
    try:
        async with AsyncSessionLocal() as db:
            knowledge_context = await load_knowledge_context_for_prompt(db, doctor_id, text)
        turn_ctx.advisory.knowledge_snippet = knowledge_context
    except Exception as e:
        log(f"[Chat] knowledge context load failed doctor={doctor_id}: {e}")

    # Run the 5-layer intent workflow pipeline
    from services.intent_workflow import run as workflow_run

    try:
        result = await workflow_run(
            text, doctor_id, history_for_routing,
            original_text=original_text,
            effective_intent=effective_intent,
            knowledge_context=knowledge_context,
            channel="web",
            turn_context=turn_ctx,
        )
    except Exception as e:
        msg = str(e)
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        log(
            f"[Chat] workflow FAILED doctor={doctor_id} status={status} "
            f"text={text[:80]!r} err={msg}"
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
                history_snapshot=list(history),
            )
            log(
                f"[Chat] blocked write stored doctor={doctor_id} "
                f"text={text[:60]!r}"
            )
        return ChatResponse(reply=result.gate.clarification_message or _UNCLEAR_INTENT_REPLY)

    intent_result = result.to_intent_result()

    return await _dispatch_intent(text, original_text, doctor_id, history, intent_result)


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


@router.post("/from-image")
async def create_record_from_image(
    image: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """OCR an image then import via import_history (ADR 0009)."""
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
    return {"reply": reply, "source": "image", "extracted_text": text}


@router.post("/from-audio")
async def create_record_from_audio(
    audio: UploadFile = File(...),
    doctor_id: str = Form(default="test_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Transcribe audio then import via import_history (ADR 0009)."""
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

    from services.wechat.wechat_domain import save_pending_record
    result = await save_pending_record(resolved_doctor_id, pending)
    if result is None:
        raise HTTPException(status_code=500, detail="保存失败，请重试")

    patient_name, record_id = result
    clear_pending_record_id(resolved_doctor_id)
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
    clear_pending_record_id(resolved_doctor_id)
    return {"ok": True}
