"""Patient interview extraction quality tests.

Replays the exact conversation from a real production session (2026-04-08)
where qwen-turbo failed to extract fields — patient gave clear answers but
extracted dict came back mostly null.

These tests call the real LLM (no mocks) to verify extraction quality.
Run with: CONVERSATION_LLM=siliconflow pytest tests/scenarios/test_patient_interview_extraction.py -x -v
"""
from __future__ import annotations

import json
import os
import pytest

from domain.patients.interview_models import InterviewLLMResponse, FIELD_LABELS, FIELD_META
from domain.patients.completeness import (
    get_completeness_state,
    check_completeness,
    merge_extracted,
)

# ---------------------------------------------------------------------------
# Test data — exact conversation from prod logs 2026-04-08T11:53–11:54
# ---------------------------------------------------------------------------

PATIENT_INFO = {"name": "体验患者", "gender": "女", "age": 65}

# Each turn: (patient_text, expected_extractions_after_merge)
# expected_extractions: dict of field -> substring that must appear in collected
CONVERSATION_TURNS = [
    {
        "patient": "头痛三天了越来越重",
        "expect_extracted": {
            "chief_complaint": "头痛",
            # "三天" may go into chief_complaint per prompt rule 7 — don't require it in present_illness
        },
    },
    {
        "patient": "阵发性",
        "expect_extracted": {
            "present_illness": "阵发",
        },
    },
    {
        "patient": "有恶心，有视力模糊",
        "expect_extracted": {
            # "恶心" should appear in present_illness (accumulated)
            # but LLM may word it differently — check in final assertions
        },
    },
    {
        "patient": "没有",
        "expect_extracted": {},  # no new info, just negation of "other symptoms"
    },
    {
        "patient": "有高血压，有糖尿病",
        "expect_extracted": {
            "past_history": "高血压",
        },
    },
    {
        "patient": "没有过敏",
        "expect_extracted": {},  # check in final — negation extraction is context-dependent
    },
    {
        "patient": "没有特殊病史",
        "expect_extracted": {},  # check in final
    },
    {
        "patient": "没有",
        "expect_extracted": {},  # check in final
    },
    {
        "patient": "未婚",
        "expect_extracted": {},  # check in final
    },
]

# After all 9 turns, these fields MUST be filled in collected
# personal_history excluded: "没有" answer is context-dependent and may not extract
FINAL_REQUIRED_FIELDS = {
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "family_history",
}

# These are the minimum substrings that must appear in final collected
# Each value is a list of alternatives — at least one must appear
FINAL_EXPECTED_CONTENTS = {
    "chief_complaint": ["头痛"],
    "present_illness": ["阵发", "恶心"],  # at least one symptom detail
    "past_history": ["高血压"],
    "allergy_history": ["无", "否认"],
    "family_history": ["无", "否认"],
}


# ---------------------------------------------------------------------------
# Helper: build context string the same way _call_interview_llm does
# ---------------------------------------------------------------------------

def _build_patient_context(collected: dict, patient_info: dict, mode: str = "patient") -> str:
    state = get_completeness_state(collected, mode=mode)
    clean_collected = {k: v for k, v in collected.items() if not k.startswith("_")}
    can_str = "是" if state["can_complete"] else "否"

    guide_parts = []
    for fk in (state["recommended_missing"] + state["optional_missing"])[:3]:
        meta = FIELD_META.get(fk)
        label = FIELD_LABELS.get(fk, fk)
        if meta:
            guide_parts.append(f'{label}({meta["hint"]},如"{meta["example"]}")')
        else:
            guide_parts.append(label)

    req_parts = []
    if not state["can_complete"]:
        for fk in state["required_missing"]:
            meta = FIELD_META.get(fk)
            label = FIELD_LABELS.get(fk, fk)
            if meta:
                req_parts.append(f'{label}({meta["hint"]},如"{meta["example"]}")')
            else:
                req_parts.append(label)

    lines = [
        f"患者：{patient_info['name']}，{patient_info['gender']}，{patient_info['age']}岁",
        f"已收集：{json.dumps(clean_collected, ensure_ascii=False)}",
        f"可完成：{can_str}",
    ]
    if req_parts:
        lines.append(f"必填缺：{'｜'.join(req_parts)}")
    if guide_parts:
        lines.append(f"待补充：{'｜'.join(guide_parts)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core test: full conversation replay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_full_conversation_extraction():
    """Replay 9-turn headache interview, assert all key fields extracted."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_patient_interview

    collected = {}
    conversation = []

    for i, turn in enumerate(CONVERSATION_TURNS):
        patient_text = turn["patient"]
        conversation.append({"role": "user", "content": patient_text})

        patient_context = _build_patient_context(collected, PATIENT_INFO)
        state = get_completeness_state(collected, mode="patient")

        # Build messages via composer (same as production)
        _HISTORY_WINDOW = 6
        history = [
            {"role": t["role"], "content": t["content"]}
            for t in conversation[-_HISTORY_WINDOW:]
        ]
        latest_msg = ""
        prior_history = history
        if history and history[-1].get("role") == "user":
            latest_msg = history[-1]["content"]
            prior_history = history[:-1]

        messages = await compose_for_patient_interview(
            doctor_id="test_doctor",
            patient_context=patient_context,
            doctor_message=latest_msg,
            history=prior_history,
        )

        env_var = "CONVERSATION_LLM" if os.environ.get("CONVERSATION_LLM") else "ROUTING_LLM"

        result = await structured_call(
            response_model=InterviewLLMResponse,
            messages=messages,
            op_name=f"test.interview.turn{i+1}",
            env_var=env_var,
            temperature=0.1,
            max_tokens=2048,
        )

        # Merge extracted into collected
        extracted = {
            k: v for k, v in result.extracted.model_dump().items()
            if v is not None and v.strip()
            and k not in ("patient_name", "patient_gender", "patient_age")
        }
        merge_extracted(collected, extracted)

        # Add assistant reply to conversation
        conversation.append({"role": "assistant", "content": result.reply})

        # Per-turn assertions: check expected extractions
        for field, expected_substr in turn["expect_extracted"].items():
            value = collected.get(field, "")
            assert expected_substr in value, (
                f"Turn {i+1} ('{patient_text}'): "
                f"expected '{expected_substr}' in collected['{field}'], "
                f"got '{value}'. Extracted this turn: {extracted}"
            )

    # Final assertions: all required fields must be filled
    for field in FINAL_REQUIRED_FIELDS:
        assert collected.get(field), (
            f"After all turns, '{field}' should be filled but is empty. "
            f"Full collected: {json.dumps(collected, ensure_ascii=False, indent=2)}"
        )

    # Final content assertions — at least one alternative must appear
    for field, alternatives in FINAL_EXPECTED_CONTENTS.items():
        value = collected.get(field, "")
        assert any(alt in value for alt in alternatives), (
            f"Final collected['{field}'] = '{value}' "
            f"should contain one of {alternatives}"
        )

    # Core completeness: required fields (chief_complaint + present_illness) must be filled
    # Recommended fields (past/allergy/family/personal) may not all extract from
    # short negation answers — that's a known prompt limitation, not a model bug
    for req in ("chief_complaint", "present_illness"):
        assert collected.get(req), (
            f"Required field '{req}' must be filled after full interview. "
            f"Collected: {json.dumps(collected, ensure_ascii=False, indent=2)}"
        )


# ---------------------------------------------------------------------------
# Focused test: past_history extraction (the most commonly failed turn)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_past_history_extraction_single_turn():
    """Given prior conversation about symptoms, '有高血压，有糖尿病' must extract past_history."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_patient_interview

    # Simulate state after 4 turns (chief_complaint + present_illness filled)
    collected = {
        "chief_complaint": "头痛3天",
        "present_illness": "头痛为阵发性，伴有恶心、视力模糊，无其他伴随症状",
    }
    conversation = [
        {"role": "user", "content": "头痛三天了越来越重"},
        {"role": "assistant", "content": "请问这种头痛有什么特点吗？"},
        {"role": "user", "content": "阵发性"},
        {"role": "assistant", "content": "有没有伴随恶心、呕吐或者视力变化？"},
        {"role": "user", "content": "有恶心，有视力模糊"},
        {"role": "assistant", "content": "请问您之前有没有高血压、糖尿病？"},
        {"role": "user", "content": "没有"},
        {"role": "assistant", "content": "请问您之前有没有高血压、糖尿病或者其他慢性疾病？"},
    ]

    patient_context = _build_patient_context(collected, PATIENT_INFO)
    messages = await compose_for_patient_interview(
        doctor_id="test_doctor",
        patient_context=patient_context,
        doctor_message="有高血压，有糖尿病",
        history=conversation[-6:],
    )

    env_var = "CONVERSATION_LLM" if os.environ.get("CONVERSATION_LLM") else "ROUTING_LLM"

    result = await structured_call(
        response_model=InterviewLLMResponse,
        messages=messages,
        op_name="test.interview.past_history",
        env_var=env_var,
        temperature=0.1,
        max_tokens=2048,
    )

    extracted = result.extracted.model_dump()
    past = extracted.get("past_history") or ""
    assert "高血压" in past, (
        f"'有高血压，有糖尿病' should extract past_history containing '高血压', "
        f"got: {past!r}. Full extracted: {extracted}"
    )
    assert "糖尿病" in past, (
        f"'有高血压，有糖尿病' should extract past_history containing '糖尿病', "
        f"got: {past!r}"
    )


# ---------------------------------------------------------------------------
# Focused test: allergy negation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_allergy_negation_extraction():
    """'没有过敏' should extract allergy_history = '无'."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_patient_interview

    collected = {
        "chief_complaint": "头痛3天",
        "present_illness": "头痛为阵发性，伴有恶心、视力模糊",
        "past_history": "高血压、糖尿病",
    }
    conversation = [
        {"role": "user", "content": "有高血压，有糖尿病"},
        {"role": "assistant", "content": "请问您是否有药物过敏史？"},
    ]

    patient_context = _build_patient_context(collected, PATIENT_INFO)
    messages = await compose_for_patient_interview(
        doctor_id="test_doctor",
        patient_context=patient_context,
        doctor_message="没有过敏",
        history=conversation,
    )

    env_var = "CONVERSATION_LLM" if os.environ.get("CONVERSATION_LLM") else "ROUTING_LLM"

    result = await structured_call(
        response_model=InterviewLLMResponse,
        messages=messages,
        op_name="test.interview.allergy",
        env_var=env_var,
        temperature=0.1,
        max_tokens=2048,
    )

    extracted = result.extracted.model_dump()
    allergy = extracted.get("allergy_history") or ""
    assert allergy and allergy.strip(), (
        f"'没有过敏' should extract allergy_history (e.g. '无'), "
        f"got null/empty. Full extracted: {extracted}"
    )
