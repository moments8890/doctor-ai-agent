"""Doctor edit tracking — logs every doctor edit to AI-generated content."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class DoctorEdit(Base):
    """Tracks individual edits a doctor makes to AI suggestions, drafts, etc."""
    __tablename__ = "doctor_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # diagnosis, draft_reply, record
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str] = mapped_column(Text, nullable=False)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # LLM-generated one-line, for later
    rule_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
