"""Interview session for patient pre-consultation (ADR 0016)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class InterviewStatus(str, Enum):
    """Patient interview session lifecycle.

    draft_created was retired in migration c9f8d2e14a20. It was set by a
    legacy doctor-side save-as-draft flow that no longer exists; the
    backfill flips any existing rows to 'confirmed'.
    """
    interviewing = "interviewing"
    reviewing = "reviewing"
    confirmed = "confirmed"
    abandoned = "abandoned"


class InterviewSessionDB(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=InterviewStatus.interviewing)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="patient")
    template_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="medical_general_v1",
    )
    collected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    conversation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_interview_patient", "patient_id", "status"),
        Index("ix_interview_doctor", "doctor_id", "status"),
        Index("ix_interview_template", "template_id"),
    )
