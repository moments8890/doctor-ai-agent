"""
运行时状态的数据库模型：游标、令牌缓存和配置文档。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class RuntimeToken(Base):
    """Generic runtime token cache for cross-instance reuse."""
    __tablename__ = "runtime_tokens"

    token_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    token_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


