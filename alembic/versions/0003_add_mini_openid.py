"""Add mini_openid to doctors table for KF ↔ Mini App identity linking

Revision ID: 0003_add_mini_openid
Revises: 0002_schema_evolution
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0003_add_mini_openid"
down_revision = "0002_schema_evolution"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _has_index(table: str, index_name: str) -> bool:
    conn = op.get_bind()
    try:
        return any(i["name"] == index_name for i in inspect(conn).get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if "mini_openid" not in _cols("doctors"):
        op.execute(text("ALTER TABLE doctors ADD COLUMN mini_openid VARCHAR(128) DEFAULT NULL"))

    idx = "ux_doctors_mini_openid"
    if not _has_index("doctors", idx):
        if dialect == "mysql":
            op.execute(text(
                "CREATE UNIQUE INDEX ux_doctors_mini_openid ON doctors(mini_openid)"
            ))
        else:
            op.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_doctors_mini_openid ON doctors(mini_openid)"
            ))


def downgrade() -> None:
    pass
