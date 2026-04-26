"""
患者门户消息的数据库模型：记录患者与医生之间的消息往来。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class PatientMessage(Base):
    """Messages exchanged between patients and doctors via the patient portal."""
    __tablename__ = "patient_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # "inbound" or "outbound"
    # --- new triage columns (ADR 0020) ---
    source: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )  # patient / ai / doctor — nullable during migration
    sender_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )  # doctor_id when source=doctor
    reference_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )  # FK to medical_records.id
    triage_category: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )
    structured_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )  # JSON
    ai_handled: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="1",
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Intake segment grouping — all messages within one continuous patient
    # intake exchange share the same intake_segment_id (UUID). Used by
    # retraction logic: when signal_flag.detect fires, all whitelist replies
    # in the same segment are marked retracted.
    intake_segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # True when this outbound AI message was generated from the whitelist
    # auto-reply path (as opposed to a doctor-authored or LLM draft).
    is_whitelist_reply: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("0"), default=False,
    )
    # Set when a whitelist auto-reply is retracted because a signal-flag
    # signal fired in the same intake_segment. Front-end renders these
    # with strikethrough + a "已撤回" tag.
    retracted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSON-serialized ChatSessionState representing the state AFTER this
    # message was processed. NULL on legacy-path messages and on
    # retroactively-inserted messages. The most recent non-NULL row for
    # a patient is the source of truth for `load_state(patient_id)`.
    chat_state_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_patient_messages_direction",
        ),
        CheckConstraint(
            "source IS NULL OR source IN ('patient','ai','doctor','system')",
            name="ck_patient_messages_source",
        ),
        Index("ix_patient_messages_patient_created", "patient_id", "created_at"),
        Index("ix_patient_messages_doctor_created", "doctor_id", "created_at"),
    )
