"""schema evolution — all inline ADD COLUMN migrations consolidated here

Revision ID: 0002_schema_evolution
Revises: 0001_baseline
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0002_schema_evolution"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cols(table: str) -> set[str]:
    """Return set of existing column names for *table*."""
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _has_index(table: str, index_name: str) -> bool:
    conn = op.get_bind()
    try:
        return any(i["name"] == index_name for i in inspect(conn).get_indexes(table))
    except Exception:
        return False


def _add(table: str, col: str, typedef: str) -> None:
    """ADD COLUMN only when missing (idempotent)."""
    if col not in _cols(table):
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


def _create_index(table: str, index_name: str, sql: str) -> None:
    if not _has_index(table, index_name):
        op.execute(text(sql))


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name  # "sqlite" or "mysql"

    # ── patients ─────────────────────────────────────────────────────────────

    # One-shot: rename age → year_of_birth (only if old schema)
    patient_cols = _cols("patients")
    if "age" in patient_cols and "year_of_birth" not in patient_cols:
        op.execute(text("ALTER TABLE patients RENAME COLUMN age TO year_of_birth"))

    for col, typedef in {
        "primary_category": "VARCHAR(32) DEFAULT NULL",
        "category_tags": "TEXT DEFAULT NULL",
        "category_computed_at": "DATETIME DEFAULT NULL",
        "category_rules_version": "VARCHAR(16) DEFAULT NULL",
        "primary_risk_level": "VARCHAR(16) DEFAULT NULL",
        "risk_tags": "TEXT DEFAULT NULL",
        "risk_score": "INTEGER DEFAULT NULL",
        "follow_up_state": "VARCHAR(16) DEFAULT NULL",
        "risk_computed_at": "DATETIME DEFAULT NULL",
        "risk_rules_version": "VARCHAR(16) DEFAULT NULL",
    }.items():
        _add("patients", col, typedef)

    # ── doctors ───────────────────────────────────────────────────────────────

    for col, typedef in {
        "channel": "VARCHAR(32) DEFAULT NULL",
        "wechat_user_id": "VARCHAR(128) DEFAULT NULL",
    }.items():
        _add("doctors", col, typedef)

    idx = "ux_doctors_channel_wechat_user_id"
    if not _has_index("doctors", idx):
        if dialect == "mysql":
            _create_index("doctors", idx,
                          "CREATE UNIQUE INDEX ux_doctors_channel_wechat_user_id "
                          "ON doctors(channel, wechat_user_id)")
        else:
            _create_index("doctors", idx,
                          "CREATE UNIQUE INDEX IF NOT EXISTS ux_doctors_channel_wechat_user_id "
                          "ON doctors(channel, wechat_user_id)")

    # ── doctor_tasks ──────────────────────────────────────────────────────────

    for col, typedef in {
        "trigger_source": "VARCHAR(32) DEFAULT NULL",
        "trigger_reason": "TEXT DEFAULT NULL",
        "updated_at": "DATETIME DEFAULT NULL",
    }.items():
        _add("doctor_tasks", col, typedef)

    # ── doctor_session_states ─────────────────────────────────────────────────

    for col, typedef in {
        "pending_record_id": "VARCHAR(64) DEFAULT NULL",
        "pending_import_id": "VARCHAR(64) DEFAULT NULL",
    }.items():
        _add("doctor_session_states", col, typedef)

    # ── medical_records ───────────────────────────────────────────────────────

    for col, typedef in {
        "updated_at": "DATETIME DEFAULT NULL",
        "record_type": "VARCHAR(32) DEFAULT 'visit'",
        "content": "TEXT DEFAULT NULL",
        "tags": "TEXT DEFAULT NULL",
        "source_message_id": "VARCHAR(128) DEFAULT NULL",
        "encounter_type": "VARCHAR(32) DEFAULT 'unknown'",
        "referenced_record_id": "INTEGER DEFAULT NULL",
        "is_signed_off": "INTEGER DEFAULT 0",
        "signed_off_at": "DATETIME DEFAULT NULL",
        "doctor_signature": "TEXT DEFAULT NULL",
    }.items():
        _add("medical_records", col, typedef)

    # ── neuro_cases ───────────────────────────────────────────────────────────

    _add("neuro_cases", "updated_at", "DATETIME DEFAULT NULL")

    # ── doctor_conversation_turns ─────────────────────────────────────────────

    _add("doctor_conversation_turns", "updated_at", "DATETIME DEFAULT NULL")

    # ── specialty_scores ──────────────────────────────────────────────────────

    for col, typedef in {
        "patient_id": "INTEGER DEFAULT NULL",
        "source": "VARCHAR(16) DEFAULT 'chat'",
        "confidence_score": "REAL DEFAULT NULL",
        "validation_status": "VARCHAR(16) DEFAULT 'pending'",
        "extracted_at": "DATETIME DEFAULT NULL",
    }.items():
        _add("specialty_scores", col, typedef)

    # ── MySQL-only composite indexes ──────────────────────────────────────────

    if dialect == "mysql":
        for table, idx_name, idx_sql in [
            ("doctor_tasks", "ix_tasks_doctor_status_due",
             "CREATE INDEX ix_tasks_doctor_status_due ON doctor_tasks(doctor_id, status, due_at)"),
            ("doctor_conversation_turns", "ix_turns_doctor_created",
             "CREATE INDEX ix_turns_doctor_created ON doctor_conversation_turns(doctor_id, created_at)"),
            ("medical_records", "ix_records_patient_created",
             "CREATE INDEX ix_records_patient_created ON medical_records(patient_id, created_at)"),
            ("specialty_scores", "ix_specialty_scores_patient_score_ts",
             "CREATE INDEX ix_specialty_scores_patient_score_ts "
             "ON specialty_scores(patient_id, score_type, extracted_at)"),
        ]:
            _create_index(table, idx_name, idx_sql)


# ---------------------------------------------------------------------------
# Downgrade — no-op (column drops are destructive, not worth automating)
# ---------------------------------------------------------------------------


def downgrade() -> None:
    pass
