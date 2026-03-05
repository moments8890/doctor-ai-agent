from __future__ import annotations
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import (
    SystemPrompt, DoctorContext, DoctorSessionState, Patient, MedicalRecordDB, NeuroCaseDB, DoctorTask, PatientLabel
)
from models.medical_record import MedicalRecord
from services.patient_categorization import RULES_VERSION, recompute_patient_category
from services.patient_risk import RULES_VERSION as RISK_RULES_VERSION, recompute_patient_risk
from services.observability import trace_block


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_system_prompt(session: AsyncSession, key: str) -> SystemPrompt | None:
    result = await session.execute(
        select(SystemPrompt).where(SystemPrompt.key == key)
    )
    return result.scalar_one_or_none()


async def upsert_system_prompt(session: AsyncSession, key: str, content: str) -> None:
    row = await get_system_prompt(session, key)
    if row:
        row.content = content
        row.updated_at = _utcnow()
    else:
        session.add(SystemPrompt(key=key, content=content))
    await session.commit()


async def get_doctor_context(session: AsyncSession, doctor_id: str) -> DoctorContext | None:
    result = await session.execute(
        select(DoctorContext).where(DoctorContext.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def upsert_doctor_context(session: AsyncSession, doctor_id: str, summary: str) -> None:
    ctx = await get_doctor_context(session, doctor_id)
    if ctx:
        ctx.summary = summary
        ctx.updated_at = _utcnow()
    else:
        session.add(DoctorContext(doctor_id=doctor_id, summary=summary))
    await session.commit()


async def get_doctor_session_state(session: AsyncSession, doctor_id: str) -> Optional[DoctorSessionState]:
    result = await session.execute(
        select(DoctorSessionState).where(DoctorSessionState.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def upsert_doctor_session_state(
    session: AsyncSession,
    doctor_id: str,
    current_patient_id: Optional[int],
    pending_create_name: Optional[str],
) -> None:
    row = await get_doctor_session_state(session, doctor_id)
    if row:
        row.current_patient_id = current_patient_id
        row.pending_create_name = pending_create_name
        row.updated_at = _utcnow()
    else:
        session.add(
            DoctorSessionState(
                doctor_id=doctor_id,
                current_patient_id=current_patient_id,
                pending_create_name=pending_create_name,
                updated_at=_utcnow(),
            )
        )
    await session.commit()


async def get_patient_for_doctor(session: AsyncSession, doctor_id: str, patient_id: int) -> Optional[Patient]:
    result = await session.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id).limit(1)
    )
    return result.scalar_one_or_none()


def _year_of_birth(age: Optional[int]) -> Optional[int]:
    if age is None:
        return None
    return datetime.now().year - age


async def create_patient(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: Optional[str],
    age: Optional[int],
) -> Patient:
    with trace_block("db", "crud.create_patient", {"doctor_id": doctor_id}):
        patient = Patient(
            doctor_id=doctor_id,
            name=name,
            gender=gender,
            year_of_birth=_year_of_birth(age),
            primary_category="new",
            category_tags="[]",
            category_rules_version=RULES_VERSION,
            category_computed_at=_utcnow(),
            primary_risk_level="low",
            risk_tags='["no_records"]',
            risk_score=0,
            follow_up_state="not_needed",
            risk_computed_at=_utcnow(),
            risk_rules_version=RISK_RULES_VERSION,
        )
        session.add(patient)
        await session.commit()
        return patient


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
    with trace_block("db", "crud.find_patient_by_name", {"doctor_id": doctor_id}):
        result = await session.execute(
            select(Patient).where(Patient.doctor_id == doctor_id, Patient.name == name).limit(1)
        )
        return result.scalar_one_or_none()


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
) -> MedicalRecordDB:
    with trace_block("db", "crud.save_record", {"doctor_id": doctor_id, "patient_id": patient_id}):
        db_record = MedicalRecordDB(
            doctor_id=doctor_id,
            patient_id=patient_id,
            chief_complaint=record.chief_complaint,
            history_of_present_illness=record.history_of_present_illness,
            past_medical_history=record.past_medical_history,
            physical_examination=record.physical_examination,
            auxiliary_examinations=record.auxiliary_examinations,
            diagnosis=record.diagnosis,
            treatment_plan=record.treatment_plan,
            follow_up_plan=record.follow_up_plan,
        )
        session.add(db_record)
        await session.commit()
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


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_records_for_patient", {"doctor_id": doctor_id, "patient_id": patient_id}):
        result = await session.execute(
            select(MedicalRecordDB)
            .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_all_patients(
    session: AsyncSession,
    doctor_id: str,
) -> list[Patient]:
    with trace_block("db", "crud.get_all_patients", {"doctor_id": doctor_id}):
        result = await session.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id)
            .order_by(Patient.created_at.desc())
            .options(selectinload(Patient.labels))
        )
        return list(result.scalars().all())


async def get_all_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_all_records_for_doctor", {"doctor_id": doctor_id}):
        result = await session.execute(
            select(MedicalRecordDB)
            .options(joinedload(MedicalRecordDB.patient))
            .where(MedicalRecordDB.doctor_id == doctor_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())


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


# ---------------------------------------------------------------------------
# DoctorTask CRUD
# ---------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    doctor_id: str,
    task_type: str,
    title: str,
    content: Optional[str] = None,
    patient_id: Optional[int] = None,
    record_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
) -> DoctorTask:
    task = DoctorTask(
        doctor_id=doctor_id,
        task_type=task_type,
        title=title,
        content=content,
        patient_id=patient_id,
        record_id=record_id,
        due_at=due_at,
        status="pending",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
) -> List[DoctorTask]:
    q = select(DoctorTask).where(DoctorTask.doctor_id == doctor_id)
    if status is not None:
        q = q.where(DoctorTask.status == status)
    q = q.order_by(DoctorTask.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_task_status(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    status: str,
) -> Optional[DoctorTask]:
    result = await session.execute(
        select(DoctorTask).where(DoctorTask.id == task_id, DoctorTask.doctor_id == doctor_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None
    task.status = status
    await session.commit()
    await session.refresh(task)
    return task


async def get_due_tasks(
    session: AsyncSession,
    now: datetime,
) -> List[DoctorTask]:
    result = await session.execute(
        select(DoctorTask).where(
            DoctorTask.status == "pending",
            DoctorTask.due_at <= now,
            DoctorTask.notified_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def mark_task_notified(
    session: AsyncSession,
    task_id: int,
) -> None:
    result = await session.execute(
        select(DoctorTask).where(DoctorTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.notified_at = _utcnow()
        await session.commit()


# ── Label management ──────────────────────────────────────────────────────────

async def create_label(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    color: Optional[str] = None,
) -> PatientLabel:
    label = PatientLabel(doctor_id=doctor_id, name=name, color=color)
    session.add(label)
    await session.commit()
    return label


async def get_labels_for_doctor(
    session: AsyncSession,
    doctor_id: str,
) -> List[PatientLabel]:
    result = await session.execute(
        select(PatientLabel)
        .where(PatientLabel.doctor_id == doctor_id)
        .order_by(PatientLabel.created_at)
    )
    return list(result.scalars().all())


async def update_label(
    session: AsyncSession,
    label_id: int,
    doctor_id: str,
    *,
    name: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[PatientLabel]:
    result = await session.execute(
        select(PatientLabel).where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        return None
    if name is not None:
        label.name = name
    if color is not None:
        label.color = color
    await session.commit()
    return label


async def delete_label(
    session: AsyncSession,
    label_id: int,
    doctor_id: str,
) -> bool:
    result = await session.execute(
        select(PatientLabel)
        .options(selectinload(PatientLabel.patients))
        .where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        return False
    # Clear via ORM — updates in-memory Patient.labels back-populates and
    # removes patient_label_assignments rows without needing raw SQL.
    label.patients.clear()
    await session.flush()
    await session.delete(label)
    await session.commit()
    return True


# ── Patient-label assignment ──────────────────────────────────────────────────

async def assign_label(
    session: AsyncSession,
    patient_id: int,
    label_id: int,
    doctor_id: str,
) -> None:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found for doctor {doctor_id}")

    label_result = await session.execute(
        select(PatientLabel).where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = label_result.scalar_one_or_none()
    if label is None:
        raise ValueError(f"Label {label_id} not found for doctor {doctor_id}")

    if label not in patient.labels:
        patient.labels.append(label)
        await session.commit()


async def remove_label(
    session: AsyncSession,
    patient_id: int,
    label_id: int,
    doctor_id: str,
) -> None:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found for doctor {doctor_id}")
    patient.labels = [lbl for lbl in patient.labels if lbl.id != label_id]
    await session.commit()


async def get_patient_labels(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> List[PatientLabel]:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return []
    return list(patient.labels)
