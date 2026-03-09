"""
HMAC-SHA256 hashing for WeChat identifiers stored in the Doctor registry.

When WECHAT_ID_HMAC_KEY is set in the environment, wechat_user_id and
mini_openid are stored as HMAC-SHA256 digests so that plaintext WeChat
identities are not persisted at rest.

If the key is not configured, hash_wechat_id() is a no-op (returns the
value unchanged). This allows gradual opt-in without breaking existing
deployments.

Migration note: run alembic migration 0012_hmac_wechat_ids to re-hash
existing plaintext values after setting WECHAT_ID_HMAC_KEY.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional


def _hmac_key() -> Optional[bytes]:
    raw = os.environ.get("WECHAT_ID_HMAC_KEY", "").strip()
    return raw.encode() if raw else None


def hash_wechat_id(value: Optional[str]) -> Optional[str]:
    """Return HMAC-SHA256 hex digest of *value* if WECHAT_ID_HMAC_KEY is set.

    Returns *value* unchanged when the key is not configured.
    Returns None when *value* is None or empty.
    """
    if not value:
        return value
    key = _hmac_key()
    if key is None:
        return value
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
