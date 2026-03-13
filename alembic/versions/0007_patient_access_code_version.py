"""Add access_code_version column to patients table.

Revision ID: 0007_patient_access_code_version
Revises: 0006_pending_message_processing_status
Create Date: 2026-03-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_patient_access_code_version"
down_revision = "0006_pending_message_processing_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("patients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "access_code_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("patients") as batch_op:
        batch_op.drop_column("access_code_version")
