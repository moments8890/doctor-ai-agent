"""CVD fields expansion — add 12 P1 clinical fields to neuro_cvd_context

Revision ID: 0005_cvd_fields_expansion
Revises: 0004_add_specialty_to_doctors
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0005_cvd_fields_expansion"
down_revision = "0004_add_specialty_to_doctors"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    conn = op.get_bind()
    try:
        return {c["name"] for c in inspect(conn).get_columns(table)}
    except Exception:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}


def _add(table: str, col: str, typedef: str) -> None:
    """ADD COLUMN only when missing (idempotent)."""
    if col not in _cols(table):
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))


def upgrade() -> None:
    # New CVD P1 fields in neuro_cvd_context
    for col, typedef in {
        # ICH
        "hemorrhage_etiology": "VARCHAR(32) DEFAULT NULL",
        # SAH extended grading
        "wfns_grade": "INTEGER DEFAULT NULL",
        "modified_fisher_grade": "INTEGER DEFAULT NULL",
        # SAH post-op monitoring
        "vasospasm_status": "VARCHAR(32) DEFAULT NULL",
        "nimodipine_regimen": "TEXT DEFAULT NULL",
        # ICH/SAH shared complication
        "hydrocephalus_status": "VARCHAR(32) DEFAULT NULL",
        # Aneurysm extended
        "aneurysm_neck_width_mm": "REAL DEFAULT NULL",
        "aneurysm_daughter_sac": "VARCHAR(8) DEFAULT NULL",
        "phases_score": "INTEGER DEFAULT NULL",
        # Moyamoya
        "suzuki_stage": "INTEGER DEFAULT NULL",
        "bypass_type": "VARCHAR(32) DEFAULT NULL",
        "perfusion_status": "VARCHAR(32) DEFAULT NULL",
    }.items():
        _add("neuro_cvd_context", col, typedef)


def downgrade() -> None:
    pass
