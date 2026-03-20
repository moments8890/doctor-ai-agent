"""Action enum — all doctor-facing intents.

Chips expose CHIP_ACTIONS subset. The ReAct agent classifies into these same
values via LLM; chips short-circuit that classification step.
"""
from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    daily_summary    = "daily_summary"
    create_record    = "create_record"
    query_patient    = "query_patient"
    query_records    = "query_records"
    update_record    = "update_record"
    create_task      = "create_task"
    export_pdf       = "export_pdf"
    search_knowledge = "search_knowledge"
    diagnosis        = "diagnosis"
    general          = "general"


CHIP_ACTIONS: set[Action] = {
    Action.daily_summary,
    Action.create_record,
    Action.query_patient,
    Action.diagnosis,
}
