"""merge onboarding + kb-pending branches

Revision ID: 8e6d5626af10
Revises: a1b2c3d4e5f6, dfbe8eaa5be9
Create Date: 2026-04-17 11:19:02.473370
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e6d5626af10'
down_revision = ('a1b2c3d4e5f6', 'dfbe8eaa5be9')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
