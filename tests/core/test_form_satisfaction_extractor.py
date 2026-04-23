"""FormSatisfactionExtractor — implements FieldExtractor for a form template."""
from __future__ import annotations

import pytest

from domain.interview.protocols import CompletenessState, SessionState
from domain.interview.templates.form_satisfaction import (
    FormSatisfactionExtractor, FORM_SATISFACTION_FIELDS,
)


@pytest.fixture
def extractor():
    return FormSatisfactionExtractor()


def test_fields_returns_form_fields(extractor):
    assert extractor.fields() is FORM_SATISFACTION_FIELDS


def test_completeness_empty_not_complete(extractor):
    state = extractor.completeness({}, "patient")
    assert state.can_complete is False
    assert "overall_rating" in state.required_missing


def test_completeness_with_required_set(extractor):
    state = extractor.completeness({"overall_rating": "满意"}, "patient")
    assert state.can_complete is True


def test_merge_simple_overwrite(extractor):
    collected = {"overall_rating": "满意"}
    extractor.merge(collected, {"overall_rating": "非常满意"})
    assert collected["overall_rating"] == "非常满意"


def test_merge_ignores_unknown(extractor):
    collected = {}
    extractor.merge(collected, {"not_a_form_field": "x"})
    assert "not_a_form_field" not in collected


def test_next_phase_returns_single_phase(extractor):
    session = SessionState(
        id="s", doctor_id="d", patient_id=1, mode="patient",
        status="interviewing", template_id="form_satisfaction_v1",
        collected={}, conversation=[], turn_count=0,
    )
    assert extractor.next_phase(session, ["default"]) == "default"


@pytest.mark.asyncio
async def test_prompt_partial_returns_messages(extractor):
    """Form templates produce a simple structured survey prompt directly,
    without going through prompt_composer (no doctor persona / KB needed)."""
    session = SessionState(
        id="s", doctor_id="d", patient_id=1, mode="patient",
        status="interviewing", template_id="form_satisfaction_v1",
        collected={}, conversation=[], turn_count=0,
    )
    state = extractor.completeness({}, "patient")

    result = await extractor.prompt_partial(
        session_state=session,
        completeness_state=state,
        phase="default",
        mode="patient",
    )
    assert isinstance(result, list)
    assert len(result) >= 1
    joined = "\n".join(m.get("content", "") for m in result)
    assert "满意" in joined


def test_extract_metadata_returns_empty(extractor):
    assert extractor.extract_metadata({"overall_rating": "满意"}) == {}


def test_post_process_reply_returns_unchanged(extractor):
    out = extractor.post_process_reply("Thanks for feedback!", {}, "patient")
    assert out == "Thanks for feedback!"
