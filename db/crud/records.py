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
    MedicalRecordVersion,
    DoctorTask,
)
from db.repositories import RecordRepository
from db.models.medical_record import MedicalRecord
from services.patient.patient_categorization import recompute_patient_category
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


async def _patient_name(session: AsyncSession, patient_id: int, doctor_id: str) -> str:
    result = await session.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = result.scalar_one_or_none()
    return patient.name if patient is not None else "患者"


async def _ensure_auto_follow_up_task(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    record_id: int,
    patient_name: str,
    follow_up_text: str,
) -> None:
    existing = await session.execute(
        select(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.record_id == record_id,
            DoctorTask.task_type == "follow_up",
            DoctorTask.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    days = _extract_follow_up_days(follow_up_text)
    due_at = _utcnow().replace(microsecond=0) + timedelta(days=days)

    session.add(
        DoctorTask(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_id=record_id,
            task_type="follow_up",
            title=f"随访提醒：{patient_name}",
            content=follow_up_text[:200],
            status="pending",
            due_at=due_at,
        )
    )
    await session.commit()


async def _detect_encounter_type(session: AsyncSession, doctor_id: str, patient_id: int | None) -> str:
    """Return 'first_visit' if patient has no prior records, 'follow_up' if they do, 'unknown' if no patient."""
    if patient_id is None:
        return "unknown"
    from sqlalchemy import func
    result = await session.execute(
        select(func.count()).where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id == patient_id,
        )
    )
    count = result.scalar() or 0
    return "first_visit" if count == 0 else "follow_up"


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
) -> MedicalRecordDB:
    with trace_block("db", "crud.save_record", {"doctor_id": doctor_id, "patient_id": patient_id}):
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        encounter_type = await _detect_encounter_type(session, doctor_id, patient_id)
        repo = RecordRepository(session)
        db_record = await repo.create(
            doctor_id=doctor_id,
            record=record,
            patient_id=patient_id,
            encounter_type=encounter_type,
        )
        if patient_id is not None:
            await recompute_patient_category(patient_id, session)
            _has_follow_up = (
                any("随访" in t or "复诊" in t for t in record.tags)
                or bool(re.search(r'随访|复诊|下次|下周', record.content))
            )
            if _env_flag_true("AUTO_FOLLOWUP_TASKS_ENABLED") and _has_follow_up:
                await _ensure_auto_follow_up_task(
                    session=session,
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    record_id=db_record.id,
                    patient_name=await _patient_name(session, patient_id, doctor_id),
                    follow_up_text=record.content,
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
) -> MedicalRecordDB:
    """Promote key scalar fields, serialise both objects, persist as a MedicalRecordDB row
    with record_type='neuro_case'."""
    pp = case.patient_profile if isinstance(case.patient_profile, dict) else {}
    ne = case.neuro_exam if isinstance(case.neuro_exam, dict) else {}

    nihss_raw = ne.get("nihss_total")
    nihss: Optional[int] = None
    if nihss_raw is not None:
        try:
            nihss = int(nihss_raw)
        except (TypeError, ValueError):
            nihss = None

    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = MedicalRecordDB(
        doctor_id=doctor_id,
        patient_id=patient_id,
        record_type="neuro_case",
        encounter_type="unknown",
        neuro_patient_name=pp.get("name"),
        nihss=nihss,
        neuro_raw_json=json.dumps(case.model_dump(), ensure_ascii=False),
        neuro_extraction_log_json=json.dumps(log.model_dump(), ensure_ascii=False),
    )
    session.add(row)
    await session.commit()
    return row


async def get_neuro_cases_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 20,
) -> List[MedicalRecordDB]:
    """Return most-recent neuro cases for a doctor."""
    result = await session.execute(
        select(MedicalRecordDB)
        .where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.record_type == "neuro_case",
        )
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def save_record_version(
    session: AsyncSession,
    record: MedicalRecordDB,
    doctor_id: str,
) -> MedicalRecordVersion:
    """Snapshot current content/tags/record_type before applying a correction."""
    version = MedicalRecordVersion(
        record_id=record.id,
        doctor_id=doctor_id,
        old_content=record.content,
        old_tags=record.tags,
        old_record_type=record.record_type,
    )
    session.add(version)
    return version



async def get_record_versions(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
) -> list[MedicalRecordVersion]:
    """Return correction history for a record, oldest first."""
    result = await session.execute(
        select(MedicalRecordVersion)
        .where(
            MedicalRecordVersion.record_id == record_id,
            MedicalRecordVersion.doctor_id == doctor_id,
        )
        .order_by(MedicalRecordVersion.changed_at.asc())
    )
    return list(result.scalars().all())


_RECORD_CLINICAL_FIELDS = frozenset({"content", "tags", "record_type"})


async def delete_record(
    session: AsyncSession,
    doctor_id: str,
    record_id: int,
) -> bool:
    """Delete a single record. Returns True if deleted, False if not found."""
    result = await session.execute(
        select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == doctor_id,
        ).limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return False
    await session.delete(record)
    await session.commit()
    return True


async def update_latest_record_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    fields: dict,
) -> Optional[MedicalRecordDB]:
    """Merge non-None corrected fields into the most recent record for a patient.

    Only fields listed in _RECORD_CLINICAL_FIELDS and present in ``fields`` with a
    non-None value are overwritten; all other fields are left untouched.
    Returns the updated record, or None if no record exists.
    """
    result = await session.execute(
        select(MedicalRecordDB)
        .where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id == patient_id,
        )
        .order_by(MedicalRecordDB.created_at.desc(), MedicalRecordDB.id.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    # Determine whether anything will change before mutating
    updates = {
        f: (json.dumps(v, ensure_ascii=False) if f == "tags" and isinstance(v, list) else v)
        for f, v in fields.items()
        if f in _RECORD_CLINICAL_FIELDS and v is not None
    }
    if updates:
        await save_record_version(session, record, doctor_id)  # snapshot before mutation
        for field, value in updates.items():
            setattr(record, field, value)
        await session.commit()
    return record
