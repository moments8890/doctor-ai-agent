"""Add ai_summary fields to patients.

Stores a short natural-language summary of the patient's clinical state,
regenerated incrementally each time a new record lands for that patient.

Revision ID: f4a2c17b9d10
Revises: 8e6d5626af10
Create Date: 2026-04-18 23:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f4a2c17b9d10"
down_revision = "8e6d5626af10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("patients", sa.Column("ai_summary_at", sa.DateTime(), nullable=True))
    op.add_column("patients", sa.Column("ai_summary_model", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("patients", "ai_summary_model")
    op.drop_column("patients", "ai_summary_at")
    op.drop_column("patients", "ai_summary")
