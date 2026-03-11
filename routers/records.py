"""
病历管理路由：提供病历的创建、查询、更新和语音/图片录入 API 端点。
"""

from __future__ import annotations

import asyncio
import json
import re
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import deque
from fastapi import APIRouter, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

from db.crud import (
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_record_versions,
    list_tasks,
    update_latest_record_for_patient,
    update_patient_demographics,
    upsert_doctor_context,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.agent import dispatch as agent_dispatch
from services.ai.fast_router import fast_route, fast_route_label
from services.session import get_session, set_pending_record_id, clear_pending_record_id
from db.crud.pending import get_pending_record, abandon_pending_record
from services.knowledge.doctor_knowledge import (
    load_knowledge_context_for_prompt,
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from services.ai.intent import Intent, IntentResult
from services.ai.structuring import structure_medical_record
from services.notify.tasks import create_appointment_task
from services.ai.transcription import transcribe_audio
from services.ai.vision import extract_text_from_image
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.knowledge.pdf_extract_llm import extract_text_from_pdf_llm
from services.observability.observability import trace_block
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id
from services.observability.turn_log import log_turn
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
from routers.records_intent_handlers import (
    handle_create_patient as _handle_create_patient,
    handle_add_record as _handle_add_record,
    handle_query_records as _handle_query_records,
    handle_list_patients as _handle_list_patients,
    background_auto_learn as _background_auto_learn,
)
from services.domain.name_utils import (
    is_valid_patient_name as _is_valid_patient_name,
    assistant_asked_for_name as _assistant_asked_for_name,
    last_assistant_was_unclear_menu as _last_assistant_was_unclear_menu,
    name_only_text as _name_only_text,
    leading_name_with_clinical_context as _leading_name_with_clinical_context,
    patient_name_from_history as _patient_name_from_history,
)

# ── Unclear-intent reply builder ──────────────────────────────────────────────

# LLM generic defaults — treated as zero-signal and skipped in the summary.
_GENERIC_LLM_REPLIES: frozenset[str] = frozenset({
    "您好！有什么可以帮您？",
    "您好，有什么可以帮您的吗？",
    "您好！请问有什么需要帮助的？",
    "您好！",
    "好的。",
})


def _build_unclear_reply(chat_reply: Optional[str]) -> str:
    """Build the fallback reply for unknown intent.

    When the LLM produced a short, non-generic response, prepend a tentative
    one-sentence summary so the doctor can quickly spot and correct any
    misunderstanding.  Pattern:

        我理解到您可能是在说：{summary}
        没太理解您的意思，能说得更具体一些吗？发送「帮助」可查看完整功能列表。

    Rules (per product spec):
    - 1 sentence max (truncated at first 。？！ within 50 chars)
    - only reflect explicit LLM interpretation — no patient-binding inference
    - skip summary if reply is generic, empty, or too verbose (> 50 chars)
    - always end with the standard clarification request
    """
    if not chat_reply:
        return _UNCLEAR_INTENT_REPLY
    summary = chat_reply.strip()
    if summary in _GENERIC_LLM_REPLIES:
        return _UNCLEAR_INTENT_REPLY
    # Extract first sentence
    for punct in ("。", "？", "！"):
        idx = summary.find(punct)
        if 0 < idx < 50:
            summary = summary[: idx + 1]
            break
    else:
        if len(summary) > 50:
            return _UNCLEAR_INTENT_REPLY
    # Skip summaries too short to be informative (e.g. "好的", "嗯")
    if len(summary) < 6:
        return _UNCLEAR_INTENT_REPLY
    return f"我理解到您可能是在说：{summary}\n{_UNCLEAR_INTENT_REPLY}"


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


async def _background_auto_learn(doctor_id: str, text: str, fields: dict) -> None:
    """Run knowledge auto-learning in the background after returning the response."""
    try:
        async with AsyncSessionLocal() as db:
            await maybe_auto_learn_knowledge(db, doctor_id, text, structured_fields=fields)
    except Exception as e:
        log(f"[Chat] background auto-learn failed doctor={doctor_id}: {e}")


# ── Remaining intent handlers ─────────────────────────────────────────────────


async def _handle_delete_patient(doctor_id: str, intent_result: IntentResult) -> ChatResponse:
    """删除患者：支持按姓名和序号精确删除。"""
    name = (intent_result.patient_name or "").strip()
    occurrence_index_raw = intent_result.extra_data.get("occurrence_index")
    occurrence_index = occurrence_index_raw if isinstance(occurrence_index_raw, int) else None
    if not name:
        return ChatResponse(reply="⚠️ 请告诉我要删除的患者姓名，例如：删除患者张三。")

    with trace_block(
        "router", "records.chat.delete_patient",
        {"doctor_id": doctor_id, "patient_name": name, "occurrence": occurrence_index},
    ):
        async with AsyncSessionLocal() as db:
            matches = await find_patients_by_exact_name(db, doctor_id, name)
            if not matches:
                return ChatResponse(reply=f"⚠️ 未找到患者【{name}】。")
            if occurrence_index is None and len(matches) > 1:
                return ChatResponse(
                    reply=f"⚠️ 找到同名患者【{name}】共 {len(matches)} 位，请发送「删除第2个患者{name}」这类指令。"
                )
            if occurrence_index is not None:
                if occurrence_index <= 0 or occurrence_index > len(matches):
                    return ChatResponse(reply=f"⚠️ 序号超出范围。同名患者【{name}】共 {len(matches)} 位。")
                target = matches[occurrence_index - 1]
            else:
                target = matches[0]
            deleted = await delete_patient_for_doctor(db, doctor_id, target.id)
            if deleted is None:
                return ChatResponse(reply=f"⚠️ 删除失败，未找到患者【{name}】。")
            asyncio.create_task(audit(
                doctor_id, "DELETE", resource_type="patient",
                resource_id=str(deleted.id), trace_id=get_current_trace_id(),
            ))
    return ChatResponse(reply=intent_result.chat_reply or f"✅ 已删除患者【{name}】及其相关记录。")


async def _handle_list_tasks(doctor_id: str) -> ChatResponse:
    """待办任务列表：展示全部待办任务。"""
    with trace_block("router", "records.chat.list_tasks", {"doctor_id": doctor_id}):
        async with AsyncSessionLocal() as db:
            tasks = await list_tasks(db, doctor_id, status="pending")
    if not tasks:
        return ChatResponse(reply="📋 暂无待办任务。")
    lines = [f"📋 待办任务（共 {len(tasks)} 条）：\n"]
    for i, task in enumerate(tasks, 1):
        due = f" | ⏰ {task.due_at.strftime('%Y-%m-%d')}" if task.due_at else ""
        lines.append(f"{i}. [{task.id}] [{task.task_type}] {task.title}{due}")
    lines.append("\n回复「完成 编号」标记任务完成")
    return ChatResponse(reply="\n".join(lines))


async def _handle_complete_task(
    text: str, doctor_id: str, intent_result: IntentResult,
) -> ChatResponse:
    """标记任务完成。"""
    task_id = intent_result.extra_data.get("task_id")
    if not isinstance(task_id, int):
        task_id_match = _COMPLETE_RE.match(text)
        task_id = int(task_id_match.group(1)) if task_id_match else None
    if not isinstance(task_id, int):
        return ChatResponse(reply="⚠️ 未能识别任务编号，请发送「完成 5」（5为任务编号）。")
    with trace_block("router", "records.chat.complete_task", {"doctor_id": doctor_id, "task_id": task_id}):
        async with AsyncSessionLocal() as db:
            task = await update_task_status(db, task_id, doctor_id, "completed")
    if task is None:
        return ChatResponse(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
    return ChatResponse(reply=intent_result.chat_reply or f"✅ 任务【{task.title}】已标记完成。")


async def _handle_schedule_appointment(doctor_id: str, intent_result: IntentResult) -> ChatResponse:
    """预约挂号：创建预约任务。"""
    patient_name = intent_result.patient_name
    if not patient_name:
        return ChatResponse(reply="⚠️ 未能识别患者姓名，请重新说明预约信息。")
    raw_time = intent_result.extra_data.get("appointment_time")
    if not raw_time:
        return ChatResponse(
            reply="⚠️ 未能识别预约时间，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。"
        )
    normalized_time = str(raw_time).replace("Z", "+00:00")
    try:
        appointment_dt = datetime.fromisoformat(normalized_time)
    except (TypeError, ValueError):
        return ChatResponse(
            reply="⚠️ 时间格式无法识别，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。"
        )
    notes = intent_result.extra_data.get("notes")
    patient_id = None
    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, doctor_id, patient_name)
        if patient:
            patient_id = patient.id
    with trace_block("router", "records.chat.schedule_appointment", {"doctor_id": doctor_id, "patient_name": patient_name}):
        task = await create_appointment_task(
            doctor_id=doctor_id, patient_name=patient_name,
            appointment_dt=appointment_dt, notes=notes, patient_id=patient_id,
        )
    return ChatResponse(
        reply=(
            f"📅 已为患者【{patient_name}】安排预约\n"
            f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
            f"任务编号：{task.id}（将在1小时前提醒）"
        )
    )


async def _handle_update_patient(doctor_id: str, intent_result: IntentResult) -> ChatResponse:
    """更新患者人口学信息。"""
    name = (intent_result.patient_name or "").strip()
    if not name:
        return ChatResponse(reply="⚠️ 请告诉我要更新哪位患者的信息。")
    if not intent_result.gender and not intent_result.age:
        return ChatResponse(reply="⚠️ 请告诉我要更新的内容，例如「修改王明的年龄为50岁」。")
    with trace_block("router", "records.chat.update_patient", {"doctor_id": doctor_id, "patient_name": name}):
        async with AsyncSessionLocal() as db:
            patient = await update_patient_demographics(
                db, doctor_id, name, gender=intent_result.gender, age=intent_result.age,
            )
    if patient is None:
        return ChatResponse(reply=f"⚠️ 未找到患者【{name}】，请先建档。")
    parts = []
    if intent_result.gender:
        parts.append(f"性别→{intent_result.gender}")
    if intent_result.age:
        parts.append(f"年龄→{intent_result.age}岁")
    log(f"[Chat] updated patient demographics [{name}] {parts} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return ChatResponse(reply=f"✅ 已更新患者【{name}】的信息：{'、'.join(parts)}。")


async def _handle_update_record(body: ChatInput, doctor_id: str, intent_result: IntentResult) -> ChatResponse:
    """更正病历：修改最近一条病历记录。"""
    name = (intent_result.patient_name or "").strip()
    if not name:
        return ChatResponse(reply="⚠️ 请告诉我要更正哪位患者的病历。")
    if intent_result.structured_fields:
        corrected = dict(intent_result.structured_fields)
        if not name and intent_result.patient_name:
            name = intent_result.patient_name.strip()
    else:
        try:
            with trace_block("router", "records.chat.update_record.llm_extract", {"doctor_id": doctor_id}):
                llm_result = await agent_dispatch(body.text)
            if llm_result.structured_fields:
                corrected = dict(llm_result.structured_fields)
                if not name and llm_result.patient_name:
                    name = llm_result.patient_name.strip()
            else:
                corrected = {}
        except Exception as e:
            log(f"[Chat] update_record LLM extraction FAILED doctor={doctor_id}: {e}")
            return ChatResponse(reply="⚠️ 病历更正失败，请稍后重试。")

    with trace_block("router", "records.chat.update_record", {"doctor_id": doctor_id, "patient_name": name}):
        async with AsyncSessionLocal() as db:
            patient = await find_patient_by_name(db, doctor_id, name)
            if patient is None:
                return ChatResponse(reply=f"⚠️ 未找到患者【{name}】，无法更正病历。")
            updated_rec = await update_latest_record_for_patient(db, doctor_id, patient.id, corrected)
    if updated_rec is None:
        return ChatResponse(reply=f"⚠️ 患者【{name}】暂无病历记录，请先保存一条再更正。")
    fields_updated = [k for k in corrected if k in ("content", "tags", "record_type")]
    log(f"[Chat] updated record for [{name}] fields={fields_updated} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="record",
        resource_id=str(updated_rec.id), trace_id=get_current_trace_id(),
    ))
    return ChatResponse(reply=intent_result.chat_reply or f"✅ 已更正患者【{name}】的最近一条病历。")


# ── Routing: resolve IntentResult from fast_route or LLM ─────────────────────

def _apply_name_fallbacks(
    body_text: str, history: list, followup_name: Optional[str], intent_result: IntentResult,
) -> IntentResult:
    """Apply deterministic patient-name fallback rules after routing."""
    if followup_name:
        intent_result.intent = Intent.add_record
        intent_result.patient_name = followup_name
    elif intent_result.intent == Intent.add_record and not intent_result.patient_name:
        leading_name = _leading_name_with_clinical_context(body_text)
        if leading_name:
            intent_result.patient_name = leading_name
        else:
            intent_result.patient_name = _patient_name_from_history(history)
    else:
        leading_name = _leading_name_with_clinical_context(body_text)
        if (
            leading_name
            and _contains_clinical_content(body_text)
            and intent_result.intent != Intent.add_record
        ):
            intent_result.intent = Intent.add_record
            if not intent_result.patient_name:
                intent_result.patient_name = leading_name
    return intent_result


async def _dispatch_via_llm(
    body: ChatInput, body_text: str, doctor_id: str, history_for_routing: list, t0: float,
) -> IntentResult:
    """调用 LLM 调度器解析意图。"""
    knowledge_context = ""
    try:
        async with AsyncSessionLocal() as db:
            knowledge_context = await load_knowledge_context_for_prompt(db, doctor_id, body_text)
    except Exception as e:
        log(f"[Chat] knowledge context load failed doctor={doctor_id}: {e}")

    try:
        with trace_block("router", "records.chat.agent_dispatch", {"doctor_id": doctor_id}):
            dispatch_kwargs: dict = {"history": history_for_routing}
            if knowledge_context:
                dispatch_kwargs["knowledge_context"] = knowledge_context
            intent_result = await agent_dispatch(body_text, **dispatch_kwargs)
        _latency_ms = (time.perf_counter() - t0) * 1000.0
        log_turn(body.text, intent_result.intent.value, "llm", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
        return intent_result
    except Exception as e:
        msg = str(e)
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        log(
            f"[Chat] agent dispatch FAILED doctor={doctor_id} status={status} "
            f"text={body_text[:80]!r} err={msg}"
        )
        detail = "rate_limit_exceeded" if status == 429 else "Service temporarily unavailable"
        raise HTTPException(status_code=status, detail=detail)


async def _resolve_intent(
    body: ChatInput, body_text: str, doctor_id: str,
    history_for_routing: list, followup_name: Optional[str],
    effective_intent: Optional[IntentResult],
) -> IntentResult:
    """确定意图：先尝试快速路由，再尝试 LLM 调度。"""
    if effective_intent is not None:
        log(f"[Chat] menu_shortcut intent={effective_intent.intent.value} doctor={doctor_id}")
        return effective_intent

    _t0 = time.perf_counter()
    _fast = fast_route(body_text, session=get_session(doctor_id))
    if _fast is not None:
        _latency_ms = (time.perf_counter() - _t0) * 1000.0
        log(f"[Chat] fast_route hit: {fast_route_label(body_text)} doctor={doctor_id}")
        log_turn(body.text, _fast.intent.value, "fast", doctor_id, _latency_ms, patient_name=_fast.patient_name)
        intent_result = _fast
    else:
        intent_result = await _dispatch_via_llm(body, body_text, doctor_id, history_for_routing, _t0)

    return _apply_name_fallbacks(body_text, history_for_routing, followup_name, intent_result)


# ── Dispatch table ────────────────────────────────────────────────────────────

async def _dispatch_intent(
    body: ChatInput, body_text: str, doctor_id: str, history: list,
    intent_result: IntentResult, followup_name: Optional[str],
) -> ChatResponse:
    """Route resolved intent to the appropriate handler."""
    intent = intent_result.intent
    if intent == Intent.create_patient:
        return await _handle_create_patient(body_text, body.text, doctor_id, intent_result)
    if intent == Intent.add_record:
        return await _handle_add_record(body, doctor_id, history, intent_result, followup_name)
    if intent == Intent.query_records:
        return await _handle_query_records(doctor_id, intent_result)
    if intent == Intent.list_patients:
        return await _handle_list_patients(doctor_id)
    if intent == Intent.delete_patient:
        return await _handle_delete_patient(doctor_id, intent_result)
    if intent == Intent.list_tasks:
        return await _handle_list_tasks(doctor_id)
    if intent == Intent.complete_task:
        return await _handle_complete_task(body.text, doctor_id, intent_result)
    if intent == Intent.schedule_appointment:
        return await _handle_schedule_appointment(doctor_id, intent_result)
    if intent == Intent.update_patient:
        return await _handle_update_patient(doctor_id, intent_result)
    if intent == Intent.update_record:
        return await _handle_update_record(body, doctor_id, intent_result)
    if intent == Intent.help:
        return ChatResponse(reply=_HELP_REPLY)
    return ChatResponse(reply=_build_unclear_reply(intent_result.chat_reply))


async def _try_fast_paths(
    body: ChatInput, body_text: str, doctor_id: str, history: list,
) -> Optional[ChatResponse]:
    """Check deterministic fast paths before routing. Returns response or None."""
    if _PATIENT_COUNT_RE.search(body.text):
        with trace_block("router", "records.chat.patient_count.fastpath", {"doctor_id": doctor_id}):
            async with AsyncSessionLocal() as db:
                patients = await get_all_patients(db, doctor_id)
        count = len(patients)
        if count == 0:
            return ChatResponse(reply="👥 当前您管理的患者数量：0。")
        return ChatResponse(reply="👥 当前您管理的患者数量：{0}。可发送「所有患者」查看名单。".format(count))

    resp = await _fastpath_delete_patient_by_id(doctor_id, body.text, _parse_delete_patient_target)
    if resp is not None:
        return resp

    resp = await _fastpath_save_context(doctor_id, body.text, history, _CONTEXT_SAVE_RE, upsert_doctor_context)
    if resp is not None:
        return resp

    knowledge_payload = parse_add_to_knowledge_command(body.text)
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

async def _chat_for_doctor(body: ChatInput, doctor_id: str) -> ChatResponse:
    """Main entry point for doctor chat — orchestrates routing and intent dispatch."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")

    history = [{"role": m.role, "content": m.content} for m in body.history]
    history_for_routing = _trim_history_for_routing(history)
    _enforce_rate_limit(doctor_id)

    notify_reply = await _handle_notify_control_command(doctor_id, body.text)
    if notify_reply is not None:
        return ChatResponse(reply=notify_reply)

    body_text = _VOICE_TRANSCRIPTION_PREFIX_RE.sub("", body.text).strip() or body.text

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

    asked_name_in_last_turn = _assistant_asked_for_name(history)
    followup_name = _name_only_text(body.text) if asked_name_in_last_turn else None

    complete_resp = await _fastpath_complete_task(body.text, doctor_id, _COMPLETE_RE)
    if complete_resp is not None:
        return complete_resp

    fast_resp = await _try_fast_paths(body, body_text, doctor_id, history)
    if fast_resp is not None:
        return fast_resp

    intent_result = await _resolve_intent(
        body, body_text, doctor_id, history_for_routing, followup_name, effective_intent,
    )
    return await _dispatch_intent(body, body_text, doctor_id, history, intent_result, followup_name)


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


@router.post("/from-image", response_model=MedicalRecord)
async def create_record_from_image(image: UploadFile = File(...)):
    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {image.content_type}. Supported: jpeg, png, webp, gif.",
        )
    try:
        image_bytes = await image.read()
        text = await extract_text_from_image(image_bytes, image.content_type)
        return await structure_medical_record(text)
    except ValueError as e:
        log(f"[Records] from-image validation failed: {e}")
        raise HTTPException(status_code=422, detail="Invalid medical record content")
    except Exception as e:
        log(f"[Records] from-image failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/from-audio", response_model=MedicalRecord)
async def create_record_from_audio(audio: UploadFile = File(...)):
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
        return await structure_medical_record(transcript)
    except ValueError as e:
        log(f"[Records] from-audio validation failed: {e}")
        raise HTTPException(status_code=422, detail="Invalid medical record content")
    except Exception as e:
        log(f"[Records] from-audio failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


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
