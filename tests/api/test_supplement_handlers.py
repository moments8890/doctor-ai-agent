"""Smoke tests for supplement queue endpoints (Task 1.13)."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Ensure src/ is on the path (mirrors tests/conftest.py)
_SRC = Path(__file__).parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from db.engine import Base
import db.models  # noqa: F401 — registers all ORM classes

from db.models.records import FieldEntryDB, MedicalRecordDB, RecordSupplementDB
from channels.web.doctor_dashboard.supplement_handlers import (
    accept,
    create_new,
    ignore,
    list_pending,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures (self-contained — no shared conftest needed)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_record_and_supplement(db_session, doctor_id="doc_test"):
    """Create a minimal MedicalRecordDB + one pending RecordSupplementDB."""
    from db.models.doctor import Doctor
    from db.models.patient import Patient

    doctor = Doctor(
        doctor_id=doctor_id,
        name="Test Doctor",
        passcode_hash="x",
    )
    db_session.add(doctor)
    await db_session.flush()

    patient = Patient(doctor_id=doctor_id, name="Patient A")
    db_session.add(patient)
    await db_session.flush()

    rec = MedicalRecordDB(
        patient_id=patient.id,
        doctor_id=doctor_id,
        status="completed",
        seed_source="explicit_interview",
    )
    db_session.add(rec)
    await db_session.flush()

    entries = [
        {
            "field_name": "chief_complaint",
            "text": "复发",
            "intake_segment_id": "seg_1",
            "created_at": "2026-04-25T10:00:00",
        }
    ]
    sup = RecordSupplementDB(
        record_id=rec.id,
        status="pending_doctor_review",
        field_entries_json=json.dumps(entries),
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(sup)
    await db_session.flush()
    return rec, sup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_writes_field_entries_and_marks_accepted(db_session):
    rec, sup = await _seed_record_and_supplement(db_session)

    result = await accept(supplement_id=sup.id, doctor_id="doc_test", session=db_session)
    assert result["status"] == "accepted"

    # FieldEntryDB row created
    fes = (
        await db_session.execute(
            select(FieldEntryDB).where(FieldEntryDB.record_id == rec.id)
        )
    ).scalars().all()
    assert any(
        fe.field_name == "chief_complaint" and fe.text == "复发" for fe in fes
    )

    # Supplement marked
    refreshed = await db_session.get(RecordSupplementDB, sup.id)
    assert refreshed.status == "accepted"
    assert refreshed.doctor_decision_by == "doc_test"
    assert refreshed.doctor_decision_at is not None


@pytest.mark.asyncio
async def test_ignore_marks_rejected_ignored(db_session):
    _rec, sup = await _seed_record_and_supplement(db_session)

    result = await ignore(supplement_id=sup.id, doctor_id="doc_test", session=db_session)
    assert result["status"] == "rejected_ignored"

    refreshed = await db_session.get(RecordSupplementDB, sup.id)
    assert refreshed.status == "rejected_ignored"
    assert refreshed.doctor_decision_by == "doc_test"


@pytest.mark.asyncio
async def test_create_new_marks_rejected_create_new(db_session):
    _rec, sup = await _seed_record_and_supplement(db_session)

    result = await create_new(
        supplement_id=sup.id, doctor_id="doc_test", session=db_session
    )
    assert result["status"] == "rejected_create_new"

    refreshed = await db_session.get(RecordSupplementDB, sup.id)
    assert refreshed.status == "rejected_create_new"
    assert refreshed.doctor_decision_by == "doc_test"


@pytest.mark.asyncio
async def test_double_decision_404s(db_session):
    """Accept once, then try to accept again — should raise 404."""
    _rec, sup = await _seed_record_and_supplement(db_session)

    await accept(supplement_id=sup.id, doctor_id="doc_test", session=db_session)

    with pytest.raises(HTTPException) as exc_info:
        await accept(supplement_id=sup.id, doctor_id="doc_test", session=db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_pending_returns_pending_only(db_session):
    _rec, sup = await _seed_record_and_supplement(db_session)

    response = await list_pending(doctor_id="doc_test", session=db_session)
    ids = [item["id"] for item in response["items"]]
    assert sup.id in ids

    # After accepting, it should no longer be in pending list
    await accept(supplement_id=sup.id, doctor_id="doc_test", session=db_session)
    response2 = await list_pending(doctor_id="doc_test", session=db_session)
    ids2 = [item["id"] for item in response2["items"]]
    assert sup.id not in ids2


@pytest.mark.asyncio
async def test_list_pending_isolates_doctors(db_session):
    """Doctor A's pending supplements must not appear in Doctor B's list."""
    from db.models.doctor import Doctor
    from db.models.patient import Patient

    # Seed Doctor B with their own record and supplement
    doc_b = Doctor(doctor_id="doc_b", name="Doctor B", passcode_hash="x")
    db_session.add(doc_b)
    await db_session.flush()

    patient_b = Patient(doctor_id="doc_b", name="Patient B")
    db_session.add(patient_b)
    await db_session.flush()

    rec_b = MedicalRecordDB(
        patient_id=patient_b.id,
        doctor_id="doc_b",
        status="completed",
        seed_source="explicit_interview",
    )
    db_session.add(rec_b)
    await db_session.flush()

    entries_b = [{"field_name": "chief_complaint", "text": "咳嗽",
                  "intake_segment_id": "seg_2", "created_at": "2026-04-25T11:00:00"}]
    sup_b = RecordSupplementDB(
        record_id=rec_b.id,
        status="pending_doctor_review",
        field_entries_json=json.dumps(entries_b),
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(sup_b)

    # Seed Doctor A separately
    _rec_a, sup_a = await _seed_record_and_supplement(db_session, doctor_id="doc_a")
    await db_session.flush()

    # doc_a sees only their supplement
    resp_a = await list_pending(doctor_id="doc_a", session=db_session)
    ids_a = [item["id"] for item in resp_a["items"]]
    assert sup_a.id in ids_a
    assert sup_b.id not in ids_a

    # doc_b sees only their supplement
    resp_b = await list_pending(doctor_id="doc_b", session=db_session)
    ids_b = [item["id"] for item in resp_b["items"]]
    assert sup_b.id in ids_b
    assert sup_a.id not in ids_b


@pytest.mark.asyncio
async def test_accept_404s_for_other_doctors_supplement(db_session):
    """Doctor B cannot accept Doctor A's pending supplement."""
    from db.models.doctor import Doctor

    # Create doctor_b in DB so FK is satisfied (supplement_handlers doesn't validate doctor existence,
    # but we need doc_b to exist for the ownership check to work cleanly)
    doc_b = Doctor(doctor_id="doc_b", name="Doctor B", passcode_hash="x")
    db_session.add(doc_b)
    await db_session.flush()

    # Seed doc_test's record and supplement
    _rec, sup = await _seed_record_and_supplement(db_session, doctor_id="doc_test")

    # doc_b tries to accept doc_test's supplement — must 404
    with pytest.raises(HTTPException) as exc_info:
        await accept(supplement_id=sup.id, doctor_id="doc_b", session=db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_accept_skips_unknown_field_names(db_session):
    """Defense-in-depth: accept ignores field_entries with non-canonical field_name."""
    from db.models.doctor import Doctor
    from db.models.patient import Patient

    doctor = Doctor(doctor_id="doc_whitelist", name="Whitelist Doc", passcode_hash="x")
    db_session.add(doctor)
    await db_session.flush()

    patient = Patient(doctor_id="doc_whitelist", name="Patient W")
    db_session.add(patient)
    await db_session.flush()

    rec = MedicalRecordDB(
        patient_id=patient.id,
        doctor_id="doc_whitelist",
        status="completed",
        seed_source="explicit_interview",
    )
    db_session.add(rec)
    await db_session.flush()

    # One valid entry (chief_complaint) + one non-canonical entry (diagnosis)
    entries = [
        {
            "field_name": "chief_complaint",
            "text": "头痛",
            "intake_segment_id": "seg_1",
            "created_at": "2026-04-25T10:00:00",
        },
        {
            "field_name": "diagnosis",
            "text": "偏头痛",
            "intake_segment_id": "seg_1",
            "created_at": "2026-04-25T10:00:00",
        },
    ]
    sup = RecordSupplementDB(
        record_id=rec.id,
        status="pending_doctor_review",
        field_entries_json=json.dumps(entries),
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add(sup)
    await db_session.flush()

    await accept(supplement_id=sup.id, doctor_id="doc_whitelist", session=db_session)

    fes = (
        await db_session.execute(
            select(FieldEntryDB).where(FieldEntryDB.record_id == rec.id)
        )
    ).scalars().all()

    field_names = [fe.field_name for fe in fes]
    # chief_complaint accepted, diagnosis skipped
    assert "chief_complaint" in field_names
    assert "diagnosis" not in field_names
    assert len(fes) == 1
