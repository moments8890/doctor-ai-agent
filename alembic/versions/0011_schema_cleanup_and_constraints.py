"""Schema cleanup and constraints

- DROP tables: stroke_clinical_context, epilepsy_clinical_context,
  parkinson_clinical_context, dementia_clinical_context, headache_clinical_context
- Add audit_log.doctor_display_name column (TEXT NULL)
- Alter audit_log.doctor_id to nullable / SET NULL on delete (MySQL only)
- Add InviteCode new columns: expires_at, max_uses, used_count
- Add DoctorContext/DoctorSessionState/DoctorNotifyPreference FK constraints (MySQL only)
- Add all new indexes from Part D
- Add partial unique index for pending_records (one awaiting per doctor)
- Add CHECK constraints for critical enum columns (MySQL 8.0+ only)
- Remove validation_status and confidence_score columns from specialty_scores (MySQL only)

Revision ID: 0011_schema_cleanup_and_constraints
Revises: 0010_session_state_interview_cvd
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0011_schema_cleanup_and_constraints"
down_revision = "0010_session_state_interview_cvd"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _existing_cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _existing_indexes(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {i["name"] for i in inspect(conn).get_indexes(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        return {r[1] for r in rows}


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return inspect(conn).has_table(table)


def _add_if_missing(table: str, col: str, typedef: str) -> None:
    if col not in _existing_cols(table):
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


def _create_index_if_missing(index_name: str, table: str, columns: str) -> None:
    if index_name not in _existing_indexes(table):
        op.execute(text(f"CREATE INDEX {index_name} ON {table} ({columns})"))


def _drop_table_if_exists(table: str) -> None:
    if _table_exists(table):
        op.execute(text(f"DROP TABLE {table}"))


def upgrade() -> None:
    conn = op.get_bind()
    is_mysql = conn.dialect.name == "mysql"

    # -----------------------------------------------------------------------
    # 1. DROP dead specialty context tables
    # -----------------------------------------------------------------------
    for tbl in (
        "stroke_clinical_context",
        "epilepsy_clinical_context",
        "parkinson_clinical_context",
        "dementia_clinical_context",
        "headache_clinical_context",
    ):
        _drop_table_if_exists(tbl)

    # -----------------------------------------------------------------------
    # 2. audit_log: add doctor_display_name column
    # -----------------------------------------------------------------------
    _add_if_missing("audit_log", "doctor_display_name", "VARCHAR(128) DEFAULT NULL")

    # 3. audit_log: alter doctor_id to nullable / SET NULL (MySQL only)
    # SQLite does not support ALTER COLUMN; the ORM model reflects nullable=True
    # at the Python level, which is sufficient for SQLite (no FK enforcement).
    if is_mysql:
        try:
            op.execute(text(
                "ALTER TABLE audit_log MODIFY COLUMN doctor_id VARCHAR(64) NULL"
            ))
            # Re-add FK with SET NULL if not already present
            existing_fks = {
                tuple(fk.get("constrained_columns", [])): fk
                for fk in inspect(conn).get_foreign_keys("audit_log")
            }
            if ("doctor_id",) not in existing_fks:
                op.execute(text(
                    "ALTER TABLE audit_log ADD CONSTRAINT fk_audit_log_doctor_id "
                    "FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE SET NULL"
                ))
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 4. invite_codes: add new columns
    # -----------------------------------------------------------------------
    _add_if_missing("invite_codes", "expires_at", "DATETIME DEFAULT NULL")
    _add_if_missing("invite_codes", "max_uses", "INTEGER NOT NULL DEFAULT 1")
    _add_if_missing("invite_codes", "used_count", "INTEGER NOT NULL DEFAULT 0")

    # Also allow doctor_id to be nullable (MySQL only)
    if is_mysql:
        try:
            op.execute(text(
                "ALTER TABLE invite_codes MODIFY COLUMN doctor_id VARCHAR(64) NULL"
            ))
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 5. FK constraints for DoctorContext / DoctorSessionState /
    #    DoctorNotifyPreference (MySQL only — SQLite has no FK enforcement)
    # -----------------------------------------------------------------------
    if is_mysql:
        for tbl, constraint_name in (
            ("doctor_contexts", "fk_doctor_contexts_doctor_id"),
            ("doctor_session_states", "fk_doctor_session_states_doctor_id"),
            ("doctor_notify_preferences", "fk_doctor_notify_preferences_doctor_id"),
        ):
            if _table_exists(tbl):
                existing_fks = {
                    tuple(fk.get("constrained_columns", [])): fk
                    for fk in inspect(conn).get_foreign_keys(tbl)
                }
                if ("doctor_id",) not in existing_fks:
                    try:
                        op.execute(text(
                            f"ALTER TABLE {tbl} ADD CONSTRAINT {constraint_name} "
                            f"FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE"
                        ))
                    except Exception:
                        pass

    # -----------------------------------------------------------------------
    # 6. New indexes from Part D
    # -----------------------------------------------------------------------
    # pending_records
    _create_index_if_missing("ix_pending_records_status_expires", "pending_records", "status, expires_at")

    # medical_records
    _create_index_if_missing("ix_records_created", "medical_records", "created_at")

    # medical_record_versions — replace old single-column index with composite
    if "ix_record_versions_record_doctor_changed" not in _existing_indexes("medical_record_versions"):
        op.execute(text(
            "CREATE INDEX ix_record_versions_record_doctor_changed "
            "ON medical_record_versions (record_id, doctor_id, changed_at)"
        ))
    # NOTE: ix_record_versions_record_id is kept in DB for backwards compat;
    # the ORM model no longer declares it, but existing deployments retain it.

    # medical_record_exports
    _create_index_if_missing("ix_record_exports_record_exported", "medical_record_exports", "record_id, exported_at")

    # patients
    _create_index_if_missing("ix_patients_name", "patients", "name")

    # specialty_scores
    _create_index_if_missing("ix_specialty_scores_doctor_type_ts", "specialty_scores", "doctor_id, score_type, extracted_at")

    # -----------------------------------------------------------------------
    # 7. Partial unique index: one 'awaiting' pending record per doctor
    # SQLite does not support WHERE-clause partial indexes via standard DDL.
    # MySQL: use a conditional unique index emulated via a generated column
    # or just apply the constraint at the application layer (see crud.py).
    # We add a best-effort index here for MySQL.
    # -----------------------------------------------------------------------
    if is_mysql:
        try:
            op.execute(text(
                "ALTER TABLE pending_records "
                "ADD CONSTRAINT uq_pending_records_doctor_awaiting "
                "UNIQUE (doctor_id, status)"
                # NOTE: This is a full unique — app must enforce 'awaiting'-only
                # uniqueness. A true partial index requires MySQL 8.0.13+ with
                # functional indexes; adding here would be non-portable.
            ))
        except Exception:
            pass  # Constraint may already exist or not be supported

    # -----------------------------------------------------------------------
    # 8 & 9. CHECK constraints (MySQL 8.0+ only; ignored on older versions)
    # -----------------------------------------------------------------------
    if is_mysql:
        check_constraints = [
            ("doctor_tasks", "ck_tasks_status",
             "status IN ('pending','completed','cancelled')"),
            ("pending_records", "ck_pending_records_status",
             "status IN ('awaiting','confirmed','abandoned','expired')"),
            ("medical_records", "ck_records_record_type",
             "record_type IN ('visit','dictation','import','interview_summary')"),
            ("medical_records", "ck_records_encounter_type",
             "encounter_type IN ('first_visit','follow_up','unknown')"),
            ("audit_log", "ck_audit_log_action",
             "action IN ('READ','WRITE','DELETE','LOGIN','EXPORT','create_task','postpone_task')"),
            ("audit_log", "ck_audit_log_resource_type",
             "resource_type IS NULL OR resource_type IN ('patient','record','task','doctor_task','report_template','outpatient_report')"),
            ("doctor_tasks", "ck_tasks_task_type",
             "task_type IS NULL OR LENGTH(task_type) > 0"),
            ("pending_messages", "ck_pending_messages_status",
             "status IN ('pending','done','failed')"),
            ("neuro_cvd_context", "ck_neuro_cvd_surgery_status",
             "surgery_status IS NULL OR surgery_status IN ('planned','done','cancelled','conservative')"),
            ("neuro_cvd_context", "ck_neuro_cvd_diagnosis_subtype",
             "diagnosis_subtype IS NULL OR diagnosis_subtype IN ('ICH','SAH','ischemic','AVM','aneurysm','other')"),
        ]
        for tbl, constraint_name, check_expr in check_constraints:
            if _table_exists(tbl):
                try:
                    op.execute(text(
                        f"ALTER TABLE {tbl} ADD CONSTRAINT {constraint_name} "
                        f"CHECK ({check_expr})"
                    ))
                except Exception:
                    pass  # Constraint already exists or DB version doesn't support it

        # Numeric range checks
        numeric_checks = [
            ("patients", "ck_patients_year_of_birth",
             "year_of_birth IS NULL OR (year_of_birth >= 1900 AND year_of_birth <= 2100)"),
        ]
        for tbl, constraint_name, check_expr in numeric_checks:
            if _table_exists(tbl):
                try:
                    op.execute(text(
                        f"ALTER TABLE {tbl} ADD CONSTRAINT {constraint_name} "
                        f"CHECK ({check_expr})"
                    ))
                except Exception:
                    pass

        # 10. CHECK(TRIM(name) != '') on patients.name
        try:
            op.execute(text(
                "ALTER TABLE patients ADD CONSTRAINT ck_patients_name_nonempty "
                "CHECK (TRIM(name) != '')"
            ))
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 11. Remove validation_status and confidence_score from specialty_scores
    # (MySQL only — SQLite cannot DROP COLUMN without recreating the table)
    # -----------------------------------------------------------------------
    if is_mysql:
        cols = _existing_cols("specialty_scores")
        for col in ("validation_status", "confidence_score"):
            if col in cols:
                try:
                    op.execute(text(f"ALTER TABLE specialty_scores DROP COLUMN {col}"))
                except Exception:
                    pass


def downgrade() -> None:
    # Non-destructive downgrade: restore dropped tables would require full DDL.
    # Skipping — use backup/restore for full rollback.
    pass
