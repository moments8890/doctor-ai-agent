"""Doctor ↔ AI conversation log."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import ForeignKey, Integer, String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class ChatRole(str, Enum):
    user = "user"
    assistant = "assistant"


class DoctorChatLog(Base):
    __tablename__ = "doctor_chat_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_doctor_chat_log_session", "session_id", "created_at"),
        Index("ix_doctor_chat_log_doctor", "doctor_id", "created_at"),
    )
