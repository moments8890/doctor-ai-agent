"""Baseline schema — single clean migration replacing all previous incremental versions.

This migration creates the complete schema from scratch. All previous migrations
(0001–0017) have been collapsed into this single baseline since there is no
production data to preserve.

Revision ID: 0001_baseline
Revises: (none)
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # doctors
    # -------------------------------------------------------------------------
    op.create_table(
        "doctors",
        sa.Column("doctor_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("specialty", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False, server_default="app"),
        sa.Column("wechat_user_id", sa.String(128), nullable=True),
        sa.Column("mini_openid", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ux_doctors_channel_wechat_user_id", "doctors", ["channel", "wechat_user_id"], unique=True)
    op.create_index("ux_doctors_mini_openid", "doctors", ["mini_openid"], unique=True)

    # -------------------------------------------------------------------------
    # invite_codes
    # -------------------------------------------------------------------------
    op.create_table(
        "invite_codes",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="SET NULL"), nullable=True),
        sa.Column("doctor_name", sa.String(128), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_invite_codes_doctor_id", "invite_codes", ["doctor_id"])

    # -------------------------------------------------------------------------
    # system_prompts
    # -------------------------------------------------------------------------
    op.create_table(
        "system_prompts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # system_prompt_versions
    # -------------------------------------------------------------------------
    op.create_table(
        "system_prompt_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prompt_key", sa.String(64), sa.ForeignKey("system_prompts.key", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=True),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_system_prompt_versions_key", "system_prompt_versions", ["prompt_key"])
    op.create_index("ix_system_prompt_versions_key_ts", "system_prompt_versions", ["prompt_key", "changed_at"])

    # -------------------------------------------------------------------------
    # patients
    # -------------------------------------------------------------------------
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("year_of_birth", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("primary_category", sa.String(32), nullable=True),
        sa.Column("category_tags", sa.Text, nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("patient_id_number", sa.String(18), nullable=True),
        sa.Column("access_code", sa.String(160), nullable=True),  # PBKDF2-SHA256 hash
        sa.UniqueConstraint("id", "doctor_id", name="uq_patients_id_doctor"),
    )
    op.create_index("ix_patients_doctor_created", "patients", ["doctor_id", "created_at"])
    op.create_index("ix_patients_doctor_category", "patients", ["doctor_id", "primary_category"])

    # -------------------------------------------------------------------------
    # patient_labels
    # -------------------------------------------------------------------------
    op.create_table(
        "patient_labels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("doctor_id", "name", name="uq_labels_doctor_name"),
    )
    op.create_index("ix_labels_doctor_created", "patient_labels", ["doctor_id", "created_at"])

    # -------------------------------------------------------------------------
    # patient_label_assignments
    # -------------------------------------------------------------------------
    op.create_table(
        "patient_label_assignments",
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE")),
        sa.Column("label_id", sa.Integer, sa.ForeignKey("patient_labels.id", ondelete="CASCADE")),
        sa.PrimaryKeyConstraint("patient_id", "label_id"),
    )

    # -------------------------------------------------------------------------
    # medical_records
    # -------------------------------------------------------------------------
    op.create_table(
        "medical_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False, server_default="visit"),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("encounter_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("neuro_patient_name", sa.String(128), nullable=True),
        sa.Column("nihss", sa.Integer, nullable=True),  # deprecated: see specialty_scores
        sa.Column("neuro_raw_json", sa.Text, nullable=True),
        sa.Column("neuro_extraction_log_json", sa.Text, nullable=True),
    )
    op.create_index("ix_medical_records_doctor_id", "medical_records", ["doctor_id"])
    op.create_index("ix_records_patient_created", "medical_records", ["patient_id", "created_at"])
    op.create_index("ix_records_doctor_created", "medical_records", ["doctor_id", "created_at"])
    op.create_index("ix_records_doctor_type_created", "medical_records", ["doctor_id", "record_type", "created_at"])
    op.create_index("ix_records_created", "medical_records", ["created_at"])

    # -------------------------------------------------------------------------
    # medical_record_versions
    # -------------------------------------------------------------------------
    op.create_table(
        "medical_record_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_content", sa.Text, nullable=True),
        sa.Column("old_tags", sa.Text, nullable=True),
        sa.Column("old_record_type", sa.String(32), nullable=True),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_record_versions_record_doctor_changed", "medical_record_versions", ["record_id", "doctor_id", "changed_at"])

    # -------------------------------------------------------------------------
    # medical_record_exports
    # -------------------------------------------------------------------------
    op.create_table(
        "medical_record_exports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("export_format", sa.String(16), nullable=True),
        sa.Column("exported_at", sa.DateTime, nullable=False),
        sa.Column("pdf_hash", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_record_exports_record_id", "medical_record_exports", ["record_id"])
    op.create_index("ix_record_exports_doctor_exported", "medical_record_exports", ["doctor_id", "exported_at"])
    op.create_index("ix_record_exports_record_exported", "medical_record_exports", ["record_id", "exported_at"])

    # -------------------------------------------------------------------------
    # specialty_scores
    # -------------------------------------------------------------------------
    op.create_table(
        "specialty_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_type", sa.String(32), nullable=False),
        sa.Column("score_value", sa.Float, nullable=True),
        sa.Column("raw_text", sa.String(256), nullable=True),
        sa.Column("details_json", sa.Text, nullable=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="chat"),
        sa.Column("extracted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("record_id", "score_type", name="uq_specialty_scores_record_type"),
    )
    op.create_index("ix_specialty_scores_record_id", "specialty_scores", ["record_id"])
    op.create_index("ix_specialty_scores_doctor_id", "specialty_scores", ["doctor_id"])
    op.create_index("ix_specialty_scores_patient_score_ts", "specialty_scores", ["patient_id", "score_type", "extracted_at"])
    op.create_index("ix_specialty_scores_doctor_type_ts", "specialty_scores", ["doctor_id", "score_type", "extracted_at"])

    # -------------------------------------------------------------------------
    # doctor_tasks
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_tasks_doctor_status_due", "doctor_tasks", ["doctor_id", "status", "due_at"])
    op.create_index("ix_tasks_status_due", "doctor_tasks", ["status", "due_at"])
    op.create_index("ix_tasks_status_task_type_due", "doctor_tasks", ["status", "task_type", "due_at"])

    # -------------------------------------------------------------------------
    # pending_records
    # -------------------------------------------------------------------------
    op.create_table(
        "pending_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patient_name", sa.String(128), nullable=True),
        sa.Column("draft_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="awaiting"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_pending_records_expires", "pending_records", ["expires_at"])
    op.create_index("ix_pending_records_status_expires", "pending_records", ["status", "expires_at"])
    op.create_index("ix_pending_records_doctor_status_expires", "pending_records", ["doctor_id", "status", "expires_at"])

    # -------------------------------------------------------------------------
    # pending_messages
    # -------------------------------------------------------------------------
    op.create_table(
        "pending_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_content", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_pending_messages_status_created", "pending_messages", ["status", "created_at"])
    op.create_index("ix_pending_messages_doctor", "pending_messages", ["doctor_id"])

    # -------------------------------------------------------------------------
    # doctor_contexts
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_contexts",
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # doctor_knowledge_items
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_knowledge_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_doctor_knowledge_items_doctor_id", "doctor_knowledge_items", ["doctor_id"])

    # -------------------------------------------------------------------------
    # doctor_session_states
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_session_states",
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("current_patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pending_create_name", sa.String(128), nullable=True),
        sa.Column("pending_record_id", sa.String(64), sa.ForeignKey("pending_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("interview_json", sa.Text, nullable=True),
        sa.Column("cvd_scale_json", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # doctor_notify_preferences
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_notify_preferences",
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("notify_mode", sa.String(16), nullable=False, server_default="auto"),
        sa.Column("schedule_type", sa.String(16), nullable=False, server_default="immediate"),
        sa.Column("interval_minutes", sa.Integer, nullable=False, server_default="1"),
        sa.Column("cron_expr", sa.String(64), nullable=True),
        sa.Column("last_auto_run_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # doctor_conversation_turns
    # -------------------------------------------------------------------------
    op.create_table(
        "doctor_conversation_turns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_turns_doctor_created", "doctor_conversation_turns", ["doctor_id", "created_at"])

    # -------------------------------------------------------------------------
    # chat_archive
    # -------------------------------------------------------------------------
    op.create_table(
        "chat_archive",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("intent_label", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_chat_archive_doctor_created", "chat_archive", ["doctor_id", "created_at"])

    # -------------------------------------------------------------------------
    # neuro_cvd_context
    # -------------------------------------------------------------------------
    op.create_table(
        "neuro_cvd_context",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("diagnosis_subtype", sa.String(32), nullable=True),
        sa.Column("surgery_status", sa.String(16), nullable=True),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("raw_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_neuro_cvd_record_id", "neuro_cvd_context", ["record_id"])
    op.create_index("ix_neuro_cvd_doctor_patient", "neuro_cvd_context", ["doctor_id", "patient_id"])
    op.create_index("ix_neuro_cvd_patient_ts", "neuro_cvd_context", ["patient_id", "created_at"])

    # -------------------------------------------------------------------------
    # audit_log
    # -------------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime, nullable=False),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="SET NULL"), nullable=True),
        sa.Column("doctor_display_name", sa.String(128), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=True),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("ok", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_audit_log_ts", "audit_log", ["ts"])
    op.create_index("ix_audit_log_doctor_ts", "audit_log", ["doctor_id", "ts"])
    op.create_index("ix_audit_log_resource", "audit_log", ["resource_type", "resource_id"])

    # -------------------------------------------------------------------------
    # runtime_cursors
    # -------------------------------------------------------------------------
    op.create_table(
        "runtime_cursors",
        sa.Column("cursor_key", sa.String(128), primary_key=True),
        sa.Column("cursor_value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # runtime_tokens
    # -------------------------------------------------------------------------
    op.create_table(
        "runtime_tokens",
        sa.Column("token_key", sa.String(128), primary_key=True),
        sa.Column("token_value", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # runtime_configs
    # -------------------------------------------------------------------------
    op.create_table(
        "runtime_configs",
        sa.Column("config_key", sa.String(64), primary_key=True),
        sa.Column("content_json", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -------------------------------------------------------------------------
    # scheduler_leases
    # -------------------------------------------------------------------------
    op.create_table(
        "scheduler_leases",
        sa.Column("lease_key", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_table("scheduler_leases")
    op.drop_table("runtime_configs")
    op.drop_table("runtime_tokens")
    op.drop_table("runtime_cursors")
    op.drop_table("audit_log")
    op.drop_table("neuro_cvd_context")
    op.drop_table("chat_archive")
    op.drop_table("doctor_conversation_turns")
    op.drop_table("doctor_notify_preferences")
    op.drop_table("doctor_session_states")
    op.drop_table("doctor_knowledge_items")
    op.drop_table("doctor_contexts")
    op.drop_table("pending_messages")
    op.drop_table("pending_records")
    op.drop_table("doctor_tasks")
    op.drop_table("specialty_scores")
    op.drop_table("medical_record_exports")
    op.drop_table("medical_record_versions")
    op.drop_table("medical_records")
    op.drop_table("patient_label_assignments")
    op.drop_table("patient_labels")
    op.drop_table("patients")
    op.drop_table("system_prompt_versions")
    op.drop_table("system_prompts")
    op.drop_table("invite_codes")
    op.drop_table("doctors")
