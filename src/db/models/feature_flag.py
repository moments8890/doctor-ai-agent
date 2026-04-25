"""
Per-doctor feature flags — one row per (doctor_id, flag_name) pair.

Absence of a row means the flag is OFF (defaults-off pattern).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class DoctorFeatureFlag(Base):
    __tablename__ = "doctor_feature_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    flag_name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
