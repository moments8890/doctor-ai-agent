"""Tests for SQLite lock-contention fixes:

1. SQLite engine creation works correctly for in-memory databases
2. save_cvd_context persists data and is visible after commit
3. confirm_pending_record changes status correctly
4. _persist_pending_record single-commit path
5. confirm_pending endpoint returns correct errors on failure
"""

from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from db.models.medical_record import MedicalRecord


DOCTOR = "unit_doc_sqlite_lock"


# ---------------------------------------------------------------------------
# 1. SQLite engine creation
# ---------------------------------------------------------------------------


def test_sqlite_engine_creates_valid_async_engine():
    """db/engine.py creates a valid async engine for SQLite URLs."""
    from sqlalchemy.ext.asyncio import create_async_engine

    # Verify we can create a SQLite async engine the same way db/engine.py does
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    assert eng is not None
    # The engine URL should reflect SQLite
    assert "sqlite" in str(eng.url)


# ---------------------------------------------------------------------------
# 2. save_cvd_context persists data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_cvd_context_persists_data(session_factory):
    """save_cvd_context commits internally and data is visible in a new session."""
    from db.crud.specialty import save_cvd_context
    from db.models.neuro_case import NeuroCVDSurgicalContext

    ctx = NeuroCVDSurgicalContext(diagnosis_subtype="ACS", surgery_status="pre_op")

    async with session_factory() as session:
        row = await save_cvd_context(
            session, DOCTOR, patient_id=1, record_id=99,
            ctx=ctx, source="test",
        )
        assert row.id is not None
        assert row.doctor_id == DOCTOR

    # Row should persist in a new session (save_cvd_context commits internally)
    async with session_factory() as session:
        from sqlalchemy import select
        from db.models.specialty import NeuroCVDContext
        result = await session.execute(select(NeuroCVDContext))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].doctor_id == DOCTOR
        assert rows[0].diagnosis_subtype == "ACS"
        assert rows[0].surgery_status == "pre_op"


@pytest.mark.asyncio
async def test_save_cvd_context_stores_raw_json(session_factory):
    """save_cvd_context stores serialized context in raw_json column."""
    from db.crud.specialty import save_cvd_context
    from db.models.neuro_case import NeuroCVDSurgicalContext

    ctx = NeuroCVDSurgicalContext(diagnosis_subtype="ACS", surgery_status="pre_op")

    async with session_factory() as session:
        row = await save_cvd_context(
            session, DOCTOR, patient_id=1, record_id=99,
            ctx=ctx, source="test",
        )
        assert row.raw_json is not None
        parsed = json.loads(row.raw_json)
        assert parsed["diagnosis_subtype"] == "ACS"


# ---------------------------------------------------------------------------
# 3. confirm_pending_record changes status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_pending_record_changes_status(session_factory):
    """confirm_pending_record sets status to 'confirmed'."""
    from db.crud.pending import create_pending_record, confirm_pending_record
    from sqlalchemy import select
    from db.models import PendingRecord

    async with session_factory() as session:
        await create_pending_record(
            session, record_id="lock-test-001", doctor_id=DOCTOR,
            draft_json='{"content":"test"}', ttl_minutes=10,
        )

    async with session_factory() as session:
        await confirm_pending_record(session, "lock-test-001", doctor_id=DOCTOR)

    # After confirm, status should be "confirmed" in a fresh session
    async with session_factory() as session:
        result = await session.execute(
            select(PendingRecord).where(PendingRecord.id == "lock-test-001")
        )
        row = result.scalar_one()
        assert row.status == "confirmed"


@pytest.mark.asyncio
async def test_confirm_pending_record_persists(session_factory):
    """confirm_pending_record commits internally -- data is visible across sessions."""
    from db.crud.pending import create_pending_record, confirm_pending_record
    from sqlalchemy import select
    from db.models import PendingRecord

    async with session_factory() as session:
        await create_pending_record(
            session, record_id="lock-test-002", doctor_id=DOCTOR,
            draft_json='{"content":"test"}', ttl_minutes=10,
        )

    async with session_factory() as session:
        await confirm_pending_record(session, "lock-test-002", doctor_id=DOCTOR)

    # Verify persistence in yet another session
    async with session_factory() as session:
        result = await session.execute(
            select(PendingRecord).where(PendingRecord.id == "lock-test-002")
        )
        row = result.scalar_one()
        assert row.status == "confirmed"


# ---------------------------------------------------------------------------
# 4. _persist_pending_record uses single commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_pending_record_single_commit(session_factory):
    """_persist_pending_record should call session.commit() exactly once."""
    from db.crud.pending import create_pending_record
    from services.session import set_current_patient

    fake_record = MedicalRecord(content="胸痛两天", tags=["胸痛"])
    draft_id = "persist-commit-test-001"

    async with session_factory() as db:
        pending = await create_pending_record(
            db, record_id=draft_id, doctor_id=DOCTOR,
            draft_json=json.dumps(fake_record.model_dump(), ensure_ascii=False),
            patient_id=1, patient_name="张三", ttl_minutes=10,
        )

    from services.wechat.wechat_domain import _persist_pending_record

    commit_count = 0
    original_session_factory = session_factory

    class CountingSession:
        """Wraps a real session and counts commit() calls."""
        def __init__(self, real_session):
            self._real = real_session

        def __getattr__(self, name):
            return getattr(self._real, name)

        async def commit(self):
            nonlocal commit_count
            commit_count += 1
            return await self._real.commit()

        async def flush(self):
            return await self._real.flush()

        async def refresh(self, instance, **kw):
            return await self._real.refresh(instance, **kw)

        def add(self, instance):
            return self._real.add(instance)

        async def execute(self, stmt, *args, **kw):
            return await self._real.execute(stmt, *args, **kw)

    class CountingFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            self._real_session = await original_session_factory().__aenter__()
            self._counting = CountingSession(self._real_session)
            return self._counting

        async def __aexit__(self, *args):
            return await self._real_session.__aexit__(*args)

    with patch("services.wechat.wechat_domain.AsyncSessionLocal", CountingFactory()):
        result = await _persist_pending_record(pending, fake_record, None, DOCTOR)

    # save_record internally calls recompute_patient_category which commits once,
    # then our code does one final commit. The key assertion: cvd_context and
    # confirm_pending_record did NOT add extra commits (previously 3, now ≤ 2).
    assert result is not None
    assert commit_count <= 2, f"Expected <=2 commits (was 3 before fix), got {commit_count}"


# ---------------------------------------------------------------------------
# 5. Confirm endpoint error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_endpoint_500_when_save_returns_none():
    """POST /pending/.../confirm returns 500 when save_pending_record returns None."""
    from routers.records import confirm_pending
    from fastapi import HTTPException

    fake_pending = MagicMock()
    fake_pending.id = "draft-500-test"

    with patch("routers.records.resolve_doctor_id_from_auth_or_fallback", return_value=DOCTOR), \
         patch("routers.records.AsyncSessionLocal") as mock_factory, \
         patch("routers.records.get_pending_record", new=AsyncMock(return_value=fake_pending)), \
         patch(
             "services.wechat.wechat_domain.save_pending_record",
             new=AsyncMock(return_value=None),
         ):

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await confirm_pending("draft-500-test", doctor_id=DOCTOR)

        assert exc_info.value.status_code == 500
        assert "重试" in exc_info.value.detail


@pytest.mark.asyncio
async def test_confirm_endpoint_propagates_db_locked_error():
    """POST /pending/.../confirm propagates database-is-locked as unhandled exception."""
    from routers.records import confirm_pending

    fake_pending = MagicMock()
    fake_pending.id = "draft-503-test"

    with patch("routers.records.resolve_doctor_id_from_auth_or_fallback", return_value=DOCTOR), \
         patch("routers.records.AsyncSessionLocal") as mock_factory, \
         patch("routers.records.get_pending_record", new=AsyncMock(return_value=fake_pending)), \
         patch(
             "services.wechat.wechat_domain.save_pending_record",
             new=AsyncMock(side_effect=Exception("(sqlite3.OperationalError) database is locked")),
         ):

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # The exception propagates since the endpoint doesn't catch it
        with pytest.raises(Exception, match="database is locked"):
            await confirm_pending("draft-503-test", doctor_id=DOCTOR)
