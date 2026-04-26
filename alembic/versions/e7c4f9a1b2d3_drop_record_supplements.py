"""Drop record_supplements table.

2026-04-25: removed in favor of "every patient submission becomes its own
medical_record" model. Closed records are no longer mutated (preserves doctor
review semantic) without needing a separate supplement queue — patient
submissions after a closed visit just become a new pending_review case the
doctor reviews normally.

See:
- src/channels/web/patient_portal/chat.py:691 — merge action declines on
  target_reviewed=True instead of creating a supplement
- removed files: src/channels/web/doctor_dashboard/supplement_handlers.py,
  frontend/web/src/v2/components/SupplementCard.jsx,
  tests/api/test_supplement_handlers.py
- removed function: domain/patient_lifecycle/dedup.py:create_supplement()

The table had 0 dev rows. Prod row check before this migration applied
should confirm 0 rows there too — if non-zero, audit those records first.

Revision ID: e7c4f9a1b2d3
Revises: c9d0e1f23456
Create Date: 2026-04-25 23:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e7c4f9a1b2d3"
# Merge both heads — c9d0e1f23456 (priority queue) + d5e6f7a8b9c0 (chat_state_snapshot).
down_revision = ("c9d0e1f23456", "d5e6f7a8b9c0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("record_supplements")


def downgrade() -> None:
    op.create_table(
        "record_supplements",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.Integer, sa.ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_doctor_review"),
        sa.Column("field_entries_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("doctor_decision_at", sa.DateTime, nullable=True),
        sa.Column("doctor_decision_by", sa.String(64), nullable=True),
    )
    op.create_index("ix_record_supplements_status", "record_supplements", ["status"])
