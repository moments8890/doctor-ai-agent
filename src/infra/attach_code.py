"""Patient attach code — small per-doctor permanent code patients use to bind.

Replaces the public-doctor-id binding with a code only the doctor knows. Schema
column is VARCHAR(8) for future headroom; v0 generates 4 chars from a 32-symbol
alphabet that excludes ambiguous characters (0/O, 1/I/l).
"""
import secrets

# 32-char alphabet excludes ambiguous: 0/O, 1/I/l
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
DEFAULT_LENGTH = 4


def generate_code(length: int = DEFAULT_LENGTH) -> str:
    """Cryptographically random uppercase code from the unambiguous alphabet."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def normalize(code: str | None) -> str:
    """User input → canonical form: uppercase, strip whitespace, no hyphens."""
    if not code:
        return ""
    return code.strip().upper().replace("-", "").replace(" ", "")
