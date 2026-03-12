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
from datetime import datetime
from typing import Optional

from db.crud import (
    create_patient as db_create_patient,
    find_patients_by_exact_name,
    save_record,
)
from db.engine import AsyncSessionLocal
from services.ai.intent import IntentResult
from services.ai.structuring import structure_medical_record
from services.domain.intent_handlers._types import HandlerResult
from services.domain.chat_constants import REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE
from services.domain.compound_normalizer import has_residual_clinical_content
from services.domain.text_cleanup import strip_leading_create_demographics
from services.notify.tasks import create_general_task
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import set_current_patient
from utils.errors import InvalidMedicalRecordError
from utils.log import log


def _contains_clinical_content(text: str, intent_result: Optional[IntentResult] = None) -> bool:
    """Check if text has meaningful clinical content after stripping demographics."""
    has_content, _ = has_residual_clinical_content(
        text or "", intent_result,
    )
    return has_content


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

    with trace_block("router", "records.chat.create_patient", {"doctor_id": doctor_id, "patient_name": name}):
        try:
            async with AsyncSessionLocal() as db:
                patient = await db_create_patient(
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
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return reply, patient


async def _append_compound_record(
    doctor_id: str, patient: object, body_text: str, name: str, reply: str,
    intent_result: Optional[IntentResult] = None,
) -> str:
    """附加病历录入到创建回复中。"""
    try:
        _clinical_text = strip_leading_create_demographics(body_text, intent_result).strip() or body_text
        with trace_block("router", "records.chat.compound_record", {"doctor_id": doctor_id, "patient_id": patient.id, "patient_name": name}):
            record = await structure_medical_record(_clinical_text)
        async with AsyncSessionLocal() as db:
            saved = await save_record(db, doctor_id, record, patient.id)
        preview = record.content[:50] + ("…" if len(record.content) > 50 else "")
        reply += f"\n✅ 已录入病历：{preview}"
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="record",
            resource_id=str(saved.id), trace_id=get_current_trace_id(),
        ))
        log(f"[create_patient] compound record saved [{name}] record_id={saved.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[create_patient] compound record save FAILED doctor={doctor_id}: {e}")
        reply += "\n⚠️ 病历录入失败，请稍后单独补充。"
    return reply


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

    # Compound record (Web channel typically provides body_text)
    if body_text and _contains_clinical_content(body_text, intent_result):
        reply = await _append_compound_record(doctor_id, patient, body_text, name, reply, intent_result)

    # Reminder task (Web channel typically provides original_text)
    if original_text:
        _reminder_m = _REMINDER_IN_MSG_RE.search(original_text)
        if _reminder_m:
            reply = await _append_reminder_task(doctor_id, patient, name, _reminder_m, reply)

    return HandlerResult(reply=reply, switch_notification=_switch)
