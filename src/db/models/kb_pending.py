"""Pending KB learning items — factual edits awaiting doctor review."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class KbPendingItem(Base):
    """A pending clinical-knowledge rule discovered from a factual doctor edit."""
    __tablename__ = "kb_pending_items"
    __table_args__ = (
        UniqueConstraint("doctor_id", "pattern_hash", "status", name="uq_kb_pending_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_rule: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_edit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    pattern_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    accepted_knowledge_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
