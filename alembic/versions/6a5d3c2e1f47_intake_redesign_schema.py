"""Intake redesign — schema changes for the LLM-driven intake flow.

Adds:
  - patient_messages.intake_session_id (FK-shaped, VARCHAR(36) UUID)
  - medical_records.template_id (provenance for which template the record was built from)
  - medical_records.carry_forward_meta (JSON: {field: {source_record_id, source_date, confirmed_by_patient}})
  - medical_records.fields_updated_this_visit (JSON: list of fields the patient updated from carry-forward)
  - intake_sessions.medical_record_id (FK set on confirm; NULL until then)
  - intake_sessions.expired_at (timestamp set when 24h decay flips status to expired)

Drops:
  - medical_records.signal_flag (renamed in f8b2c4e1a3d5; now removed entirely.
    Tier B will replace with signal_tags JSON list extracted at record completion.)
  - record_field_entries table (was the dual-write target for in-flight intake fields.
    New design uses intake_sessions.collected JSON as the single source of truth; the
    FieldEntryDB code paths are removed in the same release.)

Single migration per project preference: product is pre-launch, no protected
patient data; rollback risk acceptable because no real history to lose.

Revision ID: 6a5d3c2e1f47
Revises: 9faace9588f2
Create Date: 2026-04-26 11:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "6a5d3c2e1f47"
down_revision = "9faace9588f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # patient_messages: link chat turns to the active intake session
    op.add_column(
        "patient_messages",
        sa.Column("intake_session_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_patient_messages_intake_session_id",
        "patient_messages",
        ["intake_session_id"],
    )

    # medical_records: template provenance + carry-forward audit trail
    op.add_column(
        "medical_records",
        sa.Column("template_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "medical_records",
        sa.Column("carry_forward_meta", sa.JSON(), nullable=True),
    )
    op.add_column(
        "medical_records",
        sa.Column("fields_updated_this_visit", sa.JSON(), nullable=True),
    )

    # medical_records: drop signal_flag (replaced semantically by future signal_tags)
    with op.batch_alter_table("medical_records") as batch:
        batch.drop_column("signal_flag")

    # intake_sessions: link to the confirmed medical_record + expiration timestamp
    op.add_column(
        "intake_sessions",
        sa.Column("medical_record_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intake_sessions",
        sa.Column("expired_at", sa.DateTime(), nullable=True),
    )

    # Drop record_field_entries — replaced by intake_sessions.collected JSON
    op.drop_table("record_field_entries")


def downgrade() -> None:
    # Recreate record_field_entries
    op.create_table(
        "record_field_entries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("intake_segment_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.drop_column("intake_sessions", "expired_at")
    op.drop_column("intake_sessions", "medical_record_id")

    with op.batch_alter_table("medical_records") as batch:
        batch.add_column(sa.Column("signal_flag", sa.Boolean, nullable=False, server_default=sa.text("0")))

    op.drop_column("medical_records", "fields_updated_this_visit")
    op.drop_column("medical_records", "carry_forward_meta")
    op.drop_column("medical_records", "template_id")

    op.drop_index("ix_patient_messages_intake_session_id", table_name="patient_messages")
    op.drop_column("patient_messages", "intake_session_id")
