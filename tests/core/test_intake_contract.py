"""build_response_schema — synthesizes a per-call Pydantic class from FieldSpec list.

Spec: §3e. Class is throwaway; callers parse LLM output through it then
convert to dict before anything downstream touches the value.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.intake.contract import build_response_schema
from domain.intake.protocols import FieldSpec


def _spec(**kw):
    kw.setdefault("description", "")
    return FieldSpec(**kw)


def test_build_accepts_empty_list():
    Model = build_response_schema([])
    obj = Model()
    assert obj.model_dump() == {}


def test_string_field_nullable_when_not_required():
    Model = build_response_schema([
        _spec(name="chief_complaint", type="string", tier="optional"),
    ])
    # None is allowed because tier != "required"
    obj = Model(chief_complaint=None)
    assert obj.chief_complaint is None


def test_all_fields_are_optional_regardless_of_tier():
    """Per-turn LLM response schema treats ALL fields as Optional — tier is
    about final-state completeness, not per-call contract."""
    Model = build_response_schema([
        _spec(name="chief_complaint", type="string", tier="required"),
    ])
    # Missing required-tier field is OK in a per-turn response
    obj = Model()
    assert obj.chief_complaint is None


def test_enum_field_rejects_out_of_vocabulary():
    Model = build_response_schema([
        _spec(
            name="severity", type="enum",
            enum_values=("mild", "moderate", "severe"),
            tier="required",
        ),
    ])
    with pytest.raises(ValidationError):
        Model(severity="extreme")

    obj = Model(severity="moderate")
    assert obj.severity == "moderate"


def test_number_field_coerces_string_digits():
    Model = build_response_schema([
        _spec(name="age", type="number", tier="optional"),
    ])
    # Pydantic's int coercion accepts digit strings
    obj = Model(age="42")
    assert obj.age == 42


def test_text_field_same_as_string_for_validation():
    # type="text" is a hint to the LLM (long-form). Validation is string.
    Model = build_response_schema([
        _spec(name="present_illness", type="text", tier="optional"),
    ])
    obj = Model(present_illness="long paragraph...")
    assert obj.present_illness == "long paragraph..."


def test_description_is_carried_to_field_info():
    Model = build_response_schema([
        _spec(
            name="chief_complaint", type="string", tier="optional",
            description="Patient's primary symptom in their own words.",
        ),
    ])
    info = Model.model_fields["chief_complaint"]
    assert info.description == "Patient's primary symptom in their own words."


def test_repeated_calls_produce_independent_classes():
    fields = [_spec(name="x", type="string", tier="optional")]
    A = build_response_schema(fields)
    B = build_response_schema(fields)
    assert A is not B
    assert A.model_fields.keys() == B.model_fields.keys()


def test_unknown_type_raises_at_build_time():
    # We should catch drift early, not at LLM call time.
    # FieldSpec vocab is already Literal-constrained, but if someone extends
    # the vocab in FieldSpec without updating build_response_schema, the
    # helper must explode loudly.
    bad = FieldSpec.model_construct(
        name="x", type="unsupported_type",
        description="", tier="optional", appendable=False,
        carry_forward_modes=frozenset(), enum_values=None, label=None,
        example=None,
    )
    with pytest.raises(ValueError, match="unsupported"):
        build_response_schema([bad])
