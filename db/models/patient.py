"""
患者及标签的数据库模型，包含多对多关联表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text, Table, Column, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base
from db.models.base import _utcnow


patient_label_assignments = Table(
    "patient_label_assignments",
    Base.metadata,
    Column("patient_id", Integer, ForeignKey("patients.id", ondelete="CASCADE")),
    Column("label_id", Integer, ForeignKey("patient_labels.id", ondelete="CASCADE")),
    PrimaryKeyConstraint("patient_id", "label_id"),
)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    year_of_birth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Categorization fields (v1)
    primary_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list

    __table_args__ = (
        Index("ix_patients_doctor_created", "doctor_id", "created_at"),
        Index("ix_patients_doctor_category", "doctor_id", "primary_category"),
        Index("ix_patients_name", "name"),
        UniqueConstraint("id", "doctor_id", name="uq_patients_id_doctor"),
    )

    records: Mapped[List["MedicalRecordDB"]] = relationship("MedicalRecordDB", back_populates="patient")
    labels: Mapped[List["PatientLabel"]] = relationship(
        "PatientLabel", secondary=patient_label_assignments, back_populates="patients"
    )

    def __str__(self) -> str:
        return self.name


class PatientLabel(Base):
    """Doctor-owned custom label that can be attached to patients."""
    __tablename__ = "patient_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    patients: Mapped[List["Patient"]] = relationship(
        "Patient", secondary=patient_label_assignments, back_populates="labels"
    )

    __table_args__ = (
        Index("ix_labels_doctor_created", "doctor_id", "created_at"),
        UniqueConstraint("doctor_id", "name", name="uq_labels_doctor_name"),
    )

    def __str__(self) -> str:
        return self.name
