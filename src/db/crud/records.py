"""
病历保存与查询的数据库操作。
"""

from __future__ import annotations

import json
import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import MedicalRecordDB
from db.repositories import RecordRepository
from db.models.medical_record import MedicalRecord
from db.crud._common import _utcnow, _trace_block
from db.crud.doctor import _ensure_doctor_exists
from utils.log import log


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
    *,
    status: Optional[str] = None,
    commit: bool = True,
) -> MedicalRecordDB:
    with _trace_block("db", "crud.save_record", {"doctor_id": doctor_id, "patient_id": patient_id}):
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        repo = RecordRepository(session)
        db_record = await repo.create(
            doctor_id=doctor_id,
            record=record,
            patient_id=patient_id,
        )
        if status is not None:
            db_record.status = status
        if commit:
            await session.commit()
        return db_record


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
    with _trace_block("db", "crud.get_records_for_patient", {"doctor_id": doctor_id, "patient_id": patient_id}):
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
    offset: int = 0,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[MedicalRecordDB]:
    with _trace_block("db", "crud.get_all_records_for_doctor", {"doctor_id": doctor_id}):
        repo = RecordRepository(session)
        return await repo.list_for_doctor(
            doctor_id=doctor_id,
            limit=limit,
            offset=offset,
            patient_name=patient_name,
            date_from=date_from,
            date_to=date_to,
        )


async def count_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    with _trace_block("db", "crud.count_records_for_doctor", {"doctor_id": doctor_id}):
        repo = RecordRepository(session)
        return await repo.count_for_doctor(
            doctor_id=doctor_id,
            patient_name=patient_name,
            date_from=date_from,
            date_to=date_to,
        )


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
        for field, value in updates.items():
            setattr(record, field, value)
        await session.commit()
        log(f"[silent-save] record correction applied doctor={doctor_id} record_id={record.id} patient_id={patient_id} fields={list(updates.keys())}")
    return record
