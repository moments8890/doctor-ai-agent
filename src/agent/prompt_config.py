"""Prompt layer configuration — which layers each intent uses.

Maps IntentType → LayerConfig. The assert at module level ensures every
intent has a config entry. Adding a new IntentType without a LayerConfig
crashes at import time (server startup).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from agent.types import IntentType
from db.models.doctor import KnowledgeCategory


@dataclass(frozen=True)
class LayerConfig:
    """Which prompt layers an intent uses.

    conversation_mode:
      False (default) = Pattern 1 (single-turn): L1-3 system, L4-6 user with XML tags
      True = Pattern 2 (conversation): L1-5 system, history, L6 user plain text
    """
    system: bool = True
    common: bool = False
    intent: str = "general"
    knowledge_categories: List[KnowledgeCategory] = field(default_factory=list)
    patient_context: bool = False
    conversation_mode: bool = False


# ── Intent → LayerConfig mapping ──────────────────────────────────
# This IS the matrix from the design doc. Keep in sync.
#
# Intent             | System | Common | Intent      | Dr Knowledge                  | Patient Ctx
# -------------------|--------|--------|-------------|-------------------------------|------------
# query_record       |   ✓    |        | query       | custom                        |      ✓
# create_record      |   ✓    |   ✓    | interview   | interview_guide+red_flag+custom|      ✓
# query_task         |   ✓    |        | query       | custom                        |
# create_task        |   ✓    |        | create-task | custom                        |
# query_patient      |   ✓    |        | query       | custom                        |      ✓
# general            |   ✓    |        | general     | custom                        |

INTENT_LAYERS: dict[IntentType, LayerConfig] = {
    IntentType.query_record: LayerConfig(
        intent="query",
        knowledge_categories=[KnowledgeCategory.custom],
        patient_context=True,
    ),
    IntentType.create_record: LayerConfig(
        common=True,
        intent="interview",
        knowledge_categories=[
            KnowledgeCategory.interview_guide,
            KnowledgeCategory.red_flag,
            KnowledgeCategory.custom,
        ],
        patient_context=True,
        conversation_mode=True,
    ),
    IntentType.query_task: LayerConfig(
        intent="query",
        knowledge_categories=[KnowledgeCategory.custom],
    ),
    IntentType.create_task: LayerConfig(
        intent="create-task",
        knowledge_categories=[KnowledgeCategory.custom],
    ),
    IntentType.query_patient: LayerConfig(
        intent="query",
        knowledge_categories=[KnowledgeCategory.custom],
        patient_context=True,
    ),
    IntentType.daily_summary: LayerConfig(
        intent="general",
        knowledge_categories=[KnowledgeCategory.custom],
    ),
    IntentType.general: LayerConfig(
        intent="general",
        knowledge_categories=[KnowledgeCategory.custom],
    ),
}

# ── Fail at import if any IntentType is missing ───────────────────
_missing = set(IntentType) - set(INTENT_LAYERS)
assert not _missing, f"INTENT_LAYERS missing entries for: {_missing}. Add a LayerConfig for each new IntentType."


# ── Non-routing configs (UI-triggered flows) ─────────────────────

ROUTING_LAYERS = LayerConfig(
    intent="routing",
    knowledge_categories=[KnowledgeCategory.custom],
)

REVIEW_LAYERS = LayerConfig(
    common=True,
    intent="diagnosis",
    knowledge_categories=[
        KnowledgeCategory.diagnosis_rule,
        KnowledgeCategory.red_flag,
        KnowledgeCategory.treatment_protocol,
        KnowledgeCategory.custom,
    ],
    patient_context=True,
)

PATIENT_INTERVIEW_LAYERS = LayerConfig(
    common=True,
    intent="patient-interview",
    knowledge_categories=[
        KnowledgeCategory.interview_guide,
        KnowledgeCategory.red_flag,
        KnowledgeCategory.custom,
    ],
    patient_context=True,
    conversation_mode=True,
)
