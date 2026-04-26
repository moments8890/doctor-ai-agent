"""Tests for the deterministic extraction_confidence calculator.

Replaces LLM self-reported confidence — see Codex round 2 pushback in
the chat-intake merge spec. Denominator is the count of required
history fields (7); doctor UI displays this as N/7, not as a percent.
"""
from domain.patient_lifecycle.extraction_confidence import calculate


def test_all_seven_fields_filled_returns_one():
    fields = {
        "chief_complaint": "头痛",
        "present_illness": "三天",
        "past_history": "无",
        "allergy_history": "无",
        "personal_history": "无",
        "marital_reproductive": "已婚",
        "family_history": "无",
    }
    assert calculate(fields) == 1.0


def test_three_of_seven_returns_three_sevenths():
    fields = {
        "chief_complaint": "头痛",
        "present_illness": "三天",
        "past_history": "无",
    }
    result = calculate(fields)
    assert abs(result - 3 / 7) < 1e-9


def test_empty_strings_dont_count():
    fields = {"chief_complaint": "头痛", "present_illness": "", "past_history": "  "}
    assert calculate(fields) == 1 / 7


def test_none_values_dont_count():
    fields = {"chief_complaint": "头痛", "present_illness": None}
    assert calculate(fields) == 1 / 7


def test_unknown_fields_ignored():
    # Fields not in the required-history set should be ignored — only
    # the 7 names in REQUIRED_FIELDS contribute to the score.
    fields = {"chief_complaint": "头痛", "diagnosis": "should be ignored"}
    assert calculate(fields) == 1 / 7


def test_empty_dict_returns_zero():
    assert calculate({}) == 0.0
