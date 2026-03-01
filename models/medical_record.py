from pydantic import BaseModel
from typing import Optional


class MedicalRecord(BaseModel):
    chief_complaint: str
    history_of_present_illness: Optional[str] = None
    past_medical_history: Optional[str] = None
    physical_examination: Optional[str] = None
    auxiliary_examinations: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    follow_up_plan: Optional[str] = None
