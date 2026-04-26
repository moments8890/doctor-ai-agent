"""
病历（MedicalRecordDB）的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship  # noqa: F401 (relationship used by Patient back_populates)
from db.engine import Base
from db.models.base import _utcnow


class RecordStatus(str, Enum):
    intake_active = "intake_active"
    pending_review = "pending_review"
    diagnosis_failed = "diagnosis_failed"
    insufficient_data = "insufficient_data"  # 2026-04-25: sufficiency rule fired, LLM skipped
    completed = "completed"


class MedicalRecordDB(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False, default="visit")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # nullable for legacy; write path enforces non-empty via MedicalRecord Pydantic model
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of keyword strings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # --- Versioning ---
    version_of: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True)

    # --- Status ---
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.completed.value)

    # --- Department ---
    department: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- 病史 (7 fields) ---
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    past_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allergy_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    personal_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    marital_reproductive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    family_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- 检查 (3 fields) ---
    physical_exam: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specialist_exam: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auxiliary_exam: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- 神外 (medical_neuro_v1 extras, nullable; never written by medical_general_v1) ---
    onset_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    neuro_exam: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vascular_risk_factors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- 诊断 ---
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DROPPED — replaced by ai_suggestions table (see db/models/ai_suggestion.py)
    # ai_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    # doctor_decisions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # --- 处置 (3 fields) ---
    treatment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    orders_followup: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # --- Outcome (absorbs case_history) ---
    final_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Chat–intake merge (Phase 0) ---
    # Schema added in alembic d3d865309344. ORM declarations here so
    # callers can read/write via the standard ORM path.
    extraction_confidence: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    patient_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    intake_segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    dedup_skipped_by_patient: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    # --- Intake redesign provenance (alembic 6a5d3c2e1f47) ---
    template_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    carry_forward_meta: Mapped[Optional[dict]] = mapped_column(sa.JSON, nullable=True)
    fields_updated_this_visit: Mapped[Optional[list]] = mapped_column(sa.JSON, nullable=True)

    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="records")

    # --- Helpers ---

    def structured_dict(self) -> dict[str, str]:
        """Return clinical record fields as a dict (same keys as schema.FIELD_KEYS)."""
        from domain.records.schema import FIELD_KEYS
        return {k: getattr(self, k, None) or "" for k in FIELD_KEYS}

    def has_structured_data(self) -> bool:
        """True if at least one clinical record column is populated."""
        from domain.records.schema import FIELD_KEYS
        return any(getattr(self, k, None) for k in FIELD_KEYS)

    __table_args__ = (
        Index("ix_records_patient_created", "patient_id", "created_at"),
        Index("ix_records_doctor_created", "doctor_id", "created_at"),
        Index("ix_records_doctor_type_created", "doctor_id", "record_type", "created_at"),
        Index("ix_records_created", "created_at"),
        Index("ix_records_status", "status"),
    )

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        snippet = (self.content or "—")[:30]
        return f"{snippet} [{date}]"


# FieldEntryDB removed 2026-04-26 (alembic 6a5d3c2e1f47) — replaced by
# intake_sessions.collected JSON as the single source of truth for
# in-flight intake data. Confirmed records carry the final field values
# directly on MedicalRecordDB inline columns; provenance lives in
# carry_forward_meta + fields_updated_this_visit on the record itself.


# RecordSupplementDB removed 2026-04-25 — replaced by "every patient submission
# is its own medical_record" model. Closed records are no longer mutated
# (preserves doctor review semantic) AND no separate supplement queue is needed
# (the new submission becomes its own pending_review case the doctor reviews
# normally). See alembic e7c4f9a1b2d3 for the table drop.
