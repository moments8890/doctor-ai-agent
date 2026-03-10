"""Make invite_codes.doctor_id nullable (invite-first flow)

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not support ALTER COLUMN, so recreate the table.
    with op.batch_alter_table("invite_codes") as batch_op:
        batch_op.alter_column(
            "doctor_id",
            existing_type=sa.String(64),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("invite_codes") as batch_op:
        batch_op.alter_column(
            "doctor_id",
            existing_type=sa.String(64),
            nullable=False,
        )
