"""Field completeness — DEPRECATED shim.

Phase 2 moved this logic into domain.intake.templates.medical_general.
Re-exports derivations for legacy callers. Deletes one release after Phase 2.
"""
from __future__ import annotations

import warnings
from typing import Dict, List

warnings.warn(
    "domain.patients.completeness is deprecated; import from "
    "domain.intake.templates.medical_general instead.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor,
    MEDICAL_FIELDS,
)

# ---- Derive legacy constants from MEDICAL_FIELDS -------------------------

_by_tier: dict[str, tuple[str, ...]] = {
    tier: tuple(s.name for s in MEDICAL_FIELDS if s.tier == tier)
    for tier in ("required", "recommended", "optional")
}

_PATIENT_FIELDS = frozenset({
    "chief_complaint", "present_illness", "past_history",
    "allergy_history", "family_history", "personal_history",
    "marital_reproductive",
})

REQUIRED = _by_tier["required"]
SUBJECTIVE_RECOMMENDED = tuple(
    s.name for s in MEDICAL_FIELDS
    if s.tier == "recommended" and s.name in _PATIENT_FIELDS
)
SUBJECTIVE_OPTIONAL = tuple(
    s.name for s in MEDICAL_FIELDS
    if s.tier == "optional" and s.name in _PATIENT_FIELDS
)

DOCTOR_RECOMMENDED = _by_tier["recommended"]
DOCTOR_OPTIONAL = _by_tier["optional"]

OBJECTIVE = ("physical_exam", "specialist_exam", "auxiliary_exam")
ASSESSMENT = ("diagnosis",)
PLAN = ("treatment_plan", "orders_followup")

PATIENT_ALL = REQUIRED + SUBJECTIVE_RECOMMENDED + SUBJECTIVE_OPTIONAL
PATIENT_TOTAL = len(PATIENT_ALL)
DOCTOR_ALL = tuple(s.name for s in MEDICAL_FIELDS)
DOCTOR_TOTAL = len(DOCTOR_ALL)
ALL_COLLECTABLE = DOCTOR_ALL
TOTAL_FIELDS = DOCTOR_TOTAL

APPENDABLE = frozenset(s.name for s in MEDICAL_FIELDS if s.appendable)


_extractor = GeneralMedicalExtractor()


def check_completeness(collected: Dict[str, str], *, mode: str = "patient") -> List[str]:
    """DEPRECATED — use GeneralMedicalExtractor.completeness instead."""
    state = _extractor.completeness(collected, mode)
    if state.required_missing:
        return list(state.required_missing)
    return list(state.recommended_missing)


def get_completeness_state(collected: Dict[str, str], *, mode: str = "patient") -> dict:
    """DEPRECATED — use GeneralMedicalExtractor.completeness instead."""
    state = _extractor.completeness(collected, mode)
    return {
        "can_complete": state.can_complete,
        "required_missing": list(state.required_missing),
        "recommended_missing": list(state.recommended_missing),
        "optional_missing": list(state.optional_missing),
        "next_focus": state.next_focus,
    }


def count_filled(collected: Dict[str, str], *, mode: str = "patient") -> int:
    fields = DOCTOR_ALL if mode == "doctor" else PATIENT_ALL
    return sum(1 for f in fields if collected.get(f))


def total_fields(mode: str = "patient") -> int:
    return DOCTOR_TOTAL if mode == "doctor" else PATIENT_TOTAL


def merge_extracted(collected: Dict[str, str], extracted: Dict[str, str]) -> None:
    """DEPRECATED — use GeneralMedicalExtractor.merge instead. Mutates in-place, returns None."""
    _extractor.merge(collected, extracted)
