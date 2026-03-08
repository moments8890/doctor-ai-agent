"""
病历（MedicalRecordDB）和神经专科病例（NeuroCaseDB）的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base
from db.models.base import _utcnow


class MedicalRecordDB(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    past_medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    physical_examination: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auxiliary_examinations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)

    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="records")

    __table_args__ = (
        Index("ix_records_patient_created", "patient_id", "created_at"),
    )

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"


class NeuroCaseDB(Base):
    __tablename__ = "neuro_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)

    # Promoted scalar fields for queryability
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    encounter_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nihss: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Full extracted payloads
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_log_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)
    patient: Mapped[Optional["Patient"]] = relationship("Patient")

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"
