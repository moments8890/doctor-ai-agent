"""
病历管理路由：提供病历的创建、查询、更新和语音/图片录入 API 端点。
"""

import asyncio
import re
import os
import time
from datetime import datetime
from collections import deque
from fastapi import APIRouter, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

from db.crud import (
    create_patient as db_create_patient,
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    list_tasks,
    save_record,
    update_latest_record_for_patient,
    update_patient_demographics,
    upsert_doctor_context,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from models.medical_record import MedicalRecord
from services.ai.agent import dispatch as agent_dispatch
from services.ai.fast_router import fast_route, fast_route_label
from services.knowledge.doctor_knowledge import (
    load_knowledge_context_for_prompt,
    maybe_auto_learn_knowledge,
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from utils.errors import InvalidMedicalRecordError
from services.ai.intent import Intent
from services.notify.notify_control import (
    parse_notify_command,
    get_notify_pref,
    set_notify_mode,
    set_notify_interval,
    set_notify_cron,
    set_notify_immediate,
    format_notify_pref,
)
from services.ai.structuring import structure_medical_record
from services.notify.tasks import create_appointment_task, run_due_task_cycle
from services.ai.transcription import transcribe_audio
from services.ai.vision import extract_text_from_image
from services.observability.observability import trace_block
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id
from services.observability.turn_log import log_turn
from utils.log import log

router = APIRouter(prefix="/api/records", tags=["records"])


async def _background_auto_learn(doctor_id: str, text: str, fields: dict) -> None:
    """Run knowledge auto-learning in the background after returning the response."""
    try:
        async with AsyncSessionLocal() as db:
            await maybe_auto_learn_knowledge(db, doctor_id, text, structured_fields=fields)
    except Exception as e:
        log(f"[Chat] background auto-learn failed doctor={doctor_id}: {e}")

# Phrases that indicate the LLM accidentally extracted a question/non-name as a patient name
_BAD_NAME_FRAGMENTS = ["叫什么名字", "这位患者", "请问", "患者姓名"]
_NAME_ONLY = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_ASK_NAME_FRAGMENTS = ("叫什么名字", "患者姓名", "请提供姓名", "请告知姓名")
_LEADING_NAME = re.compile(r"^\s*([\u4e00-\u9fff]{2,4})(?:[，,\s]|$)")
_CLINICAL_HINTS = (
    "男", "女", "岁", "胸痛", "胸闷", "心悸", "头痛", "发热", "咳嗽",
    "ST", "PCI", "BNP", "EF", "诊断", "治疗", "复查",
)
_CLINICAL_CONTENT_HINTS = (
    "胸痛", "胸闷", "心悸", "头痛", "发热", "咳嗽", "气短",
    "ST", "PCI", "BNP", "EF", "诊断", "治疗", "复查", "化疗", "靶向",
)
_COMPLETE_RE = re.compile(r'^\s*完成\s*(\d+)\s*$')
_DELETE_BY_ID_RE = re.compile(r'^\s*(?:删除|删掉|移除)\s*(?:患者|病人)?\s*(?:ID|id)\s*(\d+)\s*$')
_DELETE_PATIENT_RE = re.compile(
    r'^\s*(?:删除|删掉|移除)\s*(?:第\s*([一二三四五六七八九十两\d]+)\s*个\s*)?(?:患者|病人)?\s*([\u4e00-\u9fff]{2,20})\s*$'
)
_SCHEDULE_APPOINTMENT_RE = re.compile(
    r'^\s*(?:给|为)?\s*([\u4e00-\u9fff]{2,20}?)(?:安排)?(?:预约|复诊|约诊)\s*(.+?)\s*$'
)
_PATIENT_COUNT_RE = re.compile(
    r"(我(?:现有|现在)?(?:有|管理)?多少(?:位)?(?:病人|患者)|现在有几个(?:病人|患者)|(?:病人|患者)总数)"
)
_CONTEXT_SAVE_RE = re.compile(r'^\s*(?:总结上下文|保存上下文)(?:[:：]\s*(.*))?\s*$')
_CN_ORDINAL = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_UNCLEAR_INTENT_REPLY = (
    "我还不能确定您的操作意图。请直接说明您要执行哪一种：\n"
    "1) 新建患者（例：新患者张三，男，45岁）\n"
    "2) 记录病历（例：张三，胸痛2小时，保存）\n"
    "3) 查询病历（例：查询张三）\n"
    "4) 列出患者（例：所有患者）\n"
    "5) 删除患者（例：删除第二个患者张三）\n"
    "6) 任务操作（例：看待办 / 完成 5）\n"
    "7) 预约随访（例：为张三安排复诊 2026年3月15日14:00）"
)
_ROUTING_HISTORY_MAX_MESSAGES = max(0, int(os.environ.get("ROUTING_HISTORY_MAX_MESSAGES", "2")))
_REQUESTS_PER_MINUTE = max(1, int(os.environ.get("RECORDS_CHAT_RATE_LIMIT_PER_MINUTE", "100")))
_RATE_WINDOWS: dict[str, deque] = {}


def _trim_history_for_routing(history: List[dict]) -> List[dict]:
    if _ROUTING_HISTORY_MAX_MESSAGES <= 0:
        return []
    if len(history) <= _ROUTING_HISTORY_MAX_MESSAGES:
        return history
    return history[-_ROUTING_HISTORY_MAX_MESSAGES:]

def _is_valid_patient_name(name: str) -> bool:
    """Return False if the extracted name is clearly not a real patient name."""
    if not name or not name.strip():
        return False
    if len(name.strip()) > 20:          # real Chinese names are ≤ 4 chars typically
        return False
    return not any(frag in name for frag in _BAD_NAME_FRAGMENTS)


def _assistant_asked_for_name(history: List[dict]) -> bool:
    """True when the most recent assistant message asks for patient name."""
    if not history:
        return False
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = (message.get("content") or "").strip()
        return any(fragment in content for fragment in _ASK_NAME_FRAGMENTS)
    return False


def _name_only_text(text: str) -> Optional[str]:
    """Return Chinese name for a name-only message, else None."""
    candidate = text.strip()
    if not _NAME_ONLY.match(candidate):
        return None
    if not _is_valid_patient_name(candidate):
        return None
    return candidate


def _leading_name_with_clinical_context(text: str) -> Optional[str]:
    """Extract explicit leading name from clinical dictation like '张三，男，52岁，胸闷'."""
    candidate_match = _LEADING_NAME.match(text or "")
    if not candidate_match:
        return None
    candidate = candidate_match.group(1).strip()
    if not _is_valid_patient_name(candidate):
        return None
    remainder = (text or "").strip()[len(candidate):]
    if not any(hint in remainder for hint in _CLINICAL_HINTS):
        return None
    return candidate


def _contains_clinical_content(text: str) -> bool:
    return any(hint in (text or "") for hint in _CLINICAL_CONTENT_HINTS)


_TREATMENT_HINTS = (
    "用药", "开药", "处方", "给予", "服用", "口服", "静滴", "输液",
    "手术", "PCI", "pci", "CTA", "cta", "介入", "化疗", "放疗", "靶向", "治疗", "方案", "plan",
)


def _contains_treatment_signal(text: str) -> bool:
    content = text or ""
    content_lower = content.lower()
    for hint in _TREATMENT_HINTS:
        if hint in content or hint.lower() in content_lower:
            return True
    return False


def _parse_delete_patient_target(text: str) -> tuple[Optional[int], Optional[str], Optional[int]]:
    by_id = _DELETE_BY_ID_RE.match((text or "").strip())
    if by_id:
        return int(by_id.group(1)), None, None

    by_name = _DELETE_PATIENT_RE.match((text or "").strip())
    if not by_name:
        return None, None, None
    ordinal_raw, patient_name = by_name.group(1), by_name.group(2)
    occurrence_index = None
    if ordinal_raw:
        occurrence_index = _CN_ORDINAL.get(ordinal_raw)
        if occurrence_index is None and ordinal_raw.isdigit():
            occurrence_index = int(ordinal_raw)
    return None, patient_name.strip(), occurrence_index


def _parse_schedule_appointment_target(text: str) -> tuple[Optional[str], Optional[str]]:
    m = _SCHEDULE_APPOINTMENT_RE.match((text or "").strip())
    if not m:
        return None, None
    patient_name = m.group(1).strip()
    raw_time = m.group(2).strip()
    return patient_name, _normalize_human_datetime(raw_time)


def _normalize_human_datetime(raw: str) -> Optional[str]:
    candidate = (raw or "").strip()
    if not candidate:
        return None

    # Normalize common Chinese date/time markers.
    normalized = (
        candidate.replace("年", "-")
        .replace("月", "-")
        .replace("日", " ")
        .replace("时", ":")
        .replace("分", "")
        .replace("/", "-")
        .strip()
    )
    normalized = re.sub(r"\s+", " ", normalized)

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=9, minute=0, second=0)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
}

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


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
        if len(value) > 40:
            raise ValueError("history exceeds max length (40)")
        return value


class TextInput(BaseModel):
    text: str


class ChatResponse(BaseModel):
    reply: str
    record: Optional[MedicalRecord] = None


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


async def _handle_notify_control_command(doctor_id: str, text: str) -> Optional[str]:
    parsed = parse_notify_command(text)
    if not parsed:
        return None

    action, payload = parsed
    if action == "show":
        pref = await get_notify_pref(doctor_id)
        return format_notify_pref(pref)

    if action == "set_mode":
        pref = await set_notify_mode(doctor_id, payload["notify_mode"])
        mode_text = "自动" if pref.notify_mode == "auto" else "手动"
        return "✅ 通知模式已更新为：{0}".format(mode_text)

    if action == "set_interval":
        pref = await set_notify_interval(doctor_id, int(payload["interval_minutes"]))
        return "✅ 通知频率已更新：每{0}分钟自动检查".format(pref.interval_minutes)

    if action == "set_cron":
        try:
            pref = await set_notify_cron(doctor_id, str(payload["cron_expr"]))
            return "✅ 通知计划已更新：{0}".format(pref.cron_expr or "")
        except ValueError as e:
            return "⚠️ {0}".format(str(e))

    if action == "set_immediate":
        await set_notify_immediate(doctor_id)
        return "✅ 通知计划已更新为：实时检查"

    if action == "trigger_now":
        result = await run_due_task_cycle(doctor_id=doctor_id, include_manual=True, force=True)
        return (
            "✅ 已触发待办通知：due={0}, eligible={1}, sent={2}, failed={3}"
        ).format(
            result.get("due_count", 0),
            result.get("eligible_count", 0),
            result.get("sent_count", 0),
            result.get("failed_count", 0),
        )

    return None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatInput,
    authorization: Optional[str] = Header(default=None),
):
    """General-purpose agent endpoint: dispatches via LLM and executes business logic.

    doctor_id is derived from the auth token. body.doctor_id is only used when
    RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID=true (test/dev fallback).
    Pass history as prior turns so the agent can resolve pronouns and follow-ups.
    """
    doctor_id = _resolve_doctor_id(body, authorization)
    return await _chat_for_doctor(body, doctor_id)


async def _chat_for_doctor(body: ChatInput, doctor_id: str) -> ChatResponse:
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    history = [{"role": m.role, "content": m.content} for m in body.history]
    history_for_routing = _trim_history_for_routing(history)
    _enforce_rate_limit(doctor_id)
    notify_reply = await _handle_notify_control_command(doctor_id, body.text)
    if notify_reply is not None:
        return ChatResponse(reply=notify_reply)

    asked_name_in_last_turn = _assistant_asked_for_name(history)
    followup_name = _name_only_text(body.text) if asked_name_in_last_turn else None

    complete_match = _COMPLETE_RE.match(body.text)
    if complete_match:
        task_id = int(complete_match.group(1))
        with trace_block("router", "records.chat.complete_task.fastpath", {"doctor_id": doctor_id, "task_id": task_id}):
            async with AsyncSessionLocal() as db:
                task = await update_task_status(db, task_id, doctor_id, "completed")
        if task is None:
            return ChatResponse(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
        return ChatResponse(reply=f"✅ 任务【{task.title}】已标记完成。")

    # Deterministic count query fast path: avoid LLM paraphrase-only replies.
    if _PATIENT_COUNT_RE.search(body.text):
        with trace_block("router", "records.chat.patient_count.fastpath", {"doctor_id": doctor_id}):
            async with AsyncSessionLocal() as db:
                patients = await get_all_patients(db, doctor_id)
        count = len(patients)
        if count == 0:
            return ChatResponse(reply="👥 当前您管理的患者数量：0。")
        return ChatResponse(reply="👥 当前您管理的患者数量：{0}。可发送「所有患者」查看名单。".format(count))

    delete_patient_id, delete_patient_name, delete_occurrence_index = _parse_delete_patient_target(body.text)
    if delete_patient_id is not None or delete_patient_name:
        with trace_block(
            "router",
            "records.chat.delete_patient.fastpath",
            {
                "doctor_id": doctor_id,
                "patient_id": delete_patient_id,
                "patient_name": delete_patient_name,
                "occurrence": delete_occurrence_index,
            },
        ):
            async with AsyncSessionLocal() as db:
                if delete_patient_id is not None:
                    deleted = await delete_patient_for_doctor(db, doctor_id, delete_patient_id)
                    if deleted is None:
                        return ChatResponse(reply=f"⚠️ 未找到患者 ID {delete_patient_id}。")
                    asyncio.create_task(audit(
                        doctor_id, "DELETE", resource_type="patient",
                        resource_id=str(deleted.id), trace_id=get_current_trace_id(),
                    ))
                    return ChatResponse(reply=f"✅ 已删除患者【{deleted.name}】(ID {deleted.id}) 及其相关记录。")

                matches = await find_patients_by_exact_name(db, doctor_id, delete_patient_name or "")
                if not matches:
                    return ChatResponse(reply=f"⚠️ 未找到患者【{delete_patient_name}】。")
                if delete_occurrence_index is None and len(matches) > 1:
                    preview = [f"{i + 1}. {p.name}（ID {p.id}）" for i, p in enumerate(matches[:5])]
                    prompt = "\n".join(preview)
                    return ChatResponse(
                        reply=(
                            f"⚠️ 找到同名患者【{delete_patient_name}】共 {len(matches)} 位，请指定第几个。\n"
                            f"{prompt}\n"
                            f"例如：删除第2个患者{delete_patient_name}"
                        )
                    )
                if delete_occurrence_index is not None:
                    if delete_occurrence_index <= 0 or delete_occurrence_index > len(matches):
                        return ChatResponse(
                            reply=f"⚠️ 序号超出范围。同名患者【{delete_patient_name}】共 {len(matches)} 位。"
                        )
                    target = matches[delete_occurrence_index - 1]
                else:
                    target = matches[0]
                deleted = await delete_patient_for_doctor(db, doctor_id, target.id)
                if deleted is None:
                    return ChatResponse(reply=f"⚠️ 删除失败，未找到患者【{delete_patient_name}】。")
                asyncio.create_task(audit(
                    doctor_id, "DELETE", resource_type="patient",
                    resource_id=str(deleted.id), trace_id=get_current_trace_id(),
                ))
                return ChatResponse(reply=f"✅ 已删除患者【{deleted.name}】(ID {deleted.id}) 及其相关记录。")

    schedule_patient_name, schedule_iso_time = _parse_schedule_appointment_target(body.text)
    if schedule_patient_name and schedule_iso_time:
        try:
            appointment_dt = datetime.fromisoformat(schedule_iso_time)
        except (TypeError, ValueError):
            return ChatResponse(reply="⚠️ 时间格式无法识别，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。")
        patient_id = None
        async with AsyncSessionLocal() as db:
            patient = await find_patient_by_name(db, doctor_id, schedule_patient_name)
            if patient is not None:
                patient_id = patient.id
        with trace_block(
            "router",
            "records.chat.schedule_appointment.fastpath",
            {"doctor_id": doctor_id, "patient_name": schedule_patient_name},
        ):
            task = await create_appointment_task(
                doctor_id=doctor_id,
                patient_name=schedule_patient_name,
                appointment_dt=appointment_dt,
                notes="",
                patient_id=patient_id,
            )
        return ChatResponse(
            reply=(
                f"📅 已为患者【{schedule_patient_name}】安排预约\n"
                f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
                f"任务编号：{task.id}（将在1小时前提醒）"
            )
        )

    context_match = _CONTEXT_SAVE_RE.match(body.text)
    if context_match:
        explicit_summary = (context_match.group(1) or "").strip()
        if explicit_summary:
            summary = explicit_summary
        else:
            recent_user_msgs = [m["content"] for m in history if m.get("role") == "user"][-4:]
            summary = "；".join(msg.strip() for msg in recent_user_msgs if msg and msg.strip())[:200] or "暂无摘要"
        async with AsyncSessionLocal() as db:
            await upsert_doctor_context(db, doctor_id, summary)
        return ChatResponse(reply=f"✅ 已保存医生上下文摘要：{summary}")

    knowledge_payload = parse_add_to_knowledge_command(body.text)
    if knowledge_payload is not None:
        if not knowledge_payload:
            return ChatResponse(reply="⚠️ 请在命令后补充知识内容，例如：add_to_knowledge_base 高危胸痛需先排除ACS。")
        async with AsyncSessionLocal() as db:
            item = await save_knowledge_item(db, doctor_id, knowledge_payload, source="doctor", confidence=1.0)
        if item is None:
            return ChatResponse(reply="⚠️ 知识内容为空，未保存。")
        return ChatResponse(reply=f"✅ 已加入医生知识库（#{item.id}）：{knowledge_payload}")

    # ── Fast router: resolve common intents without LLM (~0ms vs ~6s) ─────────
    _t0 = time.perf_counter()
    _fast = fast_route(body.text)
    if _fast is not None:
        _latency_ms = (time.perf_counter() - _t0) * 1000.0
        log(f"[Chat] fast_route hit: {fast_route_label(body.text)} doctor={doctor_id}")
        intent_result = _fast
        log_turn(body.text, intent_result.intent.value, "fast", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
    else:
        knowledge_context = ""
        try:
            async with AsyncSessionLocal() as db:
                knowledge_context = await load_knowledge_context_for_prompt(db, doctor_id, body.text)
        except Exception as e:
            log(f"[Chat] knowledge context load failed doctor={doctor_id}: {e}")
            knowledge_context = ""

        try:
            with trace_block("router", "records.chat.agent_dispatch", {"doctor_id": doctor_id}):
                dispatch_kwargs = {"history": history_for_routing}
                if knowledge_context:
                    dispatch_kwargs["knowledge_context"] = knowledge_context
                intent_result = await agent_dispatch(body.text, **dispatch_kwargs)
            _latency_ms = (time.perf_counter() - _t0) * 1000.0
            log_turn(body.text, intent_result.intent.value, "llm", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
        except Exception as e:
            msg = str(e)
            status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
            log(
                f"[Chat] agent dispatch FAILED doctor={doctor_id} status={status} "
                f"text={body.text[:80]!r} err={msg}"
            )
            detail = "rate_limit_exceeded" if status == 429 else "Service temporarily unavailable"
            raise HTTPException(status_code=status, detail=detail)

    # Deterministic fallback for the two-turn flow:
    # assistant asks for patient name -> doctor replies with name only.
    # Force add_record regardless of routing-model variance.
    if followup_name:
        intent_result.intent = Intent.add_record
        intent_result.patient_name = followup_name
    elif intent_result.intent == Intent.add_record and not intent_result.patient_name:
        # Deterministic fallback for one-shot notes that start with patient name.
        # Prevents LLM routing variance from dropping patient linkage.
        leading_name = _leading_name_with_clinical_context(body.text)
        if leading_name:
            intent_result.patient_name = leading_name
    else:
        # Deterministic rescue for routing drift:
        # If input is clearly clinical dictation with a leading patient name,
        # force add_record so record persistence remains stable.
        leading_name = _leading_name_with_clinical_context(body.text)
        if (
            leading_name
            and _contains_clinical_content(body.text)
            and intent_result.intent != Intent.add_record
        ):
            intent_result.intent = Intent.add_record
            if not intent_result.patient_name:
                intent_result.patient_name = leading_name

    # ── create_patient ────────────────────────────────────────────────────────
    if intent_result.intent == Intent.create_patient:
        name = intent_result.patient_name
        if not name:
            return ChatResponse(reply="好的，请告诉我患者的姓名。")
        with trace_block("router", "records.chat.create_patient", {"doctor_id": doctor_id, "patient_name": name}):
            try:
                async with AsyncSessionLocal() as db:
                    patient = await db_create_patient(
                        db, doctor_id, name, intent_result.gender, intent_result.age
                    )
            except InvalidMedicalRecordError as e:
                log(f"[Chat] create patient validation FAILED doctor={doctor_id}: {e}")
                return ChatResponse(reply="⚠️ 患者信息不完整或格式不正确，请检查后重试。")
        parts = "、".join(filter(None, [
            intent_result.gender,
            f"{intent_result.age}岁" if intent_result.age else None,
        ]))
        reply = f"✅ 已为患者【{patient.name}】建档" + (f"（{parts}）" if parts else "") + "。"
        log(f"[Chat] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="patient",
            resource_id=str(patient.id),
            trace_id=get_current_trace_id(),
        ))
        return ChatResponse(reply=reply)

    # ── add_medical_record ────────────────────────────────────────────────────
    if intent_result.intent == Intent.add_record:
        if not intent_result.patient_name or not _is_valid_patient_name(intent_result.patient_name):
            return ChatResponse(reply="请问这位患者叫什么名字？")

        treatment_signal_texts = [body.text]
        treatment_signal_texts.extend(
            (m.get("content") or "") for m in history[-8:] if m.get("role") == "user"
        )

        # Build MedicalRecord: prefer single-LLM structured_fields, fallback to dedicated LLM
        if intent_result.structured_fields:
            with trace_block("router", "records.chat.structured_fields_to_record"):
                fields = dict(intent_result.structured_fields)
                if not fields.get("chief_complaint"):
                    fields["chief_complaint"] = "门诊就诊"
                record = MedicalRecord(**{k: fields.get(k) for k in MedicalRecord.model_fields})
        else:
            doctor_ctx = [m["content"] for m in history[-10:] if m["role"] == "user"]
            if not (followup_name and body.text.strip() == followup_name):
                doctor_ctx.append(body.text)
            if not doctor_ctx:
                doctor_ctx.append(body.text)
            try:
                with trace_block("router", "records.chat.structure_medical_record"):
                    record = await structure_medical_record("\n".join(doctor_ctx))
            except Exception as e:
                log(f"[Chat] structuring FAILED doctor={doctor_id} patient={intent_result.patient_name}: {e}")
                return ChatResponse(reply="病历生成失败，请稍后重试。")

        # Guard against sparse-note hallucination: if no treatment evidence appears
        # in doctor input/history, keep treatment_plan empty.
        if record.treatment_plan and not _contains_treatment_signal("\n".join(treatment_signal_texts)):
            record.treatment_plan = None

        patient_id = None
        patient_name = intent_result.patient_name
        patient_created = False
        with trace_block("router", "records.chat.persist_record", {"doctor_id": doctor_id, "patient_name": patient_name}):
            async with AsyncSessionLocal() as db:
                if patient_name:
                    patient = await find_patient_by_name(db, doctor_id, patient_name)
                    if not patient:
                        try:
                            patient = await db_create_patient(
                                db, doctor_id, patient_name,
                                intent_result.gender, intent_result.age,
                            )
                        except InvalidMedicalRecordError as e:
                            log(f"[Chat] auto-create patient validation FAILED doctor={doctor_id}: {e}")
                            return ChatResponse(reply="⚠️ 患者姓名格式无效，请更正后再试。")
                        patient_created = True
                    else:
                        # Apply demographic corrections from the current turn (e.g. gender/age update).
                        updated = False
                        if intent_result.gender and intent_result.gender != patient.gender:
                            patient.gender = intent_result.gender
                            updated = True
                        if intent_result.age:
                            from db.repositories.patients import _year_of_birth
                            new_yob = _year_of_birth(intent_result.age)
                            if new_yob and new_yob != patient.year_of_birth:
                                patient.year_of_birth = new_yob
                                updated = True
                        if updated:
                            log(f"[Chat] updated patient demographics [{patient_name}] doctor={doctor_id}")
                    patient_id = patient.id
                await save_record(db, doctor_id, record, patient_id)

        # Fire knowledge learning in the background — does not block the response
        asyncio.create_task(_background_auto_learn(doctor_id, body.text, record.model_dump(exclude_none=True)))
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="record",
            resource_id=str(patient_id) if patient_id else None,
            trace_id=get_current_trace_id(),
        ))

        reply = intent_result.chat_reply
        if not reply:
            if patient_name:
                reply = "✅ 已为【" + patient_name + "】" + ("新建档并" if patient_created else "") + "保存病历。"
            else:
                reply = "✅ 病历已保存。"
        log(f"[Chat] saved record patient={patient_name} doctor={doctor_id}")
        return ChatResponse(reply=reply, record=record)

    # ── query_records ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.query_records:
        name = intent_result.patient_name
        with trace_block("router", "records.chat.query_records", {"doctor_id": doctor_id, "patient_name": name}):
            async with AsyncSessionLocal() as db:
                if name:
                    patient = await find_patient_by_name(db, doctor_id, name)
                    if not patient:
                        return ChatResponse(reply=f"未找到患者【{name}】。")
                    records = await get_records_for_patient(db, doctor_id, patient.id)
                    if not records:
                        return ChatResponse(reply=f"📂 患者【{name}】暂无历史记录。")
                    lines = [f"📂 患者【{name}】最近 {len(records)} 条记录："]
                    for i, r in enumerate(records, 1):
                        date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                        lines.append(f"{i}. [{date}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
                else:
                    records = await get_all_records_for_doctor(db, doctor_id)
                    if not records:
                        return ChatResponse(reply="📂 暂无任何病历记录。")
                    lines = [f"📂 最近 {len(records)} 条记录："]
                    for r in records:
                        pname = r.patient.name if r.patient else "未关联"
                        date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                        lines.append(f"【{pname}】[{date}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
        asyncio.create_task(audit(
            doctor_id, "READ", resource_type="record",
            resource_id=name,
            trace_id=get_current_trace_id(),
        ))
        return ChatResponse(reply="\n".join(lines))

    # ── list_patients ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.list_patients:
        with trace_block("router", "records.chat.list_patients", {"doctor_id": doctor_id}):
            async with AsyncSessionLocal() as db:
                patients = await get_all_patients(db, doctor_id)
        if not patients:
            return ChatResponse(reply="📂 暂无患者记录。")
        lines = [f"👥 共 {len(patients)} 位患者："]
        for i, p in enumerate(patients, 1):
            age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else None
            info = "、".join(filter(None, [p.gender, age_display]))
            lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
        return ChatResponse(reply="\n".join(lines))

    # ── delete_patient ────────────────────────────────────────────────────────
    if intent_result.intent == Intent.delete_patient:
        name = (intent_result.patient_name or "").strip()
        occurrence_index_raw = intent_result.extra_data.get("occurrence_index")
        occurrence_index = occurrence_index_raw if isinstance(occurrence_index_raw, int) else None
        if not name:
            return ChatResponse(reply="⚠️ 请告诉我要删除的患者姓名，例如：删除患者张三。")
        with trace_block(
            "router",
            "records.chat.delete_patient",
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

    # ── list_tasks ────────────────────────────────────────────────────────────
    if intent_result.intent == Intent.list_tasks:
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

    # ── complete_task ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.complete_task:
        task_id = intent_result.extra_data.get("task_id")
        if not isinstance(task_id, int):
            task_id_match = _COMPLETE_RE.match(body.text)
            task_id = int(task_id_match.group(1)) if task_id_match else None
        if not isinstance(task_id, int):
            return ChatResponse(reply="⚠️ 未能识别任务编号，请发送「完成 5」（5为任务编号）。")
        with trace_block("router", "records.chat.complete_task", {"doctor_id": doctor_id, "task_id": task_id}):
            async with AsyncSessionLocal() as db:
                task = await update_task_status(db, task_id, doctor_id, "completed")
        if task is None:
            return ChatResponse(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
        return ChatResponse(reply=intent_result.chat_reply or f"✅ 任务【{task.title}】已标记完成。")

    # ── schedule_appointment ──────────────────────────────────────────────────
    if intent_result.intent == Intent.schedule_appointment:
        patient_name = intent_result.patient_name
        if not patient_name:
            return ChatResponse(reply="⚠️ 未能识别患者姓名，请重新说明预约信息。")

        raw_time = intent_result.extra_data.get("appointment_time")
        if not raw_time:
            return ChatResponse(reply="⚠️ 未能识别预约时间，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。")

        normalized_time = str(raw_time).replace("Z", "+00:00")
        try:
            appointment_dt = datetime.fromisoformat(normalized_time)
        except (TypeError, ValueError):
            return ChatResponse(reply="⚠️ 时间格式无法识别，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。")

        notes = intent_result.extra_data.get("notes")
        patient_id = None
        async with AsyncSessionLocal() as db:
            patient = await find_patient_by_name(db, doctor_id, patient_name)
            if patient:
                patient_id = patient.id

        with trace_block("router", "records.chat.schedule_appointment", {"doctor_id": doctor_id, "patient_name": patient_name}):
            task = await create_appointment_task(
                doctor_id=doctor_id,
                patient_name=patient_name,
                appointment_dt=appointment_dt,
                notes=notes,
                patient_id=patient_id,
            )

        return ChatResponse(
            reply=(
                f"📅 已为患者【{patient_name}】安排预约\n"
                f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
                f"任务编号：{task.id}（将在1小时前提醒）"
            )
        )

    # ── update_patient (demographic correction) ───────────────────────────────
    if intent_result.intent == Intent.update_patient:
        name = (intent_result.patient_name or "").strip()
        if not name:
            return ChatResponse(reply="⚠️ 请告诉我要更新哪位患者的信息。")
        if not intent_result.gender and not intent_result.age:
            return ChatResponse(reply="⚠️ 请告诉我要更新的内容，例如「修改王明的年龄为50岁」。")
        with trace_block("router", "records.chat.update_patient", {"doctor_id": doctor_id, "patient_name": name}):
            async with AsyncSessionLocal() as db:
                patient = await update_patient_demographics(
                    db, doctor_id, name,
                    gender=intent_result.gender,
                    age=intent_result.age,
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

    # ── update_record (correct previous record in-place) ──────────────────────
    if intent_result.intent == Intent.update_record:
        name = (intent_result.patient_name or "").strip()
        if not name:
            return ChatResponse(reply="⚠️ 请告诉我要更正哪位患者的病历。")

        # Build the corrected fields: prefer LLM-extracted structured_fields from
        # update_medical_record tool call; fallback to re-dispatching to the LLM so the
        # update_medical_record tool can parse the correction phrasing accurately.
        if intent_result.structured_fields:
            corrected = dict(intent_result.structured_fields)
            # Patch patient name from LLM if fast_route missed it
            if not name and intent_result.patient_name:
                name = intent_result.patient_name.strip()
        else:
            try:
                with trace_block("router", "records.chat.update_record.llm_extract", {"doctor_id": doctor_id}):
                    # Omit history: correction texts are self-contained and history
                    # causes the LLM to give a conversational reply instead of a tool call.
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
                updated_rec = await update_latest_record_for_patient(
                    db, doctor_id, patient.id, corrected
                )

        if updated_rec is None:
            return ChatResponse(
                reply=f"⚠️ 患者【{name}】暂无病历记录，请先保存一条再更正。"
            )

        fields_updated = [k for k in corrected if k in (
            "chief_complaint", "history_of_present_illness", "past_medical_history",
            "physical_examination", "auxiliary_examinations",
            "diagnosis", "treatment_plan", "follow_up_plan",
        )]
        log(f"[Chat] updated record for [{name}] fields={fields_updated} doctor={doctor_id}")
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="record",
            resource_id=str(updated_rec.id), trace_id=get_current_trace_id(),
        ))
        reply = intent_result.chat_reply or f"✅ 已更正患者【{name}】的最近一条病历。"
        return ChatResponse(reply=reply)

    # ── unknown / conversational ──────────────────────────────────────────────
    return ChatResponse(reply=_UNCLEAR_INTENT_REPLY)


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
