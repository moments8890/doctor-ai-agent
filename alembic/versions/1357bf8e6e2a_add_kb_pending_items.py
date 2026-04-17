"""add_kb_pending_items

Revision ID: 1357bf8e6e2a
Revises: 0003_remove_review
Create Date: 2026-04-16 15:03:51.663365
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "1357bf8e6e2a"
down_revision = "0003_remove_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_pending_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("proposed_rule", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("evidence_edit_ids", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("pattern_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("accepted_knowledge_item_id", sa.Integer(),
                  sa.ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("doctor_id", "pattern_hash", "status", name="uq_kb_pending_dedupe"),
    )
    op.create_index("ix_kb_pending_items_doctor_id", "kb_pending_items", ["doctor_id"])
    op.create_index("ix_kb_pending_items_pattern_hash", "kb_pending_items", ["pattern_hash"])

    # Add the unique constraint to the existing persona_pending_items table
    with op.batch_alter_table("persona_pending_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_persona_pending_dedupe",
            ["doctor_id", "pattern_hash", "status"],
        )


def downgrade() -> None:
    with op.batch_alter_table("persona_pending_items") as batch_op:
        batch_op.drop_constraint("uq_persona_pending_dedupe", type_="unique")
    op.drop_index("ix_kb_pending_items_pattern_hash", table_name="kb_pending_items")
    op.drop_index("ix_kb_pending_items_doctor_id", table_name="kb_pending_items")
    op.drop_table("kb_pending_items")
