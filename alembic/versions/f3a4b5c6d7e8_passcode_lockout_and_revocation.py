"""Add passcode lockout + revocation columns to doctors and patients.

Layered defense for credential brute force + token revocation:

  - ``passcode_failed_attempts``  INT NOT NULL DEFAULT 0 — counter, reset on
    successful login. Trips a per-account lockout when >= LOGIN_FAIL_THRESHOLD.

  - ``passcode_locked_until``     DATETIME NULL — set to now() + LOGIN_LOCK_SECONDS
    when the threshold is hit. Login refuses while > now(); cleared on next
    successful login.

  - ``passcode_version``          INT NOT NULL DEFAULT 1 — embedded as ``pcv``
    in the JWT. Bumping the column invalidates every previously-issued token
    for that user (the unified logout endpoint, and any future passcode-change
    flow, increments it).

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-04-25 06:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


_TABLES = ("doctors", "patients")


def upgrade() -> None:
    for t in _TABLES:
        op.add_column(
            t,
            sa.Column(
                "passcode_failed_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        op.add_column(
            t,
            sa.Column("passcode_locked_until", sa.DateTime(), nullable=True),
        )
        op.add_column(
            t,
            sa.Column(
                "passcode_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )


def downgrade() -> None:
    for t in _TABLES:
        op.drop_column(t, "passcode_version")
        op.drop_column(t, "passcode_locked_until")
        op.drop_column(t, "passcode_failed_attempts")
