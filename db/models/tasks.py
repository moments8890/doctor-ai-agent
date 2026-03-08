"""
医生任务（DoctorTask）的数据库模型，用于随访提醒和待办事项管理。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class DoctorTask(Base):
    __tablename__ = "doctor_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # follow_up | emergency | appointment
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | completed | cancelled
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trigger_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # manual | risk_engine | timeline_rule
    trigger_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)

    __table_args__ = (
        Index("ix_tasks_doctor_status_due", "doctor_id", "status", "due_at"),
    )

    def __str__(self) -> str:
        return f"[{self.task_type}] {self.title}"
