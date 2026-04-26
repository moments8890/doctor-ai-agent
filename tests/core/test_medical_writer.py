"""MedicalRecordWriter.persist — integration test against real SQLite.

Uses UUID-suffixed doctor/patient ids for idempotency across runs.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from domain.intake.protocols import PersistRef, SessionState
from domain.intake.templates.medical_general import MedicalRecordWriter


def _session(**over) -> SessionState:
    defaults = dict(
        id=f"s_{uuid.uuid4().hex[:8]}",
        doctor_id=f"doc_{uuid.uuid4().hex[:8]}",
        patient_id=None,
        mode="doctor",
        status="active",
        template_id="medical_general_v1",
        collected={},
        conversation=[],
        turn_count=1,
    )
    defaults.update(over)
    return SessionState(**defaults)


@pytest.mark.asyncio
async def test_persist_with_existing_patient_id_inserts_record():
    writer = MedicalRecordWriter()

    # Seed doctor + patient
    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="张三")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doctor_id=doc_id, patient_id=pid)
    collected = {
        "chief_complaint": "头痛",
        "present_illness": "3天",
        "diagnosis": "偏头痛",
        "treatment_plan": "布洛芬",
        "orders_followup": "1周后复诊",
    }
    ref = await writer.persist(session, collected)

    assert isinstance(ref, PersistRef)
    assert ref.kind == "medical_record"

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
    assert row.chief_complaint == "头痛"
    assert row.diagnosis == "偏头痛"
    assert row.status == "completed"  # all three of diag/treat/followup set


@pytest.mark.asyncio
async def test_persist_with_missing_all_plans_is_pending_review():
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="李四")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doctor_id=doc_id, patient_id=pid)
    ref = await writer.persist(session, {"chief_complaint": "咳嗽"})

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
    assert row.status == "pending_review"


@pytest.mark.asyncio
async def test_persist_deferred_patient_creation():
    """When session.patient_id is None, writer creates a patient row from
    collected["_patient_name"] (and optional gender/age)."""
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doctor_id=doc_id, patient_id=None)
    collected = {
        "_patient_name": "王五",
        "_patient_gender": "男",
        "_patient_age": "58岁",
        "chief_complaint": "胸闷",
    }
    ref = await writer.persist(session, collected)

    # Patient row should now exist
    async with AsyncSessionLocal() as db:
        record = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
        patient = (await db.execute(
            select(Patient).where(Patient.id == record.patient_id)
        )).scalar_one()
    assert patient.name == "王五"


@pytest.mark.asyncio
async def test_persist_raises_422_when_no_patient_name():
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doctor_id=doc_id, patient_id=None)
    with pytest.raises(HTTPException) as excinfo:
        await writer.persist(session, {"chief_complaint": "x"})
    assert excinfo.value.status_code == 422
    assert "姓名" in str(excinfo.value.detail)
