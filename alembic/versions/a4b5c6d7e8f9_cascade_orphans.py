"""Tighten FK delete rules so deleting a doctor or patient is clean.

The SQLAlchemy models declare ``ondelete="CASCADE"`` for ai_suggestions and
message_drafts in some places, but the live MySQL schema was created from
older migrations and these two FKs were left as ``NO ACTION``:

  ai_suggestions.record_id          → medical_records.id    (NO ACTION → CASCADE)
  message_drafts.source_message_id  → patient_messages.id   (NO ACTION → CASCADE)

The result was that hard-deleting a doctor or patient blew up on these
constraints, forcing manual ``SET FOREIGN_KEY_CHECKS=0`` cleanup.
Right-to-be-forgotten / account deletion needs a clean cascade.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-04-25 15:00:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


# Constraint names from the live MySQL schema (verified via INFORMATION_SCHEMA).
_AI_SUG_FK = "ai_suggestions_ibfk_1"
_DRAFT_FK = "message_drafts_ibfk_1"


def _is_mysql() -> bool:
    return op.get_context().dialect.name == "mysql"


def upgrade() -> None:
    # SQLite (dev) has no real ALTER-FK support; tests recreate schema each
    # run from the SQLAlchemy model definitions, which already declare the
    # right ondelete behavior, so SQLite gets the new rules without us
    # touching them here.
    if not _is_mysql():
        return

    op.drop_constraint(_AI_SUG_FK, "ai_suggestions", type_="foreignkey")
    op.create_foreign_key(
        _AI_SUG_FK, "ai_suggestions", "medical_records",
        ["record_id"], ["id"], ondelete="CASCADE",
    )

    op.drop_constraint(_DRAFT_FK, "message_drafts", type_="foreignkey")
    op.create_foreign_key(
        _DRAFT_FK, "message_drafts", "patient_messages",
        ["source_message_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    if not _is_mysql():
        return

    op.drop_constraint(_DRAFT_FK, "message_drafts", type_="foreignkey")
    op.create_foreign_key(
        _DRAFT_FK, "message_drafts", "patient_messages",
        ["source_message_id"], ["id"],
    )

    op.drop_constraint(_AI_SUG_FK, "ai_suggestions", type_="foreignkey")
    op.create_foreign_key(
        _AI_SUG_FK, "ai_suggestions", "medical_records",
        ["record_id"], ["id"],
    )
