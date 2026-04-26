"""MedicalRecordWriter.persist — generic column-mapping regression tests.

Task 2 (Phase 4 r2): the writer must map any `collected` key whose name
matches a MedicalRecordDB column to that column, without the writer
hand-naming each column. This lets specialty variants (e.g. medical_neuro_v1)
introduce new FieldSpec + column pairs without modifying the writer.

Covers:
- Representative medical_general_v1 fields still round-trip (chief_complaint,
  past_history, treatment_plan).
- Neuro extras (onset_time, neuro_exam, vascular_risk_factors) land on the
  corresponding columns after Task 1 added them to the schema.
- Underscore-prefixed metadata keys are ignored (not written, don't raise).
- Unknown keys in `collected` that don't map to any column are silently
  ignored.
- status derivation (completed vs pending_review) is unchanged by the
  refactor.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from domain.intake.protocols import SessionState
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


async def _seed_doctor_and_patient(name: str = "测试患者") -> tuple[str, int]:
    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name=name)
        db.add(patient)
        await db.commit()
        pid = patient.id
    return doc_id, pid


async def _fetch_record(record_id: int) -> MedicalRecordDB:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_writer_maps_representative_medical_general_fields():
    """Existing medical_general_v1 fields still round-trip after refactor."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("张三")
    session = _session(doctor_id=doc_id, patient_id=pid)

    collected = {
        "chief_complaint": "腹痛3天",
        "past_history": "高血压10年",
        "treatment_plan": "口服蒙脱石散",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.chief_complaint == "腹痛3天"
    assert row.past_history == "高血压10年"
    assert row.treatment_plan == "口服蒙脱石散"


@pytest.mark.asyncio
async def test_writer_maps_neuro_fields_to_new_columns():
    """Neuro extras flow through to onset_time / neuro_exam /
    vascular_risk_factors columns without any writer changes."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("李四")
    session = _session(doctor_id=doc_id, patient_id=pid)

    collected = {
        "chief_complaint": "左侧肢体无力",
        "onset_time": "2小时前",
        "neuro_exam": "GCS 15，左上肢肌力3级",
        "vascular_risk_factors": "高血压10年",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.chief_complaint == "左侧肢体无力"
    assert row.onset_time == "2小时前"
    assert row.neuro_exam == "GCS 15，左上肢肌力3级"
    assert row.vascular_risk_factors == "高血压10年"


@pytest.mark.asyncio
async def test_writer_ignores_underscore_prefixed_keys():
    """Engine-level metadata like _patient_name must not be written to the
    record row (and must not raise an ORM error)."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("王五")
    session = _session(doctor_id=doc_id, patient_id=pid)

    collected = {
        "chief_complaint": "头晕",
        "_patient_name": "王五",
        "_patient_gender": "男",
        "_patient_age": "60岁",
        "_some_other_meta": "ignore me",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.chief_complaint == "头晕"
    # No exception raised = implicit pass for "underscore keys ignored".


@pytest.mark.asyncio
async def test_writer_silently_ignores_unknown_collected_keys():
    """Keys that don't correspond to any MedicalRecordDB column are dropped
    — no error, no data loss on the fields that do map."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("赵六")
    session = _session(doctor_id=doc_id, patient_id=pid)

    collected = {
        "chief_complaint": "咳嗽",
        "totally_unknown_field": "nope",
        "another_phantom_field": "still nope",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.chief_complaint == "咳嗽"
    assert not hasattr(row, "totally_unknown_field")


@pytest.mark.asyncio
async def test_writer_status_completed_when_all_three_set():
    """Status derivation unchanged: diagnosis + treatment_plan +
    orders_followup all set → completed."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("钱七")
    session = _session(doctor_id=doc_id, patient_id=pid)

    collected = {
        "chief_complaint": "发热",
        "diagnosis": "上呼吸道感染",
        "treatment_plan": "对症治疗",
        "orders_followup": "3天后复诊",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.status == "completed"


@pytest.mark.asyncio
async def test_writer_status_pending_review_when_any_missing():
    """Status derivation unchanged: missing any of diagnosis /
    treatment_plan / orders_followup → pending_review."""
    writer = MedicalRecordWriter()
    doc_id, pid = await _seed_doctor_and_patient("孙八")
    session = _session(doctor_id=doc_id, patient_id=pid)

    # diagnosis + treatment_plan set, orders_followup missing
    collected = {
        "chief_complaint": "腹泻",
        "diagnosis": "急性胃肠炎",
        "treatment_plan": "补液",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)

    assert row.status == "pending_review"
