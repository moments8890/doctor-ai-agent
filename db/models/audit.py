"""
审计日志（AuditLog）的数据库模型，记录医生对患者数据的增删改查操作。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class AuditLog(Base):
    """Append-only audit trail for sensitive patient data access — compliance requirement."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)        # READ | WRITE | DELETE | LOGIN
    resource_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # patient | record | task
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_doctor_ts", "doctor_id", "ts"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )
