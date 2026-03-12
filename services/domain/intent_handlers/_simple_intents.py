"""
Simple shared intent handlers — delete_patient, list_patients, list_tasks,
complete_task, schedule_appointment, update_patient, update_record,
cancel_task, postpone_task, schedule_follow_up.

Each handler returns a HandlerResult.  Channel adapters convert this to
their wire format (ChatResponse for Web, plain-text for WeChat).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.crud import (
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_task_by_id,
    list_tasks,
    update_latest_record_for_patient,
    update_patient_demographics,
    update_task_due_at,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from services.ai.intent import IntentResult
from services.notify.tasks import create_appointment_task
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import set_candidate_patient, set_current_patient
from utils.log import log

from services.domain.intent_handlers._types import HandlerResult


# ── delete_patient ──────────────────────────────────────────────────────────

async def handle_delete_patient(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """删除患者：支持按姓名和序号精确删除。"""
    name = (intent_result.patient_name or "").strip()
    occurrence_index_raw = intent_result.extra_data.get("occurrence_index")
    occurrence_index = occurrence_index_raw if isinstance(occurrence_index_raw, int) else None
    if not name:
        return HandlerResult(reply="⚠️ 请告诉我要删除的患者姓名，例如：删除患者张三。")

    with trace_block(
        "router", "records.chat.delete_patient",
        {"doctor_id": doctor_id, "patient_name": name, "occurrence": occurrence_index, "intent": "delete_patient"},
    ):
        async with AsyncSessionLocal() as db:
            matches = await find_patients_by_exact_name(db, doctor_id, name)
            if not matches:
                return HandlerResult(reply=f"⚠️ 未找到患者【{name}】。")
            if occurrence_index is None and len(matches) > 1:
                return HandlerResult(
                    reply=f"⚠️ 找到同名患者【{name}】共 {len(matches)} 位，请发送「删除第2个患者{name}」这类指令。"
                )
            if occurrence_index is not None:
                if occurrence_index <= 0 or occurrence_index > len(matches):
                    return HandlerResult(reply=f"⚠️ 序号超出范围。同名患者【{name}】共 {len(matches)} 位。")
                target = matches[occurrence_index - 1]
            else:
                target = matches[0]
            deleted = await delete_patient_for_doctor(db, doctor_id, target.id)
            if deleted is None:
                return HandlerResult(reply=f"⚠️ 删除失败，未找到患者【{name}】。")
            asyncio.create_task(audit(
                doctor_id, "DELETE", resource_type="patient",
                resource_id=str(deleted.id), trace_id=get_current_trace_id(),
            ))
    return HandlerResult(
        reply=intent_result.chat_reply or f"✅ 已删除患者【{name}】及其相关记录。",
    )


# ── list_patients ───────────────────────────────────────────────────────────

async def handle_list_patients(doctor_id: str) -> HandlerResult:
    """患者列表：展示全部患者基本信息。"""
    with trace_block("router", "records.chat.list_patients", {"doctor_id": doctor_id, "intent": "list_patients"}):
        async with AsyncSessionLocal() as db:
            patients = await get_all_patients(db, doctor_id)
    if not patients:
        return HandlerResult(reply="📂 暂无患者记录。")
    lines = [f"👥 共 {len(patients)} 位患者："]
    for i, p in enumerate(patients, 1):
        age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else None
        info = "、".join(filter(None, [p.gender, age_display]))
        lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
    return HandlerResult(reply="\n".join(lines), patients_list=list(patients))


# ── list_tasks ──────────────────────────────────────────────────────────────

async def handle_list_tasks(
    doctor_id: str, intent_result: Optional[IntentResult] = None,
) -> HandlerResult:
    """待办任务列表：展示全部待办任务。"""
    # Candidate capture from mixed-intent turns containing a patient name.
    if intent_result is not None:
        _extra = intent_result.extra_data or {}
        _cand_name = _extra.get("candidate_name")
        if _cand_name:
            set_candidate_patient(
                doctor_id, _cand_name,
                gender=_extra.get("candidate_gender"),
                age=_extra.get("candidate_age"),
            )
            log(f"[Chat] candidate patient captured from list_tasks: {_cand_name} doctor={doctor_id}")
    with trace_block("router", "records.chat.list_tasks", {"doctor_id": doctor_id, "intent": "list_tasks"}):
        async with AsyncSessionLocal() as db:
            tasks = await list_tasks(db, doctor_id, status="pending")
    if not tasks:
        return HandlerResult(reply="📋 暂无待办任务。")
    lines = [f"📋 待办任务（共 {len(tasks)} 条）：\n"]
    for i, task in enumerate(tasks, 1):
        due = f" | ⏰ {task.due_at.strftime('%Y-%m-%d')}" if task.due_at else ""
        lines.append(f"{i}. [{task.id}] [{task.task_type}] {task.title}{due}")
    lines.append("\n回复「完成 编号」标记任务完成")
    return HandlerResult(reply="\n".join(lines))


# ── complete_task ───────────────────────────────────────────────────────────

async def handle_complete_task(
    doctor_id: str, intent_result: IntentResult, *, text: str = "",
) -> HandlerResult:
    """标记任务完成。"""
    import re
    _COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')
    task_id = intent_result.extra_data.get("task_id")
    if not isinstance(task_id, int):
        task_id_match = _COMPLETE_RE.match(text)
        task_id = int(task_id_match.group(1)) if task_id_match else None
    if not isinstance(task_id, int):
        return HandlerResult(reply="⚠️ 未能识别任务编号，请发送「完成 5」（5为任务编号）。")
    with trace_block("router", "records.chat.complete_task", {"doctor_id": doctor_id, "task_id": task_id, "intent": "complete_task"}):
        async with AsyncSessionLocal() as db:
            task = await update_task_status(db, task_id, doctor_id, "completed")
    if task is None:
        return HandlerResult(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
    return HandlerResult(
        reply=intent_result.chat_reply or f"✅ 任务【{task.title}】已标记完成。",
    )


# ── schedule_appointment ────────────────────────────────────────────────────

async def handle_schedule_appointment(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """预约挂号：创建预约任务。"""
    patient_name = intent_result.patient_name
    if not patient_name:
        return HandlerResult(reply="⚠️ 未能识别患者姓名，请重新说明预约信息。")
    raw_time = intent_result.extra_data.get("appointment_time")
    if not raw_time:
        return HandlerResult(
            reply="⚠️ 未能识别预约时间，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。"
        )
    normalized_time = str(raw_time).replace("Z", "+00:00")
    try:
        appointment_dt = datetime.fromisoformat(normalized_time)
    except (TypeError, ValueError):
        return HandlerResult(
            reply="⚠️ 时间格式无法识别，请使用格式如「2026年3月15日14:00」或「2026-03-15 14:00」。"
        )
    notes = intent_result.extra_data.get("notes")
    patient_id = None
    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, doctor_id, patient_name)
        if patient:
            patient_id = patient.id
            set_current_patient(doctor_id, patient.id, patient.name)
    with trace_block("router", "records.chat.schedule_appointment", {"doctor_id": doctor_id, "patient_name": patient_name, "patient_id": patient_id, "intent": "schedule_appointment"}):
        task = await create_appointment_task(
            doctor_id=doctor_id, patient_name=patient_name,
            appointment_dt=appointment_dt, notes=notes, patient_id=patient_id,
        )
    return HandlerResult(
        reply=(
            f"📅 已为患者【{patient_name}】安排预约\n"
            f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
            f"任务编号：{task.id}（将在1小时前提醒）"
        )
    )


# ── update_patient ──────────────────────────────────────────────────────────

async def handle_update_patient(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """更新患者人口学信息。"""
    name = (intent_result.patient_name or "").strip()
    if not name:
        return HandlerResult(reply="⚠️ 请告诉我要更新哪位患者的信息。")
    if not intent_result.gender and not intent_result.age:
        return HandlerResult(reply="⚠️ 请告诉我要更新的内容，例如「修改王明的年龄为50岁」。")
    with trace_block("router", "records.chat.update_patient", {"doctor_id": doctor_id, "patient_name": name, "intent": "update_patient"}):
        async with AsyncSessionLocal() as db:
            patient = await update_patient_demographics(
                db, doctor_id, name, gender=intent_result.gender, age=intent_result.age,
            )
    if patient is None:
        return HandlerResult(reply=f"⚠️ 未找到患者【{name}】，请先创建。")
    parts = []
    if intent_result.gender:
        parts.append(f"性别→{intent_result.gender}")
    if intent_result.age:
        parts.append(f"年龄→{intent_result.age}岁")
    set_current_patient(doctor_id, patient.id, patient.name)
    log(f"[Chat] updated patient demographics [{name}] {parts} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return HandlerResult(reply=f"✅ 已更新患者【{name}】的信息：{'、'.join(parts)}。")


# ── update_record ───────────────────────────────────────────────────────────

async def handle_update_record(
    doctor_id: str, intent_result: IntentResult, *, text: str = "",
) -> HandlerResult:
    """更正病历：修改最近一条病历记录。"""
    from services.ai.agent import dispatch as agent_dispatch
    from services.session import get_session

    name = (intent_result.patient_name or "").strip()
    # Session fallback for patient name (WeChat path).
    if not name:
        sess = get_session(doctor_id)
        if sess.current_patient_name:
            name = sess.current_patient_name

    if not name:
        return HandlerResult(reply="⚠️ 请告诉我要更正哪位患者的病历。")

    if intent_result.structured_fields:
        corrected = dict(intent_result.structured_fields)
        if not name and intent_result.patient_name:
            name = intent_result.patient_name.strip()
    else:
        try:
            with trace_block("router", "records.chat.update_record.llm_extract", {"doctor_id": doctor_id, "patient_name": name, "intent": "update_record"}):
                llm_result = await agent_dispatch(text)
            if llm_result.structured_fields:
                corrected = dict(llm_result.structured_fields)
                if not name and llm_result.patient_name:
                    name = llm_result.patient_name.strip()
            else:
                corrected = {}
        except Exception as e:
            log(f"[Chat] update_record LLM extraction FAILED doctor={doctor_id}: {e}")
            return HandlerResult(reply="⚠️ 病历更正失败，请稍后重试。")

    with trace_block("router", "records.chat.update_record", {"doctor_id": doctor_id, "patient_name": name, "intent": "update_record"}):
        async with AsyncSessionLocal() as db:
            patient = await find_patient_by_name(db, doctor_id, name)
            if patient is None:
                return HandlerResult(reply=f"⚠️ 未找到患者【{name}】，无法更正病历。")
            set_current_patient(doctor_id, patient.id, patient.name)
            updated_rec = await update_latest_record_for_patient(db, doctor_id, patient.id, corrected)
    if updated_rec is None:
        return HandlerResult(reply=f"⚠️ 患者【{name}】暂无病历记录，请先保存一条再更正。")
    fields_updated = [k for k in corrected if k in ("content", "tags", "record_type")]
    log(f"[Chat] updated record for [{name}] fields={fields_updated} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="record",
        resource_id=str(updated_rec.id), trace_id=get_current_trace_id(),
    ))
    return HandlerResult(
        reply=intent_result.chat_reply or f"✅ 已更正患者【{name}】的最近一条病历。",
    )


# ── cancel_task ─────────────────────────────────────────────────────────────

async def handle_cancel_task(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """取消待办任务。"""
    task_id = intent_result.extra_data.get("task_id")
    if not task_id:
        return HandlerResult(reply="⚠️ 未能识别任务编号，请发送「取消任务 5」（5为任务编号）。")
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, "cancelled")
    if task is None:
        return HandlerResult(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
    return HandlerResult(reply=f"🚫 任务 {task_id}（{task.title}）已取消。")


# ── postpone_task ───────────────────────────────────────────────────────────

async def handle_postpone_task(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """推迟任务到期日。"""
    task_id = intent_result.extra_data.get("task_id")
    delta_days = intent_result.extra_data.get("delta_days", 7)
    if not task_id:
        return HandlerResult(reply="⚠️ 未能识别任务编号，请发送「推迟任务 5 一周」。")
    async with AsyncSessionLocal() as session:
        task = await get_task_by_id(session, task_id, doctor_id)
        if task is None:
            return HandlerResult(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
        now = datetime.now(timezone.utc)
        base = task.due_at if task.due_at and task.due_at > now else now
        new_due = base + timedelta(days=delta_days)
        await update_task_due_at(session, task_id, doctor_id, new_due)
    return HandlerResult(
        reply=(
            f"⏰ 任务 {task_id}（{task.title}）已推迟 {delta_days} 天\n"
            f"新到期时间：{new_due.strftime('%Y-%m-%d')}"
        )
    )


# ── schedule_follow_up ─────────────────────────────────────────────────────

async def handle_schedule_follow_up(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """为患者创建独立随访提醒任务。"""
    from services.notify.tasks import create_follow_up_task, extract_follow_up_days

    patient_name = intent_result.patient_name
    if not patient_name:
        return HandlerResult(reply="⚠️ 未能识别患者姓名，请说明如「给张三设3个月后随访」")

    follow_up_plan = intent_result.extra_data.get("follow_up_plan") or "下次随访"
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, patient_name)
    patient_id = patient.id if patient else None
    days = extract_follow_up_days(follow_up_plan)
    task = await create_follow_up_task(
        doctor_id=doctor_id,
        record_id=0,
        patient_name=patient_name,
        follow_up_plan=follow_up_plan,
        patient_id=patient_id,
    )
    due_str = task.due_at.strftime("%Y-%m-%d") if task.due_at else f"{days}天后"
    return HandlerResult(
        reply=(
            f"✅ 已为【{patient_name}】创建随访提醒\n"
            f"计划：{follow_up_plan}\n"
            f"到期：{due_str}（任务编号 {task.id}）"
        )
    )
