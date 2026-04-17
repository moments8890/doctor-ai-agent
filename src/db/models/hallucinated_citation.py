"""Audit log for hallucinated [KB-N] citations in LLM output."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class HallucinatedCitation(Base):
    __tablename__ = "hallucinated_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    context: Mapped[str] = mapped_column(String(32), nullable=False)
    context_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hallucinated_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
