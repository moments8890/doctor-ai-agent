"""
医生相关的数据库模型：Doctor、 等。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class KnowledgeCategory(str, Enum):
    custom = "custom"
    diagnosis = "diagnosis"
    followup = "followup"
    medication = "medication"


class DoctorKnowledgeItem(Base):
    """Per-doctor reusable knowledge snippets for prompt grounding."""
    __tablename__ = "doctor_knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[KnowledgeCategory]] = mapped_column(String(32), nullable=True, default=KnowledgeCategory.custom)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)



class InviteCode(Base):
    """Admin-provisioned access codes that grant a doctor login access to the web UI."""
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    doctor_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="SET NULL"), nullable=True, index=True)
    doctor_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Doctor(Base):
    """Doctor registry table for admin-level querying/filtering."""
    __tablename__ = "doctors"

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    year_of_birth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    passcode_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    passcode_failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    passcode_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    passcode_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("1"))
    clinic_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    finished_onboarding: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("0"))
    preferred_template_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )

    __table_args__ = (
        Index("ix_doctors_phone", "phone"),
        Index("ix_doctors_nickname", "nickname", unique=True),
    )

    def __str__(self) -> str:
        return self.name or self.doctor_id
