"""Add feedback columns to ai_suggestions — F1 explicit flag capture.

Phase F1 of docs/specs/2026-04-21-ai-feedback-capture-plan.md. Rework (per
Codex): instead of a separate ``ai_feedback`` table, we hang three nullable
columns off the existing ``ai_suggestions`` row — one suggestion, one flag,
semantically clean. The pre-existing ``reason`` column stays reserved for
the doctor's decision rationale (confirm/edit/reject); feedback gets its
own ``feedback_note`` so the two signals don't collide.

Columns added (all nullable — feedback is optional per row):
- feedback_tag          str(32), nullable — one of FeedbackReasonTag values
- feedback_note         text, nullable    — free-text, capped to 1000 chars
                                            server-side at write time
- feedback_created_at   datetime, nullable — set at flag-submission time

Behavior log (F2), digest (F3), and prompt_version (F4) land in later
migrations. Absence-flagging (F1.5 — "AI should have suggested X but
didn't") will need its own shape and is explicitly out of scope here.

Revision ID: c8e2f4a1b9d6
Revises: a7c4e9d1b3f2
Create Date: 2026-04-21 22:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c8e2f4a1b9d6"
down_revision = "a7c4e9d1b3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_suggestions") as batch_op:
        batch_op.add_column(sa.Column("feedback_tag", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("feedback_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("feedback_created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_suggestions") as batch_op:
        batch_op.drop_column("feedback_created_at")
        batch_op.drop_column("feedback_note")
        batch_op.drop_column("feedback_tag")
