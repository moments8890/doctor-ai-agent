"""Prompt layer configuration — which layers each intent uses.

Maps IntentType → LayerConfig. The assert at module level ensures every
intent has a config entry. Adding a new IntentType without a LayerConfig
crashes at import time (server startup).
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.types import IntentType


@dataclass(frozen=True)
class LayerConfig:
    """Which prompt layers an intent uses.

    Layers: L1 Identity → L2 Specialty → L3 Task → L4 Doctor Rules → L5 Case Memory → L6 Patient → L7 Input

    conversation_mode:
      False (default) = Pattern 1 (single-turn): L1-L3 system, L4-L6 user with XML tags
      True = Pattern 2 (conversation): L1-L5 system, history, L6 user plain text

    load_knowledge:
      True  → load ALL doctor KB items (L4 Doctor Rules) for this intent
      False → skip KB loading
    """
    system: bool = True
    domain: bool = False
    intent: str = "general"
    load_knowledge: bool = False
    patient_context: bool = False
    conversation_mode: bool = False


# ── Intent → LayerConfig mapping ──────────────────────────────────
# This IS the matrix from the design doc. Keep in sync.
#
# Intent             | Common | Domain | Intent      | Dr Knowledge | Patient Ctx
# -------------------|--------|--------|-------------|--------------|------------
# query_record       |   ✓    |        | query       |      ✓       |      ✓
# create_record      |   ✓    |   ✓    | interview   |      ✗       |      ✓
# query_task         |   ✓    |        | query       |      ✓       |
# create_task        |   ✓    |        | general     |      ✓       |
# query_patient      |   ✓    |        | query       |      ✓       |      ✓
# general            |   ✓    |        | general     |      ✓       |

INTENT_LAYERS: dict[IntentType, LayerConfig] = {
    IntentType.query_record: LayerConfig(
        intent="query",
        load_knowledge=True,
        patient_context=True,
    ),
    IntentType.create_record: LayerConfig(
        domain=False,  # L2 specialty not needed for field extraction (saves ~150 tokens)
        intent="interview",
        load_knowledge=False,  # Interview = structured extraction, not medical Q&A.
                               # L3 intent rules already define fields and examples.
                               # KB adds ~7500 chars of noise (often duplicated) that
                               # causes Groq json_validate_failed on long conversations.
        patient_context=True,
        conversation_mode=True,
    ),
    IntentType.query_task: LayerConfig(
        intent="query",
        load_knowledge=True,
    ),
    IntentType.create_task: LayerConfig(
        intent="general",
        load_knowledge=True,
    ),
    IntentType.query_patient: LayerConfig(
        intent="query",
        load_knowledge=True,
        patient_context=True,
    ),
    IntentType.daily_summary: LayerConfig(
        intent="general",
        load_knowledge=True,
    ),
    IntentType.general: LayerConfig(
        intent="general",
        load_knowledge=True,
    ),
}

# ── Fail at import if any IntentType is missing ───────────────────
_missing = set(IntentType) - set(INTENT_LAYERS)
assert not _missing, f"INTENT_LAYERS missing entries for: {_missing}. Add a LayerConfig for each new IntentType."


# ── Non-routing configs (UI-triggered flows) ─────────────────────

ROUTING_LAYERS = LayerConfig(
    intent="routing",
    load_knowledge=False,  # Routing only classifies intent — KB adds noise and cost
)

REVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="diagnosis",
    load_knowledge=True,
    patient_context=True,
)

FOLLOWUP_REPLY_LAYERS = LayerConfig(
    domain=True,
    intent="followup_reply",
    load_knowledge=True,
    patient_context=True,
)

PATIENT_INTERVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="patient-interview",
    load_knowledge=True,
    patient_context=True,
    conversation_mode=True,
)
