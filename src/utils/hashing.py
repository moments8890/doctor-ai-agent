"""Pure cryptographic utilities used by both db/ and services/ layers.

Contains:
- Patient portal access code generation and PBKDF2-SHA256 hashing
- WeChat identifier HMAC-SHA256 hashing for at-rest anonymisation
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import string
from typing import Optional


# ---------------------------------------------------------------------------
# Access code hashing (patient portal)
# ---------------------------------------------------------------------------
# Hash format: pbkdf2sha256$<iterations>$<salt_hex>$<hash_hex>

_ALGORITHM = "pbkdf2sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 32
_HASH_BYTES = 32

_CODE_LENGTH = 6
_CODE_ALPHABET = string.digits  # 0-9


def generate_access_code() -> str:
    """Generate a cryptographically random 6-digit access code.

    Returns the plaintext code (e.g. ``"482901"``).  The caller is responsible
    for hashing it via :func:`hash_access_code` before persistence.
    """
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def hash_access_code(plaintext: str) -> str:
    """Return a PBKDF2-SHA256 hash string for storage. Never stores plaintext."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, _ITERATIONS, dklen=_HASH_BYTES)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_access_code(plaintext: str, stored: str) -> bool:
    """Verify plaintext against a stored hash. Returns False on any format error."""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$", 3)
    except (ValueError, AttributeError):
        return False

    if algo != _ALGORITHM:
        return False

    try:
        iterations = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# WeChat ID hashing
# ---------------------------------------------------------------------------


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
