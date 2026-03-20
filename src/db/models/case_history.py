"""Case history for clinical decision support knowledge base."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class CaseSource(str, Enum):
    seed = "seed"         # pre-loaded neurosurgery seed cases
    review = "review"     # auto-created when doctor confirms a review
    manual = "manual"     # doctor manually enters a case
    import_ = "import"    # bulk import from external source (PDF, CSV, EHR)


class CaseHistory(Base):
    __tablename__ = "case_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False,
    )
    patient_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True,
    )
    record_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True,
    )
    chief_complaint: Mapped[str] = mapped_column(Text, nullable=False)
    present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="preliminary",
    )
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # CaseSource enum value
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("doctor_id", "record_id", name="uq_case_doctor_record"),
        Index("ix_case_history_doctor_confidence", "doctor_id", "confidence_status"),
    )
