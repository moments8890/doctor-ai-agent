"""add_finished_onboarding

Revision ID: dfbe8eaa5be9
Revises: 0003_remove_review
Create Date: 2026-04-15 18:48:57.238268
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dfbe8eaa5be9'
down_revision = '0003_remove_review'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('doctors', sa.Column('finished_onboarding', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    # Existing doctors have already completed onboarding
    op.execute("UPDATE doctors SET finished_onboarding = 1")


def downgrade() -> None:
    op.drop_column('doctors', 'finished_onboarding')
