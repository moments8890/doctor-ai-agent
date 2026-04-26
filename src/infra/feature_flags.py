"""
Feature flag helpers — per-doctor boolean flags.

Default behavior: flags default OFF (opt-in) unless listed in ``_DEFAULTS``,
which holds beta-stage flags that default ON (opt-out kill-switch). Insert a
row with the desired ``enabled`` value to override per doctor.

Usage::

    from infra.feature_flags import is_flag_enabled

    if await is_flag_enabled(session, doctor_id, "MY_FLAG"):
        ...
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.feature_flag import DoctorFeatureFlag

# Per-flag defaults. Beta-stage features default ON (opt-out kill-switch);
# everything else defaults OFF (opt-in). Insert a row with enabled=False to
# disable a defaulted-on flag for a specific doctor.
_DEFAULTS: dict[str, bool] = {}


async def is_flag_enabled(
    session: AsyncSession,
    doctor_id: str,
    flag_name: str,
) -> bool:
    """Per-doctor feature flag. Falls back to ``_DEFAULTS`` then to ``False``."""
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
