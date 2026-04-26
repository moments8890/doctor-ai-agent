"""Add chat_state_snapshot column to patient_messages.

Per the chat-interview merge integration (Task 1.7), ChatSessionState is
persisted as a JSON snapshot riding on patient_messages rather than in a
dedicated table. Each newly-inserted message that participates in the
state machine writes its post-turn state here. NULL on legacy-path rows
and on retroactively-inserted messages.

Revision ID: d5e6f7a8b9c0
Revises: e2f5a8b9d014
Create Date: 2026-04-25 22:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "d5e6f7a8b9c0"
down_revision = "e2f5a8b9d014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "patient_messages",
        sa.Column("chat_state_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patient_messages", "chat_state_snapshot")
