"""Pipeline types for the Understand → Execute → Compose runtime (ADR 0012)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ───────────────────────────────────────────────────────────────────


class ActionType(str, Enum):
    """All recognised operational action types (ADR 0012 §3, §6)."""
    query_records = "query_records"
    list_patients = "list_patients"
    list_tasks = "list_tasks"
    schedule_task = "schedule_task"
    select_patient = "select_patient"
    create_patient = "create_patient"
    create_record = "create_record"
    update_record = "update_record"
    none = "none"


class TaskType(str, Enum):
    """Schedule-task sub-classification (ADR 0012 §8)."""
    appointment = "appointment"
    follow_up = "follow_up"
    general = "general"


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
    ActionType.query_records: ResponseMode.llm_compose,
    ActionType.list_patients: ResponseMode.llm_compose,
    ActionType.list_tasks: ResponseMode.llm_compose,
    ActionType.schedule_task: ResponseMode.template,
    ActionType.select_patient: ResponseMode.template,
    ActionType.create_patient: ResponseMode.template,
    ActionType.create_record: ResponseMode.template,
    ActionType.update_record: ResponseMode.template,
}

READ_ACTIONS = frozenset({ActionType.query_records, ActionType.list_patients, ActionType.list_tasks})
WRITE_ACTIONS = frozenset({
    ActionType.schedule_task,
    ActionType.select_patient,
    ActionType.create_patient,
    ActionType.create_record,
    ActionType.update_record,
})


# ── Per-action typed args (ADR 0012 §8) ────────────────────────────────────


@dataclass
class SelectPatientArgs:
    patient_name: str


@dataclass
class CreatePatientArgs:
    patient_name: str
    gender: Optional[str] = None
    age: Optional[int] = None


@dataclass
class CreateRecordArgs:
    """Clinical content collected from chat_archive by commit engine."""
    patient_name: Optional[str] = None  # resolve auto-creates patient if not found


@dataclass
class UpdateRecordArgs:
    instruction: str
    patient_name: Optional[str] = None  # resolve auto-creates patient if not found


@dataclass
class QueryRecordsArgs:
    patient_name: Optional[str] = None
    limit: Optional[int] = None


@dataclass
class ListPatientsArgs:
    """Empty in phase 1."""
    pass


@dataclass
class ListTasksArgs:
    """Optional status filter for task listing."""
    status: Optional[str] = None  # "pending" | "completed" | None (all)


@dataclass
class ScheduleTaskArgs:
    task_type: Optional[str] = None  # validated against TaskType in resolve
    patient_name: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    scheduled_for: Optional[str] = None  # ISO-8601
    remind_at: Optional[str] = None      # ISO-8601


# Map action_type → args dataclass for validation
ARGS_TYPE_TABLE: Dict[ActionType, type] = {
    ActionType.select_patient: SelectPatientArgs,
    ActionType.create_patient: CreatePatientArgs,
    ActionType.create_record: CreateRecordArgs,
    ActionType.update_record: UpdateRecordArgs,
    ActionType.query_records: QueryRecordsArgs,
    ActionType.list_patients: ListPatientsArgs,
    ActionType.list_tasks: ListTasksArgs,
    ActionType.schedule_task: ScheduleTaskArgs,
    ActionType.none: type(None),
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
    scoped_only: bool = False          # True for reads — do not switch context
    record_id: Optional[int] = None    # resolve-time: target record for update_record


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
