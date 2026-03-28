"""Knowledge usage tracking — logs when KB items are cited in AI outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class KnowledgeUsageLog(Base):
    """Tracks each citation of a knowledge item in an AI-generated output."""

    __tablename__ = "knowledge_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctor_knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_context: Mapped[str] = mapped_column(String(32), nullable=False)
    patient_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
