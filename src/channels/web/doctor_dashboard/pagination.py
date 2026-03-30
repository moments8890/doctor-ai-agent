"""Cursor-based (keyset) pagination helpers."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException


def encode_cursor(created_at: datetime, row_id: int) -> str:
    """Encode a (created_at, id) pair into an opaque base64 cursor string.

    The cursor is a JSON array ``[iso_timestamp, id]`` encoded with
    URL-safe base64 so clients can pass it as a query parameter without
    escaping.
    """
    ts = created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") if created_at else ""
    payload = json.dumps([ts, row_id], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: Optional[str]) -> Optional[Tuple[datetime, int]]:
    """Decode an opaque cursor back into ``(created_at, id)``.

    Returns ``None`` when *cursor* is ``None`` or empty.
    Raises :class:`~fastapi.HTTPException` (400) on malformed input.
    """
    if cursor is None or not isinstance(cursor, str) or not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, row_id = json.loads(raw)
        created_at = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
        return created_at, int(row_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")
