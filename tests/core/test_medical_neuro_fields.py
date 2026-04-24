"""NEURO_EXTRA_FIELDS and NEURO_FIELDS — Task 3 field-spec semantics.

These lock the neuro field schema so future edits can't silently drop
required-ness, appendability, or carry-forward behavior.
"""
from __future__ import annotations

from domain.interview.templates.medical_general import MEDICAL_FIELDS
from domain.interview.templates.medical_neuro import (
    NEURO_EXTRA_FIELDS, NEURO_FIELDS,
)


def test_neuro_extra_fields_has_exactly_three_specs():
    assert len(NEURO_EXTRA_FIELDS) == 3


def test_neuro_extra_field_names():
    names = [s.name for s in NEURO_EXTRA_FIELDS]
    assert names == ["onset_time", "neuro_exam", "vascular_risk_factors"]


def test_neuro_fields_is_base_plus_extras_preserving_order():
    assert NEURO_FIELDS == [*MEDICAL_FIELDS, *NEURO_EXTRA_FIELDS]
    # Independent list identity (not mutating MEDICAL_FIELDS)
    assert NEURO_FIELDS is not MEDICAL_FIELDS
    # Order check: all base fields come first, extras last
    assert [s.name for s in NEURO_FIELDS[: len(MEDICAL_FIELDS)]] == [
        s.name for s in MEDICAL_FIELDS
    ]
    assert [s.name for s in NEURO_FIELDS[len(MEDICAL_FIELDS):]] == [
        "onset_time", "neuro_exam", "vascular_risk_factors",
    ]


def test_onset_time_is_required_and_not_appendable():
    spec = next(s for s in NEURO_EXTRA_FIELDS if s.name == "onset_time")
    assert spec.tier == "required"
    assert spec.appendable is False


def test_vascular_risk_factors_carry_forward_doctor_only():
    spec = next(
        s for s in NEURO_EXTRA_FIELDS if s.name == "vascular_risk_factors"
    )
    assert "doctor" in spec.carry_forward_modes
    assert "patient" not in spec.carry_forward_modes


def test_neuro_exam_is_appendable():
    spec = next(s for s in NEURO_EXTRA_FIELDS if s.name == "neuro_exam")
    assert spec.appendable is True
