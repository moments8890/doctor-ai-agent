"""Add interview_json and cvd_scale_json to doctor_session_states

Enables persistence of in-progress InterviewState and CVDScaleSession so that
server restarts no longer lose mid-conversation guided interview state.

Revision ID: 0010_session_state_interview_cvd
Revises: 0009_schema_integrity_and_indexes
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0010_session_state_interview_cvd"
down_revision = "0009_schema_integrity_and_indexes"
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
    _add_if_missing("doctor_session_states", "interview_json", "TEXT DEFAULT NULL")
    _add_if_missing("doctor_session_states", "cvd_scale_json", "TEXT DEFAULT NULL")


def downgrade() -> None:
    pass
