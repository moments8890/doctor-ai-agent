"""
待确认记录（PendingRecord）和待处理消息（PendingMessage）的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class PendingRecord(Base):
    """Draft AI-generated medical records awaiting doctor confirmation via WeChat."""
    __tablename__ = "pending_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    draft_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('awaiting','confirmed','abandoned','expired')", name="ck_pending_records_status"),
        Index("ix_pending_records_expires", "expires_at"),
        Index("ix_pending_records_status_expires", "status", "expires_at"),
        Index("ix_pending_records_doctor_status_expires", "doctor_id", "status", "expires_at"),
    )


class PendingMessage(Base):
    """Durable inbox for WeChat messages awaiting LLM processing."""
    __tablename__ = "pending_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','done','dead')", name="ck_pending_messages_status"),
        Index("ix_pending_messages_status_created", "status", "created_at"),
        Index("ix_pending_messages_doctor", "doctor_id"),
    )
