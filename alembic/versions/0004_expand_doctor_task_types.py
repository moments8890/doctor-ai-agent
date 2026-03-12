"""Expand doctor_tasks.task_type CHECK constraint to the live task type set.

Revision ID: 0004_expand_doctor_task_types
Revises: 0003_schema_tightening
Create Date: 2026-03-11
"""

from __future__ import annotations

from alembic import op

revision = "0004_expand_doctor_task_types"
down_revision = "0003_schema_tightening"
branch_labels = None
depends_on = None

_EXPANDED_TASK_TYPE_CHECK = (
    "task_type IN ('follow_up','emergency','appointment','general',"
    "'lab_review','referral','imaging','medication')"
)
_LEGACY_TASK_TYPE_CHECK = "task_type IN ('follow_up','emergency','appointment')"


def upgrade() -> None:
    with op.batch_alter_table("doctor_tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_doctor_tasks_task_type", type_="check")
        batch_op.create_check_constraint("ck_doctor_tasks_task_type", _EXPANDED_TASK_TYPE_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("doctor_tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_doctor_tasks_task_type", type_="check")
        batch_op.create_check_constraint("ck_doctor_tasks_task_type", _LEGACY_TASK_TYPE_CHECK)
