"""GeneralMedicalExtractor — delegation tests.

Phase 1: every method forwards to the pre-Phase-1 codepath. These tests
verify the forwarding is wire-correct. Phase 2 moves the impl inline and
these tests are updated to assert the direct implementation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.interview.protocols import CompletenessState, SessionState
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_fields_returns_medical_fields_list(extractor):
    assert extractor.fields() is MEDICAL_FIELDS


def test_merge_inline_appendable_vs_overwrite(extractor):
    """Phase 2: merge is inline, no longer delegates."""
    collected = {"chief_complaint": "头痛"}
    extractor.merge(collected, {"chief_complaint": "发热", "present_illness": "3天"})
    assert collected["chief_complaint"] == "发热"
    assert "3天" in collected["present_illness"]


def test_completeness_delegates_to_get_completeness_state(extractor):
    fake_state = {
        "can_complete": True,
        "required_missing": [],
        "recommended_missing": ["past_history"],
        "optional_missing": [],
        "next_focus": "past_history",
    }
    with patch(
        "domain.interview.templates.medical_general._get_completeness_state",
        return_value=fake_state,
    ) as mock_get:
        state = extractor.completeness({"chief_complaint": "x"}, "patient")

    mock_get.assert_called_once_with({"chief_complaint": "x"}, mode="patient")
    assert isinstance(state, CompletenessState)
    assert state.can_complete is True
    assert state.next_focus == "past_history"
    assert state.recommended_missing == ["past_history"]


def test_next_phase_returns_single_default_phase_for_now(extractor):
    session = SessionState(
        id="s1", doctor_id="d", patient_id=None, mode="patient",
        status="interviewing", template_id="medical_general_v1",
        collected={}, conversation=[], turn_count=0,
    )
    # Phase 1 doesn't implement real phase transitions — it returns the
    # one-and-only phase the template declares. See template.config.phases.
    assert extractor.next_phase(session, ["default"]) == "default"


@pytest.mark.asyncio
async def test_prompt_partial_is_awaitable_and_returns_messages(extractor):
    """prompt_partial must produce the messages list that prompt_composer
    would have produced. Phase 1 forwards to the composer directly so the
    output is byte-identical."""
    with patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[{"role": "system", "content": "..."}]),
    ) as mock_compose:
        result = await extractor.prompt_partial(
            collected={"chief_complaint": "头痛"},
            history=[{"role": "user", "content": "头痛三天"}],
            phase="default",
            mode="patient",
        )
    assert mock_compose.called
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_prompt_partial_routes_doctor_mode_to_doctor_composer(extractor):
    with patch(
        "domain.interview.templates.medical_general._compose_for_doctor_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_doc, \
         patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_pat:
        await extractor.prompt_partial(
            collected={}, history=[], phase="default", mode="doctor",
        )
    mock_doc.assert_called_once()
    mock_pat.assert_not_called()
