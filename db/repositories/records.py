"""
病历仓储层：提供病历的关联查询和 Pydantic 模型转换接口。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models import MedicalRecordDB
from models.medical_record import MedicalRecord


class RecordRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        doctor_id: str,
        record: MedicalRecord,
        patient_id: Optional[int],
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
        self.session.add(db_record)
        await self.session.commit()
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
    ) -> List[MedicalRecordDB]:
        result = await self.session.execute(
            select(MedicalRecordDB)
            .options(joinedload(MedicalRecordDB.patient))
            .where(MedicalRecordDB.doctor_id == doctor_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())
