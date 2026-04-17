"""add draft_id to knowledge_usage_log

Revision ID: a1b2c3d4e5f6
Revises: e35d92be29d1
Create Date: 2026-04-16 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e35d92be29d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('knowledge_usage_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('draft_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_knowledge_usage_log_draft_id',
            'message_drafts',
            ['draft_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('knowledge_usage_log', schema=None) as batch_op:
        batch_op.drop_constraint('fk_knowledge_usage_log_draft_id', type_='foreignkey')
        batch_op.drop_column('draft_id')
