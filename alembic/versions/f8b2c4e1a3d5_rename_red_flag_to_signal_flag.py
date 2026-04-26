"""Rename medical_records.red_flag to signal_flag.

The bool was originally named red_flag (clinical-emergency idiom). 2026-04-26
the project re-framed these as keyword-extracted signals, not categorizations
— "signal flags" plural, with Tier B replacing this single bool with a
signal_tags JSON list. This rename keeps Python ORM attribute and DB column
in sync; the legacy column will be dropped entirely in Tier B.

Revision ID: f8b2c4e1a3d5
Revises: e7c4f9a1b2d3
Create Date: 2026-04-26 10:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "f8b2c4e1a3d5"
down_revision = "f562e3670e21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL emits CHANGE COLUMN for column rename and requires the existing
    # type. SQLite ignores existing_type in batch mode. Specifying it makes
    # the migration portable across both dialects.
    with op.batch_alter_table("medical_records") as batch:
        batch.alter_column(
            "red_flag",
            new_column_name="signal_flag",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )


def downgrade() -> None:
    with op.batch_alter_table("medical_records") as batch:
        batch.alter_column(
            "signal_flag",
            new_column_name="red_flag",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )
