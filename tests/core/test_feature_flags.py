"""Unit tests for per-doctor feature flag helpers."""

from __future__ import annotations

import pytest
from datetime import datetime

from db.models.feature_flag import DoctorFeatureFlag
from infra.feature_flags import is_flag_enabled, FLAG_PATIENT_CHAT_INTAKE_ENABLED


@pytest.mark.asyncio
async def test_no_row_returns_false(db_session):
    assert await is_flag_enabled(db_session, "doc_x", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is False


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
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_x",
            flag_name=FLAG_PATIENT_CHAT_INTAKE_ENABLED,
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_other", FLAG_PATIENT_CHAT_INTAKE_ENABLED) is False
