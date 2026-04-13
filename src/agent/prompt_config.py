"""Prompt layer configuration — which layers each flow uses.

Each LayerConfig controls which prompt layers are assembled by the composer.
Routing layer removed — all flows are now explicit-action-driven.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerConfig:
    """Which prompt layers a flow uses.

    Layers: L1 Identity → L2 Specialty → L3 Task → L4 Doctor Rules → L6 Patient → L7 Input

    conversation_mode:
      False (default) = Pattern 1 (single-turn): L1-L3 system, L4-L7 user with XML tags
      True = Pattern 2 (conversation): L1-L3+Patient system, history, KB+input as user

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
    load_knowledge: bool = False
    load_persona: bool = False
    patient_context: bool = False
    conversation_mode: bool = False


# ── Flow configs (explicit-action-driven) ────────────────────────

DOCTOR_INTERVIEW_LAYERS = LayerConfig(
    domain=False,
    intent="interview",
    load_knowledge=False,
    load_persona=False,
    patient_context=True,
    conversation_mode=True,
)

REVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="diagnosis",
    load_knowledge=True,
    load_persona=True,
    patient_context=True,
)

FOLLOWUP_REPLY_LAYERS = LayerConfig(
    domain=True,
    intent="followup_reply",
    load_knowledge=True,
    load_persona=True,
    patient_context=True,
)

PATIENT_INTERVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="patient-interview",
    load_knowledge=True,
    load_persona=False,
    patient_context=True,
    conversation_mode=True,
)

DAILY_SUMMARY_LAYERS = LayerConfig(
    domain=False,
    intent="daily_summary",
    load_knowledge=True,
    load_persona=False,
    patient_context=False,
)
