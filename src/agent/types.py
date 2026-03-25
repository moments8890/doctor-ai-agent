"""Plan-and-Act agent types — routing, dispatch, and handler contracts."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """7 routing intents — routing LLM classifies into one of these."""
    query_record = "query_record"
    create_record = "create_record"
    query_task = "query_task"
    create_task = "create_task"
    query_patient = "query_patient"
    daily_summary = "daily_summary"
    general = "general"


class RoutingResult(BaseModel):
    """Structured output from the routing LLM."""
    intent: IntentType
    patient_name: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    deferred: Optional[str] = None


class HandlerResult(BaseModel):
    """Return value from intent handlers."""
    reply: str
    data: Optional[Dict[str, Any]] = None


class TurnContext(BaseModel):
    """Context passed to every handler."""
    doctor_id: str
    text: str
    history: List[Dict[str, str]] = Field(default_factory=list)
    routing: RoutingResult
