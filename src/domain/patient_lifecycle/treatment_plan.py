"""Derive a patient-visible treatment plan.

DiagnosisResult table has been removed. This module is now a stub that
returns None until treatment plan logic is migrated to read from
MedicalRecordDB.ai_diagnosis / doctor_decisions columns directly.

TODO: reimplement using MedicalRecordDB columns instead of DiagnosisResult.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def derive_treatment_plan(
    patient_id: int,
    db_session: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Build a treatment-plan dict from the latest confirmed diagnosis.

    Returns ``None`` — DiagnosisResult table removed.
    """
    return None
