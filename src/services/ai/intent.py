"""Intent and IntentResult models — shared data types used by import/export handlers."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    create_patient = "create_patient"
    add_record = "add_record"
    update_record = "update_record"
    update_patient = "update_patient"
    query_records = "query_records"
    list_patients = "list_patients"
    import_history = "import_history"
    delete_patient = "delete_patient"
    list_tasks = "list_tasks"
    complete_task = "complete_task"
    schedule_appointment = "schedule_appointment"
    export_records = "export_records"
    export_outpatient_report = "export_outpatient_report"
    schedule_follow_up = "schedule_follow_up"
    postpone_task = "postpone_task"
    cancel_task = "cancel_task"
    help = "help"
    unknown = "unknown"


class IntentResult(BaseModel):
    intent: Intent
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    extra_data: dict = Field(default_factory=dict)
    chat_reply: Optional[str] = None
    structured_fields: Optional[dict] = None
    confidence: float = 1.0
