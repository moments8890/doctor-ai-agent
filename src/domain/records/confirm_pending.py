"""
Pending-record confirmation logic — STUB.

PendingRecord table has been removed. This module is kept as a stub
for any remaining callers but all functions return None.
"""

from __future__ import annotations

from typing import Any, Optional


async def save_pending_record(
    doctor_id: str, pending: Any, *, force_confirm: bool = False,
) -> Optional[tuple]:
    """No-op — PendingRecord table removed. Returns None."""
    return None
