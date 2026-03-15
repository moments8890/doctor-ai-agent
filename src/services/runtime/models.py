"""Data models for the conversation runtime (ADR 0011 envelope + ADR 0012 pipeline)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── Turn envelope (single entry point for all channels) ────────────────────


@dataclass
class ActionPayload:
    """Typed action from UI buttons (confirm draft, abandon draft, etc.)."""
    type: str       # "draft_confirm" | "draft_abandon" | ...
    target_id: str  # e.g. pending_record_id


@dataclass
class TurnEnvelope:
    """Normalized inbound message from any channel (ADR 0011 §1).

    Text messages populate *text*; button actions populate *action* with
    text=None.  ``process_turn`` inspects both to decide the pipeline path.
    """
    doctor_id: str
    channel: str                          # "web" | "wechat" | "voice"
    modality: str = "text"                # "text" | "voice" | "action"
    text: Optional[str] = None
    action: Optional[ActionPayload] = None
    source_turn_key: Optional[str] = None  # for dedup (message_id)


@dataclass
class WorkflowState:
    """Authoritative, deterministic. Only product code may mutate."""
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    pending_draft_id: Optional[str] = None


@dataclass
class MemoryState:
    """Provisional, LLM-facing. Dead fields under ADR 0012 §17."""
    candidate_patient: Optional[Dict[str, Any]] = None
    working_note: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class DoctorCtx:
    """One mutable row per doctor — the only live conversation state."""
    doctor_id: str
    workflow: WorkflowState = field(default_factory=WorkflowState)
    memory: MemoryState = field(default_factory=MemoryState)


@dataclass
class TurnResult:
    """Final result returned to the channel adapter."""
    reply: str
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None
    record_id: Optional[int] = None  # set on draft confirm (for REST response)
    view_payload: Optional[Dict[str, Any]] = None  # structured data for web rendering (ADR 0012 §14)
