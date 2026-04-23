"""GeneralMedicalExtractor — Phase 2.5: owns medical prompt context building,
metadata extraction, and reply softening."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.interview.protocols import CompletenessState, SessionState
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def _session(collected=None, conversation=None, mode="patient", patient_id=42):
    return SessionState(
        id="s1",
        doctor_id="doc1",
        patient_id=patient_id,
        mode=mode,
        status="interviewing",
        template_id="medical_general_v1",
        collected=collected or {},
        conversation=conversation or [],
        turn_count=len(conversation or []),
    )


def test_fields_returns_medical_fields_list(extractor):
    assert extractor.fields() is MEDICAL_FIELDS


def test_merge_inline_appendable_vs_overwrite(extractor):
    collected = {"chief_complaint": "头痛"}
    extractor.merge(collected, {"chief_complaint": "发热", "present_illness": "3天"})
    assert collected["chief_complaint"] == "发热"
    assert "3天" in collected["present_illness"]


def test_completeness_returns_completeness_state_directly(extractor):
    state = extractor.completeness({"chief_complaint": "x", "present_illness": "y"}, "doctor")
    assert state.can_complete is True


def test_next_phase_returns_single_default_phase_for_now(extractor):
    session = _session()
    assert extractor.next_phase(session, ["default"]) == "default"


# ---- extract_metadata ------------------------------------------------------

def test_extract_metadata_pulls_patient_fields(extractor):
    extracted = {
        "patient_name": "张三",
        "patient_gender": "男",
        "patient_age": "45",
        "chief_complaint": "头痛",
    }
    meta = extractor.extract_metadata(extracted)
    assert meta == {
        "patient_name": "张三",
        "patient_gender": "男",
        "patient_age": "45",
    }


def test_extract_metadata_returns_empty_when_no_patient_fields(extractor):
    meta = extractor.extract_metadata({"chief_complaint": "x"})
    assert meta == {}


def test_extract_metadata_skips_empty_values(extractor):
    meta = extractor.extract_metadata({
        "patient_name": "",
        "patient_gender": None,
        "patient_age": "   ",
    })
    assert meta == {}


# ---- post_process_reply ----------------------------------------------------

def test_post_process_reply_softens_when_can_complete(extractor):
    """When can_complete=True (required fields all set), blocking language
    in reply gets rewritten."""
    collected = {"chief_complaint": "头痛", "present_illness": "3天"}
    reply = "还需要补充您的家族史。"
    out = extractor.post_process_reply(reply, collected, "patient")
    assert "还需要" not in out
    assert "如方便可再补充" in out


def test_post_process_reply_leaves_alone_when_not_complete(extractor):
    """When required fields are missing, blocking language stays."""
    reply = "还需要补充您的主诉。"
    out = extractor.post_process_reply(reply, {}, "patient")
    assert out == reply


def test_post_process_reply_strips_must_phrases(extractor):
    collected = {"chief_complaint": "x", "present_illness": "y"}
    reply = "您必须提供家族史。这样我们可以更准确诊断。"
    out = extractor.post_process_reply(reply, collected, "patient")
    assert "必须" not in out


def test_post_process_reply_fallback_when_empty(extractor):
    # "必须。还缺。" → both patterns reduce to "" → fallback triggers.
    # Note: "还需要补充X" → "如方便可再补充" (non-empty), so we need a reply
    # that uses only the purely-stripping patterns.
    collected = {"chief_complaint": "x", "present_illness": "y"}
    reply = "必须。还缺。"
    out = extractor.post_process_reply(reply, collected, "patient")
    # After stripping all blocking language, fallback kicks in
    assert out != ""
    assert "生成病历" in out or "记录" in out


# ---- prompt_partial new signature ------------------------------------------

@pytest.mark.asyncio
async def test_prompt_partial_builds_patient_context_and_dispatches(extractor):
    """Integration-level: given a SessionState + CompletenessState, the
    extractor builds medical patient_context flat text and calls the
    appropriate composer. Mocks DB + composer to isolate the prompt logic."""
    session = _session(
        collected={"chief_complaint": "头痛"},
        conversation=[
            {"role": "user", "content": "头痛三天"},
            {"role": "assistant", "content": "好的。"},
            {"role": "user", "content": "还伴随恶心"},
        ],
        mode="patient",
        patient_id=42,
    )
    state = extractor.completeness(session.collected, session.mode)

    with patch(
        "domain.interview.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "张三", "gender": "男", "age": 45}),
    ), patch(
        "domain.interview.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[{"role": "system", "content": "composed"}]),
    ) as mock_compose:
        result = await extractor.prompt_partial(
            session_state=session,
            completeness_state=state,
            phase="default",
            mode="patient",
        )

    assert isinstance(result, list)
    assert mock_compose.called
    _, kwargs = mock_compose.call_args
    # Patient context must include the patient info
    assert "张三" in kwargs["patient_context"]
    assert "45" in kwargs["patient_context"]
    # Already-collected field should appear in 已收集
    assert "已收集" in kwargs["patient_context"]
    # doctor_id threaded from session
    assert kwargs["doctor_id"] == "doc1"
    # Last user message separated from history
    assert kwargs["doctor_message"] == "还伴随恶心"


@pytest.mark.asyncio
async def test_prompt_partial_doctor_mode_uses_doctor_composer(extractor):
    session = _session(mode="doctor", patient_id=None)
    state = extractor.completeness({}, "doctor")

    with patch(
        "domain.interview.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "未知", "gender": "未知", "age": "未知"}),
    ), patch(
        "domain.interview.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.interview.templates.medical_general._compose_for_doctor_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_doc, patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_pat:
        await extractor.prompt_partial(
            session_state=session, completeness_state=state,
            phase="default", mode="doctor",
        )

    mock_doc.assert_called_once()
    mock_pat.assert_not_called()


@pytest.mark.asyncio
async def test_prompt_partial_missing_hints_appear_in_context(extractor):
    """When can_complete is False, 必填缺 appears in the patient_context with field hints."""
    session = _session(collected={}, mode="patient")
    state = extractor.completeness({}, "patient")
    assert not state.can_complete

    with patch(
        "domain.interview.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "", "gender": "", "age": ""}),
    ), patch(
        "domain.interview.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_compose:
        await extractor.prompt_partial(
            session_state=session, completeness_state=state,
            phase="default", mode="patient",
        )

    patient_context = mock_compose.call_args.kwargs["patient_context"]
    assert "必填缺" in patient_context
    # FIELD_META hint for chief_complaint
    assert "主诉" in patient_context or "主要症状" in patient_context


@pytest.mark.asyncio
async def test_prompt_partial_long_history_includes_early_summary(extractor):
    """When conversation > 6 turns, early patient turns get summarized into
    an 早期对话摘要 line in patient_context."""
    long_conv = []
    for i in range(10):
        long_conv.append({"role": "user", "content": f"早期消息{i}"})
        long_conv.append({"role": "assistant", "content": f"回复{i}"})
    session = _session(conversation=long_conv, mode="patient")
    state = extractor.completeness({}, "patient")

    with patch(
        "domain.interview.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "X", "gender": "男", "age": 30}),
    ), patch(
        "domain.interview.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=None),
    ), patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_compose:
        await extractor.prompt_partial(
            session_state=session, completeness_state=state,
            phase="default", mode="patient",
        )

    patient_context = mock_compose.call_args.kwargs["patient_context"]
    assert "早期对话摘要" in patient_context
    assert "早期消息0" in patient_context  # first early turn snippet present
