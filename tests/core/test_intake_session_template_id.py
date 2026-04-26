"""Template id threading: Doctor.preferred_template_id + IntakeSession CRUD.

The first two tests (Task 3) run against the `db_session` in-memory fixture.
The next three (Task 5) exercise the CRUD helpers which are hardwired to the
real AsyncSessionLocal — those are integration-style tests that touch the
dev DB. Each Task 5 test uses UUID-suffixed IDs to stay idempotent across
runs.
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.patients.intake_session import (
    create_session,
    load_session,
    save_session,
)


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_defaults_to_null(db_session):
    d = Doctor(doctor_id="test_pref_null", name="Test Doctor")
    db_session.add(d)
    await db_session.commit()

    row = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == "test_pref_null")
    )).scalar_one()
    assert row.preferred_template_id is None


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_can_be_set(db_session):
    d = Doctor(
        doctor_id="test_pref_set",
        name="Test Doctor",
        preferred_template_id="medical_general_v1",
    )
    db_session.add(d)
    await db_session.commit()

    row = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == "test_pref_set")
    )).scalar_one()
    assert row.preferred_template_id == "medical_general_v1"


@pytest.mark.asyncio
async def test_create_session_defaults_template_id_to_medical_general_v1():
    doc_id = f"doc_ct_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = await create_session(doctor_id=doc_id, patient_id=None)
    assert session.template_id == "medical_general_v1"

    loaded = await load_session(session.id)
    assert loaded is not None
    assert loaded.template_id == "medical_general_v1"


@pytest.mark.asyncio
async def test_create_session_accepts_explicit_template_id():
    doc_id = f"doc_ex_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = await create_session(
        doctor_id=doc_id,
        patient_id=None,
        template_id="form_satisfaction_v1",
    )
    assert session.template_id == "form_satisfaction_v1"

    loaded = await load_session(session.id)
    assert loaded.template_id == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_save_session_preserves_template_id():
    doc_id = f"doc_sv_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = await create_session(
        doctor_id=doc_id,
        patient_id=None,
        template_id="form_satisfaction_v1",
    )
    session.turn_count = 3
    await save_session(session)

    loaded = await load_session(session.id)
    assert loaded.template_id == "form_satisfaction_v1"
    assert loaded.turn_count == 3


@pytest.mark.asyncio
async def test_prompt_composer_accepts_template_id_kwarg():
    """Passthrough only — Phase 0 doesn't wire template_id into prompt
    selection yet, but the signature must accept it so Phase 1 can plumb
    it without another churn."""
    from agent.prompt_composer import (
        compose_for_doctor_intake, compose_for_patient_intake,
    )

    for fn in (compose_for_doctor_intake, compose_for_patient_intake):
        sig = inspect.signature(fn)
        assert "template_id" in sig.parameters
        assert sig.parameters["template_id"].default == "medical_general_v1"
