"""Hash existing plaintext WeChat identifiers with HMAC-SHA256

Reads WECHAT_ID_HMAC_KEY from the environment. If the key is not set,
the migration is a no-op (skipped safely) — run it again after setting
the key.

Revision ID: 0012_hmac_wechat_ids
Revises: 0011_schema_cleanup_and_constraints
Create Date: 2026-03-09
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from alembic import op
from sqlalchemy import text

revision = "0012_hmac_wechat_ids"
down_revision = "0011_schema_cleanup_and_constraints"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.migration.0012")


def _hmac_key() -> bytes | None:
    raw = os.environ.get("WECHAT_ID_HMAC_KEY", "").strip()
    return raw.encode() if raw else None


def _hash(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def _looks_hashed(value: str) -> bool:
    """64-char hex string means it's already an HMAC-SHA256 digest."""
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def upgrade() -> None:
    key = _hmac_key()
    if key is None:
        log.warning(
            "[0012] WECHAT_ID_HMAC_KEY not set — skipping WeChat ID hashing. "
            "Set the env var and run 'alembic upgrade 0012_hmac_wechat_ids' again."
        )
        return

    conn = op.get_bind()

    # Hash wechat_user_id
    rows = conn.execute(
        text("SELECT doctor_id, wechat_user_id FROM doctors WHERE wechat_user_id IS NOT NULL")
    ).fetchall()
    updated_wechat = 0
    for doctor_id, wechat_user_id in rows:
        if wechat_user_id and not _looks_hashed(wechat_user_id):
            hashed = _hash(key, wechat_user_id)
            conn.execute(
                text("UPDATE doctors SET wechat_user_id = :h WHERE doctor_id = :d"),
                {"h": hashed, "d": doctor_id},
            )
            updated_wechat += 1

    # Hash mini_openid
    rows = conn.execute(
        text("SELECT doctor_id, mini_openid FROM doctors WHERE mini_openid IS NOT NULL")
    ).fetchall()
    updated_mini = 0
    for doctor_id, mini_openid in rows:
        if mini_openid and not _looks_hashed(mini_openid):
            hashed = _hash(key, mini_openid)
            conn.execute(
                text("UPDATE doctors SET mini_openid = :h WHERE doctor_id = :d"),
                {"h": hashed, "d": doctor_id},
            )
            updated_mini += 1

    log.info(
        "[0012] WeChat ID hashing complete | updated_wechat_user_id=%s updated_mini_openid=%s",
        updated_wechat,
        updated_mini,
    )


def downgrade() -> None:
    # Cannot reverse a one-way hash — restore from backup if needed.
    log.warning("[0012] downgrade is a no-op: hashed values cannot be reversed")
