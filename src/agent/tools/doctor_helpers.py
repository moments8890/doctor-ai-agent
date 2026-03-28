"""Shared serialization helpers for doctor tools."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _serialize_record(r: Any) -> Dict[str, Any]:
    tags = []
    if getattr(r, "tags", None):
        try:
            tags = json.loads(r.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return {
        "id": r.id,
        "content": r.content or "",
        "tags": tags,
        "record_type": getattr(r, "record_type", None),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_patient(p: Any) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "gender": getattr(p, "gender", None),
        "year_of_birth": getattr(p, "year_of_birth", None),
    }


def _serialize_task(t: Any) -> Dict[str, Any]:
    return {
        "id": t.id,
        "task_type": getattr(t, "task_type", None),
        "title": getattr(t, "title", None),
        "content": getattr(t, "content", None),
        "status": getattr(t, "status", None),
        "patient_id": getattr(t, "patient_id", None),
        "due_at": t.due_at.isoformat() if getattr(t, "due_at", None) else None,
    }
