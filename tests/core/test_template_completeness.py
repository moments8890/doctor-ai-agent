"""GeneralMedicalExtractor.completeness — inline tier-based logic."""
from __future__ import annotations

import pytest

from domain.interview.protocols import CompletenessState
from domain.interview.templates.medical_general import GeneralMedicalExtractor


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_completeness_empty_doctor_mode(extractor):
    state = extractor.completeness({}, "doctor")
    assert isinstance(state, CompletenessState)
    assert state.can_complete is False
    assert "chief_complaint" in state.required_missing
    assert "present_illness" in state.required_missing


def test_completeness_empty_patient_mode(extractor):
    state = extractor.completeness({}, "patient")
    assert state.can_complete is False
    assert "chief_complaint" in state.required_missing


def test_completeness_required_filled_doctor(extractor):
    state = extractor.completeness(
        {"chief_complaint": "x", "present_illness": "y"}, "doctor",
    )
    assert state.can_complete is True
    assert state.required_missing == []
    assert "past_history" in state.recommended_missing


def test_completeness_required_filled_patient(extractor):
    state = extractor.completeness(
        {"chief_complaint": "x", "present_illness": "y"}, "patient",
    )
    assert state.can_complete is True
    assert "past_history" in state.recommended_missing
    assert "physical_exam" not in state.recommended_missing
    assert "physical_exam" not in state.optional_missing


def test_completeness_next_focus_is_first_recommended_missing(extractor):
    state = extractor.completeness(
        {"chief_complaint": "x", "present_illness": "y"}, "doctor",
    )
    assert state.next_focus in state.recommended_missing


def test_completeness_next_focus_falls_back_to_optional(extractor):
    filled = {
        "chief_complaint": "x", "present_illness": "y",
        "past_history": "x", "allergy_history": "x", "family_history": "x",
        "personal_history": "x", "physical_exam": "x", "diagnosis": "x",
        "treatment_plan": "x",
    }
    state = extractor.completeness(filled, "doctor")
    assert state.recommended_missing == []
    if state.optional_missing:
        assert state.next_focus == state.optional_missing[0]


def test_completeness_no_patient_mode_leak_of_doctor_fields(extractor):
    state = extractor.completeness({}, "patient")
    doctor_only = {
        "physical_exam", "specialist_exam", "auxiliary_exam",
        "diagnosis", "treatment_plan", "orders_followup",
    }
    all_mentioned = (
        set(state.required_missing)
        | set(state.recommended_missing)
        | set(state.optional_missing)
    )
    assert doctor_only.isdisjoint(all_mentioned)
