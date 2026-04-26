"""GeneralNeuroExtractor — Task 3 behavior tests.

Covers: fields() override, completeness semantics (onset_time required in
patient mode), merge semantics on appendable vs overwrite, prompt_partial
neuro-guidance injection, and template_id threading through the composer
call.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.protocols import SessionState
from domain.intake.templates.medical_neuro import (
    GeneralNeuroExtractor, NEURO_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralNeuroExtractor()


def _session(
    collected=None,
    conversation=None,
    mode="patient",
    patient_id=42,
    template_id="medical_neuro_v1",
):
    return SessionState(
        id="s-neuro",
        doctor_id="doc1",
        patient_id=patient_id,
        mode=mode,
        status="active",
        template_id=template_id,
        collected=collected or {},
        conversation=conversation or [],
        turn_count=len(conversation or []),
    )


# ---- fields() --------------------------------------------------------------

def test_fields_returns_neuro_fields(extractor):
    assert extractor.fields() is NEURO_FIELDS


# ---- completeness ----------------------------------------------------------

def test_patient_mode_requires_chief_complaint_and_onset_time(extractor):
    """Both chief_complaint and onset_time are required (required tier)
    and onset_time is in the neuro patient-mode subset — so both must be
    present (along with the base-required present_illness) for
    can_complete=True. Explicitly asserts onset_time appears in
    required_missing when absent, proving the extractor extended the
    base patient-mode subset with onset_time.
    """
    # Baseline: all patient-mode required fields empty.
    # onset_time must appear in required_missing — this is the core
    # assertion that the neuro patient subset actually includes it.
    state = extractor.completeness({}, "patient")
    assert state.can_complete is False
    assert "onset_time" in state.required_missing
    assert "chief_complaint" in state.required_missing

    # With chief_complaint + present_illness but no onset_time: still
    # blocked on onset_time. Proves onset_time is required, not optional.
    state = extractor.completeness(
        {"chief_complaint": "左侧肢体无力", "present_illness": "2小时前突发"},
        "patient",
    )
    assert state.can_complete is False
    assert "onset_time" in state.required_missing

    # All patient-mode required fields (including onset_time) populated →
    # can_complete flips to True.
    state = extractor.completeness(
        {
            "chief_complaint": "左侧肢体无力",
            "present_illness": "2小时前突发，无外伤",
            "onset_time": "2小时前",
        },
        "patient",
    )
    assert state.can_complete is True


# ---- merge ----------------------------------------------------------------

def test_neuro_exam_merges_with_append_semantics(extractor):
    collected: dict[str, str] = {}
    extractor.merge(collected, {"neuro_exam": "GCS 15"})
    extractor.merge(collected, {"neuro_exam": "左上肢肌力3级"})
    assert "GCS 15" in collected["neuro_exam"]
    assert "左上肢肌力3级" in collected["neuro_exam"]


def test_onset_time_merges_with_overwrite_semantics(extractor):
    collected = {"onset_time": "今晨7:30"}
    extractor.merge(collected, {"onset_time": "约2小时前"})
    # Non-appendable: new value wins outright, no concatenation separator
    assert collected["onset_time"] == "约2小时前"


# ---- prompt_partial: guidance injection -----------------------------------

@pytest.mark.asyncio
async def test_prompt_partial_injects_neuro_guidance_into_first_system_msg(
    extractor,
):
    """The extractor calls super().prompt_partial() and appends the
    【神外重点】 guidance to the first system message's content.
    """
    session = _session(
        collected={"chief_complaint": "头痛"},
        conversation=[{"role": "user", "content": "突发头痛"}],
        mode="patient",
    )
    state = extractor.completeness(session.collected, session.mode)

    composed_messages = [
        {"role": "system", "content": "base system prompt"},
        {"role": "user", "content": "turn"},
    ]
    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "X", "gender": "男", "age": 60}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.intake.templates.medical_general._compose_for_patient_intake",
        new=AsyncMock(return_value=composed_messages),
    ):
        result = await extractor.prompt_partial(
            session_state=session,
            completeness_state=state,
            phase="default",
            mode="patient",
        )

    assert isinstance(result, list)
    assert result[0]["role"] == "system"
    assert "【神外重点】" in result[0]["content"]
    # Original base content is preserved
    assert "base system prompt" in result[0]["content"]
    # Non-system messages untouched
    assert result[1] == {"role": "user", "content": "turn"}


@pytest.mark.asyncio
async def test_prompt_partial_no_system_message_is_noop(extractor):
    """If the composed messages list has no leading system message, the
    neuro extractor returns it unchanged (defensive — medical composer
    always has one, but be robust)."""
    session = _session(mode="patient")
    state = extractor.completeness(session.collected, session.mode)

    composed_messages = [{"role": "user", "content": "just a user msg"}]
    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "X", "gender": "男", "age": 60}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.intake.templates.medical_general._compose_for_patient_intake",
        new=AsyncMock(return_value=composed_messages),
    ):
        result = await extractor.prompt_partial(
            session_state=session,
            completeness_state=state,
            phase="default",
            mode="patient",
        )

    assert result == composed_messages


# ---- prompt_partial: template_id threading (parent change) ----------------

@pytest.mark.asyncio
async def test_prompt_partial_threads_session_template_id_to_patient_composer(
    extractor,
):
    """GeneralMedicalExtractor.prompt_partial must pass session_state.template_id
    (not a hardcoded 'medical_general_v1') so neuro sessions log as neuro.
    """
    session = _session(mode="patient", template_id="medical_neuro_v1")
    state = extractor.completeness(session.collected, session.mode)

    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "X", "gender": "男", "age": 60}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.intake.templates.medical_general._compose_for_patient_intake",
        new=AsyncMock(return_value=[{"role": "system", "content": "c"}]),
    ) as mock_compose:
        await extractor.prompt_partial(
            session_state=session,
            completeness_state=state,
            phase="default",
            mode="patient",
        )

    assert mock_compose.call_args.kwargs["template_id"] == "medical_neuro_v1"


@pytest.mark.asyncio
async def test_prompt_partial_threads_session_template_id_to_doctor_composer(
    extractor,
):
    session = _session(
        mode="doctor", patient_id=None, template_id="medical_neuro_v1",
    )
    state = extractor.completeness(session.collected, "doctor")

    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "X", "gender": "男", "age": 60}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.intake.templates.medical_general._compose_for_doctor_intake",
        new=AsyncMock(return_value=[{"role": "system", "content": "c"}]),
    ) as mock_doc:
        await extractor.prompt_partial(
            session_state=session,
            completeness_state=state,
            phase="default",
            mode="doctor",
        )

    assert mock_doc.call_args.kwargs["template_id"] == "medical_neuro_v1"
