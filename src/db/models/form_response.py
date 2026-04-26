"""Form response persistence (Phase 0 of intake-pipeline-extensibility).

A form response is the non-medical-record output of an intake template
whose kind is "form" (e.g. form_satisfaction_v1). Medical templates still
write to medical_records; this table is for everything else.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class FormResponseDB(Base):
    __tablename__ = "form_responses"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("intake_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )

    __table_args__ = (
        Index(
            "ix_form_response_doctor_patient_template",
            "doctor_id", "patient_id", "template_id",
        ),
        Index(
            "ix_form_response_patient_template_created",
            "patient_id", "template_id", "created_at",
        ),
    )
