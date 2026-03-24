"""WeChat channel binding for doctors."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class DoctorWechat(Base):
    __tablename__ = "doctor_wechat"

    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True)
    wechat_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    mini_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
