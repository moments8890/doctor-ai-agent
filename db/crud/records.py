"""
病历保存与查询、神经病例存储及自动随访任务创建的数据库操作。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import (
    Patient,
    MedicalRecordDB,
    NeuroCaseDB,
    DoctorTask,
)
from db.repositories import RecordRepository
from models.medical_record import MedicalRecord
from services.patient.patient_categorization import recompute_patient_category
from services.patient.patient_risk import recompute_patient_risk
from services.observability.observability import trace_block
from db.crud.doctor import _ensure_doctor_exists


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_flag_true(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


_CN_DIGITS = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_or_int(raw: str) -> Optional[int]:
    n = _CN_DIGITS.get(raw)
    if n is not None:
        return n
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _extract_follow_up_days(follow_up_plan: str) -> int:
    if not follow_up_plan:
        return 7

    if "明天" in follow_up_plan:
        return 1
    if "下周" in follow_up_plan or "下星期" in follow_up_plan:
        return 7

    m = re.search(r'([一两二三四五六七八九十\d]+)周', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 7

    m = re.search(r'([一两二三四五六七八九十\d]+)个月', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 30

    m = re.search(r'([一两二三四五六七八九十\d]+)天', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n

    return 7


async def _patient_name(session: AsyncSession, patient_id: int) -> str:
    result = await session.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    return patient.name if patient is not None else "患者"


async def _ensure_auto_follow_up_task(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    record_id: int,
    patient_name: str,
    follow_up_plan: str,
    risk_level: Optional[str] = None,
) -> None:
    existing = await session.execute(
        select(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.record_id == record_id,
            DoctorTask.task_type == "follow_up",
            DoctorTask.trigger_source == "risk_engine",
            DoctorTask.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    days = _extract_follow_up_days(follow_up_plan)
    due_at = _utcnow().replace(microsecond=0) + timedelta(days=days)

    reason = "auto follow-up from record follow_up_plan"
    if risk_level:
        reason = f"{reason}; risk_level={risk_level}"

    session.add(
        DoctorTask(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_id=record_id,
            task_type="follow_up",
            title=f"随访提醒：{patient_name}",
            content=follow_up_plan,
            status="pending",
            due_at=due_at,
            trigger_source="risk_engine",
            trigger_reason=reason,
        )
    )
    await session.commit()


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
) -> MedicalRecordDB:
    with trace_block("db", "crud.save_record", {"doctor_id": doctor_id, "patient_id": patient_id}):
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        repo = RecordRepository(session)
        db_record = await repo.create(
            doctor_id=doctor_id,
            record=record,
            patient_id=patient_id,
        )
        if patient_id is not None:
            await recompute_patient_category(patient_id, session)
            risk = await recompute_patient_risk(patient_id, session)
            if _env_flag_true("AUTO_FOLLOWUP_TASKS_ENABLED") and record.follow_up_plan:
                await _ensure_auto_follow_up_task(
                    session=session,
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    record_id=db_record.id,
                    patient_name=await _patient_name(session, patient_id),
                    follow_up_plan=record.follow_up_plan,
                    risk_level=risk.primary_risk_level if risk else None,
                )
        return db_record


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_records_for_patient", {"doctor_id": doctor_id, "patient_id": patient_id}):
        repo = RecordRepository(session)
        return await repo.list_for_patient(
            doctor_id=doctor_id,
            patient_id=patient_id,
            limit=limit,
        )


async def get_all_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_all_records_for_doctor", {"doctor_id": doctor_id}):
        repo = RecordRepository(session)
        return await repo.list_for_doctor(
            doctor_id=doctor_id,
            limit=limit,
        )


async def save_neuro_case(
    session: AsyncSession,
    doctor_id: str,
    case: "NeuroCase",  # type: ignore[name-defined]
    log: "ExtractionLog",  # type: ignore[name-defined]
    patient_id: Optional[int] = None,
) -> NeuroCaseDB:
    """Promote key scalar fields, serialise both objects, persist row."""
    pp = case.patient_profile if isinstance(case.patient_profile, dict) else {}
    ne = case.neuro_exam if isinstance(case.neuro_exam, dict) else {}
    cc = case.chief_complaint if isinstance(case.chief_complaint, dict) else {}
    dx = case.diagnosis if isinstance(case.diagnosis, dict) else {}
    enc = case.encounter if isinstance(case.encounter, dict) else {}

    nihss_raw = ne.get("nihss_total")
    nihss: Optional[int] = None
    if nihss_raw is not None:
        try:
            nihss = int(nihss_raw)
        except (TypeError, ValueError):
            nihss = None

    age_raw = pp.get("age")
    age: Optional[int] = None
    if age_raw is not None:
        try:
            age = int(age_raw)
        except (TypeError, ValueError):
            age = None

    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = NeuroCaseDB(
        doctor_id=doctor_id,
        patient_id=patient_id,
        patient_name=pp.get("name"),
        gender=pp.get("gender"),
        age=age,
        encounter_type=enc.get("type"),
        chief_complaint=cc.get("text"),
        primary_diagnosis=dx.get("primary"),
        nihss=nihss,
        raw_json=json.dumps(case.model_dump(), ensure_ascii=False),
        extraction_log_json=json.dumps(log.model_dump(), ensure_ascii=False),
    )
    session.add(row)
    await session.commit()
    return row


async def get_neuro_cases_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 20,
) -> List[NeuroCaseDB]:
    """Return most-recent neuro cases for a doctor."""
    result = await session.execute(
        select(NeuroCaseDB)
        .where(NeuroCaseDB.doctor_id == doctor_id)
        .order_by(NeuroCaseDB.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
