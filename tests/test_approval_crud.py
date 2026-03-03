"""Tests for ApprovalItem CRUD functions in db/crud.py.

All tests use the in-memory db_session fixture — no real DB or network calls.
"""
from __future__ import annotations

import json
import pytest

from db.crud import (
    create_approval_item,
    get_approval_item,
    list_approval_items,
    update_approval_item,
)


DOCTOR = "crud_approval_doc"
OTHER_DOCTOR = "other_doc"


async def test_create_stores_all_fields(db_session):
    data = {"record": {"chief_complaint": "胸痛"}, "patient_name": "张三", "gender": "男", "age": 58, "existing_patient_id": None}
    item = await create_approval_item(db_session, DOCTOR, "medical_record", data, source_text="原文")

    assert item.id is not None
    assert item.doctor_id == DOCTOR
    assert item.item_type == "medical_record"
    assert item.status == "pending"
    assert item.source_text == "原文"
    parsed = json.loads(item.suggested_data)
    assert parsed["patient_name"] == "张三"


async def test_create_status_defaults_to_pending(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    assert item.status == "pending"


async def test_create_without_source_text(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    assert item.source_text is None


async def test_get_returns_item_for_correct_doctor(db_session):
    created = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    fetched = await get_approval_item(db_session, created.id, DOCTOR)
    assert fetched is not None
    assert fetched.id == created.id


async def test_get_returns_none_for_wrong_doctor(db_session):
    created = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    result = await get_approval_item(db_session, created.id, OTHER_DOCTOR)
    assert result is None


async def test_get_returns_none_for_nonexistent_id(db_session):
    result = await get_approval_item(db_session, 99999, DOCTOR)
    assert result is None


async def test_list_returns_all_when_no_status_filter(db_session):
    await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    items = await list_approval_items(db_session, DOCTOR)
    assert len(items) == 2


async def test_list_filters_by_status(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    # Manually move one to approved via update
    await update_approval_item(db_session, item.id, DOCTOR, status="approved")
    await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})  # pending

    pending = await list_approval_items(db_session, DOCTOR, status="pending")
    approved = await list_approval_items(db_session, DOCTOR, status="approved")
    assert len(pending) == 1
    assert len(approved) == 1


async def test_update_sets_reviewed_at(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    assert item.reviewed_at is None
    updated = await update_approval_item(db_session, item.id, DOCTOR, status="approved")
    assert updated is not None
    assert updated.reviewed_at is not None
    assert updated.status == "approved"


async def test_update_returns_none_for_nonexistent_id(db_session):
    result = await update_approval_item(db_session, 99999, DOCTOR, status="approved")
    assert result is None


async def test_update_returns_none_for_wrong_doctor(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    result = await update_approval_item(db_session, item.id, OTHER_DOCTOR, status="approved")
    assert result is None


async def test_update_sets_reviewer_note(db_session):
    item = await create_approval_item(db_session, DOCTOR, "medical_record", {"record": {}})
    updated = await update_approval_item(
        db_session, item.id, DOCTOR, status="rejected", reviewer_note="转录错误"
    )
    assert updated is not None
    assert updated.reviewer_note == "转录错误"
    assert updated.status == "rejected"
