"""Interview session for patient pre-consultation (ADR 0016)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class InterviewSessionDB(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="interviewing")
    collected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    conversation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_interview_patient", "patient_id", "status"),
        Index("ix_interview_doctor", "doctor_id", "status"),
    )
