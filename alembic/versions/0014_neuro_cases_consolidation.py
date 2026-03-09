"""Add neuro-case columns to medical_records and migrate data from neuro_cases

Consolidates NeuroCaseDB into MedicalRecordDB using record_type='neuro_case'
as a discriminator. The neuro_cases table is retained (not dropped) until a
follow-up verification confirms all data has been migrated.

New columns on medical_records:
  - neuro_patient_name  VARCHAR(128) NULL
  - nihss               INTEGER NULL
  - neuro_raw_json      TEXT NULL
  - neuro_extraction_log_json TEXT NULL

Revision ID: 0014_neuro_cases_consolidation
Revises: 0013_composite_patient_fk
Create Date: 2026-03-09
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import inspect, text

revision = "0014_neuro_cases_consolidation"
down_revision = "0013_composite_patient_fk"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.migration.0014")


def _existing_cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return inspect(conn).has_table(table)


def _add_if_missing(table: str, col: str, typedef: str) -> None:
    if col not in _existing_cols(table):
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


def upgrade() -> None:
    # 1. Add neuro-specific columns to medical_records
    _add_if_missing("medical_records", "neuro_patient_name", "VARCHAR(128) DEFAULT NULL")
    _add_if_missing("medical_records", "nihss", "INTEGER DEFAULT NULL")
    _add_if_missing("medical_records", "neuro_raw_json", "TEXT DEFAULT NULL")
    _add_if_missing("medical_records", "neuro_extraction_log_json", "TEXT DEFAULT NULL")
    log.info("[0014] Added neuro columns to medical_records")

    # 2. Migrate existing rows from neuro_cases to medical_records
    if not _table_exists("neuro_cases"):
        log.info("[0014] neuro_cases table not found — skipping data migration")
        return

    conn = op.get_bind()
    rows = conn.execute(text(
        "SELECT id, doctor_id, patient_id, patient_name, nihss, "
        "raw_json, extraction_log_json, created_at, updated_at "
        "FROM neuro_cases"
    )).fetchall()

    migrated = 0
    skipped = 0
    for row in rows:
        nc_id, doctor_id, patient_id, patient_name, nihss, raw_json, extraction_log_json, created_at, updated_at = row

        # Skip if already migrated (check for existing neuro_case record with same neuro_raw_json)
        if raw_json:
            existing = conn.execute(text(
                "SELECT id FROM medical_records "
                "WHERE record_type = 'neuro_case' AND neuro_raw_json = :rj "
                "AND doctor_id = :did LIMIT 1"
            ), {"rj": raw_json, "did": doctor_id}).fetchone()
            if existing:
                skipped += 1
                continue

        conn.execute(text(
            "INSERT INTO medical_records "
            "(doctor_id, patient_id, record_type, encounter_type, "
            "neuro_patient_name, nihss, neuro_raw_json, neuro_extraction_log_json, "
            "created_at, updated_at) "
            "VALUES (:did, :pid, 'neuro_case', 'unknown', "
            ":pname, :nihss, :rj, :elj, :cat, :uat)"
        ), {
            "did": doctor_id,
            "pid": patient_id,
            "pname": patient_name,
            "nihss": nihss,
            "rj": raw_json,
            "elj": extraction_log_json,
            "cat": created_at,
            "uat": updated_at,
        })
        migrated += 1

    log.info("[0014] neuro_cases data migration complete | migrated=%s skipped=%s", migrated, skipped)


def downgrade() -> None:
    # Removing columns from SQLite requires table recreation — skip for safety.
    # On MySQL, columns can be dropped but migrated data cannot be un-migrated automatically.
    conn = op.get_bind()
    is_mysql = conn.dialect.name == "mysql"
    if is_mysql:
        for col in ("neuro_patient_name", "nihss", "neuro_raw_json", "neuro_extraction_log_json"):
            try:
                op.execute(text(f"ALTER TABLE medical_records DROP COLUMN {col}"))
            except Exception:
                pass
