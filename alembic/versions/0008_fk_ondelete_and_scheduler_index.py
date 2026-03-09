"""FK ondelete fixes and scheduler index

- doctor_tasks.record_id: add ON DELETE SET NULL so record deletion does not
  raise a FK violation when tasks reference that record (MySQL-critical)
- pending_records.patient_id: add ON DELETE SET NULL so patient deletion does
  not raise a FK violation when a pending draft exists (MySQL-critical)
- doctor_tasks: add (status, due_at) index for the scheduler's cross-doctor
  list_due_unnotified() query which has no doctor_id filter

Note on SQLite: ALTER TABLE cannot change FK constraints. The index is still
added. For the FK fixes, SQLite does not enforce FK constraints by default
(requires PRAGMA foreign_keys=ON), so the risk on SQLite is low. MySQL
deployments should apply the FK changes manually if upgrading from an existing
schema; new installs get the correct constraints via create_all().

Revision ID: 0008_fk_ondelete_and_scheduler_index
Revises: 0007_schema_fixes
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0008_fk_ondelete_and_scheduler_index"
down_revision = "0007_schema_fixes"
branch_labels = None
depends_on = None


def _existing_indexes(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {i["name"] for i in inspect(conn).get_indexes(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        return {r[1] for r in rows}


def _is_mysql() -> bool:
    conn = op.get_bind()
    return conn.dialect.name == "mysql"


def upgrade() -> None:
    # 1. Add (status, due_at) index on doctor_tasks for efficient scheduler queries
    if "ix_tasks_status_due" not in _existing_indexes("doctor_tasks"):
        op.execute(text(
            "CREATE INDEX ix_tasks_status_due ON doctor_tasks (status, due_at)"
        ))

    # 2. MySQL-only: fix FK constraints to use ON DELETE SET NULL
    #    SQLite: FK constraints cannot be altered without table rebuild; skip.
    #    New installs get correct constraints via create_all() from ORM models.
    if _is_mysql():
        conn = op.get_bind()

        # doctor_tasks.record_id → ON DELETE SET NULL
        fks = inspect(conn).get_foreign_keys("doctor_tasks")
        for fk in fks:
            if fk.get("constrained_columns") == ["record_id"]:
                fk_name = fk.get("name")
                if fk_name:
                    op.execute(text(f"ALTER TABLE doctor_tasks DROP FOREIGN KEY `{fk_name}`"))
                op.execute(text(
                    "ALTER TABLE doctor_tasks ADD CONSTRAINT fk_tasks_record_id "
                    "FOREIGN KEY (record_id) REFERENCES medical_records(id) ON DELETE SET NULL"
                ))
                break

        # pending_records.patient_id → ON DELETE SET NULL
        fks = inspect(conn).get_foreign_keys("pending_records")
        for fk in fks:
            if fk.get("constrained_columns") == ["patient_id"]:
                fk_name = fk.get("name")
                if fk_name:
                    op.execute(text(f"ALTER TABLE pending_records DROP FOREIGN KEY `{fk_name}`"))
                op.execute(text(
                    "ALTER TABLE pending_records ADD CONSTRAINT fk_pending_records_patient_id "
                    "FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL"
                ))
                break


def downgrade() -> None:
    pass
