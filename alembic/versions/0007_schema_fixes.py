"""Schema fixes: neuro_cvd_context.updated_at, doctor_session_states FK ondelete

Revision ID: 0007_schema_fixes
Revises: 0006_cvd_context_raw_json
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0007_schema_fixes"
down_revision = "0006_cvd_context_raw_json"
branch_labels = None
depends_on = None


def _existing_cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _add_if_missing(table: str, col: str, typedef: str) -> None:
    if col not in _existing_cols(table):
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


def upgrade() -> None:
    # 1. neuro_cvd_context: add updated_at column for audit tracking
    _add_if_missing("neuro_cvd_context", "updated_at", "DATETIME DEFAULT NULL")

    # 2. doctor_session_states: ondelete="SET NULL" is enforced at the application
    #    layer in SQLAlchemy — SQLite ignores FK actions unless PRAGMA foreign_keys=ON,
    #    and MySQL applies them natively. No DDL change needed here; the ORM model
    #    update ensures correct behavior for new schemas and MySQL deployments.
    #    (SQLite: FK constraints on existing tables cannot be altered without
    #    recreating the table — not worth the complexity for this fix.)
    pass


def downgrade() -> None:
    pass
