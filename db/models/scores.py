"""
专科量表评分（SpecialtyScore）数据库模型。

一条 medical_record 可关联多条量表评分（NIHSS、mRS、UPDRS 等）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class SpecialtyScore(Base):
    __tablename__ = "specialty_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False
    )
    score_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")  # chat|import|manual
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_specialty_scores_record_id", "record_id"),
        Index("ix_specialty_scores_doctor_id", "doctor_id"),
        Index("ix_specialty_scores_patient_score_ts", "patient_id", "score_type", "extracted_at"),
        Index("ix_specialty_scores_doctor_type_ts", "doctor_id", "score_type", "extracted_at"),
    )
