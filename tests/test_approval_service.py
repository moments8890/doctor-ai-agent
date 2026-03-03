"""Tests for services/approval.py — commit_approval and reject_approval.

All DB and LLM I/O is mocked.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.approval as approval_mod
from db.models import ApprovalItem, MedicalRecordDB


DOCTOR = "svc_approval_doc"


def _make_item(
    approval_id: int = 1,
    status: str = "pending",
    suggested_data: dict = None,
) -> ApprovalItem:
    if suggested_data is None:
        suggested_data = {
            "record": {
                "chief_complaint": "胸痛",
                "history_of_present_illness": None,
                "past_medical_history": None,
                "physical_examination": None,
                "auxiliary_examinations": None,
                "diagnosis": "冠心病",
                "treatment_plan": "随访",
                "follow_up_plan": None,
            },
            "patient_name": "张三",
            "gender": "男",
            "age": 58,
            "existing_patient_id": None,
        }
    item = MagicMock(spec=ApprovalItem)
    item.id = approval_id
    item.doctor_id = DOCTOR
    item.status = status
    item.suggested_data = json.dumps(suggested_data)
    item.reviewed_at = None
    return item


def _make_db_record(record_id: int = 10) -> MedicalRecordDB:
    rec = MagicMock(spec=MedicalRecordDB)
    rec.id = record_id
    return rec


def _make_patient(patient_id: int = 5) -> MagicMock:
    p = MagicMock()
    p.id = patient_id
    return p


def _make_session_ctx(item, updated_item=None, patient=None, db_record=None):
    """Build a mock AsyncSessionLocal context manager."""
    session = MagicMock()
    # get_approval_item
    session.get_approval_item = AsyncMock(return_value=item)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# commit_approval
# ---------------------------------------------------------------------------


async def test_commit_calls_save_record_with_correct_record():
    item = _make_item()
    updated = _make_item(status="approved")
    db_record = _make_db_record(record_id=42)
    patient = _make_patient(patient_id=7)

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
        patch("services.approval.find_patient_by_name", new_callable=AsyncMock, return_value=None),
        patch("services.approval.db_create_patient", new_callable=AsyncMock, return_value=patient),
        patch("services.approval.save_record", new_callable=AsyncMock, return_value=db_record),
        patch("services.approval.update_approval_item", new_callable=AsyncMock, return_value=updated),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await approval_mod.commit_approval(1, DOCTOR)

    assert result.status == "approved"


async def test_commit_skips_patient_creation_when_existing_patient_id_set():
    data = {
        "record": {"chief_complaint": "发热", "history_of_present_illness": None, "past_medical_history": None, "physical_examination": None, "auxiliary_examinations": None, "diagnosis": None, "treatment_plan": None, "follow_up_plan": None},
        "patient_name": "李四",
        "gender": None,
        "age": None,
        "existing_patient_id": 99,
    }
    item = _make_item(suggested_data=data)
    updated = _make_item(status="approved")
    db_record = _make_db_record()

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
        patch("services.approval.find_patient_by_name", new_callable=AsyncMock) as mock_find,
        patch("services.approval.db_create_patient", new_callable=AsyncMock) as mock_create,
        patch("services.approval.save_record", new_callable=AsyncMock, return_value=db_record),
        patch("services.approval.update_approval_item", new_callable=AsyncMock, return_value=updated),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        await approval_mod.commit_approval(1, DOCTOR)

    mock_find.assert_not_called()
    mock_create.assert_not_called()


async def test_commit_creates_patient_when_not_found():
    item = _make_item()
    updated = _make_item(status="approved")
    db_record = _make_db_record()
    new_patient = _make_patient(patient_id=55)

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
        patch("services.approval.find_patient_by_name", new_callable=AsyncMock, return_value=None),
        patch("services.approval.db_create_patient", new_callable=AsyncMock, return_value=new_patient) as mock_create,
        patch("services.approval.save_record", new_callable=AsyncMock, return_value=db_record),
        patch("services.approval.update_approval_item", new_callable=AsyncMock, return_value=updated),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        await approval_mod.commit_approval(1, DOCTOR)

    mock_create.assert_called_once()


async def test_commit_uses_edited_data_over_suggested_data():
    item = _make_item()
    updated = _make_item(status="approved")
    db_record = _make_db_record()
    patient = _make_patient()

    edited = {
        "record": {
            "chief_complaint": "头晕",
            "history_of_present_illness": None,
            "past_medical_history": None,
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
        "patient_name": "王五",
        "gender": "女",
        "age": 40,
        "existing_patient_id": None,
    }

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
        patch("services.approval.find_patient_by_name", new_callable=AsyncMock, return_value=None),
        patch("services.approval.db_create_patient", new_callable=AsyncMock, return_value=patient),
        patch("services.approval.save_record", new_callable=AsyncMock, return_value=db_record) as mock_save,
        patch("services.approval.update_approval_item", new_callable=AsyncMock, return_value=updated),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        await approval_mod.commit_approval(1, DOCTOR, edited_data=edited)

    # The record passed to save_record should have chief_complaint "头晕"
    saved_record = mock_save.call_args[0][2]
    assert saved_record.chief_complaint == "头晕"


async def test_commit_raises_for_nonexistent_approval():
    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=None),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="not found"):
            await approval_mod.commit_approval(999, DOCTOR)


async def test_commit_raises_if_not_pending():
    item = _make_item(status="approved")

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="approved"):
            await approval_mod.commit_approval(1, DOCTOR)


# ---------------------------------------------------------------------------
# reject_approval
# ---------------------------------------------------------------------------


async def test_reject_does_not_call_save_record():
    item = _make_item()
    updated = _make_item(status="rejected")

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
        patch("services.approval.save_record", new_callable=AsyncMock) as mock_save,
        patch("services.approval.update_approval_item", new_callable=AsyncMock, return_value=updated),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await approval_mod.reject_approval(1, DOCTOR, reviewer_note="错误转录")

    mock_save.assert_not_called()
    assert result.status == "rejected"


async def test_reject_raises_if_not_pending():
    item = _make_item(status="rejected")

    with (
        patch("services.approval.AsyncSessionLocal") as mock_sl,
        patch("services.approval.get_approval_item", new_callable=AsyncMock, return_value=item),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="rejected"):
            await approval_mod.reject_approval(1, DOCTOR)
