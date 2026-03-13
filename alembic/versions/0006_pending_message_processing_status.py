"""Add 'processing' status to pending_messages check constraint.

Revision ID: 0006_pending_message_processing_status
Revises: 0005_doctor_profile_fields
Create Date: 2026-03-12
"""

from __future__ import annotations

from alembic import op

revision = "0006_pending_message_processing_status"
down_revision = "0005_doctor_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pending_messages") as batch_op:
        batch_op.drop_constraint("ck_pending_messages_status", type_="check")
        batch_op.create_check_constraint(
            "ck_pending_messages_status",
            "status IN ('pending','processing','done','dead')",
        )


def downgrade() -> None:
    # Move any 'processing' rows back to 'pending' before tightening
    op.execute("UPDATE pending_messages SET status='pending' WHERE status='processing'")
    with op.batch_alter_table("pending_messages") as batch_op:
        batch_op.drop_constraint("ck_pending_messages_status", type_="check")
        batch_op.create_check_constraint(
            "ck_pending_messages_status",
            "status IN ('pending','done','dead')",
        )
