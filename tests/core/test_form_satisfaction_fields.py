"""FORM_SATISFACTION_FIELDS — 5 declarative fields for the satisfaction survey."""
from __future__ import annotations

from domain.intake.protocols import FieldSpec
from domain.intake.templates.form_satisfaction import FORM_SATISFACTION_FIELDS


def test_has_five_fields():
    assert len(FORM_SATISFACTION_FIELDS) == 5


def test_overall_rating_is_required_enum():
    spec = next(s for s in FORM_SATISFACTION_FIELDS if s.name == "overall_rating")
    assert spec.tier == "required"
    assert spec.type == "enum"
    assert spec.enum_values is not None
    assert "非常满意" in spec.enum_values
    assert "非常不满意" in spec.enum_values


def test_comments_is_optional_text():
    spec = next(s for s in FORM_SATISFACTION_FIELDS if s.name == "comments")
    assert spec.tier == "optional"
    assert spec.type == "text"
    assert spec.appendable is False


def test_no_carry_forward():
    for spec in FORM_SATISFACTION_FIELDS:
        assert spec.carry_forward_modes == frozenset()


def test_all_fields_have_labels_and_descriptions():
    for spec in FORM_SATISFACTION_FIELDS:
        assert spec.label, f"{spec.name}: label required"
        assert spec.description, f"{spec.name}: description required"
