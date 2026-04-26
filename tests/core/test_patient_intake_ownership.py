"""
Patient interview session ownership: /turn must reject requests from a patient
who does not own the session.

These are unit-level tests — no DB or server required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException


def _make_patient(patient_id: int) -> MagicMock:
    """Create a mock Patient ORM object with the given id."""
    p = MagicMock()
    p.id = patient_id
    p.doctor_id = "dr_test"
    p.name = f"Patient {patient_id}"
    return p


def _make_session(session_id: str, patient_id: int):
    """Create a mock InterviewSession with the given patient_id."""
    from domain.patients.interview_session import InterviewSession
    return InterviewSession(
        id=session_id,
        doctor_id="dr_test",
        patient_id=patient_id,
    )


@pytest.mark.asyncio
async def test_turn_rejects_wrong_patient():
    """A patient cannot send a turn for another patient's session."""
    from channels.web.patient_interview_routes import turn, InterviewTurnRequest

    owner_patient_id = 1
    attacker_patient_id = 2
    session_id = "session-uuid-abc"

    body = InterviewTurnRequest(session_id=session_id, text="你好")
    # Auth returns the *attacker* patient
    attacker = _make_patient(attacker_patient_id)
    # Session belongs to the *owner* patient
    owner_session = _make_session(session_id, owner_patient_id)

    with patch(
        "channels.web.patient_interview_routes._authenticate_patient",
        new_callable=AsyncMock,
        return_value=attacker,
    ), patch(
        "channels.web.patient_interview_routes.load_session",
        new_callable=AsyncMock,
        return_value=owner_session,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await turn(body, authorization="fake-token")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_turn_allows_owner():
    """The session owner can successfully send a turn."""
    from channels.web.patient_interview_routes import turn, InterviewTurnRequest
    from domain.interview.protocols import CompletenessState, TurnResult

    patient_id = 42
    session_id = "session-uuid-xyz"

    body = InterviewTurnRequest(session_id=session_id, text="我头痛")
    owner = _make_patient(patient_id)
    owner_session = _make_session(session_id, patient_id)

    # TurnResult returned by engine.next_turn
    mock_state = CompletenessState(
        can_complete=False, required_missing=["present_illness"],
        recommended_missing=[], optional_missing=[], next_focus=None,
    )
    mock_turn_result = TurnResult(
        reply="请描述一下头痛的情况",
        suggestions=[],
        state=mock_state,
        metadata={},
    )

    mock_engine = MagicMock()
    mock_engine.next_turn = AsyncMock(return_value=mock_turn_result)

    with patch(
        "channels.web.patient_interview_routes._authenticate_patient",
        new_callable=AsyncMock,
        return_value=owner,
    ), patch(
        "channels.web.patient_interview_routes.load_session",
        new_callable=AsyncMock,
        return_value=owner_session,
    ), patch(
        "channels.web.patient_interview_routes._get_engine",
        return_value=mock_engine,
    ):
        result = await turn(body, authorization="fake-token")

    assert result["reply"] == "请描述一下头痛的情况"


@pytest.mark.asyncio
async def test_turn_returns_404_for_nonexistent_session():
    """A turn for a session that does not exist returns 404."""
    from channels.web.patient_interview_routes import turn, InterviewTurnRequest

    body = InterviewTurnRequest(session_id="does-not-exist", text="你好")
    patient = _make_patient(1)

    with patch(
        "channels.web.patient_interview_routes._authenticate_patient",
        new_callable=AsyncMock,
        return_value=patient,
    ), patch(
        "channels.web.patient_interview_routes.load_session",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await turn(body, authorization="fake-token")

    assert exc_info.value.status_code == 404
