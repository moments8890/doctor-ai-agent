"""Tests for db/crud.py — all run against an in-memory SQLite database."""
import pytest
from datetime import datetime
from db.crud import (
    create_patient,
    find_patient_by_name,
    save_record,
    get_records_for_patient,
    get_all_records_for_doctor,
)
from models.medical_record import MedicalRecord

DOCTOR = "doc_001"

SAMPLE_RECORD = MedicalRecord(
    chief_complaint="头痛两天",
    history_of_present_illness="患者两天前出现持续性头痛",
    diagnosis="紧张性头痛",
    treatment_plan="口服布洛芬 400mg，每日三次",
)


# ---------------------------------------------------------------------------
# create_patient
# ---------------------------------------------------------------------------


async def test_create_patient_returns_row_with_id(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    assert patient.id is not None
    assert patient.name == "李明"
    assert patient.gender == "男"
    assert patient.year_of_birth == datetime.now().year - 45
    assert patient.doctor_id == DOCTOR


async def test_create_patient_optional_fields_none(db_session):
    patient = await create_patient(db_session, DOCTOR, "张三", None, None)
    assert patient.gender is None
    assert patient.year_of_birth is None


async def test_create_patient_different_doctors_isolated(db_session):
    p1 = await create_patient(db_session, "doc_A", "王五", None, None)
    p2 = await create_patient(db_session, "doc_B", "王五", None, None)
    assert p1.id != p2.id


# ---------------------------------------------------------------------------
# find_patient_by_name
# ---------------------------------------------------------------------------


async def test_find_patient_by_name_found(db_session):
    await create_patient(db_session, DOCTOR, "李明", "男", 45)
    found = await find_patient_by_name(db_session, DOCTOR, "李明")
    assert found is not None
    assert found.name == "李明"


async def test_find_patient_by_name_not_found(db_session):
    result = await find_patient_by_name(db_session, DOCTOR, "不存在的人")
    assert result is None


async def test_find_patient_by_name_different_doctor_returns_none(db_session):
    await create_patient(db_session, "doc_A", "李明", None, None)
    result = await find_patient_by_name(db_session, "doc_B", "李明")
    assert result is None


# ---------------------------------------------------------------------------
# save_record
# ---------------------------------------------------------------------------


async def test_save_record_with_patient(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    record = await save_record(db_session, DOCTOR, SAMPLE_RECORD, patient.id)
    assert record.id is not None
    assert record.patient_id == patient.id
    assert record.doctor_id == DOCTOR
    assert record.chief_complaint == "头痛两天"
    assert record.diagnosis == "紧张性头痛"


async def test_save_record_without_patient(db_session):
    record = await save_record(db_session, DOCTOR, SAMPLE_RECORD, patient_id=None)
    assert record.id is not None
    assert record.patient_id is None


async def test_save_record_optional_fields_preserved(db_session):
    rich = MedicalRecord(
        chief_complaint="咳嗽",
        history_of_present_illness="三天咳嗽",
        past_medical_history="无",
        physical_examination="双肺呼吸音清",
        auxiliary_examinations="胸片正常",
        diagnosis="上呼吸道感染",
        treatment_plan="多休息，多喝水",
        follow_up_plan="一周后复诊",
    )
    record = await save_record(db_session, DOCTOR, rich, patient_id=None)
    assert record.past_medical_history == "无"
    assert record.follow_up_plan == "一周后复诊"


# ---------------------------------------------------------------------------
# get_records_for_patient
# ---------------------------------------------------------------------------


async def test_get_records_returns_most_recent_first(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(3):
        rec = MedicalRecord(
            chief_complaint=f"主诉{i}",
            history_of_present_illness="现病史",
            diagnosis=f"诊断{i}",
            treatment_plan="治疗",
        )
        await save_record(db_session, DOCTOR, rec, patient.id)

    records = await get_records_for_patient(db_session, DOCTOR, patient.id)
    assert len(records) == 3
    # Most recent (last inserted) should come first
    assert records[0].chief_complaint == "主诉2"


async def test_get_records_respects_limit(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(6):
        rec = MedicalRecord(
            chief_complaint=f"主诉{i}",
            history_of_present_illness="现病史",
            diagnosis="诊断",
            treatment_plan="治疗",
        )
        await save_record(db_session, DOCTOR, rec, patient.id)

    records = await get_records_for_patient(db_session, DOCTOR, patient.id, limit=3)
    assert len(records) == 3


async def test_get_records_returns_empty_for_no_records(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    records = await get_records_for_patient(db_session, DOCTOR, patient.id)
    assert records == []


async def test_get_records_isolated_by_doctor(db_session):
    p_a = await create_patient(db_session, "doc_A", "李明", None, None)
    await save_record(db_session, "doc_A", SAMPLE_RECORD, p_a.id)

    # doc_B querying doc_A's patient_id returns nothing
    records = await get_records_for_patient(db_session, "doc_B", p_a.id)
    assert records == []


# ---------------------------------------------------------------------------
# get_all_records_for_doctor
# ---------------------------------------------------------------------------


async def test_get_all_records_returns_records_across_patients(db_session):
    p1 = await create_patient(db_session, DOCTOR, "李明", None, None)
    p2 = await create_patient(db_session, DOCTOR, "王芳", None, None)

    rec1 = MedicalRecord(chief_complaint="头痛", history_of_present_illness="两天头痛", diagnosis="紧张性头痛", treatment_plan="布洛芬")
    rec2 = MedicalRecord(chief_complaint="咳嗽", history_of_present_illness="三天咳嗽", diagnosis="上呼吸道感染", treatment_plan="多休息")
    await save_record(db_session, DOCTOR, rec1, p1.id)
    await save_record(db_session, DOCTOR, rec2, p2.id)

    records = await get_all_records_for_doctor(db_session, DOCTOR)
    assert len(records) == 2
    patient_names = {r.patient.name for r in records}
    assert patient_names == {"李明", "王芳"}


async def test_get_all_records_most_recent_first(db_session):
    p = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(3):
        await save_record(db_session, DOCTOR, MedicalRecord(
            chief_complaint=f"主诉{i}", history_of_present_illness="现病史", diagnosis=f"诊断{i}", treatment_plan="治疗"
        ), p.id)

    records = await get_all_records_for_doctor(db_session, DOCTOR)
    assert records[0].chief_complaint == "主诉2"


async def test_get_all_records_respects_limit(db_session):
    p = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(6):
        await save_record(db_session, DOCTOR, MedicalRecord(
            chief_complaint=f"主诉{i}", history_of_present_illness="现病史", diagnosis="诊断", treatment_plan="治疗"
        ), p.id)

    records = await get_all_records_for_doctor(db_session, DOCTOR, limit=3)
    assert len(records) == 3


async def test_get_all_records_empty_when_no_records(db_session):
    records = await get_all_records_for_doctor(db_session, DOCTOR)
    assert records == []


async def test_get_all_records_isolated_by_doctor(db_session):
    p = await create_patient(db_session, "doc_A", "李明", None, None)
    await save_record(db_session, "doc_A", SAMPLE_RECORD, p.id)

    records = await get_all_records_for_doctor(db_session, "doc_B")
    assert records == []


# ---------------------------------------------------------------------------
# Category fields stamped on create and save
# ---------------------------------------------------------------------------


async def test_create_patient_stamps_category_new(db_session):
    patient = await create_patient(db_session, DOCTOR, "新患者", None, None)
    assert patient.primary_category == "new"
    assert patient.category_tags == "[]"
    assert patient.category_rules_version == "v1"
    assert patient.category_computed_at is not None
    assert patient.primary_risk_level == "low"
    assert patient.risk_tags == '["no_records"]'
    assert patient.follow_up_state == "not_needed"
    assert patient.risk_rules_version == "risk-v1"


async def test_save_record_triggers_category_recompute(db_session):
    """After saving a record, the patient's primary_category must be recomputed."""
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    assert patient.primary_category == "new"

    record = MedicalRecord(
        chief_complaint="头痛",
        history_of_present_illness="两天头痛",
        diagnosis="紧张性头痛",
        treatment_plan="布洛芬",
        follow_up_plan="两周后复诊",
    )
    await save_record(db_session, DOCTOR, record, patient.id)

    # Refresh patient from DB
    from sqlalchemy import select
    from db.models import Patient
    result = await db_session.execute(select(Patient).where(Patient.id == patient.id))
    refreshed = result.scalar_one()

    # With a fresh record and follow_up_plan, should now be active_followup
    assert refreshed.primary_category == "active_followup"
    assert refreshed.category_computed_at is not None


async def test_save_record_creates_auto_followup_task_when_enabled(db_session, monkeypatch):
    from sqlalchemy import select
    from db.models import DoctorTask

    monkeypatch.setenv("AUTO_FOLLOWUP_TASKS_ENABLED", "true")
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    record = MedicalRecord(
        chief_complaint="头晕",
        history_of_present_illness="两天头晕",
        diagnosis="高血压",
        treatment_plan="口服降压药",
        follow_up_plan="两周后复诊",
    )

    db_record = await save_record(db_session, DOCTOR, record, patient.id)
    result = await db_session.execute(
        select(DoctorTask).where(
            DoctorTask.doctor_id == DOCTOR,
            DoctorTask.record_id == db_record.id,
            DoctorTask.task_type == "follow_up",
        )
    )
    task = result.scalar_one_or_none()
    assert task is not None
    assert task.trigger_source == "risk_engine"
    assert "risk_level=" in (task.trigger_reason or "")
