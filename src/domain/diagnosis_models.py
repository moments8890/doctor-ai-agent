"""
Pydantic response models for the AI diagnosis pipeline.

Shared by diagnosis_pipeline.py and any caller that needs to type-hint
against the structured LLM output.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic response models for structured LLM output
# ---------------------------------------------------------------------------

class DiagnosisDifferential(BaseModel):
    condition: str = Field(description="Diagnosis name (brief label)")
    confidence: str = Field(default="中", description="Confidence level: 低/中/高")
    detail: str = Field(default="", description="Full description: clinical reasoning + plain explanation")


class DiagnosisWorkup(BaseModel):
    test: str = Field(description="Test/examination name (brief label)")
    detail: str = Field(default="", description="Full description: rationale + plain explanation")
    urgency: str = Field(default="常规", description="Urgency: 常规/紧急/急诊")


class DiagnosisTreatment(BaseModel):
    drug_class: str = Field(default="", description="Drug class (brief label)")
    intervention: str = Field(default="观察", description="Intervention type: 手术/药物/观察/转诊")
    detail: str = Field(default="", description="Full description: treatment rationale + plain explanation")


class DiagnosisLLMResponse(BaseModel):
    """Structured response from the diagnosis LLM."""
    differentials: List[DiagnosisDifferential] = Field(default_factory=list)
    workup: List[DiagnosisWorkup] = Field(default_factory=list)
    treatment: List[DiagnosisTreatment] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

# Valid confidence values; anything else is coerced to "中".
_VALID_CONFIDENCE = {"低", "中", "高"}

# Valid urgency values for workup items.
_VALID_URGENCY = {"常规", "紧急", "急诊"}

# Valid intervention values for treatment items.
_VALID_INTERVENTION = {"手术", "药物", "观察", "转诊"}

# Maximum items per array (per spec).
_MAX_ARRAY_ITEMS = 10
