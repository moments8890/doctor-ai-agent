"""FormResponseDB ORM smoke test — round-trip a row through SQLAlchemy."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient


@pytest.mark.asyncio
async def test_form_response_round_trip(db_session):
    """Verify FormResponseDB can be persisted and retrieved with correct defaults."""
    # Setup: create doctor and patient
    d = Doctor(doctor_id="doc_fr", name="Test Doctor")
    db_session.add(d)
    await db_session.flush()

    p = Patient(doctor_id="doc_fr", name="王五")
    db_session.add(p)
    await db_session.commit()
    patient_id = p.id

    # Insert: create a form response
    fr = FormResponseDB(
        doctor_id="doc_fr",
        patient_id=patient_id,
        template_id="form_satisfaction_v1",
        payload={"q1": "5", "q2": "very good"},
    )
    db_session.add(fr)
    await db_session.commit()
    fr_id = fr.id

    # Retrieve: verify round-trip and defaults
    fetched = (await db_session.execute(
        select(FormResponseDB).where(FormResponseDB.id == fr_id)
    )).scalar_one()

    assert fetched.template_id == "form_satisfaction_v1"
    assert fetched.payload == {"q1": "5", "q2": "very good"}
    assert fetched.status == "draft"  # server_default
    assert fetched.session_id is None
