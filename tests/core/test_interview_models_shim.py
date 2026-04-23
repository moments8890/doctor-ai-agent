"""interview_models.py shim — ExtractedClinicalFields now derives from MEDICAL_FIELDS."""
from __future__ import annotations

import warnings


def test_shim_warns_on_import():
    import importlib
    import domain.patients.interview_models as _m
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(_m)
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )


def test_extracted_clinical_fields_has_expected_fields():
    from domain.patients.interview_models import ExtractedClinicalFields
    names = set(ExtractedClinicalFields.model_fields.keys())
    assert "chief_complaint" in names
    assert "present_illness" in names
    assert "diagnosis" in names


def test_field_labels_matches_template():
    from domain.patients.interview_models import FIELD_LABELS
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    for spec in MEDICAL_FIELDS:
        if spec.label and spec.name != "department":
            assert FIELD_LABELS.get(spec.name) == spec.label


def test_field_meta_preserves_hint_and_example():
    from domain.patients.interview_models import FIELD_META
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    for spec in MEDICAL_FIELDS:
        if spec.name == "department":
            continue  # department excluded from FIELD_META (no legacy entry)
        meta = FIELD_META.get(spec.name, {})
        if spec.example:
            assert meta.get("example") == spec.example
        if spec.description:
            assert meta.get("hint") == spec.description


def test_interview_llm_response_still_parseable():
    from domain.patients.interview_models import InterviewLLMResponse
    obj = InterviewLLMResponse(reply="hi", suggestions=[])
    assert obj.reply == "hi"


def test_max_turns_constant_preserved():
    from domain.patients.interview_models import MAX_TURNS
    assert MAX_TURNS == 30


def test_build_progress_still_works():
    from domain.patients.interview_models import _build_progress
    p = _build_progress({"chief_complaint": "x"}, mode="patient")
    assert p["filled"] >= 1
    assert "total" in p


def test_interview_response_dataclass_preserved():
    from domain.patients.interview_models import InterviewResponse
    r = InterviewResponse(
        reply="x", collected={}, progress={"filled": 0, "total": 7},
        status="interviewing",
    )
    assert r.reply == "x"
