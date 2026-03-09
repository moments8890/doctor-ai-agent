"""
神经外科脑血管疾病专病临床上下文表。

Promoted columns (filterable):
  diagnosis_subtype — cohort queries ("all SAH patients")
  surgery_status    — task queries ("planned surgery list")
  source            — provenance (chat|voice|import|manual)

All clinical detail lives in raw_json (Pydantic NeuroCVDSurgicalContext dump).
Adding new clinical fields requires only a Pydantic model change — no migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class NeuroCVDContext(Base):
    """脑血管专科上下文：每条病历对应一行，临床字段序列化为 raw_json。"""
    __tablename__ = "neuro_cvd_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False
    )

    # Promoted for SQL filtering
    diagnosis_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    surgery_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Full clinical payload — NeuroCVDSurgicalContext.model_dump(exclude_none=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=_utcnow, nullable=True)

    __table_args__ = (
        Index("ix_neuro_cvd_doctor_patient", "doctor_id", "patient_id"),
        Index("ix_neuro_cvd_patient_ts", "patient_id", "created_at"),
        Index("ix_neuro_cvd_subtype", "doctor_id", "diagnosis_subtype"),
        Index("ix_neuro_cvd_surgery_status", "doctor_id", "surgery_status"),
    )
