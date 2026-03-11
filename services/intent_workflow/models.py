"""Intent workflow data models — each layer produces a typed, traceable output."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from services.ai.intent import Intent, IntentResult


class IntentDecision(BaseModel):
    """Layer 1: What does the user want to do?"""

    intent: Intent
    confidence: float = 1.0
    source: str  # "fast_route", "llm", "menu_shortcut"
    chat_reply: Optional[str] = None
    structured_fields: Optional[dict] = None


class EntitySlot(BaseModel):
    """A single extracted entity with provenance."""

    value: Any
    source: str  # "llm", "fast_route", "text_leading_name", "followup", "history", "session", "candidate", "not_found"
    confidence: float = 1.0


class EntityResolution(BaseModel):
    """Layer 2: Extracted entities with provenance tracking."""

    patient_name: Optional[EntitySlot] = None
    gender: Optional[EntitySlot] = None
    age: Optional[EntitySlot] = None
    is_emergency: bool = False
    extra_data: dict = Field(default_factory=dict)


class BindingDecision(BaseModel):
    """Layer 3: Patient binding status (read-only, no DB writes)."""

    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    status: str = "no_name"  # "bound", "has_name", "no_name", "not_applicable"
    source: str = "none"  # "db_lookup", "session_id", "entity", "none"
    needs_review: bool = False


class PlannedAction(BaseModel):
    """A single planned action."""

    action: str  # Intent enum value
    params: dict = Field(default_factory=dict)


class ActionPlan(BaseModel):
    """Layer 4: What actions to take."""

    actions: list[PlannedAction] = Field(default_factory=list)
    is_compound: bool = False


class GateResult(BaseModel):
    """Layer 5: Execution safety verdict."""

    approved: bool = True
    reason: Optional[str] = None
    requires_confirmation: bool = False
    clarification_message: Optional[str] = None


class WorkflowResult(BaseModel):
    """Complete workflow output with all layer results."""

    decision: IntentDecision
    entities: EntityResolution
    binding: BindingDecision
    plan: ActionPlan
    gate: GateResult

    def to_intent_result(self) -> IntentResult:
        """Convert to legacy IntentResult for backward-compatible handler dispatch."""
        extra = dict(self.entities.extra_data)
        if self.entities.patient_name:
            extra["patient_source"] = self.entities.patient_name.source
        if self.binding.needs_review:
            extra["needs_review"] = True
            extra["attribution_source"] = self.binding.source

        return IntentResult(
            intent=self.decision.intent,
            patient_name=self.entities.patient_name.value if self.entities.patient_name else None,
            gender=self.entities.gender.value if self.entities.gender else None,
            age=self.entities.age.value if self.entities.age else None,
            is_emergency=self.entities.is_emergency,
            extra_data=extra,
            chat_reply=self.gate.clarification_message or self.decision.chat_reply,
            structured_fields=self.decision.structured_fields,
            confidence=self.decision.confidence,
        )
