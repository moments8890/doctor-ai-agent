"""Add nickname + passcode_hash auth columns to doctors and patients.

Until now, the v2 unified login squatted the existing ``phone`` column for the
nickname and the ``year_of_birth`` column for a plaintext numeric passcode.
That confused real-phone / real-birth-year semantics with auth credentials,
and stored the passcode in cleartext.

This migration:
  1. Adds ``nickname`` (String(64)) and ``passcode_hash`` (String(255)) to
     ``doctors`` and ``patients``, both nullable.
  2. Indexes ``nickname`` (and ``(doctor_id, nickname)`` for patients) so the
     login lookup stays fast.
  3. Backfills the new columns from the legacy auth-hack values:
       - Doctors: every row used phone-as-nickname and year_of_birth-as-passcode,
         so all rows with both populated are migrated.
       - Patients: only rows where both ``phone`` and ``year_of_birth`` are
         non-null are backfilled. Patients created via the doctor-side flow
         (preseed / manual) typically have ``phone IS NULL`` and a real birth
         year, so leaving them alone preserves age filtering.
  4. Leaves ``phone`` and ``year_of_birth`` columns intact so they can serve
     their original purpose (real phone / real birth year) going forward.

Revision ID: d1e2f3a4b5c6
Revises: a3b7c1d9e4f2
Create Date: 2026-04-24 00:00:00.000000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "a3b7c1d9e4f2"
branch_labels = None
depends_on = None


# Make src/ importable so we can reuse the project's PBKDF2 helper from the
# migration body. env.py already prepends src/ in most invocations, but this
# guard keeps the migration runnable in isolation.
_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _hash(plaintext: str) -> str:
    from utils.hashing import hash_passcode
    return hash_passcode(plaintext)


def upgrade() -> None:
    op.add_column("doctors", sa.Column("nickname", sa.String(length=64), nullable=True))
    op.add_column("doctors", sa.Column("passcode_hash", sa.String(length=255), nullable=True))
    op.add_column("patients", sa.Column("nickname", sa.String(length=64), nullable=True))
    op.add_column("patients", sa.Column("passcode_hash", sa.String(length=255), nullable=True))

    op.create_index("ix_doctors_nickname", "doctors", ["nickname"])
    op.create_index("ix_patients_doctor_nickname", "patients", ["doctor_id", "nickname"])

    bind = op.get_bind()

    # Filter out empty-string phone entries: a NULL check alone is not enough
    # because doctor-created patients sometimes carry phone='' (empty), which
    # would otherwise pollute nickname='' rows.
    doctor_rows = bind.execute(sa.text(
        "SELECT doctor_id, phone, year_of_birth FROM doctors "
        "WHERE phone IS NOT NULL AND phone <> '' AND year_of_birth IS NOT NULL"
    )).fetchall()
    for doctor_id, phone, yob in doctor_rows:
        bind.execute(
            sa.text(
                "UPDATE doctors SET nickname = :nick, passcode_hash = :ph "
                "WHERE doctor_id = :id"
            ),
            {"nick": phone, "ph": _hash(str(yob)), "id": doctor_id},
        )

    patient_rows = bind.execute(sa.text(
        "SELECT id, phone, year_of_birth FROM patients "
        "WHERE phone IS NOT NULL AND phone <> '' AND year_of_birth IS NOT NULL"
    )).fetchall()
    for pid, phone, yob in patient_rows:
        bind.execute(
            sa.text(
                "UPDATE patients SET nickname = :nick, passcode_hash = :ph "
                "WHERE id = :id"
            ),
            {"nick": phone, "ph": _hash(str(yob)), "id": pid},
        )


def downgrade() -> None:
    op.drop_index("ix_patients_doctor_nickname", table_name="patients")
    op.drop_index("ix_doctors_nickname", table_name="doctors")
    op.drop_column("patients", "passcode_hash")
    op.drop_column("patients", "nickname")
    op.drop_column("doctors", "passcode_hash")
    op.drop_column("doctors", "nickname")
