"""
User preferences — per-user settings stored as a JSON blob.

Works for both doctors and patients. Single row per user_id.
New preferences are added to the JSON without schema changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow

DEFAULT_PREFERENCES = {
    "font_scale": "standard",
}


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # JSON-encoded preferences blob
    preferences_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
