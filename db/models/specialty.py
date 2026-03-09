"""
专科临床上下文表：神经外科脑血管疾病（NeuroCVDContext）。

已移除：StrokeClinicalContext、EpilepsyClinicalContext、ParkinsonClinicalContext、
DementiaClinicalContext、HeadacheClinicalContext — 这五张表从未被服务层调用，已通过
migration 0011 在数据库层面删除。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class NeuroCVDContext(Base):
    """神经外科脑血管疾病专病临床上下文。

    两个可索引的过滤字段保持为独立列（diagnosis_subtype, surgery_status），
    其余临床细节存储在 raw_json 中（migration 0006 将独立列合并为 raw_json）。
    """
    __tablename__ = "neuro_cvd_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)

    # Promoted filterable columns (kept as real columns for indexing)
    diagnosis_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # ICH|SAH|ischemic|AVM|aneurysm|other
    surgery_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)      # planned|done|cancelled|conservative
    source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)              # chat|voice|import

    # All other clinical detail fields stored as JSON blob
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_neuro_cvd_doctor_patient", "doctor_id", "patient_id"),
        Index("ix_neuro_cvd_patient_ts", "patient_id", "created_at"),
    )
