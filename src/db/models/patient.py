"""
患者的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base
from db.models.base import _utcnow


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    year_of_birth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_patients_doctor_created", "doctor_id", "created_at"),
        Index("ix_patients_doctor_phone", "doctor_id", "phone"),
        UniqueConstraint("id", "doctor_id", name="uq_patients_id_doctor"),
        UniqueConstraint("doctor_id", "name", name="uq_patients_doctor_name"),
    )

    records: Mapped[List["MedicalRecordDB"]] = relationship("MedicalRecordDB", back_populates="patient")

    def __str__(self) -> str:
        return self.name
