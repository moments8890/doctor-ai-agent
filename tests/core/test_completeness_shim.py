"""completeness.py shim — legacy constants + functions re-export from template."""
from __future__ import annotations

import warnings
import pytest


def test_shim_warns_on_import():
    import importlib
    import domain.patients.completeness as _c
    importlib.reload(_c)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(_c)
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )


def test_required_matches_template_required_tier():
    from domain.patients.completeness import REQUIRED
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    expected = {s.name for s in MEDICAL_FIELDS if s.tier == "required"}
    assert set(REQUIRED) == expected


def test_appendable_matches_template_appendable_attr():
    from domain.patients.completeness import APPENDABLE
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    expected = {s.name for s in MEDICAL_FIELDS if s.appendable}
    assert set(APPENDABLE) == expected


def test_check_completeness_still_works_and_returns_list():
    from domain.patients.completeness import check_completeness
    missing = check_completeness({}, mode="patient")
    assert isinstance(missing, list)
    assert "chief_complaint" in missing


def test_get_completeness_state_still_returns_dict():
    from domain.patients.completeness import get_completeness_state
    state = get_completeness_state({}, mode="patient")
    assert isinstance(state, dict)
    assert state["can_complete"] is False
    assert "chief_complaint" in state["required_missing"]


def test_merge_extracted_still_mutates_in_place():
    from domain.patients.completeness import merge_extracted
    collected = {"chief_complaint": "x"}
    merge_extracted(collected, {"diagnosis": "y"})
    assert collected["diagnosis"] == "y"


def test_subjective_recommended_has_expected_members():
    from domain.patients.completeness import SUBJECTIVE_RECOMMENDED
    assert "past_history" in SUBJECTIVE_RECOMMENDED
    assert "allergy_history" in SUBJECTIVE_RECOMMENDED


def test_doctor_recommended_matches_template_recommended_tier():
    from domain.patients.completeness import DOCTOR_RECOMMENDED
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    expected = {s.name for s in MEDICAL_FIELDS if s.tier == "recommended"}
    assert expected.issubset(set(DOCTOR_RECOMMENDED))
