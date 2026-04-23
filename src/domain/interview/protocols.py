"""Polymorphic interview pipeline — protocol surface.

Spec: docs/superpowers/specs/2026-04-22-interview-pipeline-extensibility-design.md §3a.

This file defines shapes only — no runtime behavior. Runtime impl lives in
engine.py (generic) and templates/<name>.py (per-template).
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

# ---- aliases ----------------------------------------------------------------

Mode = Literal["patient", "doctor"]
Phase = str  # templates define their own phase tokens; engine treats opaque


# ---- data types -------------------------------------------------------------

class FieldSpec(BaseModel):
    """Declarative per-field metadata. Constrained vocabulary — widening
    requires a PR to contract.py + a matching test."""
    name: str
    type: Literal["string", "text", "number", "enum"] = "string"
    description: str                                    # LLM-facing
    example: str | None = None
    enum_values: tuple[str, ...] | None = None
    label: str | None = None                            # human label
    tier: Literal["required", "recommended", "optional"] = "optional"
    appendable: bool = False
    carry_forward_modes: frozenset[Mode] = frozenset()

    @model_validator(mode="after")
    def _enum_requires_values(self) -> "FieldSpec":
        if self.type == "enum" and not self.enum_values:
            raise ValueError(
                f"FieldSpec({self.name}): type='enum' requires enum_values"
            )
        return self


class CompletenessState(BaseModel):
    can_complete: bool
    required_missing: list[str]
    recommended_missing: list[str]
    optional_missing: list[str]
    next_focus: str | None


class PersistRef(BaseModel):
    """Reference to the persisted artifact a confirm produced. `id` is
    template-kind-specific — medical writers return medical_records.id,
    form writers return form_responses.id."""
    kind: Literal["medical_record", "form_response"]
    id: int


class TurnResult(BaseModel):
    reply: str
    suggestions: list[str] = Field(default_factory=list)
    state: CompletenessState
    # Passthrough for metadata the endpoint surfaces today (patient_name,
    # patient_gender, patient_age). Keep loose dict to avoid leaking medical
    # concepts into the engine's public type surface.
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionState(BaseModel):
    """Read-model view of an interview session exposed to the engine + templates.
    Templates MUST NOT mutate this directly; the engine owns writes."""
    id: str
    doctor_id: str
    patient_id: int | None
    mode: Mode
    status: str
    template_id: str
    collected: dict[str, str]
    conversation: list[dict[str, Any]]
    turn_count: int


# ---- protocols --------------------------------------------------------------

class FieldExtractor(Protocol):
    """Per-template. Schema, prompt, merge, completeness, metadata, post-process.
    Schema lives in fields(); everything else is behavior on top of it."""

    def fields(self) -> list[FieldSpec]: ...

    async def prompt_partial(
        self,
        session_state: "SessionState",
        completeness_state: "CompletenessState",
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        """Build the messages list for the LLM turn call.

        Gets structured state (session + completeness) and is responsible for
        all template-specific prompt shape: patient context text, conversation
        history window, missing-field hints, etc. Form templates produce a
        simple survey prompt; medical templates produce the current flat-text
        context block.
        """
        ...

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]: ...

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState: ...

    def next_phase(
        self, session: "SessionState", phases: list[Phase],
    ) -> Phase: ...

    def extract_metadata(
        self, extracted: dict[str, str],
    ) -> dict[str, str]:
        """Pop template-specific metadata out of the raw LLM extraction.

        Medical templates return patient_name/gender/age; form templates
        return {}. The engine writes returned values as underscore-prefixed
        keys into session.collected.
        """
        ...

    def post_process_reply(
        self, reply: str, collected: dict[str, str], mode: Mode,
    ) -> str:
        """Apply template-specific reply polishing.

        Medical templates apply the softening guard (rewrite blocking
        language when can_complete=True). Form templates return unchanged.
        """
        ...


class BatchExtractor(Protocol):
    """Optional per-template. Pre-finalize re-extraction from full transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None: ...


class Writer(Protocol):
    """Per-template. Pure persistence. No LLM calls, no post-confirm side
    effects (those are hooks)."""

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef: ...


class PostConfirmHook(Protocol):
    name: str

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None: ...


class EngineConfig(BaseModel):
    max_turns: int = 30
    phases: dict[Mode, list[Phase]] = Field(default_factory=dict)


class Template(Protocol):
    """Registry entry. Attributes only — templates are typically dataclasses
    or plain classes with instance attributes named below."""
    id: str
    kind: Literal["medical", "form"]
    display_name: str
    requires_doctor_review: bool
    supported_modes: tuple[Mode, ...]
    extractor: FieldExtractor
    batch_extractor: BatchExtractor | None
    writer: Writer
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]]
    config: EngineConfig
