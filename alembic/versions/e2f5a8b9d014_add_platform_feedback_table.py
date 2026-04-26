"""Add platform_feedback table.

Open-ended doctor feedback on the platform itself (distinct from the
per-AISuggestion feedback flags that already live as nullable columns
on `ai_suggestions`). Used by the v2 我的AI page's 反馈 icon to capture
"this is broken / I want X" signal from beta partner doctors.

Revision ID: e2f5a8b9d014
Revises: c9d0e1f23456
Create Date: 2026-04-25 22:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e2f5a8b9d014"
down_revision = "c9d0e1f23456"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column(
            "doctor_id",
            sa.String(64),
            sa.ForeignKey("doctors.doctor_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("doctor_display_name", sa.String(128), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("page_url", sa.String(512), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_platform_feedback_created_at",
        "platform_feedback",
        ["created_at"],
    )
    op.create_index(
        "ix_platform_feedback_doctor_id",
        "platform_feedback",
        ["doctor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_platform_feedback_doctor_id", table_name="platform_feedback")
    op.drop_index("ix_platform_feedback_created_at", table_name="platform_feedback")
    op.drop_table("platform_feedback")
