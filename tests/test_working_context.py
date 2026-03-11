"""Working context endpoint tests: verify /api/manage/working-context returns
correct patient, pending draft, and next-step state."""

import json
import pytest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from services.session import get_session, set_current_patient, set_pending_record_id


DOCTOR = "unit_doc_workctx"


def _clear_session():
    sess = get_session(DOCTOR)
    sess.current_patient_id = None
    sess.current_patient_name = None
    sess.pending_record_id = None
    sess.pending_create_name = None


@pytest.mark.asyncio
async def test_working_context_no_state():
    """When no patient or draft, returns null patient and generic next step."""
    _clear_session()
    from routers.ui import get_working_context
    result = await get_working_context(doctor_id=DOCTOR)
    assert result["current_patient"] is None
    assert result["pending_draft"] is None
    assert result["next_step"] is not None


@pytest.mark.asyncio
async def test_working_context_with_patient():
    """When current patient is set, returns patient info."""
    _clear_session()
    set_current_patient(DOCTOR, 42, "张三")
    from routers.ui import get_working_context
    result = await get_working_context(doctor_id=DOCTOR)
    assert result["current_patient"]["id"] == 42
    assert result["current_patient"]["name"] == "张三"
    assert result["pending_draft"] is None
    # With a patient set and no draft, next_step should be None
    assert result["next_step"] is None


@pytest.mark.asyncio
async def test_working_context_with_pending_draft(session_factory):
    """When a pending draft exists, returns draft info and confirmation prompt."""
    _clear_session()
    set_current_patient(DOCTOR, 42, "张三")

    from db.crud.pending import create_pending_record
    draft_id = "test-draft-wctx-001"
    async with session_factory() as db:
        await create_pending_record(
            db,
            record_id=draft_id,
            doctor_id=DOCTOR,
            draft_json='{"content": "胸痛两小时"}',
            patient_id=42,
            patient_name="张三",
            ttl_minutes=30,
        )
    set_pending_record_id(DOCTOR, draft_id)

    from routers.ui import get_working_context
    with patch("routers.ui.AsyncSessionLocal", session_factory):
        result = await get_working_context(doctor_id=DOCTOR)

    assert result["current_patient"]["name"] == "张三"
    assert result["pending_draft"] is not None
    assert result["pending_draft"]["patient_name"] == "张三"
    assert "确认" in result["next_step"]


@pytest.mark.asyncio
async def test_working_context_pending_create():
    """When pending_create_name is set, next_step mentions the patient."""
    _clear_session()
    sess = get_session(DOCTOR)
    sess.pending_create_name = "李四"
    from routers.ui import get_working_context
    result = await get_working_context(doctor_id=DOCTOR)
    assert "李四" in result["next_step"]
