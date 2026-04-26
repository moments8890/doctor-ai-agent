"""Rename interview_sessions → intake_sessions and migrate status values.

Project-wide rename: "interview" terminology replaced with "intake" everywhere.
Code identifiers, prompt files, and ORM attributes were renamed in the same
commit. This migration brings the schema and any persisted enum values in
line with the new vocabulary.

Two ops:
  1. Rename table interview_sessions → intake_sessions
  2. Update medical_records.status from 'interview_active' → 'intake_active'

Revision ID: 7e3d4a9c5b21
Revises: f8b2c4e1a3d5
Create Date: 2026-04-26 11:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "7e3d4a9c5b21"
down_revision = "f8b2c4e1a3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("interview_sessions", "intake_sessions")
    op.execute(
        "UPDATE medical_records "
        "SET status = 'intake_active' "
        "WHERE status = 'interview_active'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE medical_records "
        "SET status = 'interview_active' "
        "WHERE status = 'intake_active'"
    )
    op.rename_table("intake_sessions", "interview_sessions")
