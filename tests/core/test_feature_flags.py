"""Unit tests for the per-doctor feature flag helper."""

from __future__ import annotations

from datetime import datetime

import pytest

from db.models.feature_flag import DoctorFeatureFlag
from infra.feature_flags import is_flag_enabled


_TEST_FLAG = "TEST_OPT_IN_FLAG"


@pytest.mark.asyncio
async def test_no_row_defaults_false(db_session):
    """No row + flag not in _DEFAULTS → False (opt-in)."""
    assert await is_flag_enabled(db_session, "doc_no_row", _TEST_FLAG) is False


@pytest.mark.asyncio
async def test_row_with_enabled_true_returns_true(db_session):
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_a",
            flag_name=_TEST_FLAG,
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_a", _TEST_FLAG) is True


@pytest.mark.asyncio
async def test_row_with_enabled_false_returns_false(db_session):
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_b",
            flag_name=_TEST_FLAG,
            enabled=False,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_b", _TEST_FLAG) is False


@pytest.mark.asyncio
async def test_other_doctor_isolated(db_session):
    """A doctor's row does not affect a different doctor."""
    db_session.add(
        DoctorFeatureFlag(
            doctor_id="doc_x",
            flag_name=_TEST_FLAG,
            enabled=True,
            created_at=datetime.utcnow(),
        )
    )
    await db_session.flush()
    assert await is_flag_enabled(db_session, "doc_other", _TEST_FLAG) is False
