"""
医生相关的数据库模型：Doctor、DoctorContext、DoctorSessionState 等。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class DoctorContext(Base):
    """Persistent compressed memory for a doctor — survives server restarts."""
    __tablename__ = "doctor_contexts"
    __table_args__ = (
        Index("ix_doctor_contexts_updated_at", "updated_at"),
    )

    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DoctorKnowledgeItem(Base):
    """Per-doctor reusable knowledge snippets for prompt grounding."""
    __tablename__ = "doctor_knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DoctorSessionState(Base):
    """Persistent light session state for each doctor/external user."""
    __tablename__ = "doctor_session_states"

    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True)
    current_patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    pending_create_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    pending_record_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("pending_records.id", ondelete="SET NULL"), nullable=True)
    interview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cvd_scale_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DoctorNotifyPreference(Base):
    """Per-doctor notification mode and cadence controls."""
    __tablename__ = "doctor_notify_preferences"

    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True)
    notify_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")  # auto | manual
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="immediate")  # immediate | interval | cron
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cron_expr: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_auto_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ChatArchive(Base):
    """Permanent append-only log of all doctor↔AI exchanges for future training / vocab expansion.

    Never truncated — unlike doctor_conversation_turns which is a rolling window.
    intent_label is null until a human reviewer annotates it.
    """
    __tablename__ = "chat_archive"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # human review annotation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_chat_archive_doctor_created", "doctor_id", "created_at"),
    )


class DoctorConversationTurn(Base):
    """Persisted doctor conversation turns to support cross-node continuity."""
    __tablename__ = "doctor_conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_turns_doctor_created", "doctor_id", "created_at"),
    )


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
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="app")
    wechat_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mini_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ux_doctors_channel_wechat_user_id", "channel", "wechat_user_id", unique=True),
        Index("ux_doctors_mini_openid", "mini_openid", unique=True),
    )

    def __str__(self) -> str:
        return self.name or self.doctor_id
