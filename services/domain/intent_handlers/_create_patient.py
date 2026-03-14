"""
Unified create_patient handler — channel-agnostic business logic.

Merges Web (records_intent_handlers.py) and WeChat (wechat_domain.py)
create_patient implementations into a single handler returning HandlerResult.

Web-specific traits kept:
  - Exact name + age-based patient matching
  - Compound record creation when clinical content detected
  - Reminder task creation from message text

WeChat behavior preserved:
  - Works without body_text (no compound record/reminder)
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Optional

from db.crud import (
    create_patient as db_create_patient,
    find_patient_by_name,
    find_patients_by_exact_name,
)
from db.engine import AsyncSessionLocal
from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.domain.chat_constants import REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE
from services.notify.tasks import create_general_task
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import clear_pending_create, set_current_patient
from utils.errors import InvalidMedicalRecordError
from utils.log import log, safe_create_task


async def _create_or_reuse_patient(
    doctor_id: str, name: str, patient: Optional[object], intent_result: IntentResult,
) -> "tuple[str, object]":
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
        log(f"[create_patient] reusing existing patient [{name}] id={patient.id} doctor={doctor_id}")
        return reply, patient

    with trace_block("router", "records.chat.create_patient", {"doctor_id": doctor_id}):
        try:
            async with AsyncSessionLocal() as db:
                patient, _access_code = await db_create_patient(
                    db, doctor_id, name, intent_result.gender, intent_result.age
                )
        except InvalidMedicalRecordError as e:
            log(f"[create_patient] validation FAILED doctor={doctor_id}: {e}")
            return "⚠️ 患者信息不完整或格式不正确，请检查后重试。", None
    parts = "、".join(filter(None, [
        intent_result.gender,
        f"{intent_result.age}岁" if intent_result.age else None,
    ]))
    reply = f"✅ 已为患者【{patient.name}】创建" + (f"（{parts}）" if parts else "") + "。"
    log(f"[create_patient] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
    safe_create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return reply, patient



async def _append_reminder_task(
    doctor_id: str, patient: object, name: str, reminder_match: "re.Match",
    reply: str,
) -> str:
    """附加提醒任务到创建回复中。"""
    import re
    task_title_raw = reminder_match.group(1).strip().rstrip("。！")
    task_title = f"【{name}】{task_title_raw}"
    try:
        task = await create_general_task(doctor_id, task_title, patient_id=patient.id)
        reply += f"\n📋 已创建提醒任务：{task_title}（编号 {task.id}）"
        log(f"[create_patient] compound task created [{task_title}] id={task.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[create_patient] compound task create FAILED doctor={doctor_id}: {e}")
    return reply


async def handle_create_patient(
    doctor_id: str,
    intent_result: IntentResult,
    body_text: Optional[str] = None,
    original_text: Optional[str] = None,
) -> HandlerResult:
    """Unified create_patient handler for both Web and WeChat channels.

    Args:
        doctor_id: Doctor identifier.
        intent_result: Classified intent with patient_name, gender, age.
        body_text: Processed message text (for compound record detection).
            If None, compound record/reminder detection is skipped (WeChat default).
        original_text: Raw message text (for reminder regex matching).
            If None, reminder detection is skipped.
    """
    name = intent_result.patient_name
    if not name:
        # Web/Voice channels pass body_text; set pending state so the next
        # message with a bare name will resume patient creation.
        # WeChat's non-compound path passes body_text=None and uses its own
        # handle_name_lookup / handle_pending_create flow instead.
        if body_text is not None:
            from services.session import set_pending_create
            set_pending_create(doctor_id, "__pending__")
        return HandlerResult(reply="好的，请告诉我患者的姓名。")

    _yob = (datetime.now().year - intent_result.age) if intent_result.age else None
    async with AsyncSessionLocal() as db:
        _candidates = await find_patients_by_exact_name(db, doctor_id, name)

    if _yob is not None:
        yob_match = next((p for p in _candidates if p.year_of_birth == _yob), None)
        patient = yob_match or (_candidates[0] if _candidates else None)
    else:
        patient = _candidates[0] if _candidates else None

    reply, patient = await _create_or_reuse_patient(doctor_id, name, patient, intent_result)
    if patient is None:
        return HandlerResult(reply=reply)

    # Pin resolved patient to session
    _prev = set_current_patient(doctor_id, patient.id, patient.name)
    _switch = f"🔄 已从【{_prev}】切换到【{patient.name}】" if _prev else None

    # Reminder task (Web channel typically provides original_text)
    if original_text:
        _reminder_m = _REMINDER_IN_MSG_RE.search(original_text)
        if _reminder_m:
            reply = await _append_reminder_task(doctor_id, patient, name, _reminder_m, reply)

    return HandlerResult(reply=reply, switch_notification=_switch)


async def handle_pending_create_reply(
    text: str,
    doctor_id: str,
    pending_name: str,
) -> Optional[HandlerResult]:
    """Shared handler for pending-create state with a real patient name.

    Handles the follow-up after a patient name was stored in pending_create
    (non-sentinel path). Extracts gender/age from text.

    Returns:
        HandlerResult — demographics provided; patient created with info.
        None — no demographics detected; patient auto-created with name only,
               pending_create cleared, current_patient set.  Caller should
               fall through to the normal workflow so the text is routed
               through classify → bind → plan → gate.

    Used by the shared precheck layer.
    """
    # Extract gender/age from text
    gender = None
    if re.search(r"男", text):
        gender = "男"
    elif re.search(r"女", text):
        gender = "女"

    age = None
    m = re.search(r"(\d+)\s*岁", text)
    if m:
        age = int(m.group(1))

    # No demographics → auto-create patient, let the text go through the
    # full workflow pipeline (classify → bind → plan → gate) instead of
    # the legacy fast_route bypass.
    if gender is None and age is None:
        async with AsyncSessionLocal() as db:
            patient = await find_patient_by_name(db, doctor_id, pending_name)
            if patient is None:
                patient, _access_code = await db_create_patient(db, doctor_id, pending_name, None, None)
                safe_create_task(audit(
                    doctor_id, "WRITE", resource_type="patient",
                    resource_id=str(patient.id),
                ))
            set_current_patient(doctor_id, patient.id, patient.name)
        clear_pending_create(doctor_id)
        log(f"[pending_create] auto-created patient [{pending_name}] id={patient.id} "
            f"doctor={doctor_id} — falling through to workflow")
        return None

    # Have demographics — create or reuse patient
    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, doctor_id, pending_name)
        if patient is None:
            patient, _access_code = await db_create_patient(db, doctor_id, pending_name, gender, age)
            safe_create_task(audit(
                doctor_id, "WRITE", resource_type="patient",
                resource_id=str(patient.id),
            ))
        set_current_patient(doctor_id, patient.id, patient.name)

    clear_pending_create(doctor_id)
    parts = "、".join(filter(None, [gender, f"{age}岁" if age else None]))
    info = f"（{parts}）" if parts else ""
    return HandlerResult(reply=f"好的，{pending_name}已建档{info}。")
