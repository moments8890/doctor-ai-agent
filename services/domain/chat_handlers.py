"""
聊天意图处理器：将各类医生操作意图分发到对应的业务逻辑，
包括创建、录入病历、查询、删除、任务管理和预约等功能。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from db.crud import (
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
    create_patient as db_create_patient,
    update_task_status,
)
from db.crud.pending import create_pending_record
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.structuring import structure_medical_record
from services.domain.name_utils import is_valid_patient_name, patient_name_from_history
from services.domain.patient_ops import resolve_patient
from services.domain.record_ops import assemble_record
from services.notify.tasks import create_appointment_task, create_general_task, run_due_task_cycle
from services.notify.notify_control import (
    parse_notify_command,
    get_notify_pref,
    set_notify_mode,
    set_notify_interval,
    set_notify_cron,
    set_notify_immediate,
    format_notify_pref,
)
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import set_pending_record_id
from utils.errors import InvalidMedicalRecordError
from utils.log import log

_DRAFT_TTL_MINUTES = int(os.environ.get("PENDING_RECORD_TTL_MINUTES", "30"))


# ---------------------------------------------------------------------------
# Shared response model (defined here to avoid circular imports with routers)
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    """Standard chat reply with an optional structured medical record.

    When an add_record intent creates a pending draft, pending_id and
    pending_patient_name are set so the frontend can render a confirm card.
    """
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REMINDER_IN_MSG_RE = re.compile(
    r"(?:下午|明天|早上|晚上|今天|稍后|待会|一会儿?)?[，,\s]*提醒我\s*(.{2,20}?)(?:[。！\s]|$)"
)
_COMPLETE_RE = re.compile(r'^\s*完成\s*(\d+)\s*$')
_CREATE_PREAMBLE_RE = re.compile(
    r"^(?:帮我?|请)?(?:录入|建立|新建|创建)"
    r"(?:.*?(?:新病人|新患者|患者|病人))?"
    r"\s*[，,]?\s*[\u4e00-\u9fff]{2,4}\s*[，,]?"
    r"(?:\s*[男女](?:性)?\s*[，,]?)?"
    r"(?:\s*\d+\s*岁\s*[，,。]?)?\s*",
    re.DOTALL,
)
class _PatientValidationError(Exception):
    pass


def _contains_clinical_content(text: str) -> bool:
    """Check if text has meaningful clinical content via residual-text heuristic."""
    from services.domain.compound_normalizer import has_residual_clinical_content
    has_content, _ = has_residual_clinical_content(text or "")
    return has_content


async def _maybe_create_followup_task(
    doctor_id: str,
    patient_name: str,
    patient_id: Optional[int],
    record_id: int,
    follow_up_plan: str,
) -> None:
    """Create a follow-up task in the background; swallow all errors."""
    try:
        from services.notify.tasks import create_follow_up_task
        await create_follow_up_task(
            doctor_id=doctor_id,
            record_id=record_id,
            patient_name=patient_name,
            follow_up_plan=follow_up_plan,
            patient_id=patient_id,
        )
        log(f"[Chat] auto-created follow-up task for [{patient_name}]: {follow_up_plan}")
    except Exception as e:
        log(f"[Chat] follow-up task creation failed for [{patient_name}]: {e}")


# ---------------------------------------------------------------------------
# Per-intent handler functions
# ---------------------------------------------------------------------------

async def handle_create_patient(
    body_text: str,
    original_text: str,
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理创建意图：创建或复用患者档案，可附带病历和提醒。"""
    name = intent_result.patient_name
    if not name:
        return ChatResponse(reply="好的，请告诉我患者的姓名。")

    _yob = (datetime.now().year - intent_result.age) if intent_result.age else None
    async with AsyncSessionLocal() as db:
        _candidates = await find_patients_by_exact_name(db, doctor_id, name)

    if _yob is not None:
        yob_match = next((p for p in _candidates if p.year_of_birth == _yob), None)
        patient = yob_match or (_candidates[0] if _candidates else None)
    else:
        patient = _candidates[0] if _candidates else None

    reply, patient = await _create_or_reuse_patient(doctor_id, name, patient, intent_result)

    # Compound record creation is now handled by the dispatch layer via
    # planner compound_actions, not inline here (draft-first safety model).

    _reminder_m = _REMINDER_IN_MSG_RE.search(original_text)
    if _reminder_m:
        reply = await _append_reminder_task(doctor_id, patient, name, _reminder_m, reply)

    return ChatResponse(reply=reply)


async def _create_or_reuse_patient(
    doctor_id: str,
    name: str,
    patient: Optional[object],
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> tuple[str, object]:
    """创建或复用已有患者，返回 (reply, patient)。"""
    if patient is not None:
        _age_str = (
            f"{datetime.now().year - patient.year_of_birth}岁"
            if patient.year_of_birth else None
        )
        parts = "、".join(filter(None, [patient.gender, _age_str]))
        reply = (
            f"ℹ️ 患者【{name}】已存在（ID {patient.id}"
            f"{('，' + parts) if parts else ''}），已复用现有档案。"
        )
        log(f"[Chat] reusing existing patient [{name}] id={patient.id} doctor={doctor_id}")
        return reply, patient

    with trace_block("router", "records.chat.create_patient", {"doctor_id": doctor_id, "patient_name": name}):
        try:
            async with AsyncSessionLocal() as db:
                patient = await db_create_patient(
                    db, doctor_id, name, intent_result.gender, intent_result.age
                )
        except InvalidMedicalRecordError as e:
            log(f"[Chat] create patient validation FAILED doctor={doctor_id}: {e}")
            raise _PatientValidationError("⚠️ 患者信息不完整或格式不正确，请检查后重试。") from e

    parts = "、".join(filter(None, [
        intent_result.gender,
        f"{intent_result.age}岁" if intent_result.age else None,
    ]))
    reply = f"✅ 已为患者【{patient.name}】创建" + (f"（{parts}）" if parts else "") + "。"
    log(f"[Chat] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return reply, patient


async def _append_compound_record(
    doctor_id: str,
    patient: object,
    body_text: str,
    name: str,
    reply: str,
) -> str:
    """附加病历录入到创建回复中。"""
    try:
        _clinical_text = _CREATE_PREAMBLE_RE.sub("", body_text).strip() or body_text
        with trace_block("router", "records.chat.compound_record"):
            record = await structure_medical_record(_clinical_text)
        async with AsyncSessionLocal() as db:
            saved = await save_record(db, doctor_id, record, patient.id)
        preview = record.content[:50] + ("…" if len(record.content) > 50 else "")
        reply += f"\n✅ 已录入病历：{preview}"
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="record",
            resource_id=str(saved.id), trace_id=get_current_trace_id(),
        ))
        log(f"[Chat] compound record saved [{name}] record_id={saved.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[Chat] compound record save FAILED doctor={doctor_id}: {e}")
        reply += "\n⚠️ 病历录入失败，请稍后单独补充。"
    return reply


async def _append_reminder_task(
    doctor_id: str,
    patient: object,
    name: str,
    reminder_match: "re.Match",
    reply: str,
) -> str:
    """附加提醒任务到创建回复中。"""
    task_title_raw = reminder_match.group(1).strip().rstrip("。！")
    task_title = f"【{name}】{task_title_raw}"
    try:
        task = await create_general_task(doctor_id, task_title, patient_id=patient.id)
        reply += f"\n📋 已创建提醒任务：{task_title}（编号 {task.id}）"
        log(f"[Chat] compound task created [{task_title}] id={task.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[Chat] compound task create FAILED doctor={doctor_id}: {e}")
    return reply


async def _resolve_add_record_patient(
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
    history: list,
) -> "tuple[Optional[int], Optional[str]] | ChatResponse":
    """患者解析子步骤：补全姓名、调用 resolve_patient，返回 (patient_id, patient_name) 或错误响应。"""
    if not intent_result.patient_name or not is_valid_patient_name(intent_result.patient_name):
        _hist_name = patient_name_from_history(history)
        if _hist_name:
            intent_result.patient_name = _hist_name
            log(f"[Chat] resolved patient from history: {_hist_name} doctor={doctor_id}")
        else:
            return ChatResponse(reply="请问这位患者叫什么名字？")

    patient_id = None
    patient_name = intent_result.patient_name
    async with AsyncSessionLocal() as db:
        if patient_name:
            try:
                patient, patient_created = await resolve_patient(
                    db, doctor_id, patient_name,
                    gender=intent_result.gender, age=intent_result.age,
                )
            except InvalidMedicalRecordError as e:
                log(f"[Chat] auto-create patient validation FAILED doctor={doctor_id}: {e}")
                return ChatResponse(reply="⚠️ 患者姓名格式无效，请更正后再试。")
            patient_id = patient.id
            patient_name = patient.name
            if patient_created:
                asyncio.create_task(audit(
                    doctor_id, "WRITE", resource_type="patient",
                    resource_id=str(patient_id), trace_id=get_current_trace_id(),
                ))
    return patient_id, patient_name


async def _save_emergency_record(
    doctor_id: str,
    record: object,
    patient_id: Optional[int],
    patient_name: Optional[str],
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """紧急病历直接保存并审计，跳过草稿确认流程。"""
    async with AsyncSessionLocal() as db:
        saved = await save_record(db, doctor_id, record, patient_id)
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="record",
        resource_id=str(saved.id), trace_id=get_current_trace_id(),
    ))
    reply = intent_result.chat_reply or (
        f"🚨 已为【{patient_name}】紧急保存病历。" if patient_name else "🚨 病历已紧急保存。"
    )
    log(f"[Chat] emergency record saved patient={patient_name} doctor={doctor_id}")
    return ChatResponse(reply=reply, record=record)


async def _create_pending_draft(
    doctor_id: str,
    record: object,
    patient_id: Optional[int],
    patient_name: Optional[str],
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """将病历保存为待确认草稿，返回草稿预览响应。"""
    draft_id = uuid.uuid4().hex
    draft_data = record.model_dump()
    cvd_raw = (intent_result.extra_data or {}).get("cvd_context")
    if cvd_raw:
        draft_data["cvd_context"] = cvd_raw
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_DRAFT_TTL_MINUTES)

    async with AsyncSessionLocal() as db:
        await create_pending_record(
            db,
            record_id=draft_id,
            doctor_id=doctor_id,
            draft_json=json.dumps(draft_data, ensure_ascii=False),
            patient_id=patient_id,
            patient_name=patient_name,
            ttl_minutes=_DRAFT_TTL_MINUTES,
        )
    set_pending_record_id(doctor_id, draft_id)

    preview = record.content[:80] + ("…" if len(record.content or "") > 80 else "")
    if patient_name:
        reply = f"已为【{patient_name}】生成病历草稿，请确认后保存：\n{preview}"
    else:
        reply = f"已生成病历草稿，请确认后保存：\n{preview}"
    log(f"[Chat] pending draft created patient={patient_name} draft={draft_id} doctor={doctor_id}")
    return ChatResponse(
        reply=reply,
        record=record,
        pending_id=draft_id,
        pending_patient_name=patient_name,
        pending_expires_at=expires_at.isoformat(),
    )


async def handle_add_record(
    body: "ChatInput",  # type: ignore[name-defined]
    doctor_id: str,
    history: list,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理录入病历意图：解析患者、生成结构化病历，保存为待确认草稿。"""
    with trace_block("router", "records.chat.pending_draft", {"doctor_id": doctor_id}):
        patient_result = await _resolve_add_record_patient(doctor_id, intent_result, history)
        if isinstance(patient_result, ChatResponse):
            return patient_result
        patient_id, patient_name = patient_result

        try:
            with trace_block("router", "records.chat.assemble_record"):
                record = await assemble_record(
                    intent_result, body.text, history, doctor_id, patient_id=patient_id
                )
        except Exception as e:
            log(f"[Chat] structuring FAILED doctor={doctor_id} patient={patient_name}: {e}")
            return ChatResponse(reply="病历生成失败，请稍后重试。")

        if getattr(intent_result, "is_emergency", False):
            return await _save_emergency_record(doctor_id, record, patient_id, patient_name, intent_result)

        return await _create_pending_draft(doctor_id, record, patient_id, patient_name, intent_result)


async def handle_query_records(
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理查询病历意图：按患者姓名或全量查询病历记录。"""
    from services.session import get_session

    name = intent_result.patient_name
    if not name:
        _sess = get_session(doctor_id)
        name = getattr(_sess, 'current_patient_name', None)
        if name:
            log(f"[Chat] query_records resolved patient from session: {name} doctor={doctor_id}")

    with trace_block("router", "records.chat.query_records", {"doctor_id": doctor_id, "patient_name": name}):
        async with AsyncSessionLocal() as db:
            lines = await _build_query_lines(db, doctor_id, name)
            if isinstance(lines, str):
                return ChatResponse(reply=lines)

    asyncio.create_task(audit(
        doctor_id, "READ", resource_type="record",
        resource_id=name, trace_id=get_current_trace_id(),
    ))
    return ChatResponse(reply="\n".join(lines))


async def _build_query_lines(db: object, doctor_id: str, name: Optional[str]) -> "list | str":
    """查询并格式化病历列表，返回行列表或错误字符串。"""
    if name:
        patient = await find_patient_by_name(db, doctor_id, name)
        if not patient:
            return f"未找到患者【{name}】。"
        records = await get_records_for_patient(db, doctor_id, patient.id)
        if not records:
            return f"📂 患者【{name}】暂无历史记录。"
        lines = [f"📂 患者【{name}】最近 {len(records)} 条记录："]
        for i, r in enumerate(records, 1):
            date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
            lines.append(f"{i}. [{date}] {(r.content or '—')[:60]}")
    else:
        records = await get_all_records_for_doctor(db, doctor_id)
        if not records:
            return "📂 暂无任何病历记录。"
        lines = [f"📂 最近 {len(records)} 条记录："]
        for r in records:
            pname = r.patient.name if r.patient else "未关联"
            date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
            lines.append(f"【{pname}】[{date}] {(r.content or '—')[:60]}")
    return lines


async def handle_list_patients(doctor_id: str) -> ChatResponse:
    """处理患者列表意图：展示全部患者基本信息。"""
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


async def handle_delete_patient(
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理删除患者意图：支持按姓名和序号精确删除。"""
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
            target = _select_patient_target(matches, occurrence_index, name)
            if isinstance(target, ChatResponse):
                return target
            deleted = await delete_patient_for_doctor(db, doctor_id, target.id)
            if deleted is None:
                return ChatResponse(reply=f"⚠️ 删除失败，未找到患者【{name}】。")
            asyncio.create_task(audit(
                doctor_id, "DELETE", resource_type="patient",
                resource_id=str(deleted.id), trace_id=get_current_trace_id(),
            ))
    return ChatResponse(reply=intent_result.chat_reply or f"✅ 已删除患者【{name}】及其相关记录。")


def _select_patient_target(matches: list, occurrence_index: Optional[int], name: str) -> "object | ChatResponse":
    """Select which patient from a list of same-name matches. Returns target or error ChatResponse."""
    if occurrence_index is not None:
        if occurrence_index <= 0 or occurrence_index > len(matches):
            return ChatResponse(reply=f"⚠️ 序号超出范围。同名患者【{name}】共 {len(matches)} 位。")
        return matches[occurrence_index - 1]
    return matches[0]


async def handle_list_tasks(doctor_id: str) -> ChatResponse:
    """处理待办任务列表意图。"""
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


async def handle_complete_task(
    text: str,
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理标记任务完成意图。"""
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


async def handle_schedule_appointment(
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理预约挂号意图：创建预约任务。"""
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
    patient_id = await _lookup_patient_id(doctor_id, patient_name)

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


async def _lookup_patient_id(doctor_id: str, patient_name: str) -> Optional[int]:
    """Look up patient ID by name; return None if not found."""
    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, doctor_id, patient_name)
        return patient.id if patient else None


async def handle_update_patient(
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理更新患者人口学信息意图。"""
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
        return ChatResponse(reply=f"⚠️ 未找到患者【{name}】，请先创建。")

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


async def handle_update_record(
    body: "ChatInput",  # type: ignore[name-defined]
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> ChatResponse:
    """处理更正病历意图：修改最近一条病历记录。"""
    name = (intent_result.patient_name or "").strip()
    if not name:
        return ChatResponse(reply="⚠️ 请告诉我要更正哪位患者的病历。")

    corrected = await _extract_correction_fields(body, doctor_id, intent_result)
    if corrected is None:
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


async def _extract_correction_fields(
    body: "ChatInput",  # type: ignore[name-defined]
    doctor_id: str,
    intent_result: "IntentResult",  # type: ignore[name-defined]
) -> Optional[dict]:
    """从意图或 LLM 中提取更正字段。返回 None 表示提取失败。"""
    if intent_result.structured_fields:
        return dict(intent_result.structured_fields)

    try:
        from services.ai.agent import dispatch as agent_dispatch
        with trace_block("router", "records.chat.update_record.llm_extract", {"doctor_id": doctor_id}):
            llm_result = await agent_dispatch(body.text)
        if llm_result.structured_fields:
            return dict(llm_result.structured_fields)
        return {}
    except Exception as e:
        log(f"[Chat] update_record LLM extraction FAILED doctor={doctor_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Notify-control command handler (moved from routers/records.py)
# ---------------------------------------------------------------------------

async def handle_notify_control_command(doctor_id: str, text: str) -> Optional[str]:
    """解析并执行通知控制命令，返回回复文本；无匹配返回 None。"""
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
            result.get("due_count", 0), result.get("eligible_count", 0),
            result.get("sent_count", 0), result.get("failed_count", 0),
        )
    return None


# ---------------------------------------------------------------------------
# Fast-path command handlers (moved from routers/records.py)
# ---------------------------------------------------------------------------

async def fastpath_complete_task(
    text: str, doctor_id: str, complete_re: "re.Pattern",
) -> Optional[ChatResponse]:
    """Intercept 完成 N before routing to skip LLM."""
    m = complete_re.match(text)
    if not m:
        return None
    task_id = int(m.group(1))
    with trace_block("router", "records.chat.complete_task.fastpath", {"doctor_id": doctor_id, "task_id": task_id}):
        async with AsyncSessionLocal() as db:
            task = await update_task_status(db, task_id, doctor_id, "completed")
    if task is None:
        return ChatResponse(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
    return ChatResponse(reply=f"✅ 任务【{task.title}】已标记完成。")


async def fastpath_delete_patient_by_id(
    doctor_id: str, text: str, parse_fn: "callable",
) -> Optional[ChatResponse]:
    """快速路径：按 ID 删除患者；不匹配返回 None。"""
    delete_patient_id, _, _ = parse_fn(text)
    if delete_patient_id is None:
        return None
    with trace_block(
        "router", "records.chat.delete_patient_by_id.fastpath",
        {"doctor_id": doctor_id, "patient_id": delete_patient_id},
    ):
        async with AsyncSessionLocal() as db:
            deleted = await delete_patient_for_doctor(db, doctor_id, delete_patient_id)
    if deleted is None:
        return ChatResponse(reply=f"⚠️ 未找到患者 ID {delete_patient_id}。")
    asyncio.create_task(audit(
        doctor_id, "DELETE", resource_type="patient",
        resource_id=str(deleted.id), trace_id=get_current_trace_id(),
    ))
    return ChatResponse(reply=f"✅ 已删除患者【{deleted.name}】(ID {deleted.id}) 及其相关记录。")


async def fastpath_save_context(
    doctor_id: str, text: str, history: list, context_save_re: "re.Pattern",
    upsert_fn: "callable",
) -> Optional[ChatResponse]:
    """快速路径：保存医生上下文摘要；不匹配返回 None。"""
    context_match = context_save_re.match(text)
    if not context_match:
        return None
    explicit_summary = (context_match.group(1) or "").strip()
    if explicit_summary:
        summary = explicit_summary
    else:
        recent_user_msgs = [m["content"] for m in history if m.get("role") == "user"][-4:]
        summary = "；".join(msg.strip() for msg in recent_user_msgs if msg and msg.strip())[:200] or "暂无摘要"
    async with AsyncSessionLocal() as db:
        await upsert_fn(db, doctor_id, summary)
    return ChatResponse(reply=f"✅ 已保存医生上下文摘要：{summary}")
