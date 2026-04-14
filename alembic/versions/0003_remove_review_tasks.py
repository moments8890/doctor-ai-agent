"""Remove review-type tasks (belong in 审核 tab, not 任务).

Deletes tasks created by interview_summary with title starting with '审阅患者'.
These are review notifications, not actionable follow-up tasks.

Revision ID: 0003_remove_review
Revises: 0002_simplify_task
Create Date: 2026-04-14
"""
from __future__ import annotations

from alembic import op

revision = "0003_remove_review"
down_revision = "0002_simplify_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM doctor_tasks WHERE title LIKE '审阅患者%'")


def downgrade() -> None:
    pass  # Cannot restore deleted rows
