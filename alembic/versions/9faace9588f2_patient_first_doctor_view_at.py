"""patient_first_doctor_view_at

Adds `first_doctor_view_at` to patients, plus a composite index on
(doctor_id, first_doctor_view_at) for the unseen-patient count query.
Backfills existing rows to their `last_activity_at` / `created_at` /
NOW() so they don't appear as "new" on first deploy.

Revision ID: 9faace9588f2
Revises: 7e3d4a9c5b21
Create Date: 2026-04-26 10:43:38.767235
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9faace9588f2'
down_revision = '7e3d4a9c5b21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("first_doctor_view_at", sa.DateTime, nullable=True))
    op.create_index(
        "ix_patients_doctor_first_view",
        "patients",
        ["doctor_id", "first_doctor_view_at"],
    )

    # Backfill so existing patients are NOT treated as "new" on first deploy.
    # Order of preference for the synthetic view-at value: last_activity_at
    # (best signal of doctor engagement), then created_at, then NOW().
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE patients "
        "SET first_doctor_view_at = COALESCE(last_activity_at, created_at, CURRENT_TIMESTAMP) "
        "WHERE first_doctor_view_at IS NULL"
    ))


def downgrade() -> None:
    op.drop_index("ix_patients_doctor_first_view", table_name="patients")
    op.drop_column("patients", "first_doctor_view_at")
