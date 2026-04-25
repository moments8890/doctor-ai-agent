"""Unit tests for per-doctor feature flag helpers."""

from __future__ import annotations

import pytest
from datetime import datetime

from db.models.feature_flag import DoctorFeatureFlag
from infra.feature_flags import is_flag_enabled, FLAG_PATIENT_CHAT_INTAKE_ENABLED


@pytest.mark.asyncio
async def test_no_row_for_intake_flag_defaults_true_in_beta(db_session):
    """Beta-stage feature: PATIENT_CHAT_INTAKE_ENABLED defaults True when no row exists."""
    assert await is_flag_enabled(db_session, "doc_no_row", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is True


@pytest.mark.asyncio
async def test_no_row_for_unknown_flag_defaults_false(db_session):
    """Other flags still default False (opt-in)."""
    assert await is_flag_enabled(db_session, "doc_no_row", "SOME_OTHER_FLAG") is False


@pytest.mark.asyncio
async def test_explicit_false_row_overrides_default_true(db_session):
    """Kill-switch: explicit enabled=False row disables the beta-default flag for that doctor."""
    db_session.add(DoctorFeatureFlag(
        doctor_id="doc_disabled",
        flag_name=FLAG_PATIENT_CHAT_INTAKE_ENABLED,
        enabled=False,
        created_at=datetime.utcnow(),
    ))
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_disabled", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is False


@pytest.mark.asyncio
async def test_row_with_enabled_true_returns_true(db_session):
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_a",
            flag_name=FLAG_PATIENT_CHAT_INTAKE_ENABLED,
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_a", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is True


@pytest.mark.asyncio
async def test_row_with_enabled_false_returns_false(db_session):
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_b",
            flag_name=FLAG_PATIENT_CHAT_INTAKE_ENABLED,
            enabled=False,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_b", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is False


@pytest.mark.asyncio
async def test_other_doctor_isolated(db_session):
    """A doctor with an explicit True row does not affect another doctor with no row.
    With the beta default, the other doctor also gets True (default-on)."""
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_x",
            flag_name=FLAG_PATIENT_CHAT_INTAKE_ENABLED,
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    # doc_other has no row — falls back to default True (beta)
    assert await is_flag_enabled(db_session, "doc_other", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is True
