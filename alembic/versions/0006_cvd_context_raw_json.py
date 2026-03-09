"""CVD context: replace 26 clinical columns with raw_json + 2 extra indexes

Revision ID: 0006_cvd_context_raw_json
Revises: 0005_cvd_fields_expansion
Create Date: 2026-03-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

revision = "0006_cvd_context_raw_json"
down_revision = "0005_cvd_fields_expansion"
branch_labels = None
depends_on = None

# Columns to DROP (the 26 clinical detail columns now stored in raw_json).
# surgery_status and diagnosis_subtype are kept as promoted filterable columns.
_DROP_COLS = [
    "hemorrhage_location",
    "ich_score",
    "ich_volume_ml",
    "hemorrhage_etiology",
    "hunt_hess_grade",
    "fisher_grade",
    "wfns_grade",
    "modified_fisher_grade",
    "vasospasm_status",
    "nimodipine_regimen",
    "hydrocephalus_status",
    "spetzler_martin_grade",
    "gcs_score",
    "aneurysm_location",
    "aneurysm_size_mm",
    "aneurysm_neck_width_mm",
    "aneurysm_morphology",
    "aneurysm_daughter_sac",
    "aneurysm_treatment",
    "phases_score",
    "suzuki_stage",
    "bypass_type",
    "perfusion_status",
    "surgery_type",
    "surgery_date",
    "surgical_approach",
    "mrs_score",
    "barthel_index",
]


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


def _drop_if_present(table: str, col: str) -> None:
    """SQLite < 3.35 doesn't support DROP COLUMN — skip silently on those versions."""
    if col not in _existing_cols(table):
        return
    try:
        op.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))
    except Exception:
        pass  # SQLite < 3.35: column stays but is unused; harmless


def upgrade() -> None:
    # 1. Add raw_json column
    _add_if_missing("neuro_cvd_context", "raw_json", "TEXT DEFAULT NULL")

    # 2. Migrate existing rows: pack promoted columns back into raw_json
    #    so data already in the DB isn't lost on upgrade.
    conn = op.get_bind()
    existing = _existing_cols("neuro_cvd_context")
    migrate_cols = [c for c in _DROP_COLS if c in existing]
    if migrate_cols:
        rows = conn.execute(text("SELECT id, raw_json, " + ", ".join(migrate_cols) +
                                  " FROM neuro_cvd_context")).fetchall()
        import json
        col_names = ["id", "raw_json"] + migrate_cols
        for row in rows:
            d = dict(zip(col_names, row))
            row_id = d.pop("id")
            existing_json = {}
            try:
                existing_json = json.loads(d.pop("raw_json") or "{}")
            except Exception:
                d.pop("raw_json", None)
            # Merge existing typed values into raw_json (typed values win)
            merged = {**existing_json, **{k: v for k, v in d.items() if v is not None}}
            if merged:
                conn.execute(
                    text("UPDATE neuro_cvd_context SET raw_json = :j WHERE id = :i"),
                    {"j": json.dumps(merged, ensure_ascii=False), "i": row_id},
                )

    # 3. Drop the clinical columns (idempotent — skips on SQLite < 3.35)
    for col in _DROP_COLS:
        _drop_if_present("neuro_cvd_context", col)

    # 4. Add new indexes for promoted filterable columns
    try:
        op.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_neuro_cvd_subtype "
            "ON neuro_cvd_context (doctor_id, diagnosis_subtype)"
        ))
        op.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_neuro_cvd_surgery_status "
            "ON neuro_cvd_context (doctor_id, surgery_status)"
        ))
    except Exception:
        pass


def downgrade() -> None:
    pass
