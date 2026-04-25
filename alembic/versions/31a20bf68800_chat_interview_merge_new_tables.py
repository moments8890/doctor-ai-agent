"""chat_interview_merge_new_tables

Adds two new tables for the chat-interview merge:

- record_field_entries: append-only history field entries. Replaces
  direct mutation of the 7 history string columns on medical_records
  (legacy columns kept for backward-compat reads).
- record_supplements: patient-supplied supplements to doctor-reviewed
  records. Doctor explicitly accepts / rejects rather than silent
  mutation of clinical work product.

Revision ID: 31a20bf68800
Revises: d3d865309344
Create Date: 2026-04-25 15:02:10.907940
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '31a20bf68800'
down_revision = 'd3d865309344'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record_field_entries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("intake_segment_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_record_field_entries_record_id", "record_field_entries", ["record_id"])
    op.create_index("ix_record_field_entries_record_field", "record_field_entries", ["record_id", "field_name"])

    op.create_table(
        "record_supplements",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_doctor_review"),
        sa.Column("field_entries_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("doctor_decision_at", sa.DateTime, nullable=True),
        sa.Column("doctor_decision_by", sa.String(64), nullable=True),
    )
    op.create_index("ix_record_supplements_record_id", "record_supplements", ["record_id"])
    op.create_index("ix_record_supplements_status", "record_supplements", ["status"])


def downgrade() -> None:
    op.drop_index("ix_record_supplements_status", table_name="record_supplements")
    op.drop_index("ix_record_supplements_record_id", table_name="record_supplements")
    op.drop_table("record_supplements")
    op.drop_index("ix_record_field_entries_record_field", table_name="record_field_entries")
    op.drop_index("ix_record_field_entries_record_id", table_name="record_field_entries")
    op.drop_table("record_field_entries")
