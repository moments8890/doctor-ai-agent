"""
Tests for db/crud.py — all run against an in-memory SQLite database.
"""

import pytest
from datetime import datetime
from sqlalchemy import select
from db.crud import (
    create_patient,
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_neuro_cases_for_doctor,
    save_record,
    save_neuro_case,
    get_records_for_patient,
    get_all_records_for_doctor,
    create_label,
    get_labels_for_doctor,
    update_label,
    delete_label,
    assign_label,
    remove_label,
    get_patient_labels,
)
from db.models import Doctor, DoctorTask, NeuroCaseDB
from db.models.medical_record import MedicalRecord
from db.models.neuro_case import ExtractionLog, NeuroCase
from utils.errors import InvalidMedicalRecordError
from utils.errors import LabelNotFoundError
from utils.errors import PatientNotFoundError

DOCTOR = "doc_001"

SAMPLE_RECORD = MedicalRecord(
    content="头痛两天。患者两天前出现持续性头痛，诊断紧张性头痛，口服布洛芬 400mg，每日三次。",
    tags=["紧张性头痛"],
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


async def test_create_patient_wechat_identifier_backfills_doctor_identity(db_session):
    wechat_doctor = "wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ"
    await create_patient(db_session, wechat_doctor, "王五", None, None)

    row = (await db_session.execute(select(Doctor).where(Doctor.doctor_id == wechat_doctor))).scalar_one_or_none()
    assert row is not None
    assert row.channel == "wechat"
    assert row.wechat_user_id == wechat_doctor


async def test_create_patient_invalid_name_raises(db_session):
    with pytest.raises(InvalidMedicalRecordError):
        await create_patient(db_session, DOCTOR, "   ", "男", 45)


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
    assert "头痛两天" in record.content


async def test_save_record_without_patient(db_session):
    record = await save_record(db_session, DOCTOR, SAMPLE_RECORD, patient_id=None)
    assert record.id is not None
    assert record.patient_id is None


async def test_save_record_optional_fields_preserved(db_session):
    rich = MedicalRecord(
        content="咳嗽三天，既往史无，双肺呼吸音清，胸片正常，诊断上呼吸道感染，多休息多喝水，一周后复诊。",
        tags=["上呼吸道感染"],
    )
    record = await save_record(db_session, DOCTOR, rich, patient_id=None)
    assert "上呼吸道感染" in record.content


# ---------------------------------------------------------------------------
# get_records_for_patient
# ---------------------------------------------------------------------------


async def test_get_records_returns_most_recent_first(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(3):
        rec = MedicalRecord(
            content=f"主诉{i} 现病史 诊断{i} 治疗",
            tags=[f"诊断{i}"],
        )
        await save_record(db_session, DOCTOR, rec, patient.id)

    records = await get_records_for_patient(db_session, DOCTOR, patient.id)
    assert len(records) == 3
    # Most recent (last inserted) should come first
    assert "主诉2" in records[0].content


async def test_get_records_respects_limit(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(6):
        rec = MedicalRecord(
            content=f"主诉{i} 现病史 诊断 治疗",
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

    rec1 = MedicalRecord(content="头痛 两天头痛 紧张性头痛 布洛芬", tags=["紧张性头痛"])
    rec2 = MedicalRecord(content="咳嗽 三天咳嗽 上呼吸道感染 多休息", tags=["上呼吸道感染"])
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
            content=f"主诉{i} 现病史 诊断{i} 治疗"
        ), p.id)

    records = await get_all_records_for_doctor(db_session, DOCTOR)
    assert "主诉2" in records[0].content


async def test_get_all_records_respects_limit(db_session):
    p = await create_patient(db_session, DOCTOR, "李明", None, None)
    for i in range(6):
        await save_record(db_session, DOCTOR, MedicalRecord(
            content=f"主诉{i} 现病史 诊断 治疗"
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
    assert patient.primary_risk_level == "low"
    assert patient.risk_tags == '["no_records"]'
    assert patient.follow_up_state == "not_needed"


async def test_save_record_triggers_category_recompute(db_session):
    """After saving a record, the patient's primary_category must be recomputed."""
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    assert patient.primary_category == "new"

    record = MedicalRecord(
        content="头痛 两天头痛 紧张性头痛 布洛芬 两周后复诊",
        tags=["紧张性头痛", "两周后复诊"],
    )
    await save_record(db_session, DOCTOR, record, patient.id)

    # Refresh patient from DB
    from sqlalchemy import select
    from db.models import Patient
    result = await db_session.execute(select(Patient).where(Patient.id == patient.id))
    refreshed = result.scalar_one()

    # With a fresh record and follow_up tag, should now be active_followup
    assert refreshed.primary_category == "active_followup"


async def test_save_record_creates_auto_followup_task_when_enabled(db_session, monkeypatch):
    from sqlalchemy import select
    from db.models import DoctorTask

    monkeypatch.setenv("AUTO_FOLLOWUP_TASKS_ENABLED", "true")
    patient = await create_patient(db_session, DOCTOR, "李明", "男", 45)
    record = MedicalRecord(
        content="头晕 两天头晕 高血压 口服降压药 两周后复诊",
        tags=["高血压", "两周后复诊"],
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


# ---------------------------------------------------------------------------
# Label management
# ---------------------------------------------------------------------------


async def test_create_and_list_labels(db_session):
    await create_label(db_session, DOCTOR, "转诊候选", "#FF4444")
    await create_label(db_session, DOCTOR, "重点随访", "#4444FF")
    labels = await get_labels_for_doctor(db_session, DOCTOR)
    assert len(labels) == 2
    assert labels[0].name == "转诊候选"
    assert labels[1].name == "重点随访"


async def test_create_label_default_color_is_none(db_session):
    label = await create_label(db_session, DOCTOR, "无颜色标签")
    assert label.color is None
    assert label.id is not None


async def test_update_label_name(db_session):
    label = await create_label(db_session, DOCTOR, "旧名称")
    updated = await update_label(db_session, label.id, DOCTOR, name="新名称")
    assert updated is not None
    assert updated.name == "新名称"


async def test_update_label_color(db_session):
    label = await create_label(db_session, DOCTOR, "标签", "#111111")
    updated = await update_label(db_session, label.id, DOCTOR, color="#AABBCC")
    assert updated is not None
    assert updated.color == "#AABBCC"
    assert updated.name == "标签"


async def test_delete_label(db_session):
    label = await create_label(db_session, DOCTOR, "待删除")
    result = await delete_label(db_session, label.id, DOCTOR)
    assert result is True
    remaining = await get_labels_for_doctor(db_session, DOCTOR)
    assert len(remaining) == 0


async def test_delete_label_wrong_doctor_returns_false(db_session):
    label = await create_label(db_session, DOCTOR, "某标签")
    result = await delete_label(db_session, label.id, "other_doctor")
    assert result is False
    labels = await get_labels_for_doctor(db_session, DOCTOR)
    assert len(labels) == 1


async def test_assign_label_to_patient(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    label = await create_label(db_session, DOCTOR, "重点随访")
    await assign_label(db_session, patient.id, label.id, DOCTOR)
    assigned = await get_patient_labels(db_session, patient.id, DOCTOR)
    assert len(assigned) == 1
    assert assigned[0].name == "重点随访"


async def test_assign_label_idempotent(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    label = await create_label(db_session, DOCTOR, "重点随访")
    await assign_label(db_session, patient.id, label.id, DOCTOR)
    await assign_label(db_session, patient.id, label.id, DOCTOR)
    assigned = await get_patient_labels(db_session, patient.id, DOCTOR)
    assert len(assigned) == 1


async def test_remove_label_from_patient(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    label = await create_label(db_session, DOCTOR, "转诊候选")
    await assign_label(db_session, patient.id, label.id, DOCTOR)
    await remove_label(db_session, patient.id, label.id, DOCTOR)
    remaining = await get_patient_labels(db_session, patient.id, DOCTOR)
    assert remaining == []


async def test_delete_label_removes_from_patient(db_session):
    patient = await create_patient(db_session, DOCTOR, "李明", None, None)
    label = await create_label(db_session, DOCTOR, "待删除标签")
    await assign_label(db_session, patient.id, label.id, DOCTOR)
    await delete_label(db_session, label.id, DOCTOR)
    remaining = await get_patient_labels(db_session, patient.id, DOCTOR)
    assert remaining == []


async def test_label_doctor_isolation(db_session):
    p_a = await create_patient(db_session, "doc_A", "张三", None, None)
    await create_label(db_session, "doc_A", "标签A")
    label_b = await create_label(db_session, "doc_B", "标签B")

    with pytest.raises(LabelNotFoundError):
        await assign_label(db_session, p_a.id, label_b.id, "doc_A")

    assert await get_patient_labels(db_session, p_a.id, "doc_A") == []
    b_labels = await get_labels_for_doctor(db_session, "doc_B")
    assert all(lbl.doctor_id == "doc_B" for lbl in b_labels)


async def test_assign_label_missing_patient_raises_patient_not_found(db_session):
    label = await create_label(db_session, DOCTOR, "标签A")
    with pytest.raises(PatientNotFoundError):
        await assign_label(db_session, patient_id=999999, label_id=label.id, doctor_id=DOCTOR)


async def test_remove_label_missing_patient_raises_patient_not_found(db_session):
    label = await create_label(db_session, DOCTOR, "标签B")
    with pytest.raises(PatientNotFoundError):
        await remove_label(db_session, patient_id=999999, label_id=label.id, doctor_id=DOCTOR)


async def test_find_patients_by_exact_name_returns_latest_first(db_session):
    p1 = await create_patient(db_session, DOCTOR, "章三", "男", 30)
    p2 = await create_patient(db_session, DOCTOR, "章三", "男", 29)
    matches = await find_patients_by_exact_name(db_session, DOCTOR, "章三")
    assert [p.id for p in matches] == [p2.id, p1.id]


async def test_delete_patient_for_doctor_removes_related_rows(db_session):
    from sqlalchemy import select
    from db.models import DoctorSessionState, MedicalRecordDB

    patient = await create_patient(db_session, DOCTOR, "待删除患者", None, None)
    await save_record(db_session, DOCTOR, SAMPLE_RECORD, patient.id)
    db_session.add(DoctorTask(doctor_id=DOCTOR, patient_id=patient.id, task_type="follow_up", title="随访", status="pending"))
    db_session.add(NeuroCaseDB(doctor_id=DOCTOR, patient_id=patient.id, patient_name="待删除患者"))
    db_session.add(DoctorSessionState(doctor_id=DOCTOR, current_patient_id=patient.id, pending_create_name=None))
    await db_session.commit()

    deleted = await delete_patient_for_doctor(db_session, DOCTOR, patient.id)
    assert deleted is not None
    assert deleted.id == patient.id

    assert await find_patient_by_name(db_session, DOCTOR, "待删除患者") is None
    records = (await db_session.execute(select(MedicalRecordDB).where(MedicalRecordDB.patient_id == patient.id))).scalars().all()
    assert records == []
    tasks = (await db_session.execute(select(DoctorTask).where(DoctorTask.patient_id == patient.id))).scalars().all()
    assert tasks == []
    neuro_rows = (await db_session.execute(select(NeuroCaseDB).where(NeuroCaseDB.patient_id == patient.id))).scalars().all()
    assert neuro_rows == []
    session_state = (await db_session.execute(select(DoctorSessionState).where(DoctorSessionState.doctor_id == DOCTOR))).scalar_one()
    assert session_state.current_patient_id is None


async def test_delete_patient_for_doctor_returns_none_when_missing(db_session):
    deleted = await delete_patient_for_doctor(db_session, DOCTOR, 999999)
    assert deleted is None


async def test_save_neuro_case_inserts_into_neuro_cases_table(db_session):
    neuro_case = NeuroCase(
        case_id="N-UT-001",
        patient_profile={"name": "神经甲", "gender": "male", "age": 68},
        encounter={"type": "emergency"},
        chief_complaint={"text": "突发言语含糊3小时", "duration": "3小时"},
        neuro_exam={"nihss_total": 8, "speech": "构音障碍"},
        diagnosis={"primary": "急性脑梗死待排", "stroke_type": "unknown"},
    )
    extraction_log = ExtractionLog()

    row = await save_neuro_case(db_session, DOCTOR, neuro_case, extraction_log)
    assert row.id is not None
    assert row.patient_name == "神经甲"
    assert row.nihss == 8

    listed = await get_neuro_cases_for_doctor(db_session, DOCTOR, limit=10)
    assert any(r.id == row.id for r in listed)

    persisted = (
        await db_session.execute(
            select(NeuroCaseDB).where(
                NeuroCaseDB.doctor_id == DOCTOR,
                NeuroCaseDB.id == row.id,
            )
        )
    ).scalars().all()
    assert len(persisted) == 1
