"""Make nickname indexes unique on doctors and patients.

Followup to ``d1e2f3a4b5c6_add_nickname_passcode_auth``: now that nickname is
the canonical login credential, enforce uniqueness at the database level.

  - ``ix_doctors_nickname`` becomes UNIQUE: at most one doctor per nickname.
  - ``ix_patients_doctor_nickname`` becomes UNIQUE on ``(doctor_id, nickname)``:
    each doctor's patients have distinct nicknames; the same nickname may
    still appear under different doctors.

Both indexes were created in the previous migration as ordinary (non-unique)
indexes. We drop and re-create them with ``unique=True``. SQLite, MySQL, and
Postgres all treat NULLs as distinct in unique indexes, so existing rows with
nickname IS NULL (e.g. doctor-created patients without an auth profile) are
unaffected.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-04-24 00:30:00.000000
"""
from __future__ import annotations

from alembic import op


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_doctors_nickname", table_name="doctors")
    op.create_index(
        "ix_doctors_nickname", "doctors", ["nickname"], unique=True,
    )

    op.drop_index("ix_patients_doctor_nickname", table_name="patients")
    op.create_index(
        "ix_patients_doctor_nickname",
        "patients",
        ["doctor_id", "nickname"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_patients_doctor_nickname", table_name="patients")
    op.create_index(
        "ix_patients_doctor_nickname",
        "patients",
        ["doctor_id", "nickname"],
    )

    op.drop_index("ix_doctors_nickname", table_name="doctors")
    op.create_index("ix_doctors_nickname", "doctors", ["nickname"])
