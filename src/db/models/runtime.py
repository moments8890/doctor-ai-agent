"""
运行时状态的数据库模型：游标、令牌缓存、配置文档和调度器租约。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Text
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


class RuntimeConfig(Base):
    """Runtime JSON config documents editable from admin UI."""
    __tablename__ = "runtime_configs"

    config_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class SchedulerLease(Base):
    """Distributed scheduler lease to avoid duplicate multi-instance runs."""
    __tablename__ = "scheduler_leases"

    lease_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
