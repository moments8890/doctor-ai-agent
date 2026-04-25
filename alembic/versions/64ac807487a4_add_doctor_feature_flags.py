"""Add doctor_feature_flags table for per-doctor boolean feature flags.

Revision ID: 64ac807487a4
Revises: d4c1bf3188b1
Create Date: 2026-04-25 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "64ac807487a4"
down_revision = "d4c1bf3188b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctor_feature_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("doctor_id", sa.String(64), nullable=False),
        sa.Column("flag_name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_doctor_feature_flags_doctor_flag",
        "doctor_feature_flags",
        ["doctor_id", "flag_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_doctor_feature_flags_doctor_flag", table_name="doctor_feature_flags")
    op.drop_table("doctor_feature_flags")
