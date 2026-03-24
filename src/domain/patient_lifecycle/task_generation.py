"""Auto-generate patient tasks when a doctor confirms a diagnosis.

DiagnosisResult table has been removed. This module is now a stub.
TODO: reimplement task generation from MedicalRecordDB.ai_diagnosis column.
"""
from __future__ import annotations

from typing import Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tasks import DoctorTask


async def generate_patient_tasks(
    diagnosis_result: Any,
    db_session: AsyncSession,
) -> List[DoctorTask]:
    """No-op — DiagnosisResult table removed. Returns empty list."""
    return []
