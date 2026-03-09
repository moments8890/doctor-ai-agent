"""Add UNIQUE(id, doctor_id) on patients and composite FK on medical_records

Row-level security enforcement: the composite unique index on patients
plus the composite FK on medical_records prevents a record with
patient_id=P being saved under a different doctor than the one who owns
patient P.

MySQL-only DDL. SQLite enforces this at the application layer (all CRUD
already filters by doctor_id).

Revision ID: 0013_composite_patient_fk
Revises: 0012_hmac_wechat_ids
Create Date: 2026-03-09
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import inspect, text

revision = "0013_composite_patient_fk"
down_revision = "0012_hmac_wechat_ids"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.migration.0013")


def _existing_indexes(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {i["name"] for i in inspect(conn).get_indexes(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        return {r[1] for r in rows}


def upgrade() -> None:
    conn = op.get_bind()
    is_mysql = conn.dialect.name == "mysql"

    if not is_mysql:
        log.info("[0013] Non-MySQL dialect — skipping composite FK DDL (enforced at application layer)")
        return

    # 1. Add UNIQUE(id, doctor_id) on patients so it can serve as FK target.
    existing = _existing_indexes("patients")
    if "uq_patients_id_doctor" not in existing:
        try:
            op.execute(text(
                "ALTER TABLE patients "
                "ADD CONSTRAINT uq_patients_id_doctor UNIQUE (id, doctor_id)"
            ))
            log.info("[0013] Added UNIQUE(id, doctor_id) on patients")
        except Exception as exc:
            log.warning("[0013] Could not add uq_patients_id_doctor: %s", exc)

    # 2. Add composite FK on medical_records(patient_id, doctor_id) ->
    #    patients(id, doctor_id). This enforces that a record's doctor_id
    #    must match the owning patient's doctor_id.
    existing_fks = {
        tuple(sorted(fk.get("constrained_columns", []))): fk
        for fk in inspect(conn).get_foreign_keys("medical_records")
    }
    if ("doctor_id", "patient_id") not in existing_fks:
        try:
            op.execute(text(
                "ALTER TABLE medical_records "
                "ADD CONSTRAINT fk_records_patient_doctor "
                "FOREIGN KEY (patient_id, doctor_id) "
                "REFERENCES patients (id, doctor_id) "
                "ON DELETE CASCADE"
            ))
            log.info("[0013] Added composite FK (patient_id, doctor_id) on medical_records")
        except Exception as exc:
            log.warning("[0013] Could not add composite FK: %s", exc)


def downgrade() -> None:
    conn = op.get_bind()
    is_mysql = conn.dialect.name == "mysql"
    if not is_mysql:
        return

    try:
        op.execute(text(
            "ALTER TABLE medical_records DROP FOREIGN KEY fk_records_patient_doctor"
        ))
    except Exception:
        pass

    try:
        op.execute(text(
            "ALTER TABLE patients DROP INDEX uq_patients_id_doctor"
        ))
    except Exception:
        pass
