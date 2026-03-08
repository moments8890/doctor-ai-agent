"""
待确认记录（PendingRecord/PendingImport）和待处理消息（PendingMessage）的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class PendingRecord(Base):
    """Draft AI-generated medical records awaiting doctor confirmation via WeChat.

    Flow: LLM structures → PendingRecord (awaiting) → doctor replies "确认" →
    record moves to medical_records. Expires after 10 minutes if not confirmed.
    """
    __tablename__ = "pending_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID hex
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    draft_json: Mapped[str] = mapped_column(Text, nullable=False)   # JSON-serialized MedicalRecord
    raw_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # original dictation
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting")  # awaiting|confirmed|abandoned|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_pending_records_doctor_status", "doctor_id", "status"),
        Index("ix_pending_records_expires", "expires_at"),
    )


class PendingImport(Base):
    """Bulk patient history import awaiting doctor confirmation.

    Flow: extract text from PDF/Word/voice → structure chunks → PendingImport (awaiting)
    → doctor replies "确认导入" → records saved to medical_records. Expires after 30 min.
    """
    __tablename__ = "pending_imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID hex
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="text")  # pdf|word|voice|text|chat_export
    chunks_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of structured records
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting")  # awaiting|confirmed|partial|abandoned|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_pending_imports_doctor_status", "doctor_id", "status"),
        Index("ix_pending_imports_expires", "expires_at"),
    )


class PendingMessage(Base):
    """Durable inbox for WeChat messages awaiting LLM processing.

    Written BEFORE spawning the background task so messages survive process restarts.
    Processor marks status='done' on success, 'failed' on error.
    On startup, any 'pending' record older than 60 s is re-queued.
    """
    __tablename__ = "pending_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")  # text | voice | image
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | done | failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pending_messages_status_created", "status", "created_at"),
        Index("ix_pending_messages_doctor", "doctor_id"),
    )
