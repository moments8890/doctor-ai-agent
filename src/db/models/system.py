"""
系统提示词（SystemPrompt）和历史版本（SystemPromptVersion）的数据库模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class SystemPrompt(Base):
    """Editable LLM system prompts — loaded at call-time, editable via Admin UI."""
    __tablename__ = "system_prompts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)   # e.g. "structuring"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __str__(self) -> str:
        return self.key


class SystemPromptVersion(Base):
    """Append-only version history for system prompts — enables rollback on bad prompt changes."""
    __tablename__ = "system_prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(64), ForeignKey("system_prompts.key", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_system_prompt_versions_key_ts", "prompt_key", "changed_at"),
    )
