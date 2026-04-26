"""Prompt layer configuration — which layers each flow uses.

Each LayerConfig controls which prompt layers are assembled by the composer.
Routing layer removed — all flows are now explicit-action-driven.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerConfig:
    """Which prompt layers a flow uses.

    Layers: L0 Style Guard → L1 Identity → L2 Specialty → L3 Task →
            L4 Doctor Rules → L4p Persona → L6 Patient → L7 Input

    conversation_mode:
      False (default) = Pattern 1 (single-turn): L0-L3 system, L4-L7 user with XML tags
      True = Pattern 2 (conversation): L0-L3+Patient system, history, KB+input as user

    style_guard:
      True  → prepend common/style_guard.md (anti-AI-smell, banned phrases,
              escalation forms, listing prohibition). Use for any patient/
              doctor-facing text generation.
      False → skip (extraction/internal flows that don't generate prose).

    load_knowledge:
      True  → load doctor KB items (L4 Doctor Rules) for this flow
      False → skip KB loading

    load_persona:
      True  → load doctor persona (expression style) from doctor_personas table
      False → skip persona loading (structured extraction flows)
    """
    system: bool = True
    domain: bool = False
    intent: str = "general"
    style_guard: bool = False
    load_knowledge: bool = False
    load_persona: bool = False
    load_examples: bool = False
    example_limit: int = 0
    patient_context: bool = False
    conversation_mode: bool = False


# ── Flow configs (explicit-action-driven) ────────────────────────

DOCTOR_INTAKE_LAYERS = LayerConfig(
    domain=False,
    intent="intake",
    style_guard=False,  # doctor talks TO the AI to record; not patient-facing prose
    load_knowledge=False,
    load_persona=False,
    patient_context=True,
    conversation_mode=True,
)

REVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="diagnosis",
    style_guard=True,  # doctor reads diagnosis cards; structured but evidence/risk text needs guard
    load_knowledge=True,
    load_persona=True,
    patient_context=True,
)

FOLLOWUP_REPLY_LAYERS = LayerConfig(
    domain=True,
    intent="followup_reply",
    style_guard=True,  # patient-facing
    load_knowledge=True,
    load_persona=True,
    load_examples=True,  # L5: complaint-clustered MedDG/meddialog exemplars
    example_limit=3,
    patient_context=True,
)

PATIENT_INTAKE_LAYERS = LayerConfig(
    domain=True,
    intent="patient-intake",
    style_guard=True,  # patient-facing
    # 2026-04-26: load_knowledge → False. Intake is gather-only — the LLM
    # must not cite KB items ([KB-N]) or suggest tests/treatments based on
    # the doctor's KB. Clinical judgment happens later when the doctor
    # reviews the medical_record (FOLLOWUP_REPLY_LAYERS keeps load_knowledge=True).
    load_knowledge=False,
    load_persona=True,  # 2026-04-25: was False — pre-visit chat could not sound like the doctor
    load_examples=True,  # L5: complaint-clustered exemplars (intake register)
    example_limit=2,
    patient_context=True,
    conversation_mode=True,
)

DAILY_SUMMARY_LAYERS = LayerConfig(
    domain=False,
    intent="daily_summary",
    style_guard=True,  # doctor reads the summary; needs same anti-smell rules
    load_knowledge=True,
    load_persona=False,
    patient_context=False,
)
