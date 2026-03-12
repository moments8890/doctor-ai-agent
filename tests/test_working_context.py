"""Working context endpoint tests: verify /api/manage/working-context returns
correct patient, pending draft, and next-step state.

Also covers cross-doctor auth isolation and cold-session hydration for
workbench context + pending-record endpoints (WS1/WS2)."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from services.session import get_session, set_current_patient, set_pending_record_id


DOCTOR = "unit_doc_workctx"
_HYDRATE = "routers.ui.hydrate_session_state"


def _clear_session():
    sess = get_session(DOCTOR)
    sess.current_patient_id = None
    sess.current_patient_name = None
    sess.pending_record_id = None
    sess.pending_create_name = None


# ---------------------------------------------------------------------------
# Basic working-context tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_working_context_no_state():
    """When no patient or draft, returns null patient and generic next step."""
    _clear_session()
    from routers.ui import get_working_context
    with patch(_HYDRATE, new_callable=AsyncMock):
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
    with patch(_HYDRATE, new_callable=AsyncMock):
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
    with patch("routers.ui.AsyncSessionLocal", session_factory), \
         patch(_HYDRATE, new_callable=AsyncMock):
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
    with patch(_HYDRATE, new_callable=AsyncMock):
        result = await get_working_context(doctor_id=DOCTOR)
    assert "李四" in result["next_step"]


# ---------------------------------------------------------------------------
# WS1: Cross-doctor auth isolation — resolved principal must be used
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_working_context_uses_resolved_doctor_id():
    """working-context uses resolved principal, not raw query doctor_id."""
    attacker = "attacker_doc"
    victim = "victim_doc"
    # Set state for victim
    victim_sess = get_session(victim)
    victim_sess.current_patient_id = 99
    victim_sess.current_patient_name = "VictimPatient"
    victim_sess.pending_record_id = None
    victim_sess.pending_create_name = None
    # Clear attacker state
    attacker_sess = get_session(attacker)
    attacker_sess.current_patient_id = None
    attacker_sess.current_patient_name = None
    attacker_sess.pending_record_id = None
    attacker_sess.pending_create_name = None

    from routers.ui import get_working_context
    # Simulate: attacker sends doctor_id=victim but auth resolves to attacker
    with patch("routers.ui._resolve_ui_doctor_id", return_value=attacker), \
         patch(_HYDRATE, new_callable=AsyncMock):
        result = await get_working_context(doctor_id=victim)

    # Should see attacker's empty state, NOT victim's patient
    assert result["current_patient"] is None


@pytest.mark.asyncio
async def test_pending_record_endpoint_uses_resolved_doctor_id():
    """pending-record read uses resolved principal, not raw query doctor_id."""
    attacker = "attacker_doc_pr"
    victim = "victim_doc_pr"
    victim_sess = get_session(victim)
    victim_sess.pending_record_id = "secret-draft-id"
    attacker_sess = get_session(attacker)
    attacker_sess.pending_record_id = None

    from routers.ui import get_pending_record_endpoint
    with patch("routers.ui._resolve_ui_doctor_id", return_value=attacker), \
         patch(_HYDRATE, new_callable=AsyncMock):
        result = await get_pending_record_endpoint(doctor_id=victim)

    # Attacker has no pending record — should get None
    assert result is None


@pytest.mark.asyncio
async def test_confirm_endpoint_uses_resolved_doctor_id():
    """confirm endpoint uses resolved principal, not raw query doctor_id."""
    from fastapi import HTTPException
    attacker = "attacker_doc_cf"
    victim = "victim_doc_cf"
    victim_sess = get_session(victim)
    victim_sess.pending_record_id = "victim-draft"
    attacker_sess = get_session(attacker)
    attacker_sess.pending_record_id = None

    from routers.ui import confirm_pending_record_endpoint
    with patch("routers.ui._resolve_ui_doctor_id", return_value=attacker), \
         patch(_HYDRATE, new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await confirm_pending_record_endpoint(doctor_id=victim)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_abandon_endpoint_uses_resolved_doctor_id():
    """abandon endpoint uses resolved principal, not raw query doctor_id."""
    from fastapi import HTTPException
    attacker = "attacker_doc_ab"
    victim = "victim_doc_ab"
    victim_sess = get_session(victim)
    victim_sess.pending_record_id = "victim-draft"
    attacker_sess = get_session(attacker)
    attacker_sess.pending_record_id = None

    from routers.ui import abandon_pending_record_endpoint
    with patch("routers.ui._resolve_ui_doctor_id", return_value=attacker), \
         patch(_HYDRATE, new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await abandon_pending_record_endpoint(doctor_id=victim)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# WS2: Hydration is called before session reads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_working_context_calls_hydrate():
    """working-context calls hydrate_session_state before reading session."""
    _clear_session()
    from routers.ui import get_working_context
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_hydrate:
        await get_working_context(doctor_id=DOCTOR)
    mock_hydrate.assert_awaited_once_with(DOCTOR)


@pytest.mark.asyncio
async def test_pending_record_calls_hydrate():
    """pending-record endpoint calls hydrate before reading session."""
    _clear_session()
    from routers.ui import get_pending_record_endpoint
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_hydrate:
        await get_pending_record_endpoint(doctor_id=DOCTOR)
    mock_hydrate.assert_awaited_once_with(DOCTOR)


@pytest.mark.asyncio
async def test_confirm_calls_hydrate():
    """confirm endpoint calls hydrate with write_intent=True before reading session."""
    from fastapi import HTTPException
    _clear_session()
    from routers.ui import confirm_pending_record_endpoint
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_hydrate:
        with pytest.raises(HTTPException):
            await confirm_pending_record_endpoint(doctor_id=DOCTOR)
    mock_hydrate.assert_awaited_once_with(DOCTOR, write_intent=True)


@pytest.mark.asyncio
async def test_abandon_calls_hydrate():
    """abandon endpoint calls hydrate with write_intent=True before reading session."""
    from fastapi import HTTPException
    _clear_session()
    from routers.ui import abandon_pending_record_endpoint
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_hydrate:
        with pytest.raises(HTTPException):
            await abandon_pending_record_endpoint(doctor_id=DOCTOR)
    mock_hydrate.assert_awaited_once_with(DOCTOR, write_intent=True)


# ---------------------------------------------------------------------------
# WS2b: Cold-start hydration — verify hydrate runs before get_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_working_context_calls_hydrate_on_cold_start():
    """On cold start, working-context must hydrate before get_session reads."""
    _clear_session()
    call_order = []

    async def _tracking_hydrate(doc_id, **kwargs):
        call_order.append("hydrate")

    def _tracking_get_session(doc_id):
        call_order.append("get_session")
        return get_session(doc_id)

    from routers.ui import get_working_context
    with patch(_HYDRATE, side_effect=_tracking_hydrate) as mock_h, \
         patch("routers.ui.get_session", side_effect=_tracking_get_session):
        await get_working_context(doctor_id=DOCTOR)
    mock_h.assert_awaited_once()
    assert call_order.index("hydrate") < call_order.index("get_session"), \
        "hydrate must be called before get_session"


@pytest.mark.asyncio
async def test_pending_record_get_calls_hydrate():
    """pending-record GET must hydrate before reading session on cold start."""
    _clear_session()
    call_order = []

    async def _tracking_hydrate(doc_id, **kwargs):
        call_order.append("hydrate")

    def _tracking_get_session(doc_id):
        call_order.append("get_session")
        return get_session(doc_id)

    from routers.ui import get_pending_record_endpoint
    with patch(_HYDRATE, side_effect=_tracking_hydrate) as mock_h, \
         patch("routers.ui.get_session", side_effect=_tracking_get_session):
        await get_pending_record_endpoint(doctor_id=DOCTOR)
    mock_h.assert_awaited_once()
    assert call_order.index("hydrate") < call_order.index("get_session"), \
        "hydrate must be called before get_session"


@pytest.mark.asyncio
async def test_pending_record_confirm_calls_hydrate_with_write_intent():
    """confirm POST must hydrate with write_intent=True before session read."""
    from fastapi import HTTPException
    _clear_session()
    from routers.ui import confirm_pending_record_endpoint
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_h:
        with pytest.raises(HTTPException):
            await confirm_pending_record_endpoint(doctor_id=DOCTOR)
    mock_h.assert_awaited_once_with(DOCTOR, write_intent=True)


@pytest.mark.asyncio
async def test_pending_record_abandon_calls_hydrate_with_write_intent():
    """abandon POST must hydrate with write_intent=True before session read."""
    from fastapi import HTTPException
    _clear_session()
    from routers.ui import abandon_pending_record_endpoint
    with patch(_HYDRATE, new_callable=AsyncMock) as mock_h:
        with pytest.raises(HTTPException):
            await abandon_pending_record_endpoint(doctor_id=DOCTOR)
    mock_h.assert_awaited_once_with(DOCTOR, write_intent=True)
