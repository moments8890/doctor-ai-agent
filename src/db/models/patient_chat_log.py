"""Patient ↔ AI/Doctor conversation log."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class PatientChatRole(str, Enum):
    user = "user"
    assistant = "assistant"
    ai = "ai"


class MessageDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageSource(str, Enum):
    patient = "patient"
    ai = "ai"
    doctor = "doctor"


class PatientChatLog(Base):
    __tablename__ = "patient_chat_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    sender_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    triage_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ai_handled: Mapped[bool] = mapped_column(Boolean, nullable=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_patient_chat_log_session", "session_id", "created_at"),
        Index("ix_patient_chat_log_patient", "patient_id", "created_at"),
    )
