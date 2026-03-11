"""Schema tightening: unique patient names per doctor, CHECK constraints on status columns.

Revision ID: 0003_schema_tightening
Revises: 0002_pending_message_attempt_count
Create Date: 2026-03-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_schema_tightening"
down_revision = "0002_pending_message_attempt_count"
branch_labels = None
depends_on = None


def _check_no_duplicate_patient_names(connection: sa.engine.Connection) -> None:
    """Fail loudly if existing data has duplicate (doctor_id, name) rows."""
    result = connection.execute(
        sa.text(
            "SELECT doctor_id, name, COUNT(*) AS cnt "
            "FROM patients GROUP BY doctor_id, name HAVING cnt > 1"
        )
    )
    dupes = result.fetchall()
    if dupes:
        lines = [f"  doctor_id={r[0]} name={r[1]} count={r[2]}" for r in dupes]
        raise RuntimeError(
            "Cannot apply uq_patients_doctor_name — duplicate (doctor_id, name) rows exist:\n"
            + "\n".join(lines)
            + "\nResolve duplicates before re-running this migration."
        )


def upgrade() -> None:
    conn = op.get_bind()
    _check_no_duplicate_patient_names(conn)

    # Step 1: unique patient name per doctor
    op.create_unique_constraint("uq_patients_doctor_name", "patients", ["doctor_id", "name"])

    # Step 3: CHECK constraints for status / type columns
    op.create_check_constraint(
        "ck_pending_records_status", "pending_records",
        "status IN ('awaiting','confirmed','abandoned','expired')",
    )
    op.create_check_constraint(
        "ck_pending_messages_status", "pending_messages",
        "status IN ('pending','done','dead')",
    )
    op.create_check_constraint(
        "ck_doctor_tasks_status", "doctor_tasks",
        "status IN ('pending','completed','cancelled')",
    )
    op.create_check_constraint(
        "ck_doctor_tasks_task_type", "doctor_tasks",
        "task_type IN ('follow_up','emergency','appointment')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_doctor_tasks_task_type", "doctor_tasks", type_="check")
    op.drop_constraint("ck_doctor_tasks_status", "doctor_tasks", type_="check")
    op.drop_constraint("ck_pending_messages_status", "pending_messages", type_="check")
    op.drop_constraint("ck_pending_records_status", "pending_records", type_="check")
    op.drop_constraint("uq_patients_doctor_name", "patients", type_="unique")
