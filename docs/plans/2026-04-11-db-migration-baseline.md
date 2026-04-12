# DB Migration Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stale Alembic migrations (0001-0007) with a single baseline that matches the current ORM schema, and make Alembic the sole DDL path for production.

**Architecture:** Delete old migrations, write one `0001_baseline` covering all 21 current ORM tables. Remove `create_tables()` from production startup. Stamp production DB so Alembic knows it's at baseline.

**Tech Stack:** SQLAlchemy 2.0 (async), Alembic, MySQL (prod), SQLite (dev/test)

**Spec:** `docs/specs/2026-04-11-db-migration-baseline-design.md`

---

### Task 1: Delete old migrations, write new 0001_baseline

**Files:**
- Delete: `alembic/versions/0001_baseline.py`
- Delete: `alembic/versions/0002_pending_message_attempt_count.py`
- Delete: `alembic/versions/0003_schema_tightening.py`
- Delete: `alembic/versions/0004_expand_doctor_task_types.py`
- Delete: `alembic/versions/0005_doctor_profile_fields.py`
- Delete: `alembic/versions/0006_pending_message_processing_status.py`
- Delete: `alembic/versions/0007_patient_access_code_version.py`
- Create: `alembic/versions/0001_baseline.py`

- [ ] **Step 1: Delete old migration files**

```bash
rm alembic/versions/0001_baseline.py \
   alembic/versions/0002_pending_message_attempt_count.py \
   alembic/versions/0003_schema_tightening.py \
   alembic/versions/0004_expand_doctor_task_types.py \
   alembic/versions/0005_doctor_profile_fields.py \
   alembic/versions/0006_pending_message_processing_status.py \
   alembic/versions/0007_patient_access_code_version.py
```

- [ ] **Step 2: Create new `alembic/versions/0001_baseline.py`**

Write the file with the complete schema for all 21 ORM tables. The tables must
be created in FK-dependency order. Here is the exact content:

```python
"""Baseline schema — all 21 ORM tables as of 2026-04-11.

Replaces the previous 0001-0007 migration chain which had drifted out of sync
with the ORM models. On production (which already has the correct schema via
create_tables()), run `alembic stamp 0001_baseline` instead of `alembic upgrade`.

Revision ID: 0001_baseline
Revises: (none)
Create Date: 2026-04-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # doctors
    # -----------------------------------------------------------------
    op.create_table(
        "doctors",
        sa.Column("doctor_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("specialty", sa.String(64), nullable=True),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("year_of_birth", sa.Integer, nullable=True),
        sa.Column("clinic_name", sa.String(128), nullable=True),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_doctors_phone", "doctors", ["phone"])

    # -----------------------------------------------------------------
    # invite_codes
    # -----------------------------------------------------------------
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

    # -----------------------------------------------------------------
    # patients
    # -----------------------------------------------------------------
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("year_of_birth", sa.Integer, nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_activity_at", sa.DateTime, nullable=True),
        sa.Column("seed_source", sa.String(32), nullable=True),
        sa.UniqueConstraint("id", "doctor_id", name="uq_patients_id_doctor"),
        sa.UniqueConstraint("doctor_id", "name", name="uq_patients_doctor_name"),
    )
    op.create_index("ix_patients_doctor_created", "patients", ["doctor_id", "created_at"])
    op.create_index("ix_patients_doctor_phone", "patients", ["doctor_id", "phone"])

    # -----------------------------------------------------------------
    # doctor_knowledge_items
    # -----------------------------------------------------------------
    op.create_table(
        "doctor_knowledge_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("reference_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("seed_source", sa.String(32), nullable=True),
    )
    op.create_index("ix_doctor_knowledge_items_doctor_id", "doctor_knowledge_items", ["doctor_id"])

    # -----------------------------------------------------------------
    # medical_records
    # -----------------------------------------------------------------
    op.create_table(
        "medical_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False, server_default="visit"),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("seed_source", sa.String(32), nullable=True),
        sa.Column("version_of", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("department", sa.Text, nullable=True),
        # 病史 (7 fields)
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("present_illness", sa.Text, nullable=True),
        sa.Column("past_history", sa.Text, nullable=True),
        sa.Column("allergy_history", sa.Text, nullable=True),
        sa.Column("personal_history", sa.Text, nullable=True),
        sa.Column("marital_reproductive", sa.Text, nullable=True),
        sa.Column("family_history", sa.Text, nullable=True),
        # 检查 (3 fields)
        sa.Column("physical_exam", sa.Text, nullable=True),
        sa.Column("specialist_exam", sa.Text, nullable=True),
        sa.Column("auxiliary_exam", sa.Text, nullable=True),
        # 诊断
        sa.Column("diagnosis", sa.Text, nullable=True),
        # 处置 (3 fields)
        sa.Column("treatment_plan", sa.Text, nullable=True),
        sa.Column("orders_followup", sa.Text, nullable=True),
        sa.Column("suggested_tasks", sa.Text, nullable=True),
        # Outcome
        sa.Column("final_diagnosis", sa.Text, nullable=True),
        sa.Column("treatment_outcome", sa.Text, nullable=True),
        sa.Column("key_symptoms", sa.Text, nullable=True),
    )
    op.create_index("ix_medical_records_doctor_id", "medical_records", ["doctor_id"])
    op.create_index("ix_records_patient_created", "medical_records", ["patient_id", "created_at"])
    op.create_index("ix_records_doctor_created", "medical_records", ["doctor_id", "created_at"])
    op.create_index("ix_records_doctor_type_created", "medical_records", ["doctor_id", "record_type", "created_at"])
    op.create_index("ix_records_created", "medical_records", ["created_at"])
    op.create_index("ix_records_status", "medical_records", ["status"])

    # -----------------------------------------------------------------
    # doctor_tasks
    # -----------------------------------------------------------------
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
        sa.Column("target", sa.String(16), nullable=False, server_default="doctor"),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_id", sa.Integer, nullable=True),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.Column("link_type", sa.String(16), nullable=True),
        sa.Column("link_id", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("reminder_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("seed_source", sa.String(32), nullable=True),
        sa.CheckConstraint("status IN ('pending','notified','completed','cancelled')", name="ck_doctor_tasks_status"),
        sa.CheckConstraint("task_type IN ('general','review','follow_up','medication','checkup')", name="ck_doctor_tasks_task_type"),
        sa.CheckConstraint("target IN ('doctor','patient')", name="ck_doctor_tasks_target"),
        sa.CheckConstraint("source_type IS NULL OR source_type IN ('manual','rule','diagnosis_auto')", name="ck_doctor_tasks_source_type"),
    )
    op.create_index("ix_tasks_doctor_status_due", "doctor_tasks", ["doctor_id", "status", "due_at"])
    op.create_index("ix_tasks_status_due", "doctor_tasks", ["status", "due_at"])
    op.create_index("ix_tasks_status_task_type_due", "doctor_tasks", ["status", "task_type", "due_at"])
    op.create_index("ix_tasks_target_patient_status", "doctor_tasks", ["target", "patient_id", "status"])

    # -----------------------------------------------------------------
    # doctor_wechat
    # -----------------------------------------------------------------
    op.create_table(
        "doctor_wechat",
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("wechat_user_id", sa.String(128), nullable=True, unique=True),
        sa.Column("mini_openid", sa.String(128), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # patient_auth
    # -----------------------------------------------------------------
    op.create_table(
        "patient_auth",
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("access_code", sa.String(160), nullable=False),
        sa.Column("access_code_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # doctor_chat_log
    # -----------------------------------------------------------------
    op.create_table(
        "doctor_chat_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("patient_id", sa.Integer, nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_doctor_chat_log_session_id", "doctor_chat_log", ["session_id"])
    op.create_index("ix_doctor_chat_log_session", "doctor_chat_log", ["session_id", "created_at"])
    op.create_index("ix_doctor_chat_log_doctor", "doctor_chat_log", ["doctor_id", "created_at"])

    # -----------------------------------------------------------------
    # interview_sessions
    # -----------------------------------------------------------------
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="interviewing"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="patient"),
        sa.Column("collected", sa.Text, nullable=True),
        sa.Column("conversation", sa.Text, nullable=True),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_interview_patient", "interview_sessions", ["patient_id", "status"])
    op.create_index("ix_interview_doctor", "interview_sessions", ["doctor_id", "status"])

    # -----------------------------------------------------------------
    # ai_suggestions
    # -----------------------------------------------------------------
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id"), nullable=False),
        sa.Column("doctor_id", sa.String(64), nullable=False),
        sa.Column("section", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("urgency", sa.String(16), nullable=True),
        sa.Column("intervention", sa.String(16), nullable=True),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("edited_text", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.Column("is_custom", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("seed_source", sa.String(32), nullable=True),
    )
    op.create_index("ix_ai_suggestions_record_id", "ai_suggestions", ["record_id"])
    op.create_index("ix_ai_suggestions_doctor_id", "ai_suggestions", ["doctor_id"])

    # -----------------------------------------------------------------
    # knowledge_usage_log
    # -----------------------------------------------------------------
    op.create_table(
        "knowledge_usage_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), nullable=False),
        sa.Column("knowledge_item_id", sa.Integer, sa.ForeignKey("doctor_knowledge_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_context", sa.String(32), nullable=False),
        sa.Column("patient_id", sa.String(64), nullable=True),
        sa.Column("record_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_knowledge_usage_log_doctor_id", "knowledge_usage_log", ["doctor_id"])
    op.create_index("ix_knowledge_usage_log_knowledge_item_id", "knowledge_usage_log", ["knowledge_item_id"])

    # -----------------------------------------------------------------
    # doctor_edits
    # -----------------------------------------------------------------
    op.create_table(
        "doctor_edits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("field_name", sa.String(64), nullable=True),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("edited_text", sa.Text, nullable=False),
        sa.Column("diff_summary", sa.Text, nullable=True),
        sa.Column("rule_created", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_doctor_edits_doctor_id", "doctor_edits", ["doctor_id"])

    # -----------------------------------------------------------------
    # doctor_personas
    # -----------------------------------------------------------------
    op.create_table(
        "doctor_personas",
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fields_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("onboarded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("edit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("summary_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # persona_pending_items
    # -----------------------------------------------------------------
    op.create_table(
        "persona_pending_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(32), nullable=False),
        sa.Column("proposed_rule", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("evidence_summary", sa.Text, nullable=False),
        sa.Column("evidence_edit_ids", sa.Text, nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("pattern_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_persona_pending_items_doctor_id", "persona_pending_items", ["doctor_id"])
    op.create_index("ix_persona_pending_items_pattern_hash", "persona_pending_items", ["pattern_hash"])

    # -----------------------------------------------------------------
    # patient_messages
    # -----------------------------------------------------------------
    op.create_table(
        "patient_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("sender_id", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.Integer, nullable=True),
        sa.Column("triage_category", sa.String(32), nullable=True),
        sa.Column("structured_data", sa.Text, nullable=True),
        sa.Column("ai_handled", sa.Boolean, nullable=True, server_default="1"),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("seed_source", sa.String(32), nullable=True),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_patient_messages_direction"),
        sa.CheckConstraint("source IS NULL OR source IN ('patient','ai','doctor','system')", name="ck_patient_messages_source"),
    )
    op.create_index("ix_patient_messages_patient_created", "patient_messages", ["patient_id", "created_at"])
    op.create_index("ix_patient_messages_doctor_created", "patient_messages", ["doctor_id", "created_at"])

    # -----------------------------------------------------------------
    # message_drafts
    # -----------------------------------------------------------------
    op.create_table(
        "message_drafts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.String(64), nullable=False),
        sa.Column("source_message_id", sa.Integer, sa.ForeignKey("patient_messages.id"), nullable=False),
        sa.Column("draft_text", sa.Text, nullable=False),
        sa.Column("edited_text", sa.Text, nullable=True),
        sa.Column("cited_knowledge_ids", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="generated"),
        sa.Column("ai_disclosure", sa.String(100), nullable=False, server_default="AI辅助生成，经医生审核"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("seed_source", sa.String(32), nullable=True),
    )
    op.create_index("ix_message_drafts_doctor_id", "message_drafts", ["doctor_id"])
    op.create_index("ix_message_drafts_patient_id", "message_drafts", ["patient_id"])

    # -----------------------------------------------------------------
    # user_preferences
    # -----------------------------------------------------------------
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("preferences_json", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # runtime_tokens
    # -----------------------------------------------------------------
    op.create_table(
        "runtime_tokens",
        sa.Column("token_key", sa.String(128), primary_key=True),
        sa.Column("token_value", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # scheduler_leases
    # -----------------------------------------------------------------
    op.create_table(
        "scheduler_leases",
        sa.Column("lease_key", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # -----------------------------------------------------------------
    # audit_log
    # -----------------------------------------------------------------
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


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("scheduler_leases")
    op.drop_table("runtime_tokens")
    op.drop_table("user_preferences")
    op.drop_table("message_drafts")
    op.drop_table("patient_messages")
    op.drop_table("persona_pending_items")
    op.drop_table("doctor_personas")
    op.drop_table("doctor_edits")
    op.drop_table("knowledge_usage_log")
    op.drop_table("ai_suggestions")
    op.drop_table("interview_sessions")
    op.drop_table("doctor_chat_log")
    op.drop_table("patient_auth")
    op.drop_table("doctor_wechat")
    op.drop_table("doctor_tasks")
    op.drop_table("medical_records")
    op.drop_table("doctor_knowledge_items")
    op.drop_table("patients")
    op.drop_table("invite_codes")
    op.drop_table("doctors")
```

- [ ] **Step 3: Verify migration runs on fresh SQLite**

```bash
rm -f /tmp/test_migration.db
DATABASE_URL= ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_migration.db \
  .venv/bin/alembic upgrade head
```

Expected: all 21 tables created, no errors.

- [ ] **Step 4: Verify downgrade works**

```bash
DATABASE_URL= ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_migration.db \
  .venv/bin/alembic downgrade base
```

Expected: all tables dropped, no errors.

- [ ] **Step 5: Clean up and commit**

```bash
rm -f /tmp/test_migration.db
git add alembic/versions/
git commit -m "feat(db): replace stale migrations with single baseline

Collapse 0001-0007 into one 0001_baseline covering all 21 current ORM
tables. The old chain had drifted out of sync with models — tables and
columns existed in prod (via create_tables) but not in migrations.

On production: run 'alembic stamp 0001_baseline' (no DDL, just updates
alembic_version row). On new installs: 'alembic upgrade head' creates
the full schema."
```

---

### Task 2: Simplify production startup (remove create_tables from prod path)

**Files:**
- Modify: `src/startup/db_init.py`
- Modify: `src/db/init_db.py`

- [ ] **Step 1: Update `src/startup/db_init.py`**

Remove `create_tables()` from the startup path. Alembic is now the sole DDL
path. Keep `seed_prompts` and `backfill_doctors_registry` (they don't do DDL).

Replace the `init_database` function:

```python
async def init_database(startup_log: logging.Logger) -> None:
    """Run Alembic migrations, backfill doctors, and seed prompts."""
    from db.init_db import seed_prompts, backfill_doctors_registry

    await run_alembic_migrations()
    _added_doctors = await backfill_doctors_registry()
    startup_log.info("[DB] doctors backfill completed | inserted=%s", _added_doctors)
    await seed_prompts()
```

- [ ] **Step 2: Remove `_backfill_missing_columns` from `src/db/init_db.py`**

Delete the `_backfill_missing_columns()` function entirely and remove its call
from `create_tables()`. The `create_tables()` function itself stays — it's used
by test fixtures.

The updated `create_tables()`:

```python
async def create_tables() -> None:
    """Create all tables from ORM metadata.

    Used by test fixtures only. Production DDL is managed by Alembic.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 3: Commit**

```bash
git add src/startup/db_init.py src/db/init_db.py
git commit -m "refactor(db): remove create_tables from prod startup

Alembic is now the sole DDL path. create_tables() is kept for test
fixtures only. _backfill_missing_columns() removed entirely."
```

---

### Task 3: Update bash hook, AGENTS.md, and db README

**Files:**
- Modify: `.claude/hooks/guard-bash.sh`
- Modify: `AGENTS.md`
- Modify: `src/db/README.md`

- [ ] **Step 1: Remove Alembic block from bash hook**

In `.claude/hooks/guard-bash.sh`, delete lines 14-17 (the `alembic` block):

```bash
# 1. Block alembic (AGENTS.md: "No Alembic migrations")
if echo "$CMD" | grep -qiE '\balembic\b'; then
  echo "BLOCKED: alembic is not allowed (AGENTS.md: No Alembic migrations until production launch)" >&2
  exit 2
fi
```

- [ ] **Step 2: Update AGENTS.md**

Replace the two migration-related bullet points (lines 126-127):

Old:
```
- **DB schema changes** — add to `src/db/models/`; `create_tables()` handles creation automatically; document any manual cleanup/migration impact in the commit message and PR description
- **No Alembic migrations** — do not create or run Alembic migrations until first production launch; for dev, use `create_tables()` or manual `ALTER TABLE` statements
```

New:
```
- **DB schema changes** — update ORM models in `src/db/models/`, then write an Alembic migration: `alembic revision -m "description"`. Test with `alembic upgrade head` on a fresh SQLite DB. Production migrations run automatically at startup via `run_alembic_migrations()`.
```

- [ ] **Step 3: Update `src/db/README.md`**

Replace the full contents:

```markdown
# DB Module

Purpose:
- Owns database schema, initialization, and CRUD operations.

Key areas:
- `models/` — SQLAlchemy ORM models.
- `crud/` — Async CRUD functions.
- `repositories/` — Higher-level query wrappers.
- `engine.py` — Async engine + session factory (`AsyncSessionLocal`).
- `init_db.py` — Test-only table creation + startup backfills.

Schema changes:
- Edit models in `models/`, then write an Alembic migration.
- Run `alembic revision -m "short description"` to create a new migration file.
- Migrations live in `alembic/versions/` with sequential numbering (0001, 0002, ...).
- Production migrations run automatically at startup (`src/startup/db_init.py`).
- Test fixtures use `Base.metadata.create_all` directly (no Alembic).
```

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/guard-bash.sh AGENTS.md src/db/README.md
git commit -m "docs: update migration workflow in AGENTS.md and db README

Remove 'No Alembic' rule. Alembic is now the official DDL tool.
Remove alembic block from bash guard hook."
```

---

### Task 4: Update memory

**Files:**
- Delete: `~/.claude/projects/-Volumes-ORICO-Code-doctor-ai-agent/memory/feedback_no_alembic.md`
- Modify: `~/.claude/projects/-Volumes-ORICO-Code-doctor-ai-agent/memory/MEMORY.md`

- [ ] **Step 1: Delete the stale feedback memory**

```bash
rm ~/.claude/projects/-Volumes-ORICO-Code-doctor-ai-agent/memory/feedback_no_alembic.md
```

- [ ] **Step 2: Update MEMORY.md**

Remove the line `- [No Alembic migrations](feedback_no_alembic.md) — skip migrations until first production launch`.

Add under Current Architecture:
```
- Alembic is the sole DDL path for production; `create_tables()` is test-only
```

---

### Task 5: Verify end-to-end

- [ ] **Step 1: Run existing tests to confirm nothing broke**

```bash
.venv/bin/python -m pytest tests/ -x -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent 2>&1 | tail -20
```

Expected: all tests pass (they use `Base.metadata.create_all` which still works).

- [ ] **Step 2: Test fresh Alembic upgrade**

```bash
rm -f /tmp/test_e2e.db
DATABASE_URL= ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_e2e.db \
  .venv/bin/alembic upgrade head
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('/tmp/test_e2e.db')
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()]
print(f'Tables created: {len(tables)}')
for t in tables:
    print(f'  {t}')
conn.close()
"
rm -f /tmp/test_e2e.db
```

Expected: 22 tables (21 ORM + `alembic_version`).

- [ ] **Step 3: Test stamp flow (simulates production)**

```bash
rm -f /tmp/test_stamp.db
# Create a DB that already has the schema (like prod)
ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_stamp.db \
  .venv/bin/python -c "
import asyncio
import os
os.environ['ENVIRONMENT'] = 'dev'
os.environ['PATIENTS_DB_PATH'] = '/tmp/test_stamp.db'
from db.init_db import create_tables
asyncio.run(create_tables())
print('Tables created via create_tables()')
"
# Stamp it
DATABASE_URL= ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_stamp.db \
  .venv/bin/alembic stamp 0001_baseline
# Verify
DATABASE_URL= ENVIRONMENT=dev PATIENTS_DB_PATH=/tmp/test_stamp.db \
  .venv/bin/alembic current
rm -f /tmp/test_stamp.db
```

Expected: `0001_baseline (head)`.
