"""MEDICAL_FIELDS translates scattered medical metadata into a FieldSpec list.

No behavior change vs. the pre-phase-1 code — these tests lock the semantics
so Phase 2 refactors can't accidentally drop a field or flip an append rule.
"""
from __future__ import annotations

import pytest

from domain.interview.templates.medical_general import MEDICAL_FIELDS
from domain.patients.completeness import APPENDABLE, REQUIRED
from domain.patients.interview_models import (
    ExtractedClinicalFields, FIELD_LABELS, FIELD_META,
)
from channels.web.doctor_interview.shared import _CARRY_FORWARD_FIELDS


def test_every_extracted_field_has_a_spec():
    pydantic_names = {
        n for n in ExtractedClinicalFields.model_fields.keys()
        # patient_name/gender/age are metadata, not clinical fields
        if not n.startswith("patient_")
    }
    spec_names = {s.name for s in MEDICAL_FIELDS}
    assert pydantic_names <= spec_names, (
        f"Fields missing a FieldSpec: {pydantic_names - spec_names}"
    )


def test_no_extra_clinical_specs():
    clinical_spec_names = {
        s.name for s in MEDICAL_FIELDS if not s.name.startswith("_")
    }
    pydantic_names = set(ExtractedClinicalFields.model_fields.keys())
    pydantic_names |= {"patient_name", "patient_gender", "patient_age"}
    assert clinical_spec_names <= pydantic_names, (
        f"Spurious FieldSpecs: {clinical_spec_names - pydantic_names}"
    )


def test_required_tier_matches_completeness_required():
    required_spec_names = {s.name for s in MEDICAL_FIELDS if s.tier == "required"}
    assert required_spec_names == set(REQUIRED)


def test_appendable_flag_matches_completeness_appendable():
    appendable_spec_names = {s.name for s in MEDICAL_FIELDS if s.appendable}
    assert appendable_spec_names == set(APPENDABLE)


def test_carry_forward_matches_shared_carry_forward():
    carry_spec_names = {
        s.name for s in MEDICAL_FIELDS if "doctor" in s.carry_forward_modes
    }
    assert carry_spec_names == set(_CARRY_FORWARD_FIELDS)


def test_every_spec_has_label():
    for s in MEDICAL_FIELDS:
        assert s.label, f"FieldSpec({s.name}): label required for UI"


def test_every_spec_has_description():
    for s in MEDICAL_FIELDS:
        assert s.description, f"FieldSpec({s.name}): description required for LLM prompt"


def test_labels_match_field_labels_dict():
    for s in MEDICAL_FIELDS:
        if s.name in FIELD_LABELS:
            assert s.label == FIELD_LABELS[s.name], (
                f"{s.name}: label drift vs FIELD_LABELS"
            )


def test_descriptions_prefer_field_meta_hint():
    # When FIELD_META has a hint for the field, the FieldSpec's description
    # must incorporate that hint (substring match) so LLM prompt behavior
    # stays identical.
    for s in MEDICAL_FIELDS:
        meta = FIELD_META.get(s.name)
        if meta and meta.get("hint"):
            assert meta["hint"] in s.description, (
                f"{s.name}: description missing FIELD_META hint text"
            )


def test_examples_prefer_field_meta_example():
    for s in MEDICAL_FIELDS:
        meta = FIELD_META.get(s.name)
        if meta and meta.get("example"):
            assert s.example == meta["example"]
