"""Prompt context must split confirmed-collected vs unconfirmed-carry-forward.

Regression: when carry-forward seeds 5 phase-2 fields with
``confirmed_by_patient: false``, the LLM saw those fields in BOTH
``已收集`` (they're in the dict) AND ``必填缺`` (engine treats them as
missing). Faced with a contradictory signal the LLM ignored phase 2 and
kept asking phase-1 questions forever.

Fix: ``GeneralMedicalExtractor.prompt_partial`` now surfaces unconfirmed
carry-forward in a separate ``待确认（上次记录）`` block so the LLM has
a clear instruction to ask the patient to confirm each carried value.
"""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from domain.intake.protocols import CompletenessState, SessionState
from domain.intake.templates.medical_general import GeneralMedicalExtractor


def _state(collected):
    return SessionState(
        id="s1",
        doctor_id="d1",
        patient_id=42,
        mode="patient",
        status="active",
        template_id="medical_general_v1",
        collected=collected,
        conversation=[],
        turn_count=1,
    )


def _empty_completeness():
    return CompletenessState(
        can_complete=False,
        required_missing=[
            "past_history", "allergy_history", "family_history",
            "personal_history", "marital_reproductive",
        ],
        recommended_missing=[],
        optional_missing=[],
        next_focus=None,
    )


@pytest.mark.asyncio
async def test_unconfirmed_cf_renders_as_pending_block():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腹痛",
        "past_history": "无",
        "family_history": "父亲糖尿病",
        "_carry_forward_meta": {
            "past_history": {"confirmed_by_patient": False, "source_record_id": 1},
            "family_history": {"confirmed_by_patient": False, "source_record_id": 1},
        },
    }
    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "张三", "gender": "男", "age": "30"}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=""),
    ):
        messages = await extractor.prompt_partial(
            session_state=_state(collected),
            completeness_state=_empty_completeness(),
            phase=("phase_1", "subjective"),
            mode="patient",
        )

    full_prompt = "\n".join(m.get("content", "") for m in messages)

    # The new "本次新填" block contains only the chief_complaint.
    assert '已收集（本次新填）：{"chief_complaint": "腹痛"}' in full_prompt
    # The carry-forward fields are NOT in the 已收集 block (they'd be there
    # if the split logic broke).
    assert '"past_history"' not in full_prompt.split("待确认")[0].split("已收集")[1]
    # The pending block exists, with the carried values quoted.
    assert "待确认（上次记录" in full_prompt
    assert '"无"' in full_prompt
    assert '"父亲糖尿病"' in full_prompt


@pytest.mark.asyncio
async def test_confirmed_cf_renders_normally():
    """When carry-forward fields ARE confirmed, they belong in 本次新填,
    not 待确认 — they're now first-class data."""
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腹痛",
        "past_history": "无",
        "_carry_forward_meta": {
            "past_history": {"confirmed_by_patient": True, "source_record_id": 1},
        },
    }
    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "张三", "gender": "男", "age": "30"}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=""),
    ):
        messages = await extractor.prompt_partial(
            session_state=_state(collected),
            completeness_state=_empty_completeness(),
            phase=("phase_1", "subjective"),
            mode="patient",
        )

    full_prompt = "\n".join(m.get("content", "") for m in messages)
    assert '"past_history": "无"' in full_prompt
    # The data block has the parenthesized label; substring "待确认" alone
    # is in the prompt rules (Rule 21.1 mentions 待确认 字段). Match the
    # specific block header instead.
    assert "待确认（上次记录" not in full_prompt


@pytest.mark.asyncio
async def test_no_cf_meta_renders_normally():
    """No _carry_forward_meta at all → no 待确认 block, simple 已收集."""
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "腹痛", "present_illness": "三天"}
    with patch(
        "domain.intake.templates.medical_general._load_patient_info",
        new=AsyncMock(return_value={"name": "张三", "gender": "男", "age": "30"}),
    ), patch(
        "domain.intake.templates.medical_general._load_previous_history",
        new=AsyncMock(return_value=""),
    ):
        messages = await extractor.prompt_partial(
            session_state=_state(collected),
            completeness_state=_empty_completeness(),
            phase=("phase_1", "subjective"),
            mode="patient",
        )

    full_prompt = "\n".join(m.get("content", "") for m in messages)
    # The data block has the parenthesized label; substring "待确认" alone
    # is in the prompt rules (Rule 21.1 mentions 待确认 字段). Match the
    # specific block header instead.
    assert "待确认（上次记录" not in full_prompt
    assert "已收集（本次新填）" in full_prompt
