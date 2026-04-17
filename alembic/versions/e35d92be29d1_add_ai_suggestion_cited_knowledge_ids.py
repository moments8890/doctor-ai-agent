"""add_ai_suggestion_cited_knowledge_ids

Revision ID: e35d92be29d1
Revises: d3576d9356f8
Create Date: 2026-04-16 22:05:37.792344
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e35d92be29d1'
down_revision = 'd3576d9356f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_suggestions", sa.Column("cited_knowledge_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_suggestions", "cited_knowledge_ids")
