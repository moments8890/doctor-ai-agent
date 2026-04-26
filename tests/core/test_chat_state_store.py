"""Tests for ChatSessionState load/serialize via patient_messages snapshot."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.doctor import Doctor
from domain.patient_lifecycle.chat_state import ChatSessionState
from domain.patient_lifecycle.chat_state_store import load_state, serialize_state


pytestmark = pytest.mark.asyncio


async def _seed_doctor_and_patient(session) -> tuple[str, int]:
    """Insert a doctor + patient and return (doctor_id, patient_id)."""
    doctor = Doctor(doctor_id="doc_test_state_store", nickname="t")
    session.add(doctor)
    await session.flush()
    patient = Patient(name="p_test", doctor_id=doctor.doctor_id)
    session.add(patient)
    await session.flush()
    return doctor.doctor_id, patient.id


async def test_load_state_returns_idle_when_no_messages(db_session):
    doctor_id, patient_id = await _seed_doctor_and_patient(db_session)
    state = await load_state(db_session, patient_id)
    assert state.state == "idle"
    assert state.record_id is None
    assert state.intake_segment_id is None


async def test_load_state_returns_parsed_snapshot(db_session):
    doctor_id, patient_id = await _seed_doctor_and_patient(db_session)
    snap = ChatSessionState(
        state="intake",
        record_id=42,
        intake_segment_id="seg-abc",
        last_intake_turn_at_iso="2026-04-25T10:00:00+00:00",
    )
    msg = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content="hi", direction="inbound", source="patient",
        chat_state_snapshot=serialize_state(snap),
    )
    db_session.add(msg)
    await db_session.flush()

    loaded = await load_state(db_session, patient_id)
    assert loaded.state == "intake"
    assert loaded.record_id == 42
    assert loaded.intake_segment_id == "seg-abc"
    assert loaded.last_intake_turn_at_iso == "2026-04-25T10:00:00+00:00"


async def test_load_state_returns_idle_on_corrupt_json(db_session):
    doctor_id, patient_id = await _seed_doctor_and_patient(db_session)
    msg = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content="hi", direction="inbound", source="patient",
        chat_state_snapshot="not valid json {{{",
    )
    db_session.add(msg)
    await db_session.flush()

    loaded = await load_state(db_session, patient_id)
    assert loaded.state == "idle"
    assert loaded.cancellation_reason is None


async def test_load_state_skips_legacy_null_snapshot_rows(db_session):
    doctor_id, patient_id = await _seed_doctor_and_patient(db_session)
    # Legacy: no snapshot at all.
    legacy = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content="legacy turn", direction="inbound", source="patient",
        chat_state_snapshot=None,
    )
    db_session.add(legacy)
    await db_session.flush()

    loaded = await load_state(db_session, patient_id)
    assert loaded.state == "idle"


async def test_load_state_returns_most_recent_snapshot(db_session):
    """If multiple snapshots exist, the latest (by created_at) wins."""
    doctor_id, patient_id = await _seed_doctor_and_patient(db_session)
    older = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content="older", direction="inbound", source="patient",
        chat_state_snapshot=serialize_state(ChatSessionState(state="intake", record_id=1)),
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    newer = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content="newer", direction="inbound", source="patient",
        chat_state_snapshot=serialize_state(ChatSessionState(state="qa_window", record_id=2)),
        created_at=datetime.utcnow(),
    )
    db_session.add(older)
    db_session.add(newer)
    await db_session.flush()

    loaded = await load_state(db_session, patient_id)
    assert loaded.state == "qa_window"
    assert loaded.record_id == 2


async def test_serialize_state_roundtrips_all_fields():
    state = ChatSessionState(
        state="intake",
        record_id=99,
        intake_segment_id="seg-xyz",
        last_intake_turn_at_iso="2026-04-25T11:11:11+00:00",
        qa_window_entered_at_iso=None,
        cancellation_reason=None,
    )
    raw = serialize_state(state)
    parsed = json.loads(raw)
    assert parsed["state"] == "intake"
    assert parsed["record_id"] == 99
    assert parsed["intake_segment_id"] == "seg-xyz"
    # All ChatSessionState fields appear in the dict (dataclasses.asdict)
    assert "qa_window_entered_at_iso" in parsed
    assert "cancellation_reason" in parsed
