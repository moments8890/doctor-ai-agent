from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class MedicalRecord(BaseModel):
    chief_complaint: str = Field(..., min_length=1, max_length=2000)
    history_of_present_illness: Optional[str] = Field(default=None, max_length=8000)
    past_medical_history: Optional[str] = Field(default=None, max_length=8000)
    physical_examination: Optional[str] = Field(default=None, max_length=8000)
    auxiliary_examinations: Optional[str] = Field(default=None, max_length=8000)
    diagnosis: Optional[str] = Field(default=None, max_length=4000)
    treatment_plan: Optional[str] = Field(default=None, max_length=4000)
    follow_up_plan: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("chief_complaint")
    @classmethod
    def _strip_chief_complaint(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("chief_complaint cannot be empty")
        return stripped
