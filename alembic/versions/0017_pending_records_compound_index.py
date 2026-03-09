"""Add compound index (doctor_id, status, expires_at) on pending_records

- Adds ix_pending_records_doctor_status_expires for efficient doctor-scoped expiry queries

Revision ID: 0017_pending_records_compound_index
Revises: 0016_patient_demographics_and_hardening
Create Date: 2026-03-09
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import inspect, text

revision = "0017_pending_records_compound_index"
down_revision = "0016_patient_demographics_and_hardening"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
        {"n": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    idx = "ix_pending_records_doctor_status_expires"
    if not _index_exists(conn, idx):
        op.create_index(idx, "pending_records", ["doctor_id", "status", "expires_at"])
        logger.info("Created index %s", idx)
    else:
        logger.info("Index %s already exists, skipping", idx)


def downgrade() -> None:
    conn = op.get_bind()
    idx = "ix_pending_records_doctor_status_expires"
    if _index_exists(conn, idx):
        op.drop_index(idx, table_name="pending_records")
