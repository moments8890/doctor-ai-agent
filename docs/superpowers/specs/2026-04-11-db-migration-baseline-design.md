# DB Migration Baseline — Design Spec

**Date:** 2026-04-11
**Status:** Approved
**Context:** Production is live on Tencent Cloud (MySQL). Real data must be preserved.

## Problem

Alembic has 7 migrations (0001-0007, March 9-13) but the ORM models have
diverged significantly since then. The `create_tables()` + `_backfill_missing_columns()`
startup hack has kept the actual DB schema in sync with models, but Alembic's
version pointer is stuck at `0007` and the old migration chain no longer
reflects reality. We need Alembic as the sole schema management tool going forward.

## Approach

Collapse all existing migrations into a single new `0001_baseline` that
represents the **current ORM schema exactly**. On production, `alembic stamp`
marks the DB as "at this revision" without executing any DDL. For new installs,
the migration creates the full schema from scratch.

## Schema Inventory

### Tables from current ORM models (the new baseline creates these)

| Table | Model | PK |
|-------|-------|----|
| `doctors` | Doctor | doctor_id (String 64) |
| `invite_codes` | InviteCode | code (String 32) |
| `patients` | Patient | id (auto int) |
| `medical_records` | MedicalRecordDB | id (auto int) |
| `doctor_tasks` | DoctorTask | id (auto int) |
| `doctor_knowledge_items` | DoctorKnowledgeItem | id (auto int) |
| `doctor_wechat` | DoctorWechat | doctor_id (String 64) |
| `patient_auth` | PatientAuth | patient_id (int) |
| `doctor_chat_log` | DoctorChatLog | id (auto int) |
| `interview_sessions` | InterviewSessionDB | id (String 36) |
| `ai_suggestions` | AISuggestion | id (auto int) |
| `knowledge_usage_log` | KnowledgeUsageLog | id (auto int) |
| `doctor_edits` | DoctorEdit | id (auto int) |
| `doctor_personas` | DoctorPersona | doctor_id (String 64) |
| `persona_pending_items` | PersonaPendingItem | id (auto int) |
| `patient_messages` | PatientMessage | id (auto int) |
| `message_drafts` | MessageDraft | id (auto int) |
| `user_preferences` | UserPreferences | user_id (String 64) |
| `runtime_tokens` | RuntimeToken | token_key (String 128) |
| `scheduler_leases` | SchedulerLease | lease_key (String 64) |
| `audit_log` | AuditLog | id (auto int) |

### Legacy tables (exist in prod DB, NOT in ORM models)

These are left untouched. No DROP. A future cleanup migration can remove them
after confirming they hold no valuable data.

- `system_prompts`, `system_prompt_versions`
- `patient_labels`, `patient_label_assignments`
- `medical_record_versions`, `medical_record_exports`
- `specialty_scores`, `neuro_cvd_context`
- `pending_records`, `pending_messages`
- `doctor_contexts`, `doctor_session_states`
- `doctor_notify_preferences`
- `doctor_conversation_turns`, `chat_archive`
- `runtime_cursors`, `runtime_configs`

## Changes

### 1. New `alembic/versions/0001_baseline.py`

- Delete all 7 existing migration files
- Write a single `0001_baseline` that creates the 21 tables above with all
  columns, indexes, constraints, and CHECK constraints matching current ORM models
- `downgrade()` drops all 21 tables in reverse FK order
- The migration is written for MySQL compatibility (no SQLite-specific PRAGMA)

### 2. Startup flow changes (`src/startup/db_init.py` + `src/db/init_db.py`)

**Before:**
```
create_tables()          # Base.metadata.create_all — idempotent DDL
  _backfill_missing_columns()  # SQLite PRAGMA hack
run_alembic_migrations() # alembic upgrade head
```

**After:**
```
run_alembic_migrations() # alembic upgrade head — sole DDL path
```

- Remove `create_tables()` from production startup
- Remove `_backfill_missing_columns()` entirely
- Keep `create_tables()` available for test fixtures (conftest.py uses it)
- `run_alembic_migrations()` stays as-is (already handles errors gracefully)

### 3. Bash hook update (`.claude/hooks/guard-bash.sh`)

Remove the Alembic block (lines 14-17). Alembic is now the official tool.

### 4. Documentation updates

- `AGENTS.md`: Remove "No Alembic migrations" rule, add migration workflow section
- `src/db/README.md`: Update to reflect Alembic as the DDL path

### 5. Memory update

Retire `feedback_no_alembic.md` — the rule is no longer in effect.

## Production Deploy Procedure

After merging this change, on the production server:

```bash
# 1. Deploy code as usual (deploy.sh pulls + restarts)
#    The new startup skips create_tables(), runs alembic upgrade head.
#    But alembic_version still says "0007..." which doesn't exist in the new
#    migration chain. So alembic upgrade head will fail gracefully (existing
#    try/except in run_alembic_migrations catches this).

# 2. SSH into prod and stamp the baseline:
cd /home/ubuntu/doctor-ai-agent
.venv/bin/alembic stamp 0001_baseline

# 3. Verify:
.venv/bin/alembic current
# Should show: 0001_baseline (head)

# 4. Restart to confirm clean startup:
sudo systemctl restart doctor-ai-backend
```

After stamping, future `alembic upgrade head` calls (on every startup) become
no-ops until a new migration is added.

## Testing

- Run `alembic upgrade head` on a fresh SQLite DB → all 21 tables created
- Run `alembic downgrade base` → all tables dropped
- Existing pytest fixtures that use `Base.metadata.create_all` continue to work
- `alembic current` on stamped DB shows `0001_baseline (head)`

## Non-goals

- No schema changes in this PR (columns, types, constraints stay as-is)
- No dropping of legacy tables
- No Alembic autogenerate setup (manual migrations for now)
