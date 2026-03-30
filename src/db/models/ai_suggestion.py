"""AI 诊断建议表 — 每条 AI 建议一行，医生决策直接更新行。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base


class SuggestionSection(str, Enum):
    differential = "differential"
    workup = "workup"
    treatment = "treatment"


class SuggestionDecision(str, Enum):
    confirmed = "confirmed"
    rejected = "rejected"
    edited = "edited"
    custom = "custom"


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    section: Mapped[str] = mapped_column(String(32), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    intervention: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
