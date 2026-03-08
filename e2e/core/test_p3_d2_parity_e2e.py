from __future__ import annotations

from typing import List, Tuple
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from db.crud import create_patient, save_record
from db.models import DoctorTask, MedicalRecordDB, Patient
from models.medical_record import MedicalRecord
from services.notify.tasks import run_due_task_cycle


REALWORLD_CASES: List[Tuple[str, str, List[str], List[str]]] = [
    (
        "rw_critical_stemi",
        "王强，男，59岁，突发胸痛2小时，STEMI，拟急诊PCI，0天复查",
        ["critical", "high"],
        ["STEMI", "PCI"],
    ),
    (
        "rw_high_bnp",
        "李敏，女，66岁，急性胸闷，ACS，BNP升高，EF下降，0天复查",
        ["high", "medium"],
        ["ACS", "BNP", "EF"],
    ),
    (
        "rw_medium_followup",
        "赵峰，男，48岁，活动后胸闷，建议随访观察，0天复查",
        ["medium", "low"],
        ["随访"],
    ),
]


async def _fetch_patient(session, patient_id: int) -> Patient:
    result = await session.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    assert patient is not None
    return patient


@pytest.mark.asyncio
async def test_p3_d2_smoke_chain_parity(db_session, session_factory, monkeypatch) -> None:
    """OpenClaw parity smoke:
    intake -> record -> risk -> task -> notification.
    """
    import services.notify.tasks as tasks_service

    monkeypatch.setenv("AUTO_FOLLOWUP_TASKS_ENABLED", "true")

    # Route task notification DB writes through the same in-memory test DB.
    monkeypatch.setattr(tasks_service, "AsyncSessionLocal", session_factory)
    mocked_notify = AsyncMock()
    monkeypatch.setattr(tasks_service, "send_doctor_notification", mocked_notify)

    doctor_id = "doc_p3d2_smoke"
    patient = await create_patient(db_session, doctor_id, "张三", "男", 52)

    record = MedicalRecord(
        chief_complaint="胸痛3天",
        history_of_present_illness="活动后胸闷加重",
        past_medical_history="糖尿病",
        physical_examination=None,
        auxiliary_examinations="BNP升高",
        diagnosis="冠心病待排，STEMI风险",
        treatment_plan="继续监测心电图并评估PCI时机",
        follow_up_plan="0天复查",
    )
    saved = await save_record(db_session, doctor_id, record, patient.id)
    assert saved.id is not None

    patient_row = await _fetch_patient(db_session, patient.id)
    assert patient_row.primary_risk_level in {"medium", "high", "critical"}
    assert patient_row.risk_score is not None and patient_row.risk_score > 0

    tasks_before = await db_session.execute(
        select(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.patient_id == patient.id,
            DoctorTask.task_type == "follow_up",
        )
    )
    followup = tasks_before.scalar_one_or_none()
    assert followup is not None
    assert followup.status == "pending"

    summary = await run_due_task_cycle()
    assert summary["due_count"] >= 1
    assert summary["sent_count"] >= 1
    assert summary["failed_count"] == 0
    assert mocked_notify.await_count >= 1

    async with session_factory() as verify_session:
        tasks_after = await verify_session.execute(
            select(DoctorTask).where(DoctorTask.id == followup.id)
        )
        notified = tasks_after.scalar_one_or_none()
        assert notified is not None
        assert notified.notified_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,input_text,expected_levels,diagnosis_tokens",
    REALWORLD_CASES,
)
async def test_p3_d2_realworld_matrix_parity(
    case_id: str,
    input_text: str,
    expected_levels: List[str],
    diagnosis_tokens: List[str],
    session_factory,
    monkeypatch,
) -> None:
    """OpenClaw parity real-world matrix:
    validates risk and persistence across representative cases.
    """
    import services.notify.tasks as tasks_service

    monkeypatch.setenv("AUTO_FOLLOWUP_TASKS_ENABLED", "true")
    monkeypatch.setattr(tasks_service, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(tasks_service, "send_doctor_notification", AsyncMock())

    async with session_factory() as session:
        doctor_id = "doc_%s" % case_id
        patient_name = "患者_%s" % case_id[-4:]
        patient = await create_patient(session, doctor_id, patient_name, "男", 55)

        record = MedicalRecord(
            chief_complaint=input_text.split("，")[0],
            history_of_present_illness=input_text,
            past_medical_history=None,
            physical_examination=None,
            auxiliary_examinations="BNP升高" if "BNP" in input_text else None,
            diagnosis=input_text,
            treatment_plan=input_text,
            follow_up_plan="0天复查",
        )
        saved = await save_record(session, doctor_id, record, patient.id)
        assert saved.id is not None

        rec_result = await session.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == saved.id)
        )
        saved_record = rec_result.scalar_one_or_none()
        assert saved_record is not None
        for token in diagnosis_tokens:
            assert token in (saved_record.diagnosis or "")

        patient_row = await _fetch_patient(session, patient.id)
        assert patient_row.primary_risk_level in set(expected_levels)
        assert patient_row.risk_score is not None and patient_row.risk_score >= 0

    summary = await run_due_task_cycle()
    assert summary["failed_count"] == 0
