"""
Feature flag helpers — per-doctor boolean flags.

Default behavior: most flags are OFF (opt-in). Beta-stage flags listed in
_DEFAULTS are ON by default (opt-out kill-switch): insert a row with
enabled=False to disable for a specific doctor.

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

# Per-flag default. Beta-stage features default ON (opt-out kill-switch);
# everything else defaults OFF (opt-in). To kill switch: insert a row with enabled=False.
_DEFAULTS: dict[str, bool] = {
    FLAG_PATIENT_CHAT_INTAKE_ENABLED: True,
}


async def is_flag_enabled(
    session: AsyncSession,
    doctor_id: str,
    flag_name: str,
) -> bool:
    """Per-doctor feature flag. If no row exists, falls back to _DEFAULTS for the flag,
    or False if the flag has no default. To override per doctor, insert a row with the
    desired enabled value.
    """
    row = (
        await session.execute(
            select(DoctorFeatureFlag).where(
                DoctorFeatureFlag.doctor_id == doctor_id,
                DoctorFeatureFlag.flag_name == flag_name,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return bool(row.enabled)
    return _DEFAULTS.get(flag_name, False)
