"""Cap pending AI suggestions per (record, section).

Phase 2a data migration for the inline-suggestions plan
(docs/specs/2026-04-20-inline-suggestions-plan.md). The UI is moving to a
single decisive recommendation per decision axis (differential=1, treatment=1,
workup=2). This migration trims already-generated pending rows to match.

Caps (top N kept per record_id + section):
- differential -> 1
- treatment    -> 1
- workup       -> 2

"Top" ordering: (is_custom DESC, id ASC) — doctor-added custom rows win, then
LLM output order (id ascending).

Behavior:
- Rows beyond the cap (pending only, i.e. decision IS NULL) are SOFT-rejected:
  decision='rejected', decided_at=<migration time>, reason=<flag string>.
- Already-decided rows (confirmed/edited/rejected/custom) are untouched.
- downgrade() reverses by matching the reason flag exactly.

Reversibility guard: the reason flag string below is unique to this migration
so downgrade() will not touch any other rejected rows.

Revision ID: a7c4e9d1b3f2
Revises: f4a2c17b9d10
Create Date: 2026-04-20 21:40:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "a7c4e9d1b3f2"
down_revision = "f4a2c17b9d10"
branch_labels = None
depends_on = None


MIGRATION_REASON_FLAG = "migration_2026_04_20_cap"


def upgrade() -> None:
    """Soft-reject pending rows beyond the per-section cap.

    Uses a window-function subquery (ROW_NUMBER OVER PARTITION BY record_id,
    section ORDER BY is_custom DESC, id ASC) to rank pending rows within each
    group, then marks ranks beyond the cap as rejected. Window functions work
    on SQLite 3.25+ and MySQL 8.0+; the derived-table form (SELECT ... FROM
    (SELECT ... ) ranked WHERE ...) is portable across both dialects.

    Note: MySQL historically disallowed `UPDATE t WHERE id IN (SELECT ... FROM t)`
    but allows it when the inner query is wrapped in a derived table — which
    is exactly what we do here (the outer SELECT id FROM (ranked) ranked).
    """
    op.execute(
        f"""
        UPDATE ai_suggestions
        SET decision   = 'rejected',
            decided_at = CURRENT_TIMESTAMP,
            reason     = '{MIGRATION_REASON_FLAG}'
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       section,
                       ROW_NUMBER() OVER (
                           PARTITION BY record_id, section
                           ORDER BY is_custom DESC, id ASC
                       ) AS rn
                FROM ai_suggestions
                WHERE decision IS NULL
            ) ranked
            WHERE (ranked.section = 'differential' AND ranked.rn > 1)
               OR (ranked.section = 'treatment'    AND ranked.rn > 1)
               OR (ranked.section = 'workup'       AND ranked.rn > 2)
        )
        """
    )


def downgrade() -> None:
    """Revert rows marked by this migration back to pending.

    We identify our rows by the unique reason flag string so we cannot collide
    with other rejected rows (e.g. user-rejected or earlier cleanup scripts).
    """
    op.execute(
        f"""
        UPDATE ai_suggestions
        SET decision   = NULL,
            decided_at = NULL,
            reason     = NULL
        WHERE reason = '{MIGRATION_REASON_FLAG}'
        """
    )
