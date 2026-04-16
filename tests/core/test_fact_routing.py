"""Unit tests for fact-branch routing: Pydantic contract, PII scrub, hash helpers."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock

from domain.knowledge.persona_classifier import (
    ClassifyResult,
    KbCategory,
    LearningType,
    PersonaField,
    classify_edit,
    compute_kb_pattern_hash,
    compute_pattern_hash,
)
from domain.knowledge.pending_common import scrub_pii


# ── ClassifyResult contract ─────────────────────────────────────────


def test_classify_result_style_requires_persona_field():
    with pytest.raises(ValueError, match="persona_field required"):
        ClassifyResult(
            type=LearningType.style,
            summary="x", confidence="high",
        )


def test_classify_result_style_rejects_kb_fields():
    with pytest.raises(ValueError, match="kb fields must be empty"):
        ClassifyResult(
            type=LearningType.style,
            persona_field=PersonaField.closing,
            summary="x", confidence="high",
            kb_category=KbCategory.diagnosis,
        )


def test_classify_result_factual_requires_kb_category():
    with pytest.raises(ValueError, match="kb_category required"):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            proposed_kb_rule="some rule longer than ten chars",
        )


def test_classify_result_factual_requires_non_empty_rule():
    with pytest.raises(ValueError, match="proposed_kb_rule required"):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            kb_category=KbCategory.diagnosis,
            proposed_kb_rule="   ",
        )


def test_classify_result_context_specific_rejects_all_learning_fields():
    with pytest.raises(ValueError, match="all learning fields must be empty"):
        ClassifyResult(
            type=LearningType.context_specific,
            persona_field=PersonaField.reply_style,
            summary="x", confidence="high",
        )


def test_classify_result_factual_valid():
    r = ClassifyResult(
        type=LearningType.factual,
        summary="修正了药名",
        confidence="high",
        kb_category=KbCategory.medication,
        proposed_kb_rule="硝苯地平而非氨氯地平",
    )
    assert r.type == LearningType.factual
    assert r.kb_category == KbCategory.medication
    assert r.persona_field is None


def test_classify_result_rule_too_long_fails():
    with pytest.raises(Exception):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            kb_category=KbCategory.custom,
            proposed_kb_rule="a" * 301,
        )


# ── Hash helpers ────────────────────────────────────────────────────


def test_kb_pattern_hash_differs_from_persona():
    p = compute_pattern_hash("closing", "foo")
    k = compute_kb_pattern_hash("closing", "foo")
    assert p != k


def test_persona_hash_stable():
    assert compute_pattern_hash("reply_style", "x") == compute_pattern_hash("reply_style", "x")


def test_kb_hash_stable():
    assert compute_kb_pattern_hash("medication", "x") == compute_kb_pattern_hash("medication", "x")


# ── PII scrub ───────────────────────────────────────────────────────


def test_scrub_pii_phone():
    out = scrub_pii("call me at 13800138000 tomorrow")
    assert "13800138000" not in out
    assert "[已脱敏]" in out


def test_scrub_pii_name_label():
    out = scrub_pii("姓名：张三去年手术")
    assert "张三" not in out
    assert "[已脱敏]" in out


def test_scrub_pii_idcard():
    out = scrub_pii("ID 110101199001011234 here")
    assert "110101199001011234" not in out


def test_scrub_pii_date():
    out = scrub_pii("术后2024-03-15复查")
    assert "2024-03-15" not in out


def test_scrub_pii_noop_on_clean_text():
    clean = "颅脑术后头痛患者不建议使用NSAIDs"
    assert scrub_pii(clean) == clean


def test_scrub_pii_empty_string():
    assert scrub_pii("") == ""


# ── classify_edit LLM integration (mocked) ──────────────────────────


async def test_classify_edit_rejects_identical_text():
    assert await classify_edit("same", "same") is None


async def test_classify_edit_rejects_empty():
    assert await classify_edit("", "b") is None
    assert await classify_edit("a", "") is None


async def test_classify_edit_returns_none_on_invalid_llm_output():
    from domain.knowledge import persona_classifier as pc

    with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
        # Patch the llm_call imported inside classify_edit
        with patch("agent.llm.llm_call", new=AsyncMock(return_value="not json")):
            r = await classify_edit("a", "b")
            assert r is None


async def test_classify_edit_parses_factual_response():
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "factual",
        "persona_field": "",
        "summary": "修正药名",
        "confidence": "high",
        "kb_category": "medication",
        "proposed_kb_rule": "硝苯地平而非氨氯地平",
    }
    with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
        with patch("agent.llm.llm_call", new=AsyncMock(return_value=json.dumps(payload))):
            r = await classify_edit("use A", "use B")
            assert r is not None
            assert r.type == LearningType.factual
            assert r.kb_category == KbCategory.medication
            assert r.persona_field is None


async def test_classify_edit_parses_style_response():
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "style",
        "persona_field": "closing",
        "summary": "删除祝福语",
        "confidence": "high",
        "kb_category": "",
        "proposed_kb_rule": "",
    }
    with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
        with patch("agent.llm.llm_call", new=AsyncMock(return_value=json.dumps(payload))):
            r = await classify_edit("a closing", "a")
            assert r is not None
            assert r.type == LearningType.style
            assert r.persona_field == PersonaField.closing


async def test_classify_edit_parses_context_specific_response():
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "context_specific",
        "persona_field": "",
        "summary": "针对特定患者",
        "confidence": "high",
        "kb_category": "",
        "proposed_kb_rule": "",
    }
    with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
        with patch("agent.llm.llm_call", new=AsyncMock(return_value=json.dumps(payload))):
            r = await classify_edit("a", "a with糖尿病 note")
            assert r is not None
            assert r.type == LearningType.context_specific


async def test_classify_edit_strips_markdown_fences():
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "style", "persona_field": "edits",
        "summary": "shorter", "confidence": "low",
        "kb_category": "", "proposed_kb_rule": "",
    }
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
        with patch("agent.llm.llm_call", new=AsyncMock(return_value=wrapped)):
            r = await classify_edit("a", "b")
            assert r is not None
            assert r.type == LearningType.style
