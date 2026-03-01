from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import ForeignKey, String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    records: Mapped[List["MedicalRecordDB"]] = relationship("MedicalRecordDB", back_populates="patient")

    def __str__(self) -> str:
        return self.name


class MedicalRecordDB(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    past_medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    physical_examination: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auxiliary_examinations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="records")

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"
