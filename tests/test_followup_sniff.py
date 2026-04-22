"""Tier-2 sniff test for the followup_reply (draft-reply) prompt.

Tier-2 sniff: hard structural invariants only, no LLM-as-judge.

Runs 5 curated scenarios through a real LLM via
``domain.patient_lifecycle.draft_reply.generate_draft_reply``.

Skipped unless a provider env var (ROUTING_LLM / PROVIDER) is set AND
the corresponding API key is present.

Manual invocation (groq example)::

    PROVIDER=groq PYTHONPATH=src ENVIRONMENT=development \\
      .venv/bin/python -m pytest tests/test_followup_sniff.py \\
      -m slow -v --rootdir=.

Assertions are intentionally *structural* (non-empty reply, length
bounds, no hallucinated KB citations, red-flag contains urgent-care
language). Semantic correctness is deferred to tier-3.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import pytest_asyncio

# ── Env setup BEFORE importing anything that touches db.engine ──────────
os.environ.setdefault("ENVIRONMENT", "development")
_SNIFF_DB_PATH = Path(tempfile.gettempdir()) / "doctor_ai_followup_sniff.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_SNIFF_DB_PATH}")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Import provider keys from config/runtime.json into env when the operator
# hasn't already exported them (mirrors test_diagnosis_sniff.py).
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
    """Return a provider name with its API key configured, or None."""
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
        "followup sniff needs PROVIDER set; run with "
        "`PROVIDER=groq GROQ_API_KEY=... pytest tests/test_followup_sniff.py "
        "-m slow` (or set ROUTING_LLM instead)"
    ),
)


# ── Scenarios ──────────────────────────────────────────────────────────

# Each scenario: patient message text + expected structural behavior.
# Descriptions mirror the prompt's example-space in src/agent/prompts/intent/
# followup_reply.md (improvement / red-flag / side-effect / off-topic /
# non-compliance).

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "improvement_reassurance",
        "description": "Patient reports improvement → gentle reassurance",
        # Intentionally avoid RED_FLAG_KEYWORDS substrings like 伤口/加重/
        # 突然/头痛加剧 so the keyword detector doesn't false-positive on
        # a recovery message. (Sniff is testing prompt output shape, not
        # the independently-tested detect_red_flags keyword list.)
        "message": "医生，这两天感觉比之前好多了，睡眠也改善了，整体状态还行吧？",
        "expect_red_flag": False,
        "expect_urgent_care_language": False,
    },
    {
        "id": "new_warning_symptom",
        "description": "Sudden left-side weakness → red flag, must urge ER/hospital",
        "message": "下午左手突然没力气拿不住筷子，持续了几分钟就好了，现在说话也感觉有点不利索。",
        "expect_red_flag": True,
        "expect_urgent_care_language": True,
    },
    {
        "id": "med_side_effect",
        "description": "Med side effect query → should suggest consulting/contact",
        "message": "开浦兰吃了第一次，特别困，一直在睡。正常吗？要继续吃吗？",
        "expect_red_flag": False,
        "expect_urgent_care_language": False,
    },
    {
        "id": "unrelated_greeting",
        "description": "Off-topic greeting → polite short reply, no medical advice",
        "message": "你好",
        "expect_red_flag": False,
        "expect_urgent_care_language": False,
    },
    {
        "id": "non_compliance_schedule",
        "description": "Patient skipped dose → expect reminder + gentle tone",
        "message": "医生，昨晚睡着了忘了吃药，今早才发现，要补吃吗？",
        "expect_red_flag": False,
        "expect_urgent_care_language": False,
    },
]


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def _schema_ready():
    """Create tables on the test DB once per module."""
    import db.models  # noqa: F401
    from db.engine import engine, Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def doctor_and_patient(_schema_ready) -> Tuple[str, int]:
    """Create fresh doctor + patient + one generic KB item.

    Returns (doctor_id, patient_id). The KB item is a benign follow-up
    rule so the composer has *something* to cite (the prompt encourages
    but does not require a citation).
    """
    from db.engine import AsyncSessionLocal
    from db.crud.doctor import _ensure_doctor_exists
    from db.models.doctor import DoctorKnowledgeItem
    from db.models.patient import Patient
    from domain.knowledge.doctor_knowledge import invalidate_knowledge_cache

    doctor_id = f"sniff_fr_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        await _ensure_doctor_exists(db, doctor_id)

        kb = DoctorKnowledgeItem(
            doctor_id=doctor_id,
            content="术后头痛VAS≤6分属正常；出现新发肢体无力/言语不清需立即急诊。",
            category="followup",
        )
        db.add(kb)

        patient = Patient(
            doctor_id=doctor_id,
            name="李叔",
            gender="男",
        )
        db.add(patient)

        await db.commit()
        await db.refresh(patient)
        patient_id = patient.id

    invalidate_knowledge_cache(doctor_id)
    return doctor_id, patient_id


# ── Tests ─────────────────────────────────────────────────────────────

# Tight-but-generous reply bounds. Prompt target is "≤100 chars" but the
# LLM may go slightly over in red-flag cases. Upper bound is deliberately
# lax (400 chars) so we don't false-fail on legitimate prose; we care
# more that the reply isn't a single character or a paragraph of 2000.
_MIN_REPLY_LEN = 4
_MAX_REPLY_LEN = 400

# Minimum keyword set for red-flag "come to hospital / ER" language.
_URGENT_KEYWORDS = (
    "医院", "急诊", "就诊", "120", "立即", "马上", "尽快", "及时",
)


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS],
)
async def test_followup_sniff(scenario: Dict[str, Any], doctor_and_patient):
    """Run one followup scenario through generate_draft_reply and check
    structural invariants only."""
    from domain.patient_lifecycle.draft_reply import generate_draft_reply

    doctor_id, patient_id = doctor_and_patient

    # Pin ROUTING_LLM for deterministic provider selection.
    os.environ["ROUTING_LLM"] = _PROVIDER or os.environ.get("ROUTING_LLM", "")

    result = await generate_draft_reply(
        doctor_id=doctor_id,
        patient_id=patient_id,
        message_id=0,  # no PatientMessage row — citation log is non-fatal
        patient_message_text=scenario["message"],
        patient_context="",
    )

    # ── Non-None / shape ──────────────────────────────────────────────
    assert result is not None, (
        f"[{scenario['id']}] generate_draft_reply returned None — "
        f"likely LLM call failure. input={scenario['message']!r}"
    )

    print(
        f"\n[{scenario['id']}] reply_len={len(result.text)} "
        f"is_red_flag={result.is_red_flag} "
        f"cited={result.cited_knowledge_ids} "
        f"confidence={result.confidence}"
    )
    print(f"  reply: {result.text!r}")

    # ── Reply text shape ──────────────────────────────────────────────
    assert isinstance(result.text, str), (
        f"[{scenario['id']}] reply not a str; got {type(result.text)}"
    )
    assert len(result.text.strip()) >= _MIN_REPLY_LEN, (
        f"[{scenario['id']}] reply too short "
        f"({len(result.text.strip())} < {_MIN_REPLY_LEN}); "
        f"reply={result.text!r}"
    )
    assert len(result.text) <= _MAX_REPLY_LEN, (
        f"[{scenario['id']}] reply too long "
        f"({len(result.text)} > {_MAX_REPLY_LEN}); reply={result.text!r}"
    )

    # ── KB citation hygiene ───────────────────────────────────────────
    # The pipeline strips [KB-N] from the user-facing text. No marker
    # should remain in the cleaned reply.
    residual_markers = re.findall(r"\[KB-\d+\]", result.text)
    assert not residual_markers, (
        f"[{scenario['id']}] residual [KB-N] marker leaked into "
        f"user-facing text: {residual_markers}; reply={result.text!r}"
    )

    # cited_knowledge_ids must all be ints
    assert all(isinstance(i, int) for i in result.cited_knowledge_ids), (
        f"[{scenario['id']}] non-int in cited_knowledge_ids: "
        f"{result.cited_knowledge_ids!r}"
    )

    # ── Structured field types ────────────────────────────────────────
    assert isinstance(result.is_red_flag, bool), (
        f"[{scenario['id']}] is_red_flag not bool: {result.is_red_flag!r}"
    )
    assert isinstance(result.confidence, (int, float)), (
        f"[{scenario['id']}] confidence not numeric: {result.confidence!r}"
    )
    assert 0.0 <= float(result.confidence) <= 1.0, (
        f"[{scenario['id']}] confidence out of [0,1]: {result.confidence!r}"
    )

    # ── Red-flag detector behavior (keyword side) ─────────────────────
    # detect_red_flags() is a pure keyword check — verify it fires when
    # we staged a known-dangerous input.
    assert result.is_red_flag == scenario["expect_red_flag"], (
        f"[{scenario['id']}] is_red_flag={result.is_red_flag} but "
        f"expected {scenario['expect_red_flag']}; "
        f"message={scenario['message']!r}"
    )

    # ── Red-flag language invariant ───────────────────────────────────
    if scenario["expect_urgent_care_language"]:
        lower = result.text
        has_urgent = any(kw in lower for kw in _URGENT_KEYWORDS)
        assert has_urgent, (
            f"[{scenario['id']}] red-flag scenario must suggest ER/hospital "
            f"but reply contains none of {_URGENT_KEYWORDS}; "
            f"reply={result.text!r}"
        )
