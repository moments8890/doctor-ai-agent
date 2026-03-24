"""Patient portal authentication."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class PatientAuth(Base):
    __tablename__ = "patient_auth"

    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    access_code: Mapped[str] = mapped_column(String(160), nullable=False)
    access_code_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
