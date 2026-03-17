"""
病历（MedicalRecordDB）的数据库模型。
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
    record_type: Mapped[str] = mapped_column(String(32), nullable=False, default="visit")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of keyword strings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="records")

    __table_args__ = (
        Index("ix_records_patient_created", "patient_id", "created_at"),
        Index("ix_records_doctor_created", "doctor_id", "created_at"),
        Index("ix_records_doctor_type_created", "doctor_id", "record_type", "created_at"),
        Index("ix_records_created", "created_at"),
    )

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        snippet = (self.content or "—")[:30]
        return f"{snippet} [{date}]"



class MedicalRecordVersion(Base):
    """Append-only correction log — written whenever a confirmed record's content or tags are updated."""
    __tablename__ = "medical_record_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    old_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    old_record_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_record_versions_record_doctor_changed", "record_id", "doctor_id", "changed_at"),
    )


class MedicalRecordExport(Base):
    """Audit log for PDF/document exports of medical records."""
    __tablename__ = "medical_record_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    export_format: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # pdf|markdown|docx
    exported_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    pdf_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # SHA256 of generated file for tamper detection
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_record_exports_record_id", "record_id"),
        Index("ix_record_exports_doctor_exported", "doctor_id", "exported_at"),
        Index("ix_record_exports_record_exported", "record_id", "exported_at"),
    )
