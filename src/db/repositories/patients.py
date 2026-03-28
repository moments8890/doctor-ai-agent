"""
患者仓储层：提供带标签预加载的患者查询和分页检索接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Patient


def _year_of_birth(age: Optional[int]) -> Optional[int]:
    if age is None:
        return None
    return datetime.now().year - age


class PatientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        doctor_id: str,
        name: str,
        gender: Optional[str],
        age: Optional[int],
        access_code_hash: Optional[str] = None,
    ) -> Patient:
        patient = Patient(
            doctor_id=doctor_id,
            name=name,
            gender=gender,
            year_of_birth=_year_of_birth(age),
        )
        self.session.add(patient)
        await self.session.flush()  # get patient.id before creating PatientAuth
        if access_code_hash is not None:
            from db.models.patient_auth import PatientAuth
            from sqlalchemy import select as _select
            existing = (await self.session.execute(
                _select(PatientAuth).where(PatientAuth.patient_id == patient.id)
            )).scalar_one_or_none()
            if existing is None:
                self.session.add(PatientAuth(patient_id=patient.id, access_code=access_code_hash))
        await self.session.commit()
        return patient

    async def get_for_doctor(self, doctor_id: str, patient_id: int) -> Optional[Patient]:
        result = await self.session.execute(
            select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def find_by_name(self, doctor_id: str, name: str) -> Optional[Patient]:
        result = await self.session.execute(
            select(Patient).where(Patient.doctor_id == doctor_id, Patient.name == name).limit(1)
        )
        return result.scalar_one_or_none()

    async def find_by_exact_name(self, doctor_id: str, name: str, limit: int = 100) -> List[Patient]:
        result = await self.session.execute(
            select(Patient)
            
            .where(Patient.doctor_id == doctor_id, Patient.name == name)
            .order_by(Patient.created_at.desc(), Patient.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_doctor(self, doctor_id: str, limit: int = 200, offset: int = 0) -> List[Patient]:
        sort_ts = func.coalesce(Patient.last_activity_at, Patient.created_at)
        result = await self.session.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id)
            .order_by(sort_ts.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
