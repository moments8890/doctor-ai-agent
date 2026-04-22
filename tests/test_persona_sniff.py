"""Tier-2 sniff test for the persona-classify prompt.

Tier-2 sniff: hard structural invariants only, no LLM-as-judge.

The persona-classify prompt lives at
``src/agent/prompts/persona-classify.md``. Despite the name, it does NOT
classify doctor *specialty* — it classifies a doctor's EDIT of an AI
draft into one of three types (style / factual / context_specific) with
associated enum fields. Entry point:
``domain.knowledge.persona_classifier.classify_edit(original, edited)``.

5 scenarios cover the typical + edge cases:
  1. Structural rewrite  → type=style, persona_field set
  2. Drug-name correction → type=factual, kb_category set, proposed rule
  3. Patient-specific note → type=context_specific, all extras empty
  4. Trivially small edit → type=style (low confidence expected)
  5. Emoji / slang edit   → should not crash; still returns a
     ClassifyResult with valid enum values

Skipped unless a provider env var (ROUTING_LLM / PROVIDER) is set AND
the corresponding API key is present.

Manual invocation (groq example)::

    PROVIDER=groq PYTHONPATH=src ENVIRONMENT=development \\
      .venv/bin/python -m pytest tests/test_persona_sniff.py \\
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
_SNIFF_DB_PATH = Path(tempfile.gettempdir()) / "doctor_ai_persona_sniff.db"
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
        "persona sniff needs PROVIDER set; run with "
        "`PROVIDER=groq GROQ_API_KEY=... pytest tests/test_persona_sniff.py "
        "-m slow` (or set ROUTING_LLM instead)"
    ),
)


# ── Scenarios ──────────────────────────────────────────────────────────

# Each scenario gives an (original, edited) pair plus the expected
# structural type. proposed_kb_rule / persona_field presence are the
# core invariants.

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "style_closing_rewrite",
        "description": "Shortened tone + dropped closing — clearly style",
        "original": (
            "张阿姨您好，您的血压控制得不错，继续目前的用药方案即可。"
            "建议每周测量血压2-3次并记录。祝您身体健康，早日康复！"
        ),
        "edited": (
            "张阿姨你好，血压还行，继续吃药就好。每周量2-3次血压记录下。"
        ),
        "expect_type": "style",
    },
    {
        "id": "factual_drug_swap",
        "description": "Drug name corrected → type=factual, kb_category=medication",
        "original": "建议继续服用氨氯地平控制血压，同时注意低盐饮食。",
        "edited":   "建议继续服用硝苯地平控制血压，同时注意低盐饮食。",
        "expect_type": "factual",
    },
    {
        "id": "context_specific_comorbidity",
        "description": "Patient-specific note appended → type=context_specific",
        "original": "术后请注意伤口护理，按时换药，有异常及时就诊。",
        "edited": (
            "术后请注意伤口护理，按时换药，有异常及时就诊。"
            "因为您有糖尿病，伤口愈合可能较慢，请特别注意血糖控制。"
        ),
        "expect_type": "context_specific",
    },
    {
        "id": "style_minor_wording",
        "description": "Tiny wording edits — should still return a valid type",
        "original": "建议您近期复查一下血常规。",
        "edited":   "建议近期复查血常规。",
        "expect_type": "style",
    },
    {
        "id": "style_emoji_slang",
        "description": "Edit adds emoji + slang — must not crash and must "
                       "return a valid enum value",
        "original": "请按时服药，有问题及时联系医生。",
        "edited":   "按时吃药哈~ 有事儿随时找我 👨‍⚕️",
        # Most likely classified as style, but we accept any valid type
        # here because the LLM may reasonably call it context_specific.
        # The invariant is: enum values valid, no crash.
        "expect_type": None,
    },
]


# ── Tests ─────────────────────────────────────────────────────────────

_VALID_TYPES = {"style", "factual", "context_specific"}
_VALID_PERSONA_FIELDS = {
    "reply_style", "closing", "structure", "avoid", "edits", None,
}
_VALID_KB_CATEGORIES = {
    "diagnosis", "medication", "followup", "custom", None,
}
_VALID_CONFIDENCE = {"low", "medium", "high"}


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS],
)
async def test_persona_sniff(scenario: Dict[str, Any]):
    """Run classify_edit and check enum/type invariants."""
    from domain.knowledge.persona_classifier import (
        classify_edit,
        ClassifyResult,
        LearningType,
        PersonaField,
        KbCategory,
    )

    # Pin ROUTING_LLM so the provider is deterministic.
    os.environ["ROUTING_LLM"] = _PROVIDER or os.environ.get("ROUTING_LLM", "")

    result = await classify_edit(scenario["original"], scenario["edited"])

    assert result is not None, (
        f"[{scenario['id']}] classify_edit returned None — LLM call or "
        f"JSON parse failed. original={scenario['original']!r} "
        f"edited={scenario['edited']!r}"
    )
    assert isinstance(result, ClassifyResult), (
        f"[{scenario['id']}] expected ClassifyResult, got {type(result)}"
    )

    print(
        f"\n[{scenario['id']}] type={result.type.value} "
        f"persona_field="
        f"{result.persona_field.value if result.persona_field else None} "
        f"kb_category="
        f"{result.kb_category.value if result.kb_category else None} "
        f"confidence={result.confidence} "
        f"summary={result.summary!r}"
    )

    # ── Enum invariants ───────────────────────────────────────────────
    assert result.type.value in _VALID_TYPES, (
        f"[{scenario['id']}] invalid type={result.type!r}"
    )
    pf = result.persona_field.value if result.persona_field else None
    assert pf in _VALID_PERSONA_FIELDS, (
        f"[{scenario['id']}] invalid persona_field={pf!r}"
    )
    kc = result.kb_category.value if result.kb_category else None
    assert kc in _VALID_KB_CATEGORIES, (
        f"[{scenario['id']}] invalid kb_category={kc!r}"
    )
    assert result.confidence in _VALID_CONFIDENCE, (
        f"[{scenario['id']}] invalid confidence={result.confidence!r}"
    )

    # ── Summary hygiene ───────────────────────────────────────────────
    assert result.summary and result.summary.strip(), (
        f"[{scenario['id']}] empty summary"
    )
    assert len(result.summary) <= 500, (
        f"[{scenario['id']}] summary too long: {len(result.summary)} chars"
    )

    # ── Contract enforcement (already done by Pydantic validator, but
    # assert here so failures point at this test, not the validator) ──
    if result.type == LearningType.style:
        assert result.persona_field is not None, (
            f"[{scenario['id']}] type=style but persona_field is None"
        )
        assert not result.proposed_kb_rule, (
            f"[{scenario['id']}] type=style but proposed_kb_rule non-empty: "
            f"{result.proposed_kb_rule!r}"
        )
        assert result.kb_category is None, (
            f"[{scenario['id']}] type=style but kb_category set: "
            f"{result.kb_category!r}"
        )
    elif result.type == LearningType.factual:
        assert result.kb_category is not None, (
            f"[{scenario['id']}] type=factual but kb_category is None"
        )
        assert result.proposed_kb_rule.strip(), (
            f"[{scenario['id']}] type=factual but proposed_kb_rule empty"
        )
        assert len(result.proposed_kb_rule) <= 300, (
            f"[{scenario['id']}] proposed_kb_rule too long: "
            f"{len(result.proposed_kb_rule)} > 300"
        )
        assert result.persona_field is None, (
            f"[{scenario['id']}] type=factual but persona_field set: "
            f"{result.persona_field!r}"
        )
    else:  # context_specific
        assert result.persona_field is None, (
            f"[{scenario['id']}] type=context_specific but persona_field set"
        )
        assert result.kb_category is None, (
            f"[{scenario['id']}] type=context_specific but kb_category set"
        )
        assert not result.proposed_kb_rule, (
            f"[{scenario['id']}] type=context_specific but "
            f"proposed_kb_rule set: {result.proposed_kb_rule!r}"
        )

    # ── Scenario-specific expected type (when deterministic) ──────────
    if scenario.get("expect_type"):
        assert result.type.value == scenario["expect_type"], (
            f"[{scenario['id']}] expected type="
            f"{scenario['expect_type']!r} but got {result.type.value!r}. "
            f"summary={result.summary!r}"
        )
