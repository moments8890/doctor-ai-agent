"""Pipeline types for the Understand → Execute → Compose runtime (ADR 0012, 0013)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ───────────────────────────────────────────────────────────────────


class ActionType(str, Enum):
    """Simplified action types (ADR 0013 Stream A)."""
    none = "none"
    query = "query"
    record = "record"
    update = "update"
    task = "task"


class ClarificationKind(str, Enum):
    """Shared by understand and resolve (ADR 0012 §4)."""
    missing_field = "missing_field"
    ambiguous_intent = "ambiguous_intent"
    ambiguous_patient = "ambiguous_patient"
    not_found = "not_found"
    invalid_time = "invalid_time"
    blocked = "blocked"
    unsupported = "unsupported"


class ResponseMode(str, Enum):
    """How compose renders the final reply (ADR 0012 §3, §9)."""
    direct_reply = "direct_reply"
    llm_compose = "llm_compose"
    template = "template"


# ── Const tables ────────────────────────────────────────────────────────────

RESPONSE_MODE_TABLE: Dict[ActionType, ResponseMode] = {
    ActionType.none: ResponseMode.direct_reply,
    ActionType.query: ResponseMode.llm_compose,
    ActionType.record: ResponseMode.template,
    ActionType.update: ResponseMode.template,
    ActionType.task: ResponseMode.template,
}

READ_ACTIONS = frozenset({ActionType.query})
WRITE_ACTIONS = frozenset({ActionType.record, ActionType.update, ActionType.task})


# ── Per-action typed args (ADR 0013 Stream A) ──────────────────────────────


@dataclass
class QueryArgs:
    target: Optional[str] = None       # "records" | "patients" | "tasks"
    patient_name: Optional[str] = None
    limit: Optional[int] = None
    status: Optional[str] = None       # for tasks: "pending" | "completed"


@dataclass
class RecordArgs:
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None


@dataclass
class UpdateArgs:
    instruction: str
    patient_name: Optional[str] = None


@dataclass
class TaskArgs:
    patient_name: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    scheduled_for: Optional[str] = None
    remind_at: Optional[str] = None


# Map action_type → args dataclass for validation
ARGS_TYPE_TABLE: Dict[ActionType, type] = {
    ActionType.none: type(None),
    ActionType.query: QueryArgs,
    ActionType.record: RecordArgs,
    ActionType.update: UpdateArgs,
    ActionType.task: TaskArgs,
}


# ── Clarification (shared by understand + resolve, ADR 0012 §4) ────────────


@dataclass
class Clarification:
    kind: ClarificationKind
    missing_fields: List[str] = field(default_factory=list)
    options: List[Dict[str, Any]] = field(default_factory=list)
    suggested_question: Optional[str] = None
    message_key: Optional[str] = None
    searched_name: Optional[str] = None  # patient name that was looked up


# ── Understand output (ADR 0012 §3) ────────────────────────────────────────


@dataclass
class ActionIntent:
    action_type: ActionType
    args: Optional[Any] = None  # typed per action via ARGS_TYPE_TABLE


@dataclass
class UnderstandResult:
    actions: List[ActionIntent]
    chat_reply: Optional[str] = None  # only for action_type == none
    clarification: Optional[Clarification] = None


# ── Execute output types (ADR 0012 §5a–5c) ─────────────────────────────────


@dataclass
class ResolvedAction:
    action_type: ActionType
    patient_id: Optional[int] = None   # fully resolved for patient-scoped actions
    patient_name: Optional[str] = None
    args: Optional[Any] = None         # validated and normalised
    record_id: Optional[int] = None    # resolve-time: target record for update


@dataclass
class ReadResult:
    status: str  # "ok" | "empty" | "error"
    data: Optional[Any] = None
    total_count: Optional[int] = None
    truncated: bool = False
    message_key: Optional[str] = None
    error_key: Optional[str] = None


@dataclass
class CommitResult:
    status: str  # "ok" | "pending_confirmation" | "error"
    data: Optional[Any] = None
    message_key: Optional[str] = None
    error_key: Optional[str] = None


# ── Errors ──────────────────────────────────────────────────────────────────


class UnderstandError(Exception):
    """Raised when the understand LLM call fails or returns unparseable output."""
    pass
