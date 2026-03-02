from __future__ import annotations
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import SystemPrompt, DoctorContext, Patient, MedicalRecordDB, NeuroCaseDB
from models.medical_record import MedicalRecord


async def get_system_prompt(session: AsyncSession, key: str) -> SystemPrompt | None:
    result = await session.execute(
        select(SystemPrompt).where(SystemPrompt.key == key)
    )
    return result.scalar_one_or_none()


async def upsert_system_prompt(session: AsyncSession, key: str, content: str) -> None:
    row = await get_system_prompt(session, key)
    if row:
        row.content = content
        row.updated_at = datetime.utcnow()
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
        ctx.updated_at = datetime.utcnow()
    else:
        session.add(DoctorContext(doctor_id=doctor_id, summary=summary))
    await session.commit()


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
    patient = Patient(doctor_id=doctor_id, name=name, gender=gender, year_of_birth=_year_of_birth(age))
    session.add(patient)
    await session.commit()
    return patient


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
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
    return db_record


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
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
    result = await session.execute(
        select(Patient)
        .where(Patient.doctor_id == doctor_id)
        .order_by(Patient.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10,
) -> list[MedicalRecordDB]:
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
