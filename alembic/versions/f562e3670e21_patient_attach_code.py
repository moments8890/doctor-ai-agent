"""patient_attach_code

Adds VARCHAR(8) patient_attach_code to doctors with a UNIQUE constraint and
backfills a random 4-char code for every existing doctor. The width of 8
leaves room to grow the v0 4-char default to 6 or 8 chars later without a
schema change.

Revision ID: f562e3670e21
Revises: e7c4f9a1b2d3
Create Date: 2026-04-26 10:06:49.461532
"""
from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f562e3670e21'
down_revision = 'e7c4f9a1b2d3'
branch_labels = None
depends_on = None


# Inlined to avoid coupling migrations to evolving application code.
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _gen() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def upgrade() -> None:
    op.add_column("doctors", sa.Column("patient_attach_code", sa.String(8), nullable=True))
    op.create_index(
        "ix_doctors_patient_attach_code", "doctors", ["patient_attach_code"], unique=True,
    )

    # Backfill existing doctors with random codes; retry on the rare unique-collision.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT doctor_id FROM doctors WHERE patient_attach_code IS NULL")
    ).all()
    used = {
        r[0] for r in bind.execute(
            sa.text(
                "SELECT patient_attach_code FROM doctors WHERE patient_attach_code IS NOT NULL"
            )
        ).all() if r[0]
    }
    for (did,) in rows:
        for _ in range(50):
            code = _gen()
            if code in used:
                continue
            try:
                bind.execute(
                    sa.text(
                        "UPDATE doctors SET patient_attach_code = :c WHERE doctor_id = :d"
                    ),
                    {"c": code, "d": did},
                )
                used.add(code)
                break
            except Exception:
                continue


def downgrade() -> None:
    op.drop_index("ix_doctors_patient_attach_code", table_name="doctors")
    op.drop_column("doctors", "patient_attach_code")
