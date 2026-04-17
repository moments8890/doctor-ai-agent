"""add_hallucinated_citations

Revision ID: d3576d9356f8
Revises: 1357bf8e6e2a
Create Date: 2026-04-16 21:58:41.796107
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3576d9356f8'
down_revision = '1357bf8e6e2a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hallucinated_citations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("context", sa.String(32), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=True),
        sa.Column("hallucinated_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_hallucinated_citations_doctor_id", "hallucinated_citations", ["doctor_id"])
    op.create_index("ix_hallucinated_citations_created_at", "hallucinated_citations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_hallucinated_citations_created_at", table_name="hallucinated_citations")
    op.drop_index("ix_hallucinated_citations_doctor_id", table_name="hallucinated_citations")
    op.drop_table("hallucinated_citations")
