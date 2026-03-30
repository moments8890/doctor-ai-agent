"""
消息草稿模型：AI 生成的随访回复草稿，供医生审核后发送。
"""

from __future__ import annotations

from enum import Enum as PyEnum
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class DraftStatus(str, PyEnum):
    generated = "generated"
    edited = "edited"
    sent = "sent"
    dismissed = "dismissed"
    stale = "stale"


class MessageDraft(Base):
    __tablename__ = "message_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patient_messages.id"), nullable=False,
    )
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_knowledge_ids: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )  # JSON list of int IDs
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DraftStatus.generated.value,
    )
    ai_disclosure: Mapped[str] = mapped_column(
        String(100), nullable=False, default="AI辅助生成，经医生审核",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
