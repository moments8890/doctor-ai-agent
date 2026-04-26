"""Intake session for patient pre-consultation (ADR 0016)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class IntakeStatus(str, Enum):
    """Patient intake session lifecycle.

    expired added 2026-04-26 (alembic 6a5d3c2e1f47) — set by 24h idle
    decay; eligible for resume if no newer confirmed record exists.
    """
    active = "active"
    reviewing = "reviewing"
    confirmed = "confirmed"
    abandoned = "abandoned"
    expired = "expired"


class IntakeSessionDB(Base):
    __tablename__ = "intake_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=IntakeStatus.active)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="patient")
    template_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="medical_general_v1",
    )
    collected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON dict
    conversation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    # --- Intake redesign (alembic 6a5d3c2e1f47) ---
    medical_record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_intake_patient", "patient_id", "status"),
        Index("ix_intake_doctor", "doctor_id", "status"),
        Index("ix_intake_template", "template_id"),
    )
