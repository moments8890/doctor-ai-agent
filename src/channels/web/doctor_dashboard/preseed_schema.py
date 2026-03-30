"""Pydantic models for validating preseed_data.json at load time."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class SeedSuggestion(BaseModel):
    section: str  # differential | workup | treatment
    content: str
    detail: str  # may contain [KB-1] / [KB-2] placeholders
    confidence: str  # 高 | 中 | 低
    urgency: Optional[str] = None
    intervention: Optional[str] = None


class SeedRecord(BaseModel):
    key: str
    record_type: str  # visit | interview_summary
    status: str  # completed | pending_review
    days_ago: int  # relative timestamp
    department: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    past_history: Optional[str] = None
    allergy_history: Optional[str] = None
    personal_history: Optional[str] = None
    marital_reproductive: Optional[str] = None
    family_history: Optional[str] = None
    physical_exam: Optional[str] = None
    specialist_exam: Optional[str] = None
    auxiliary_exam: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    orders_followup: Optional[str] = None
    content: Optional[str] = None
    suggestions: List[SeedSuggestion] = []


class SeedMessage(BaseModel):
    content: str  # patient's message
    triage: str  # routine | info | question | urgent | concern
    auto_send: bool  # True → AI auto-replied, False → draft for doctor
    ai_reply: str  # AI reply text (may contain [KB-N] placeholders)
    days_ago: int = 0


class SeedTask(BaseModel):
    title: str
    task_type: str  # follow_up | checkup | general
    due_days: int  # days from now until due
    content: Optional[str] = None
    status: str = "pending"  # pending | completed


class SeedPatient(BaseModel):
    key: str
    name: str
    gender: str  # male | female
    age: int
    phone: Optional[str] = None
    records: List[SeedRecord]
    messages: List[SeedMessage]
    tasks: List[SeedTask]


class SeedKnowledgeItem(BaseModel):
    key: str
    title: str
    content: str


class SeedSpec(BaseModel):
    knowledge_items: List[SeedKnowledgeItem]
    patients: List[SeedPatient]
