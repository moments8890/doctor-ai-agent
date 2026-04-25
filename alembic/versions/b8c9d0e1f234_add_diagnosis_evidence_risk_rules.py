"""Add evidence/risk_signals/trigger_rule_ids columns to ai_suggestions.

Part of the diagnosis schema migration (locked plan Day 10-15). New
diagnosis prompt (2026-04-25) outputs:
- evidence: List[str]      atomic clinical facts
- risk_signals: List[str]  when to escalate
- trigger_rule_ids: List[str]  KB rules that fired

These coexist with legacy `confidence` and `detail` columns (kept
nullable for backward-compat with historical rows). Frontend will
prefer new fields when present; falls back to detail/confidence.

Revision ID: b8c9d0e1f234
Revises: a4b5c6d7e8f9
Create Date: 2026-04-25 14:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "b8c9d0e1f234"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSON-encoded arrays stored as Text. Same pattern as cited_knowledge_ids.
    op.add_column("ai_suggestions", sa.Column("evidence_json", sa.Text(), nullable=True))
    op.add_column("ai_suggestions", sa.Column("risk_signals_json", sa.Text(), nullable=True))
    op.add_column("ai_suggestions", sa.Column("trigger_rule_ids_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_suggestions", "trigger_rule_ids_json")
    op.drop_column("ai_suggestions", "risk_signals_json")
    op.drop_column("ai_suggestions", "evidence_json")
