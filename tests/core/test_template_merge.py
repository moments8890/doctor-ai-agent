"""GeneralMedicalExtractor.merge — inline logic using FieldSpec.appendable."""
from __future__ import annotations

import pytest

from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_merge_appends_appendable_fields(extractor):
    collected = {"present_illness": "头痛3天"}
    result = extractor.merge(collected, {"present_illness": "无发热"})
    assert "头痛3天" in result["present_illness"]
    assert "无发热" in result["present_illness"]
    assert "；" in result["present_illness"]


def test_merge_overwrites_non_appendable_fields(extractor):
    collected = {"chief_complaint": "头痛"}
    result = extractor.merge(collected, {"chief_complaint": "发热"})
    assert result["chief_complaint"] == "发热"


def test_merge_skips_duplicate_values_on_appendable(extractor):
    collected = {"present_illness": "头痛3天"}
    result = extractor.merge(collected, {"present_illness": "头痛"})
    assert result["present_illness"] == "头痛3天"


def test_merge_ignores_unknown_fields(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"not_a_real_field": "y"})
    assert "not_a_real_field" not in result


def test_merge_ignores_empty_values(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"chief_complaint": "", "diagnosis": None})
    assert result["chief_complaint"] == "x"
    assert "diagnosis" not in result


def test_merge_returns_same_dict_instance(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"diagnosis": "y"})
    assert result is collected


def test_merge_trims_whitespace(extractor):
    collected = {}
    result = extractor.merge(collected, {"chief_complaint": "  头痛  "})
    assert result["chief_complaint"] == "头痛"
