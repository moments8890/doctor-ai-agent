"""Interview Pydantic models + field metadata — DEPRECATED shim.

Phase 2 moved the canonical schema into domain.interview.templates.medical_general.
This module re-exports derivations for legacy callers. _build_progress and
the dataclasses remain because they're still used by the legacy turn loop
in interview_turn.py (Phase 2.5 deletes it).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

warnings.warn(
    "domain.patients.interview_models is deprecated; import from "
    "domain.interview.templates.medical_general instead.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.interview.contract import build_response_schema
from domain.interview.templates.medical_general import MEDICAL_FIELDS

MAX_TURNS = 30


# ---- ExtractedClinicalFields: derived from MEDICAL_FIELDS ------------------

_ClinicalBase = build_response_schema(MEDICAL_FIELDS)


class ExtractedClinicalFields(_ClinicalBase):  # type: ignore[misc,valid-type]
    """Legacy alias over build_response_schema(MEDICAL_FIELDS).

    Overrides the two 'required' tier fields (chief_complaint, present_illness)
    to Optional so that zero-arg construction works — the LLM sometimes emits
    partial turns and the default_factory must not raise.

    Adds back patient_name/gender/age — engine-level metadata (not in
    MEDICAL_FIELDS) that the LLM prompt still asks for.
    """
    # required-tier fields: make Optional so default_factory=ExtractedClinicalFields works
    chief_complaint: Optional[str] = Field(None, description="主诉：主要症状+持续时间")
    present_illness: Optional[str] = Field(None, description="现病史：症状详情、检查结果、用药")

    patient_name: Optional[str] = Field(None, description="患者姓名")
    patient_gender: Optional[str] = Field(None, description="患者性别（男/女）")
    patient_age: Optional[str] = Field(None, description="患者年龄")


class InterviewLLMResponse(BaseModel):
    """Structured response from the interview LLM."""

    reply: str = Field(
        default="请继续描述您的情况。",
        description="给医生或患者的自然语言回复",
    )
    extracted: ExtractedClinicalFields = Field(
        default_factory=ExtractedClinicalFields,
        description="本轮新提取的病历字段",
    )
    suggestions: List[str] = Field(default_factory=list)


# ---- Derived metadata dicts ------------------------------------------------

FIELD_LABELS: Dict[str, str] = {
    s.name: s.label
    for s in MEDICAL_FIELDS
    if s.label and s.name != "department"
}

FIELD_META: Dict[str, dict] = {
    s.name: {
        "hint": s.description,
        "example": s.example,
        "tier": s.tier,
    }
    for s in MEDICAL_FIELDS
    if s.description and s.name != "department"
}

_FIELD_PRIORITY: Dict[str, str] = {
    s.name: s.tier
    for s in MEDICAL_FIELDS
    if s.name != "department"
}

_PATIENT_PHASES = [
    ("主诉与现病史", ["chief_complaint", "present_illness"]),
    ("病史采集", ["past_history", "allergy_history", "family_history", "personal_history"]),
    ("补充信息", ["marital_reproductive"]),
]


# ---- _build_progress — used by legacy turn loop ----------------------------

def _build_progress(collected: Dict[str, str], mode: str = "patient") -> dict:
    """Build structured progress metadata for UI rendering."""
    from domain.patients.completeness import (
        REQUIRED, DOCTOR_RECOMMENDED,
        SUBJECTIVE_RECOMMENDED,
    )

    _PATIENT_FIELDS = {
        "chief_complaint", "present_illness", "past_history",
        "allergy_history", "family_history", "personal_history", "marital_reproductive",
    }
    fields = {}
    for key, priority in _FIELD_PRIORITY.items():
        if mode == "patient" and key not in _PATIENT_FIELDS:
            continue
        fields[key] = {
            "status": "filled" if collected.get(key) else "empty",
            "priority": priority,
            "label": FIELD_LABELS.get(key, key),
        }

    filled = sum(1 for f in fields.values() if f["status"] == "filled")
    total = len(fields)
    pct = int(round(filled / total * 100)) if total else 0

    phase = "完成"
    if mode == "patient":
        for phase_name, phase_fields in _PATIENT_PHASES:
            if any(not collected.get(f) for f in phase_fields):
                phase = phase_name
                break

    can_complete = all(collected.get(f) for f in REQUIRED)

    if mode == "doctor":
        req_fields = list(REQUIRED)
        rec_fields = [f for f in DOCTOR_RECOMMENDED if f not in REQUIRED]
    else:
        req_fields = list(REQUIRED)
        rec_fields = [f for f in SUBJECTIVE_RECOMMENDED if f not in REQUIRED]

    required_count = sum(1 for f in req_fields if collected.get(f))
    required_total = len(req_fields)
    recommended_count = sum(1 for f in rec_fields if collected.get(f))
    recommended_total = len(rec_fields)

    return {
        "filled": filled,
        "total": total,
        "pct": pct,
        "phase": phase,
        "fields": fields,
        "can_complete": can_complete,
        "required_count": required_count,
        "required_total": required_total,
        "recommended_count": recommended_count,
        "recommended_total": recommended_total,
    }


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: dict
    status: str
    missing: List[str] = None
    suggestions: List[str] = None
    ready_to_review: bool = False
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[str] = None
    retryable: bool = False
