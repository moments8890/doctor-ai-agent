"""Add priority column to message_drafts.

Codex round-5 review (locked plan, post-deferral-policy):
The AI's "已转给医生" defer pattern only works as a safety net IF the
doctor sees the alert quickly. Without a priority signal the draft
sits in a generic queue and creates a silent-wait failure mode for
stroke / ACS / postop bleed / thunderclap headache.

This migration adds a `priority` column on `message_drafts`. Values:
  - NULL / "normal":   regular draft, normal queue order
  - "urgent":          AI emitted defer-to-doctor pattern → bump in queue
  - "critical":        defer-to-doctor pattern + after-hours (22:00-06:00)
                       → top of queue + (future) push notification

Frontend sorts queue by priority DESC, then created_at DESC, so urgent
drafts surface first regardless of arrival time.

Revision ID: c9d0e1f23456
Revises: b8c9d0e1f234
Create Date: 2026-04-25 16:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c9d0e1f23456"
# Merge migration: this revises BOTH the diagnosis-schema head
# (b8c9d0e1f234) and the parallel doctor_feature_flags head
# (64ac807487a4) so the graph collapses back to a single head.
down_revision = ("b8c9d0e1f234", "64ac807487a4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message_drafts", sa.Column("priority", sa.String(16), nullable=True))
    op.create_index("ix_message_drafts_priority", "message_drafts", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_message_drafts_priority", table_name="message_drafts")
    op.drop_column("message_drafts", "priority")
