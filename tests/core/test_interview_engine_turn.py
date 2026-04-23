"""InterviewEngine.next_turn — Phase 1 forwards to legacy interview_turn().

These tests confirm the engine's contract (input session_id + text →
TurnResult) and that the legacy function is still the execution engine.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.interview.engine import InterviewEngine
from domain.interview.protocols import CompletenessState, TurnResult


@pytest.fixture
def engine():
    return InterviewEngine()


@pytest.mark.asyncio
async def test_next_turn_returns_turnresult(engine):
    fake_legacy_response = type("R", (), {
        "reply": "ok",
        "collected": {"chief_complaint": "头痛"},
        "progress": {"filled": 1, "total": 14},
        "status": "interviewing",
        "missing": [],
        "suggestions": ["休息"],
        "ready_to_review": False,
        "retryable": False,
        "patient_name": None,
        "patient_gender": None,
        "patient_age": None,
    })()

    with patch(
        "domain.interview.engine._legacy_interview_turn",
        new=AsyncMock(return_value=fake_legacy_response),
    ):
        result = await engine.next_turn(
            session_id="s1", user_input="hello",
        )

    assert isinstance(result, TurnResult)
    assert result.reply == "ok"
    assert result.suggestions == ["休息"]
    assert isinstance(result.state, CompletenessState)


@pytest.mark.asyncio
async def test_next_turn_surfaces_patient_metadata(engine):
    fake = type("R", (), {
        "reply": "", "collected": {}, "progress": {"filled": 0, "total": 7},
        "status": "interviewing", "missing": [], "suggestions": [],
        "ready_to_review": False, "retryable": False,
        "patient_name": "张三", "patient_gender": "男", "patient_age": "50",
    })()
    with patch(
        "domain.interview.engine._legacy_interview_turn",
        new=AsyncMock(return_value=fake),
    ):
        result = await engine.next_turn("s1", "x")
    assert result.metadata.get("patient_name") == "张三"
    assert result.metadata.get("patient_gender") == "男"
    assert result.metadata.get("patient_age") == "50"


@pytest.mark.asyncio
async def test_next_turn_state_reflects_completeness_can_complete(engine):
    fake = type("R", (), {
        "reply": "", "collected": {"chief_complaint": "x", "present_illness": "y"},
        "progress": {"filled": 2, "total": 14},
        "status": "reviewing", "missing": [], "suggestions": [],
        "ready_to_review": True, "retryable": False,
        "patient_name": None, "patient_gender": None, "patient_age": None,
    })()
    with patch(
        "domain.interview.engine._legacy_interview_turn",
        new=AsyncMock(return_value=fake),
    ):
        result = await engine.next_turn("s1", "x")
    assert result.state.can_complete is True
