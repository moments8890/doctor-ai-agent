"""FormResponseWriter — persists form template output to form_responses."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient
from domain.intake.protocols import PersistRef, SessionState
from domain.intake.writers import FormResponseWriter


def _session(doctor_id, patient_id, template_id="form_satisfaction_v1"):
    return SessionState(
        id=f"s_{uuid.uuid4().hex[:8]}",
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode="patient",
        status="active",
        template_id=template_id,
        collected={},
        conversation=[],
        turn_count=1,
    )


@pytest.mark.asyncio
async def test_persist_inserts_form_response_row():
    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="张三")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doc_id, pid)
    collected = {
        "overall_rating": "满意",
        "doctor_rating": "非常满意",
        "comments": "医生很耐心",
    }
    ref = await writer.persist(session, collected)

    assert isinstance(ref, PersistRef)
    assert ref.kind == "form_response"

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.id == ref.id)
        )).scalar_one()
    assert row.doctor_id == doc_id
    assert row.patient_id == pid
    assert row.template_id == "form_satisfaction_v1"
    assert row.payload["overall_rating"] == "满意"
    assert row.payload["comments"] == "医生很耐心"
    assert row.status == "draft"


@pytest.mark.asyncio
async def test_persist_links_session_id():
    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="李四")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doc_id, pid)
    ref = await writer.persist(session, {"overall_rating": "一般"})

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.id == ref.id)
        )).scalar_one()
    assert row.session_id == session.id


@pytest.mark.asyncio
async def test_persist_requires_patient_id():
    from fastapi import HTTPException
    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doc_id, None)
    with pytest.raises(HTTPException) as excinfo:
        await writer.persist(session, {"overall_rating": "满意"})
    assert excinfo.value.status_code == 422
