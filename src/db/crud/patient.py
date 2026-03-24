"""
患者创建、查询、删除的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import (
    Patient,
    MedicalRecordDB,
    DoctorTask,
)
from db.repositories import PatientRepository
from utils.hashing import generate_access_code, hash_access_code  # noqa: F401 — re-exported for callers
from utils.errors import InvalidMedicalRecordError, PatientNotFoundError
from db.crud._common import _trace_block
from db.crud.doctor import _ensure_doctor_exists
from utils.log import log, safe_create_task


def _audit(doctor_id: str, action: str, **kwargs):
    """Lazy-import audit to avoid db/ → services/ module-level dependency."""
    from infra.observability.audit import audit
    return audit(doctor_id, action, **kwargs)


async def get_patient_for_doctor(session: AsyncSession, doctor_id: str, patient_id: int) -> Optional[Patient]:
    repo = PatientRepository(session)
    return await repo.get_for_doctor(doctor_id, patient_id)


async def create_patient(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: Optional[str],
    age: Optional[int],
) -> tuple["Patient", str]:
    """Create a patient and auto-generate a 6-digit portal access code.

    Returns ``(patient, plaintext_access_code)``.  The plaintext code is
    returned as a separate value so the caller can display it **once** to
    the doctor.  It is **not** persisted — only the PBKDF2-SHA256 hash is
    stored in the database.
    """
    with _trace_block("db", "crud.create_patient", {"doctor_id": doctor_id}):
        cleaned_name = (name or "").strip()
        if not cleaned_name or len(cleaned_name) > 128:
            raise InvalidMedicalRecordError("Invalid patient name", context={"doctor_id": doctor_id})
        doctor_id = await _ensure_doctor_exists(session, doctor_id)

        plaintext_code = generate_access_code()
        hashed_code = hash_access_code(plaintext_code)

        repo = PatientRepository(session)
        patient = await repo.create(
            doctor_id=doctor_id,
            name=cleaned_name,
            gender=gender,
            age=age,
            access_code_hash=hashed_code,
        )
        log(f"[create_patient] access code generated for patient [{cleaned_name}] id={patient.id}")
        return patient, plaintext_code


async def set_patient_access_code(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
) -> str:
    """Generate a new access code for an existing patient.

    Returns the **plaintext** 6-digit code so the doctor can share it with the
    patient.  Only the PBKDF2-SHA256 hash is stored in the database.

    Raises:
        PatientNotFoundError: If no patient with *patient_id* belongs to *doctor_id*.
    """
    repo = PatientRepository(session)
    patient = await repo.get_for_doctor(doctor_id, patient_id)
    if patient is None:
        raise PatientNotFoundError(
            context={"doctor_id": doctor_id, "patient_id": str(patient_id)}
        )
    from db.models.patient_auth import PatientAuth
    plaintext_code = generate_access_code()
    hashed_code = hash_access_code(plaintext_code)
    auth_row = (
        await session.execute(
            select(PatientAuth).where(PatientAuth.patient_id == patient.id).limit(1)
        )
    ).scalar_one_or_none()
    if auth_row is None:
        session.add(PatientAuth(patient_id=patient.id, access_code=hashed_code, access_code_version=1))
    else:
        auth_row.access_code = hashed_code
        auth_row.access_code_version = (auth_row.access_code_version or 0) + 1
    await session.commit()
    log(f"[set_patient_access_code] new access code set for patient id={patient_id} doctor={doctor_id}")
    return plaintext_code


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
    with _trace_block("db", "crud.find_patient_by_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_name(doctor_id, name)


async def find_patients_by_exact_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> list[Patient]:
    with _trace_block("db", "crud.find_patients_by_exact_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_exact_name(doctor_id, name)


async def delete_patient_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
) -> Optional[Patient]:
    patient_result = await session.execute(
        select(Patient)
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
        .limit(1)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return None

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
    await session.delete(patient)
    await session.commit()
    return patient


async def get_all_patients(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10000,
) -> list[Patient]:
    with _trace_block("db", "crud.get_all_patients", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.list_for_doctor(doctor_id, limit=limit)


async def search_patients_nl(
    session: AsyncSession,
    doctor_id: str,
    criteria: "PatientSearchCriteria",  # type: ignore[name-defined]
    limit: int = 20,
) -> list[Patient]:
    """Search patients using structured criteria extracted from a natural language query."""
    from domain.patients.nl_search import PatientSearchCriteria  # local import avoids circular

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
            def _escape_like(s: str) -> str:
                """Escape SQL LIKE wildcards so user input is matched literally."""
                return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

            kw_filters = [
                or_(
                    MedicalRecordDB.content.like(f"%{_escape_like(kw)}%"),
                    MedicalRecordDB.tags.like(f"%{_escape_like(kw)}%"),
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
