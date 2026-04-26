"""Platform-level doctor feedback — open-ended "this app is broken / I want X".

Distinct from `AISuggestion.feedback_*` columns, which capture per-suggestion
flags ("this AI suggestion was wrong"). This table is the catch-all that
the doctor uses to tell us the platform itself has a problem or a
missing feature. Surfaced in v2 via the 反馈 icon on the 我的AI page.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class PlatformFeedback(Base):
    """Open-ended platform feedback rows — append-only."""
    __tablename__ = "platform_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, index=True
    )
    # `doctor_id` is nullable so unauthenticated visitors (e.g. patient portal
    # users on the same SPA bundle) can still submit feedback if we later open
    # this surface to them. Today only authenticated doctors hit it.
    doctor_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="SET NULL"),
        nullable=True,
    )
    doctor_display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_platform_feedback_doctor_id", "doctor_id"),
    )
