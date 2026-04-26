"""Tests for the new-patient detection endpoints.

Load-bearing checks:
- unseen-count only counts patients in the last 24h with NULL first_doctor_view_at
- mark-viewed is idempotent (first call wins, second is a no-op)
- Cross-doctor mark-viewed returns 404 (NOT 403) — no existence oracle
- Cross-doctor unseen-count is doctor-scoped (other doctors' patients ignored)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from db.models.doctor import Doctor
from db.models.patient import Patient
from channels.web.doctor_dashboard.new_patient_handlers import (
    mark_patient_viewed,
    unseen_patient_count,
)


@pytest.mark.asyncio
async def test_unseen_count_zero_when_no_new_patients(db_session):
    db_session.add(Doctor(doctor_id="doc_a", name="Dr A"))
    await db_session.flush()
    result = await unseen_patient_count(doctor_id="doc_a", authorization=None, db=db_session)
    assert result == {"count": 0}


@pytest.mark.asyncio
async def test_unseen_count_excludes_already_viewed(db_session):
    db_session.add(Doctor(doctor_id="doc_b", name="Dr B"))
    db_session.add(Patient(
        id=10, doctor_id="doc_b", name="viewed",
        created_at=datetime.utcnow() - timedelta(hours=2),
        first_doctor_view_at=datetime.utcnow() - timedelta(hours=1),
    ))
    db_session.add(Patient(
        id=11, doctor_id="doc_b", name="unviewed",
        created_at=datetime.utcnow() - timedelta(hours=2),
        first_doctor_view_at=None,
    ))
    await db_session.flush()
    result = await unseen_patient_count(doctor_id="doc_b", authorization=None, db=db_session)
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_unseen_count_excludes_patients_older_than_24h(db_session):
    """Stale unviewed patients (created > 24h ago) are NOT counted as 'new'.
    Prevents a dropped mark-viewed POST from stranding the badge forever.
    """
    db_session.add(Doctor(doctor_id="doc_c", name="Dr C"))
    db_session.add(Patient(
        id=20, doctor_id="doc_c", name="stale",
        created_at=datetime.utcnow() - timedelta(hours=25),
        first_doctor_view_at=None,
    ))
    db_session.add(Patient(
        id=21, doctor_id="doc_c", name="fresh",
        created_at=datetime.utcnow() - timedelta(minutes=30),
        first_doctor_view_at=None,
    ))
    await db_session.flush()
    result = await unseen_patient_count(doctor_id="doc_c", authorization=None, db=db_session)
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_unseen_count_isolates_doctors(db_session):
    """Doctor A's count never includes Doctor B's unviewed patients."""
    db_session.add(Doctor(doctor_id="doc_d", name="Dr D"))
    db_session.add(Doctor(doctor_id="doc_e", name="Dr E"))
    db_session.add(Patient(
        id=30, doctor_id="doc_e", name="other",
        created_at=datetime.utcnow() - timedelta(minutes=10),
        first_doctor_view_at=None,
    ))
    await db_session.flush()
    result = await unseen_patient_count(doctor_id="doc_d", authorization=None, db=db_session)
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_mark_viewed_sets_timestamp_when_null(db_session):
    db_session.add(Doctor(doctor_id="doc_f", name="Dr F"))
    db_session.add(Patient(
        id=40, doctor_id="doc_f", name="p",
        created_at=datetime.utcnow(),
        first_doctor_view_at=None,
    ))
    await db_session.flush()

    result = await mark_patient_viewed(patient_id=40, doctor_id="doc_f", authorization=None, db=db_session)
    assert result == {"id": 40, "first_doctor_view_at_set": True}

    refreshed = (await db_session.execute(
        select(Patient).where(Patient.id == 40)
    )).scalar_one()
    assert refreshed.first_doctor_view_at is not None


@pytest.mark.asyncio
async def test_mark_viewed_is_idempotent(db_session):
    """Second call doesn't overwrite the first timestamp."""
    db_session.add(Doctor(doctor_id="doc_g", name="Dr G"))
    earlier = datetime.utcnow() - timedelta(hours=3)
    db_session.add(Patient(
        id=50, doctor_id="doc_g", name="p",
        created_at=datetime.utcnow() - timedelta(hours=4),
        first_doctor_view_at=earlier,
    ))
    await db_session.flush()

    result = await mark_patient_viewed(patient_id=50, doctor_id="doc_g", authorization=None, db=db_session)
    assert result == {"id": 50, "first_doctor_view_at_set": False}

    refreshed = (await db_session.execute(
        select(Patient).where(Patient.id == 50)
    )).scalar_one()
    # Allow a few microseconds of jitter from SQLite datetime round-trip.
    assert abs((refreshed.first_doctor_view_at - earlier).total_seconds()) < 1


@pytest.mark.asyncio
async def test_mark_viewed_cross_doctor_returns_404(db_session):
    """Doctor A cannot mark Doctor B's patient as viewed. 404 'Patient not
    found' — same envelope whether the patient doesn't exist OR belongs to
    a different doctor (no existence oracle across the doctor boundary).
    """
    db_session.add(Doctor(doctor_id="doc_h", name="Dr H"))
    db_session.add(Doctor(doctor_id="doc_i", name="Dr I"))
    db_session.add(Patient(
        id=60, doctor_id="doc_i", name="not_yours",
        created_at=datetime.utcnow(),
        first_doctor_view_at=None,
    ))
    await db_session.flush()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await mark_patient_viewed(patient_id=60, doctor_id="doc_h", authorization=None, db=db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_viewed_unknown_patient_returns_404(db_session):
    """Same envelope for non-existent patient ID."""
    db_session.add(Doctor(doctor_id="doc_j", name="Dr J"))
    await db_session.flush()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await mark_patient_viewed(patient_id=99999, doctor_id="doc_j", authorization=None, db=db_session)
    assert exc.value.status_code == 404
