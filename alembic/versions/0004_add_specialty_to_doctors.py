"""Add specialty column to doctors table

Revision ID: 0004_add_specialty_to_doctors
Revises: 0003_add_mini_openid
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0004_add_specialty_to_doctors"
down_revision = "0003_add_mini_openid"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def upgrade() -> None:
    if "specialty" not in _cols("doctors"):
        op.execute(text("ALTER TABLE doctors ADD COLUMN specialty VARCHAR(64) DEFAULT NULL"))


def downgrade() -> None:
    pass
