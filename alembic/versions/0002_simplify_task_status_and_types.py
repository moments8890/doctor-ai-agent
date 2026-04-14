"""Simplify task status (remove 'notified', add notified_at) and types (5→2).

- Add notified_at column (DateTime, nullable) to doctor_tasks
- Migrate existing notified rows: SET notified_at=updated_at, status='pending'
- Migrate task types: medication/checkup/review → follow_up
- Uses batch mode for SQLite CHECK constraint support

Revision ID: 0002_simplify_task
Revises: 0001_baseline
Create Date: 2026-04-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_simplify_task"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Data migrations first (before constraint changes)
    op.execute(
        "UPDATE doctor_tasks SET status = 'pending' "
        "WHERE status = 'notified'"
    )
    op.execute(
        "UPDATE doctor_tasks SET task_type = 'follow_up' "
        "WHERE task_type IN ('medication', 'checkup', 'review')"
    )

    # 2. Schema changes via batch mode (required for SQLite)
    with op.batch_alter_table("doctor_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("doctor_tasks") as batch_op:
        batch_op.drop_column("notified_at")
