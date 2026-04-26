"""Add intake_sessions.prompt_version for self-healing on prompt changes.

When the patient-intake prompt changes (e.g., a safety fix removing
"立即去急诊" instructions), in-flight intake_sessions still have old
conversation history that the LLM will mimic regardless of the new
system prompt. The fix is to wipe conversation but keep collected so
the patient resumes under the new rules without losing progress.

This migration adds the column. Engine code compares
session.prompt_version against CURRENT_INTAKE_PROMPT_VERSION on each
turn; mismatch → conversation reset + version bump. Future prompt
edits just bump the constant; sessions self-heal on next turn.

Revision ID: 4d8e7a2c1f93
Revises: 6a5d3c2e1f47
Create Date: 2026-04-26 14:50:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "4d8e7a2c1f93"
down_revision = "6a5d3c2e1f47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intake_sessions",
        sa.Column("prompt_version", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("intake_sessions", "prompt_version")
