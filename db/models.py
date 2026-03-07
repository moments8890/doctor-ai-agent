from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import ForeignKey, Index, String, Integer, DateTime, Text, Table, Column, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.engine import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


patient_label_assignments = Table(
    "patient_label_assignments",
    Base.metadata,
    Column("patient_id", Integer, ForeignKey("patients.id", ondelete="CASCADE")),
    Column("label_id", Integer, ForeignKey("patient_labels.id", ondelete="CASCADE")),
    PrimaryKeyConstraint("patient_id", "label_id"),
)



class SystemPrompt(Base):
    """Editable LLM system prompts — loaded at call-time, editable via Admin UI."""
    __tablename__ = "system_prompts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)   # e.g. "structuring"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return self.key


class SystemPromptVersion(Base):
    """Append-only version history for system prompts — enables rollback on bad prompt changes."""
    __tablename__ = "system_prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_system_prompt_versions_key_ts", "prompt_key", "changed_at"),
    )


class DoctorContext(Base):
    """Persistent compressed memory for a doctor — survives server restarts."""
    __tablename__ = "doctor_contexts"

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    pending_create_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    pending_record_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pending_import_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DoctorNotifyPreference(Base):
    """Per-doctor notification mode and cadence controls."""
    __tablename__ = "doctor_notify_preferences"

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notify_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")  # auto | manual
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="immediate")  # immediate | interval | cron
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cron_expr: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_auto_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SchedulerLease(Base):
    """Distributed scheduler lease to avoid duplicate multi-instance runs."""
    __tablename__ = "scheduler_leases"

    lease_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RuntimeCursor(Base):
    """Generic runtime cursor store (e.g. WeCom sync cursor) for cross-instance consistency."""
    __tablename__ = "runtime_cursors"

    cursor_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    cursor_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RuntimeToken(Base):
    """Generic runtime token cache for cross-instance reuse."""
    __tablename__ = "runtime_tokens"

    token_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    token_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RuntimeConfig(Base):
    """Runtime JSON config documents editable from admin UI."""
    __tablename__ = "runtime_configs"

    config_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DoctorConversationTurn(Base):
    """Persisted doctor conversation turns to support cross-node continuity."""
    __tablename__ = "doctor_conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)

    __table_args__ = (
        Index("ix_turns_doctor_created", "doctor_id", "created_at"),
    )


class Doctor(Base):
    """Doctor registry table for admin-level querying/filtering."""
    __tablename__ = "doctors"

    doctor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="app")
    wechat_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ux_doctors_channel_wechat_user_id", "channel", "wechat_user_id", unique=True),
    )

    def __str__(self) -> str:
        return self.name or self.doctor_id


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    year_of_birth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Categorization fields (v1)
    primary_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list
    category_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    category_rules_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Risk fields (v1)
    primary_risk_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    risk_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    risk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    follow_up_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    risk_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    risk_rules_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        Index("ix_patients_doctor_category", "doctor_id", "primary_category"),
        Index("ix_patients_doctor_risk", "doctor_id", "primary_risk_level"),
    )

    records: Mapped[List["MedicalRecordDB"]] = relationship("MedicalRecordDB", back_populates="patient")
    labels: Mapped[List["PatientLabel"]] = relationship(
        "PatientLabel", secondary=patient_label_assignments, back_populates="patients"
    )

    def __str__(self) -> str:
        return self.name


class MedicalRecordDB(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    past_medical_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    physical_examination: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auxiliary_examinations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    treatment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    follow_up_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)

    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="records")

    __table_args__ = (
        Index("ix_records_patient_created", "patient_id", "created_at"),
    )

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"


class NeuroCaseDB(Base):
    __tablename__ = "neuro_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=True)

    # Promoted scalar fields for queryability
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    encounter_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nihss: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Full extracted payloads
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_log_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=True)
    patient: Mapped[Optional["Patient"]] = relationship("Patient")

    def __str__(self) -> str:
        date = self.created_at.strftime("%Y-%m-%d") if self.created_at else "—"
        return f"{self.chief_complaint or '—'} [{date}]"


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


class PatientLabel(Base):
    """Doctor-owned custom label that can be attached to patients."""
    __tablename__ = "patient_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    patients: Mapped[List["Patient"]] = relationship(
        "Patient", secondary=patient_label_assignments, back_populates="labels"
    )

    def __str__(self) -> str:
        return self.name


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
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_doctor_ts", "doctor_id", "ts"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )


class PendingRecord(Base):
    """Draft AI-generated medical records awaiting doctor confirmation via WeChat.

    Flow: LLM structures → PendingRecord (awaiting) → doctor replies "确认" →
    record moves to medical_records. Expires after 10 minutes if not confirmed.
    """
    __tablename__ = "pending_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID hex
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    draft_json: Mapped[str] = mapped_column(Text, nullable=False)   # JSON-serialized MedicalRecord
    raw_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # original dictation
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting")  # awaiting|confirmed|abandoned|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_pending_records_doctor_status", "doctor_id", "status"),
        Index("ix_pending_records_expires", "expires_at"),
    )


class PendingImport(Base):
    """Bulk patient history import awaiting doctor confirmation.

    Flow: extract text from PDF/Word/voice → structure chunks → PendingImport (awaiting)
    → doctor replies "确认导入" → records saved to medical_records. Expires after 30 min.
    """
    __tablename__ = "pending_imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID hex
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="text")  # pdf|word|voice|text|chat_export
    chunks_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of structured records
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting")  # awaiting|confirmed|partial|abandoned|expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_pending_imports_doctor_status", "doctor_id", "status"),
        Index("ix_pending_imports_expires", "expires_at"),
    )


class PendingMessage(Base):
    """Durable inbox for WeChat messages awaiting LLM processing.

    Written BEFORE spawning the background task so messages survive process restarts.
    Processor marks status='done' on success, 'failed' on error.
    On startup, any 'pending' record older than 60 s is re-queued.
    """
    __tablename__ = "pending_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")  # text | voice | image
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | done | failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pending_messages_status_created", "status", "created_at"),
        Index("ix_pending_messages_doctor", "doctor_id"),
    )
