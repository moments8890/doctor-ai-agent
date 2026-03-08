"""
患者仓储层：提供带标签预加载的患者查询和分页检索接口。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Patient
from services.patient.patient_categorization import RULES_VERSION
from services.patient.patient_risk import RULES_VERSION as RISK_RULES_VERSION


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
    ) -> Patient:
        patient = Patient(
            doctor_id=doctor_id,
            name=name,
            gender=gender,
            year_of_birth=_year_of_birth(age),
            primary_category="new",
            category_tags="[]",
            category_rules_version=RULES_VERSION,
            category_computed_at=datetime.now(timezone.utc),
            primary_risk_level="low",
            risk_tags='["no_records"]',
            risk_score=0,
            follow_up_state="not_needed",
            risk_computed_at=datetime.now(timezone.utc),
            risk_rules_version=RISK_RULES_VERSION,
        )
        self.session.add(patient)
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

    async def find_by_exact_name(self, doctor_id: str, name: str) -> List[Patient]:
        result = await self.session.execute(
            select(Patient)
            .options(selectinload(Patient.labels))
            .where(Patient.doctor_id == doctor_id, Patient.name == name)
            .order_by(Patient.created_at.desc(), Patient.id.desc())
        )
        return list(result.scalars().all())

    async def list_for_doctor(self, doctor_id: str) -> List[Patient]:
        result = await self.session.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id)
            .order_by(Patient.created_at.desc())
            .options(selectinload(Patient.labels))
        )
        return list(result.scalars().all())
