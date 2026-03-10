"""
患者创建、查询、删除及标签管理的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import (
    Patient,
    PatientLabel,
    MedicalRecordDB,
    DoctorTask,
    DoctorSessionState,
    PendingRecord,
)
from db.repositories import PatientRepository
from services.observability.observability import trace_block
from services.observability.audit import audit
from utils.errors import InvalidMedicalRecordError, LabelNotFoundError, PatientNotFoundError
from db.crud.doctor import _ensure_doctor_exists
from utils.log import log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_patient_for_doctor(session: AsyncSession, doctor_id: str, patient_id: int) -> Optional[Patient]:
    repo = PatientRepository(session)
    return await repo.get_for_doctor(doctor_id, patient_id)


async def create_patient(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: Optional[str],
    age: Optional[int],
) -> Patient:
    with trace_block("db", "crud.create_patient", {"doctor_id": doctor_id}):
        cleaned_name = (name or "").strip()
        if not cleaned_name or len(cleaned_name) > 128:
            raise InvalidMedicalRecordError("Invalid patient name", context={"doctor_id": doctor_id})
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        repo = PatientRepository(session)
        return await repo.create(
            doctor_id=doctor_id,
            name=cleaned_name,
            gender=gender,
            age=age,
        )


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
    with trace_block("db", "crud.find_patient_by_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_name(doctor_id, name)


async def find_patients_by_exact_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> list[Patient]:
    with trace_block("db", "crud.find_patients_by_exact_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_exact_name(doctor_id, name)


async def delete_patient_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
) -> Optional[Patient]:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
        .limit(1)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return None

    patient.labels.clear()
    await session.flush()

    # manual cascade for SQLite compatibility — DB-level cascade handles MySQL/Postgres
    await session.execute(
        delete(MedicalRecordDB).where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id == patient_id,
        )
    )
    await session.execute(
        delete(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.patient_id == patient_id,
        )
    )
    # neuro_case records (now stored in medical_records) are cascade-deleted
    # when the patient row is deleted; no explicit delete needed here.
    await session.execute(
        delete(PendingRecord).where(
            PendingRecord.doctor_id == doctor_id,
            PendingRecord.patient_id == patient_id,
        )
    )
    await session.execute(
        update(DoctorSessionState)
        .where(
            DoctorSessionState.doctor_id == doctor_id,
            DoctorSessionState.current_patient_id == patient_id,
        )
        .values(current_patient_id=None, updated_at=_utcnow())
    )
    await session.delete(patient)
    await session.commit()
    return patient


async def get_all_patients(
    session: AsyncSession,
    doctor_id: str,
) -> list[Patient]:
    with trace_block("db", "crud.get_all_patients", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.list_for_doctor(doctor_id)


async def create_label(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    color: Optional[str] = None,
) -> PatientLabel:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    label = PatientLabel(doctor_id=doctor_id, name=name, color=color)
    session.add(label)
    await session.commit()
    import asyncio
    asyncio.ensure_future(audit(doctor_id, "WRITE", resource_type="patient_label", resource_id=str(label.id)))
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
    import asyncio
    asyncio.ensure_future(audit(doctor_id, "WRITE", resource_type="patient_label", resource_id=str(label_id)))
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
    import asyncio
    asyncio.ensure_future(audit(doctor_id, "DELETE", resource_type="patient_label", resource_id=str(label_id)))
    return True


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
        raise PatientNotFoundError(
            context={"doctor_id": doctor_id, "patient_id": str(patient_id)}
        )

    label_result = await session.execute(
        select(PatientLabel).where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = label_result.scalar_one_or_none()
    if label is None:
        raise LabelNotFoundError(
            context={"doctor_id": doctor_id, "label_id": str(label_id)}
        )

    if label not in patient.labels:
        patient.labels.append(label)
        await session.commit()
        import asyncio
        asyncio.ensure_future(audit(doctor_id, "WRITE", resource_type="patient_label", resource_id=f"{patient_id}:{label_id}"))


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
        raise PatientNotFoundError(
            context={"doctor_id": doctor_id, "patient_id": str(patient_id)}
        )
    patient.labels = [lbl for lbl in patient.labels if lbl.id != label_id]
    await session.commit()
    import asyncio
    asyncio.ensure_future(audit(doctor_id, "DELETE", resource_type="patient_label", resource_id=f"{patient_id}:{label_id}"))


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


async def search_patients_nl(
    session: AsyncSession,
    doctor_id: str,
    criteria: "PatientSearchCriteria",  # type: ignore[name-defined]
    limit: int = 20,
) -> list[Patient]:
    """Search patients using structured criteria extracted from a natural language query."""
    from services.patient.nl_search import PatientSearchCriteria  # local import avoids circular

    q = select(Patient).where(Patient.doctor_id == doctor_id)

    if criteria.surname:
        q = q.where(Patient.name.like(f"{criteria.surname}%"))

    if criteria.gender:
        q = q.where(Patient.gender == criteria.gender)

    current_year = datetime.now(timezone.utc).year
    if criteria.age_min is not None:
        q = q.where(Patient.year_of_birth <= current_year - criteria.age_min)
    if criteria.age_max is not None:
        q = q.where(Patient.year_of_birth >= current_year - criteria.age_max)

    if criteria.keywords or criteria.days_since_visit is not None:
        since = (
            datetime.now(timezone.utc) - timedelta(days=criteria.days_since_visit)
            if criteria.days_since_visit is not None else None
        )
        rec_q = select(MedicalRecordDB.patient_id).where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id.is_not(None),
        )
        if criteria.keywords:
            kw_filters = [
                or_(
                    MedicalRecordDB.content.like(f"%{kw}%"),
                    MedicalRecordDB.tags.like(f"%{kw}%"),
                )
                for kw in criteria.keywords
            ]
            rec_q = rec_q.where(and_(*kw_filters))
        if since is not None:
            rec_q = rec_q.where(MedicalRecordDB.created_at >= since)
        rec_q = rec_q.distinct()
        q = q.where(Patient.id.in_(rec_q))

    q = q.order_by(Patient.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_patient_demographics(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> Optional[Patient]:
    """Update gender and/or year_of_birth on the most recent patient row for this doctor+name."""
    from db.repositories.patients import _year_of_birth
    repo = PatientRepository(session)
    patient = await repo.find_by_name(doctor_id, name)
    if patient is None:
        return None
    updated = False
    if gender in ("男", "女") and gender != patient.gender:
        patient.gender = gender
        updated = True
    if age is not None:
        new_yob = _year_of_birth(age)
        if new_yob and new_yob != patient.year_of_birth:
            patient.year_of_birth = new_yob
            updated = True
    if updated:
        await session.commit()
        log(f"[silent-save] patient demographics updated doctor={doctor_id} patient={patient.id} name={name!r} gender={gender} age={age}")
    return patient
