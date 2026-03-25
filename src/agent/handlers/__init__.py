"""Handler registry — import all handlers to trigger @register decorators."""
from __future__ import annotations

from agent.handlers import (
    query_record,
    create_record,
    create_task,
    query_task,
    query_patient,
    daily_summary,
    general,
)
