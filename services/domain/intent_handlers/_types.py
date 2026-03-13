"""
HandlerResult — channel-agnostic result from shared intent handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from db.models.medical_record import MedicalRecord


@dataclass
class HandlerResult:
    """Channel-agnostic result from a shared intent handler.

    Routers convert this to their wire format:
    - Web → ChatResponse (JSON with pending metadata)
    - WeChat → plain-text reply string
    """

    reply: str
    switch_notification: Optional[str] = None  # e.g. "🔄 已从【A】切换到【B】"
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None    # ISO-8601 UTC
    records_list: List[Any] = field(default_factory=list)
    patients_list: List[Any] = field(default_factory=list)
