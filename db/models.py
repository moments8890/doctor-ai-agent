from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import ForeignKey, Index, String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base



class SystemPrompt(Base):
    """Editable LLM system prompts — loaded at call-time, editable via Admin UI."""
    __tablename__ = "system_prompts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)   # e.g. "structuring"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __str__(self) -> str:
        return self.key


class DoctorContext(Base):
    """Persistent compressed memory for a doctor — survives server restarts."""
    __tablename__ = "doctor_contexts"

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    year_of_birth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Categorization fields (v1)
    primary_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list
    category_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    category_rules_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        Index("ix_patients_doctor_category", "doctor_id", "primary_category"),
    )

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


class NeuroCaseDB(Base):
    __tablename__ = "neuro_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)

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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    patient: Mapped[Optional["Patient"]] = relationship("Patient")

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"


class DoctorTask(Base):
    __tablename__ = "doctor_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # follow_up | emergency | appointment
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | completed | cancelled
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __str__(self) -> str:
        return f"[{self.task_type}] {self.title}"
