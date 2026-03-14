"""
病历仓储层：提供病历的关联查询和 Pydantic 模型转换接口。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models import MedicalRecordDB
from db.models.medical_record import MedicalRecord


def _parse_date_str(s: str, *, end_of_day: bool = False) -> datetime:
    """Parse 'YYYY-MM-DD' to a datetime. If end_of_day, set to 23:59:59."""
    dt = datetime.strptime(s, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


class RecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        doctor_id: str,
        record: MedicalRecord,
        patient_id: Optional[int],
        encounter_type: str = "unknown",
    ) -> MedicalRecordDB:
        db_record = MedicalRecordDB(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_type=record.record_type,
            content=record.content,
            tags=json.dumps(record.tags, ensure_ascii=False) if record.tags else None,
            encounter_type=encounter_type,
        )
        self.session.add(db_record)
        await self.session.flush()
        return db_record

    async def list_for_patient(
        self,
        *,
        doctor_id: str,
        patient_id: int,
        limit: int,
    ) -> List[MedicalRecordDB]:
        result = await self.session.execute(
            select(MedicalRecordDB)
            .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_doctor(
        self,
        *,
        doctor_id: str,
        limit: int,
        offset: int = 0,
        patient_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[MedicalRecordDB]:
        from db.models import Patient
        stmt = (
            select(MedicalRecordDB)
            .options(joinedload(MedicalRecordDB.patient))
            .where(MedicalRecordDB.doctor_id == doctor_id)
        )
        if patient_name:
            stmt = stmt.join(Patient, MedicalRecordDB.patient_id == Patient.id).where(
                Patient.name.like(f"%{patient_name}%")
            )
        if date_from:
            stmt = stmt.where(MedicalRecordDB.created_at >= _parse_date_str(date_from))
        if date_to:
            stmt = stmt.where(MedicalRecordDB.created_at <= _parse_date_str(date_to, end_of_day=True))
        stmt = stmt.order_by(MedicalRecordDB.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_for_doctor(
        self,
        *,
        doctor_id: str,
        patient_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> int:
        from sqlalchemy import func
        from db.models import Patient
        stmt = select(func.count(MedicalRecordDB.id)).where(
            MedicalRecordDB.doctor_id == doctor_id
        )
        if patient_name:
            stmt = stmt.join(Patient, MedicalRecordDB.patient_id == Patient.id).where(
                Patient.name.like(f"%{patient_name}%")
            )
        if date_from:
            stmt = stmt.where(MedicalRecordDB.created_at >= _parse_date_str(date_from))
        if date_to:
            stmt = stmt.where(MedicalRecordDB.created_at <= _parse_date_str(date_to, end_of_day=True))
        result = await self.session.execute(stmt)
        return result.scalar() or 0
