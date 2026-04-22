"""Add prompt_hash to ai_suggestions + message_drafts (AI quality loop).

Unblocks the quality-loop work: correlating a stored AI output back to the
exact prompt version that generated it. Without this, "did my prompt change
help?" is answerable only by time-range heuristics (risky when multiple
edits land in a window). With a stable hash column we can group suggestions
by prompt version and compute acceptance/edit-ratio deltas.

Columns added (both nullable — historical rows stay null; no backfill):
- ai_suggestions.prompt_hash   varchar(64) — hash of composed system prompt
- message_drafts.prompt_hash   varchar(64) — same

varchar(64) is SHA-256 hex width; MD5 (32) fits fine. The existing llm.call
event already logs `prompt_hash` via _log_llm_call() — the write path just
needs to stash the same value on the row being persisted. Not done in this
migration — pure schema change, code wiring follows in a separate commit.

Revision ID: b5e7d21a4c83
Revises: c8e2f4a1b9d6
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "b5e7d21a4c83"
down_revision = "c8e2f4a1b9d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_suggestions",
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "message_drafts",
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("message_drafts", "prompt_hash")
    op.drop_column("ai_suggestions", "prompt_hash")
