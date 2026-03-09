"""Schema integrity fixes and missing indexes

- Add FK doctors.doctor_id to patients.doctor_id and patient_labels.doctor_id
- Add UniqueConstraint(doctor_id, name) to patient_labels
- Fix invite_codes.active column type INTEGER → BOOLEAN (no-op on SQLite/MySQL tinyint)
- Add composite indexes:
    ix_patients_doctor_created (patients.doctor_id, patients.created_at)
    ix_labels_doctor_created (patient_labels.doctor_id, patient_labels.created_at)
    ix_records_doctor_created (medical_records.doctor_id, medical_records.created_at)
    ix_neuro_cases_doctor_created (neuro_cases.doctor_id, neuro_cases.created_at)
- Add record_id indexes on all specialty context tables
- AuditLog.ok: now uses explicit Boolean (SQLAlchemy ORM-level fix; no DDL change needed)

Revision ID: 0009_schema_integrity_and_indexes
Revises: 0008_fk_ondelete_and_scheduler_index
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0009_schema_integrity_and_indexes"
down_revision = "0008_fk_ondelete_and_scheduler_index"
branch_labels = None
depends_on = None


def _existing_indexes(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {i["name"] for i in inspect(conn).get_indexes(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        return {r[1] for r in rows}


def _create_index_if_missing(index_name: str, table: str, columns: str) -> None:
    if index_name not in _existing_indexes(table):
        op.execute(text(
            f"CREATE INDEX {index_name} ON {table} ({columns})"
        ))


def _create_unique_index_if_missing(index_name: str, table: str, columns: str) -> None:
    if index_name not in _existing_indexes(table):
        op.execute(text(
            f"CREATE UNIQUE INDEX {index_name} ON {table} ({columns})"
        ))


def upgrade() -> None:
    # --- Composite indexes for doctor-scoped list queries ---
    _create_index_if_missing("ix_patients_doctor_created", "patients", "doctor_id, created_at")
    _create_index_if_missing("ix_labels_doctor_created", "patient_labels", "doctor_id, created_at")
    _create_index_if_missing("ix_records_doctor_created", "medical_records", "doctor_id, created_at")
    _create_index_if_missing("ix_neuro_cases_doctor_created", "neuro_cases", "doctor_id, created_at")

    # --- record_id indexes on specialty context tables ---
    _create_index_if_missing("ix_stroke_context_record_id", "stroke_clinical_context", "record_id")
    _create_index_if_missing("ix_epilepsy_context_record_id", "epilepsy_clinical_context", "record_id")
    _create_index_if_missing("ix_parkinson_context_record_id", "parkinson_clinical_context", "record_id")
    _create_index_if_missing("ix_dementia_context_record_id", "dementia_clinical_context", "record_id")
    _create_index_if_missing("ix_headache_context_record_id", "headache_clinical_context", "record_id")
    _create_index_if_missing("ix_neuro_cvd_record_id", "neuro_cvd_context", "record_id")

    # --- Unique constraint: patient_labels(doctor_id, name) ---
    _create_unique_index_if_missing("uq_labels_doctor_name", "patient_labels", "doctor_id, name")

    # --- FK constraints: patients.doctor_id and patient_labels.doctor_id ---
    # SQLite: cannot ALTER TABLE to add FK constraint; skip (no FK enforcement by default).
    # MySQL: add FK constraints if missing.
    conn = op.get_bind()
    if conn.dialect.name == "mysql":
        # patients.doctor_id → doctors.doctor_id
        existing_fks = {
            tuple(fk.get("constrained_columns", [])): fk
            for fk in inspect(conn).get_foreign_keys("patients")
        }
        if ("doctor_id",) not in existing_fks:
            op.execute(text(
                "ALTER TABLE patients ADD CONSTRAINT fk_patients_doctor_id "
                "FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE"
            ))

        # patient_labels.doctor_id → doctors.doctor_id
        existing_fks = {
            tuple(fk.get("constrained_columns", [])): fk
            for fk in inspect(conn).get_foreign_keys("patient_labels")
        }
        if ("doctor_id",) not in existing_fks:
            op.execute(text(
                "ALTER TABLE patient_labels ADD CONSTRAINT fk_patient_labels_doctor_id "
                "FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE"
            ))


def downgrade() -> None:
    pass
