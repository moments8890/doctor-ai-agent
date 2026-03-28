"""Doctor-role business logic — called by Plan-and-Act handlers.

This module is the public hub. Shared helpers live in doctor_helpers.py,
read-only tools in doctor_read.py, and write tools in doctor_write.py.
"""
from __future__ import annotations

# ── Shared serialization helpers (re-exported for backwards compat) ──
from agent.tools.doctor_helpers import (
    _serialize_record,
    _serialize_patient,
    _serialize_task,
)

# ── Read-only tools ──────────────────────────────────────────────────
from agent.tools.doctor_read import (
    query_records,
    list_patients,
    list_tasks,
    search_knowledge,
    search_patients,
    get_patient_timeline,
)

# ── Write tools ──────────────────────────────────────────────────────
from agent.tools.doctor_write import (
    create_record,
    update_record,
    create_task,
    complete_task,
    export_pdf,
)

__all__ = [
    # helpers
    "_serialize_record",
    "_serialize_patient",
    "_serialize_task",
    # read
    "query_records",
    "list_patients",
    "list_tasks",
    "search_knowledge",
    "search_patients",
    "get_patient_timeline",
    # write
    "create_record",
    "update_record",
    "create_task",
    "complete_task",
    "export_pdf",
]
