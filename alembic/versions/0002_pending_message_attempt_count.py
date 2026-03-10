"""Add attempt_count to pending_messages.

Revision ID: 0002_pending_message_attempt_count
Revises: 0001_baseline
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_pending_message_attempt_count"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pending_messages",
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pending_messages", "attempt_count")
