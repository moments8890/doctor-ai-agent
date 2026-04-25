"""
Feature flag helpers — per-doctor boolean flags, defaults-off.

Usage::

    from infra.feature_flags import is_flag_enabled, FLAG_PATIENT_CHAT_INTAKE_ENABLED

    if await is_flag_enabled(session, doctor_id, FLAG_PATIENT_CHAT_INTAKE_ENABLED):
        ...
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.feature_flag import DoctorFeatureFlag

FLAG_PATIENT_CHAT_INTAKE_ENABLED = "PATIENT_CHAT_INTAKE_ENABLED"


async def is_flag_enabled(
    session: AsyncSession,
    doctor_id: str,
    flag_name: str,
) -> bool:
    """Return True only if a row exists for (doctor_id, flag_name) with enabled=True.

    Missing row → False (defaults-off).
    """
    row = (
        await session.execute(
            select(DoctorFeatureFlag).where(
                DoctorFeatureFlag.doctor_id == doctor_id,
                DoctorFeatureFlag.flag_name == flag_name,
            )
        )
    ).scalar_one_or_none()
    return bool(row and row.enabled)
