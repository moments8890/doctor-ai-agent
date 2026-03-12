"""Add visit_scenario and note_style columns to doctors table.

Revision ID: 0005_doctor_profile_fields
Revises: 0004_expand_doctor_task_types
Create Date: 2026-03-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_doctor_profile_fields"
down_revision = "0004_expand_doctor_task_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("doctors") as batch_op:
        batch_op.add_column(sa.Column("visit_scenario", sa.String(256), nullable=True))
        batch_op.add_column(sa.Column("note_style", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("doctors") as batch_op:
        batch_op.drop_column("note_style")
        batch_op.drop_column("visit_scenario")
