"""Diagnosis results for clinical decision support."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class DiagnosisStatus(str, Enum):
    pending = "pending"       # pipeline queued / running
    completed = "completed"   # AI results ready, awaiting doctor review
    confirmed = "confirmed"   # doctor has reviewed and confirmed
    failed = "failed"         # pipeline error (LLM timeout, etc.)


class DiagnosisResult(Base):
    __tablename__ = "diagnosis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("medical_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doctor_decisions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    red_flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_references: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    agreement_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_diagnosis_results_doctor_status", "doctor_id", "status"),
    )
