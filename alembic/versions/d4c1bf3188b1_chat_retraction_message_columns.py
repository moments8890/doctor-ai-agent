"""chat_retraction_message_columns

Adds intake_segment_id and is_whitelist_reply columns to patient_messages.

- intake_segment_id: groups messages belonging to one continuous intake exchange.
  Used by red-flag retraction to scope which whitelist replies to retract.
- is_whitelist_reply: marks AI auto-replies generated from the whitelist path.
  Only these replies are retracted when a red-flag fires in the same segment.

Revision ID: d4c1bf3188b1
Revises: 11f853154f3e
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4c1bf3188b1'
down_revision = '11f853154f3e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "patient_messages",
        sa.Column("intake_segment_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "patient_messages",
        sa.Column(
            "is_whitelist_reply",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_patient_messages_intake_segment_id",
        "patient_messages",
        ["intake_segment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_messages_intake_segment_id", table_name="patient_messages")
    op.drop_column("patient_messages", "is_whitelist_reply")
    op.drop_column("patient_messages", "intake_segment_id")
