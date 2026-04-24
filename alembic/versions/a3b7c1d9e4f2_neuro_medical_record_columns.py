"""Add neuro-specific columns to medical_records.

Adds three nullable TEXT columns used by `medical_neuro_v1`:
- onset_time — 发病时间 (thrombolysis window)
- neuro_exam — 神经系统查体 (GCS / pupils / strength / reflexes)
- vascular_risk_factors — 血管危险因素 (HTN / DM / AF / smoking / family history)

Existing rows receive NULL — no backfill. `medical_general_v1` never writes
these columns.

Revision ID: a3b7c1d9e4f2
Revises: c9f8d2e14a20
Create Date: 2026-04-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a3b7c1d9e4f2"
down_revision = "c9f8d2e14a20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medical_records", sa.Column("onset_time", sa.Text(), nullable=True))
    op.add_column("medical_records", sa.Column("neuro_exam", sa.Text(), nullable=True))
    op.add_column(
        "medical_records",
        sa.Column("vascular_risk_factors", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("medical_records", "vascular_risk_factors")
    op.drop_column("medical_records", "neuro_exam")
    op.drop_column("medical_records", "onset_time")
