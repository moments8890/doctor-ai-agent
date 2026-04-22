"""AI 诊断建议表 — 每条 AI 建议一行，医生决策直接更新行。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base


class SuggestionSection(str, Enum):
    differential = "differential"
    workup = "workup"
    treatment = "treatment"


class SuggestionDecision(str, Enum):
    confirmed = "confirmed"
    rejected = "rejected"
    edited = "edited"
    custom = "custom"


class FeedbackReasonTag(str, Enum):
    """Why the doctor flagged this suggestion (F1 explicit flag).

    Lives here (not in its own model file) because feedback is now columns on
    ``AISuggestion`` rather than a separate table — keeping the enum next to
    the row it annotates.
    """

    wrong_diagnosis = "wrong_diagnosis"
    insufficient_evidence = "insufficient_evidence"
    against_experience = "against_experience"
    other = "other"


class FeedbackDoctorAction(str, Enum):
    """What the doctor did with the suggestion at flag time.

    Retained as a validation-only enum — it is NOT persisted into its own
    column on ``ai_suggestions`` (the existing ``decision`` column already
    captures the terminal doctor action on the row). We keep the enum so the
    handler can validate inbound payloads without accepting arbitrary strings.
    """

    confirmed = "confirmed"
    edited = "edited"
    rejected = "rejected"
    pending = "pending"


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    section: Mapped[str] = mapped_column(String(32), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    intervention: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    cited_knowledge_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # F1 explicit-flag feedback. All three nullable — feedback is optional per
    # row. Note: `reason` above is reserved for the doctor's decision rationale
    # (confirm/edit/reject); `feedback_note` is intentionally separate so the
    # two signals don't collide.
    feedback_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    feedback_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
