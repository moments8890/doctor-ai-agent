"""患者门户访问码的 PBKDF2-SHA256 哈希与校验工具。

Patient portal access code hashing using PBKDF2-SHA256.

Hashes are stored as:  pbkdf2sha256$<iterations>$<salt_hex>$<hash_hex>
This format is self-describing and allows future algorithm migration.
"""

from __future__ import annotations

import hashlib
import hmac
import os


_ALGORITHM = "pbkdf2sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 32
_HASH_BYTES = 32


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
