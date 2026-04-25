"""chat_interview_merge_backfill

Backfill existing single-string history fields into FieldEntryDB
single-entry rows. Each non-empty value on the 7 history columns of
medical_records becomes one record_field_entries row, with
intake_segment_id=NULL and created_at copied from the parent record.

Idempotent: skips any record that already has at least one entry,
so re-running the upgrade is a no-op.

Revision ID: 11f853154f3e
Revises: 31a20bf68800
Create Date: 2026-04-25 15:04:43.551494
"""
from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11f853154f3e'
down_revision = '31a20bf68800'
branch_labels = None
depends_on = None


# The 7 history fields on medical_records that move to FieldEntryDB.
# Append-only writes go to FieldEntryDB after Phase 0; legacy columns
# stay populated for backward-compat reads.
FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


def upgrade() -> None:
    bind = op.get_bind()
    records = bind.execute(sa.text(
        "SELECT id, created_at, " + ", ".join(FIELDS) + " FROM medical_records"
    )).mappings().all()

    existing_record_ids = {
        row["record_id"]
        for row in bind.execute(sa.text(
            "SELECT DISTINCT record_id FROM record_field_entries"
        )).mappings().all()
    }

    inserts = 0
    for r in records:
        if r["id"] in existing_record_ids:
            continue
        for field in FIELDS:
            value = r[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            bind.execute(sa.text(
                "INSERT INTO record_field_entries "
                "(record_id, field_name, text, intake_segment_id, created_at) "
                "VALUES (:rid, :fn, :tx, NULL, :ca)"
            ), {
                "rid": r["id"],
                "fn": field,
                "tx": value,
                "ca": r["created_at"] or datetime.utcnow(),
            })
            inserts += 1
    print(f"[backfill] inserted {inserts} field entries from "
          f"{len(records) - len(existing_record_ids)} new records")


def downgrade() -> None:
    # No-op: removing backfilled rows would lose data if the original
    # columns were edited in the meantime. Safe rollback is to drop the
    # FieldEntryDB table via the prior migration (31a20bf68800).
    pass
