"""Tier-2 sniff test for the closest live "intent-routing" prompt.

Tier-2 sniff: hard structural invariants only, no LLM-as-judge.

NOTE on prompt identity:
    The historical doctor-side ``intent/routing.md`` was removed when the
    pipeline moved to explicit-action-driven flows (see comment in
    ``src/agent/prompt_config.py``: "Routing layer removed — all flows
    are now explicit-action-driven"). The only remaining LLM-based
    *intent router* in the codebase is the patient-message triage
    classifier defined in ``src/agent/prompts/intent/triage-classify.md``
    and invoked via ``domain.patient_lifecycle.triage.classify``. That is
    the prompt exercised here.

The triage classifier maps inbound patient messages into one of five
intent categories:

    informational | symptom_report | side_effect |
    general_question | urgent

and returns a confidence score in [0, 1].

Skipped unless a provider env var (TRIAGE_LLM / ROUTING_LLM / PROVIDER)
is set AND the corresponding API key is present.

Manual invocation (groq example)::

    PROVIDER=groq PYTHONPATH=src ENVIRONMENT=development \\
      .venv/bin/python -m pytest tests/test_routing_sniff.py \\
      -m slow -v --rootdir=.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ── Env setup BEFORE importing anything that touches db.engine ──────────
os.environ.setdefault("ENVIRONMENT", "development")
_SNIFF_DB_PATH = Path(tempfile.gettempdir()) / "doctor_ai_routing_sniff.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_SNIFF_DB_PATH}")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from utils.app_config import load_config_from_json as _load_cfg

    _, _cfg_values = _load_cfg()
    for _k in (
        "GROQ_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY",
        "TENCENT_LKEAP_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY",
        "SILICONFLOW_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        _v = _cfg_values.get(_k, "")
        if _v and not os.environ.get(_k):
            os.environ[_k] = _v
except Exception:
    pass


# ── Provider resolution ────────────────────────────────────────────────

_PROVIDER_KEY_ENV = {
    "deepseek":      "DEEPSEEK_API_KEY",
    "siliconflow":   "SILICONFLOW_API_KEY",
    "dashscope":     "DASHSCOPE_API_KEY",
    "tencent_lkeap": "TENCENT_LKEAP_API_KEY",
    "groq":          "GROQ_API_KEY",
    "sambanova":     "SAMBANOVA_API_KEY",
    "cerebras":      "CEREBRAS_API_KEY",
    "openrouter":    "OPENROUTER_API_KEY",
    "ollama":        "OLLAMA_API_KEY",
}


def _resolve_test_provider() -> Optional[str]:
    candidates = [
        os.environ.get("TRIAGE_LLM", "").strip().lower(),
        os.environ.get("ROUTING_LLM", "").strip().lower(),
        os.environ.get("PROVIDER", "").strip().lower(),
    ]
    for name in candidates:
        if not name or name not in _PROVIDER_KEY_ENV:
            continue
        key_env = _PROVIDER_KEY_ENV[name]
        if name == "ollama" or os.environ.get(key_env, "").strip():
            return name
    return None


_PROVIDER = _resolve_test_provider()

pytestmark = pytest.mark.skipif(
    _PROVIDER is None,
    reason=(
        "routing sniff needs PROVIDER set; run with "
        "`PROVIDER=groq GROQ_API_KEY=... pytest tests/test_routing_sniff.py "
        "-m slow` (or set TRIAGE_LLM / ROUTING_LLM instead)"
    ),
)


# ── Scenarios ──────────────────────────────────────────────────────────
#
# Five messages, one per documented triage category. The assertion is
# structural (valid enum + valid confidence range). We additionally
# assert on *category* for the unambiguous cases (urgent, clear
# informational). The ambiguous case validates only the enum membership
# since the safe-default rule may legitimately reroute to
# general_question.

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "informational_med_timing",
        "description": "Pure info question about dosing timing",
        "message": "我的药什么时候吃？饭前还是饭后？",
        # "general_question" is an acceptable safe-default here; we
        # permit either informational or general_question.
        "allowed_categories": {"informational", "general_question"},
    },
    {
        "id": "symptom_report_new_symptom",
        "description": "New onset cough with phlegm — clearly symptom_report",
        "message": "医生，我今天开始咳嗽了，有黄痰，已经两天了。",
        "allowed_categories": {"symptom_report", "general_question"},
    },
    {
        "id": "side_effect_post_antihypertensive",
        "description": "Dizziness after BP med → side_effect",
        "message": "吃了降压药以后一直头晕，是不是副作用？",
        "allowed_categories": {"side_effect", "symptom_report", "general_question"},
    },
    {
        "id": "urgent_chest_pain_dyspnea",
        "description": "Chest pain + dyspnea → urgent",
        "message": "胸口突然很痛，喘不上来气。",
        # Urgent must be returned here — if not, the classifier is unsafe.
        "allowed_categories": {"urgent"},
    },
    {
        "id": "general_question_ambiguous",
        "description": "Ambiguous / unclear → safe default general_question",
        "message": "我想问个问题但不知道怎么说。",
        "allowed_categories": {
            "general_question", "informational",
        },
    },
]

_ALL_VALID_CATEGORIES = {
    "informational", "symptom_report", "side_effect",
    "general_question", "urgent",
}


# ── Tests ─────────────────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS],
)
async def test_routing_sniff(scenario: Dict[str, Any]):
    """Run one scenario through triage.classify and check invariants."""
    from domain.patient_lifecycle.triage import (
        classify, TriageCategory, TriageResult,
    )

    # Pin TRIAGE_LLM so the provider resolution inside classify() is
    # deterministic.
    os.environ["TRIAGE_LLM"] = _PROVIDER or os.environ.get(
        "TRIAGE_LLM", os.environ.get("ROUTING_LLM", ""),
    )

    # Empty patient_context dict — classify() serialises to JSON and
    # injects into the system prompt. The prompt tolerates an empty
    # context block.
    result = await classify(
        message=scenario["message"],
        patient_context={},
        doctor_id="",
    )

    # ── Shape ─────────────────────────────────────────────────────────
    assert isinstance(result, TriageResult), (
        f"[{scenario['id']}] expected TriageResult, got {type(result)}"
    )
    assert isinstance(result.category, TriageCategory), (
        f"[{scenario['id']}] category not a TriageCategory: "
        f"{type(result.category)}"
    )

    print(
        f"\n[{scenario['id']}] category={result.category.value} "
        f"confidence={result.confidence:.2f}"
    )

    # ── Enum membership (no hallucinated categories) ──────────────────
    assert result.category.value in _ALL_VALID_CATEGORIES, (
        f"[{scenario['id']}] hallucinated category="
        f"{result.category.value!r}; valid set={_ALL_VALID_CATEGORIES}"
    )

    # ── Confidence range ──────────────────────────────────────────────
    assert isinstance(result.confidence, (int, float)), (
        f"[{scenario['id']}] confidence not numeric: {result.confidence!r}"
    )
    assert 0.0 <= float(result.confidence) <= 1.0, (
        f"[{scenario['id']}] confidence out of [0,1]: {result.confidence!r}"
    )

    # ── Scenario-specific allowed set ─────────────────────────────────
    # Note: classify() itself downgrades low-confidence (<0.7) results
    # to general_question as a safety default, so we always allow
    # general_question *unless* the scenario whitelist explicitly omits
    # it (e.g. the urgent scenario — downgrading urgent to
    # general_question is a real bug we want to surface).
    allowed = scenario["allowed_categories"]
    assert result.category.value in allowed, (
        f"[{scenario['id']}] category={result.category.value!r} not in "
        f"allowed set {allowed}; input={scenario['message']!r}"
    )
