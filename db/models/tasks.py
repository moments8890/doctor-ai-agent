"""
医生任务（DoctorTask）的数据库模型，用于随访提醒和待办事项管理。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.engine import Base
from db.models.base import _utcnow


class DoctorTask(Base):
    __tablename__ = "doctor_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # follow_up | emergency | appointment
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | completed | cancelled
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','completed','cancelled')", name="ck_doctor_tasks_status"),
        CheckConstraint("task_type IN ('follow_up','emergency','appointment')", name="ck_doctor_tasks_task_type"),
        Index("ix_tasks_doctor_status_due", "doctor_id", "status", "due_at"),
        Index("ix_tasks_status_due", "status", "due_at"),  # scheduler: list_due_unnotified queries across all doctors
        Index("ix_tasks_status_task_type_due", "status", "task_type", "due_at"),
    )

    def __str__(self) -> str:
        return f"[{self.task_type}] {self.title}"
