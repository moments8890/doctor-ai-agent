"""Tier-2 lightweight sniff test for the AI diagnosis pipeline.

Minimum regression coverage for the Phase 2b prompt cap change:
  - differentials → 1 item
  - treatment    → ≤1 item
  - workup       → ≤2 items

Runs 5 curated scenarios through a real LLM. Skipped unless a provider
env var (DIAGNOSIS_LLM / STRUCTURING_LLM / PROVIDER) is set AND the
corresponding API key is present.

Manual invocation (groq example)::

    PROVIDER=groq PYTHONPATH=src ENVIRONMENT=development \\
      .venv/bin/python -m pytest tests/test_diagnosis_sniff.py \\
      -m slow -v --rootdir=.

These assertions are intentionally *structural* (shape + enum caps +
non-empty critical fields). No semantic LLM-as-judge checks — that is
tier-3 work tracked separately.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import pytest_asyncio

# ── Env setup BEFORE importing anything that touches db.engine ──────────
# db.engine reads DATABASE_URL / ENVIRONMENT at import time, so the
# ordering here matters. We intentionally do NOT mutate existing values
# (CI or a caller may already have a real DB pointed at us).
os.environ.setdefault("ENVIRONMENT", "development")
# Use an absolute path under the system temp dir — SQLAlchemy's
# `sqlite+aiosqlite:///...` rejects relative paths that can't be opened
# from the CWD the pytest harness happens to use.
_SNIFF_DB_PATH = Path(tempfile.gettempdir()) / "doctor_ai_sniff.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_SNIFF_DB_PATH}")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Import provider keys from config/runtime.json into env when the operator
# hasn't already exported them. Mirrors tests/scenarios/runner.py, which
# does the same for its scenario harness.
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

# Map provider name → API-key env var (mirrors infra/llm/client.py).
_PROVIDER_KEY_ENV = {
    "deepseek":      "DEEPSEEK_API_KEY",
    "siliconflow":   "SILICONFLOW_API_KEY",
    "dashscope":     "DASHSCOPE_API_KEY",
    "tencent_lkeap": "TENCENT_LKEAP_API_KEY",
    "groq":          "GROQ_API_KEY",
    "sambanova":     "SAMBANOVA_API_KEY",
    "cerebras":      "CEREBRAS_API_KEY",
    "openrouter":    "OPENROUTER_API_KEY",
    "ollama":        "OLLAMA_API_KEY",  # optional — ollama is local
}


def _resolve_test_provider() -> Optional[str]:
    """Return a provider name that has its API key configured, or None.

    Resolution order:
      1. DIAGNOSIS_LLM (pipeline's own primary)
      2. STRUCTURING_LLM (pipeline's fallback)
      3. PROVIDER (convenience env for manual runs)
    For each candidate, we also require the matching *_API_KEY to be set
    (ollama is exempt — it's local).
    """
    candidates = [
        os.environ.get("DIAGNOSIS_LLM", "").strip().lower(),
        os.environ.get("STRUCTURING_LLM", "").strip().lower(),
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
        "diagnosis sniff needs PROVIDER set; run with "
        "`PROVIDER=groq GROQ_API_KEY=... pytest tests/test_diagnosis_sniff.py "
        "-m slow` (or set DIAGNOSIS_LLM / STRUCTURING_LLM instead)"
    ),
)


# ── Scenarios ──────────────────────────────────────────────────────────

# Each scenario: a dict of structured MedicalRecordDB columns. Keys must
# match `domain.records.schema.FIELD_KEYS` — the pipeline routes them
# into the LLM prompt via _format_structured_fields().

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "neurosurgery_typical",
        "description": "Ample evidence — MRI shows frontal meningioma",
        "structured": {
            "chief_complaint": "头痛2周，加重3天",
            "present_illness": "持续性前额头痛，伴恶心呕吐，近日视物模糊",
            "past_history":    "高血压10年",
            "auxiliary_exam":  "MRI示右额叶占位，均匀强化，宽基底附着硬脑膜",
        },
        "expect_kb_citation": False,
    },
    {
        "id": "info_insufficient",
        "description": "Only chief complaint, no history",
        "structured": {
            "chief_complaint": "头痛",
        },
        "expect_kb_citation": False,
    },
    {
        "id": "thunderclap_sah",
        "description": "Sudden thunderclap headache — possible SAH",
        "structured": {
            "chief_complaint": "突发剧烈头痛1小时",
            "present_illness": "一小时前搬重物时突发爆炸样头痛，伴恶心呕吐、颈项强直，疼痛评分10/10",
            "past_history":    "既往无头痛史",
            "physical_exam":   "颈项强直（+），Kernig征（+）",
        },
        "expect_kb_citation": False,
    },
    {
        "id": "kb_citation",
        "description": "KB-1 rule must be cited when relevant",
        "structured": {
            "chief_complaint": "胸痛3小时",
            "present_illness": "突发胸骨后压榨样疼痛，伴出汗，向左肩放射",
            "past_history":    "高血压8年，吸烟20年",
        },
        "expect_kb_citation": True,
    },
    {
        "id": "cardiovascular_cross_specialty",
        "description": "Chest pain + HTN — confirms prompt isn't neuro-only",
        "structured": {
            "chief_complaint": "活动后胸闷气短2周",
            "present_illness": "爬2层楼后出现胸闷气短，休息可缓解，无胸痛",
            "past_history":    "高血压15年，未规律服药；父亲60岁冠心病史",
            "physical_exam":   "BP 160/95 mmHg，心率 82 次/分，双肺清",
        },
        "expect_kb_citation": False,
    },
]


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def _schema_ready():
    """Create tables on the test DB once per module."""
    import db.models  # noqa: F401 — register all ORM models
    from db.engine import engine, Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Leave tables around for post-mortem inspection.


@pytest_asyncio.fixture
async def doctor_with_kb(_schema_ready) -> Tuple[str, int]:
    """Create a fresh doctor + one KB item for the KB-citation scenario.

    Returns (doctor_id, kb_id). The KB id is what the prompt will render
    as [KB-{id}]. We seed a rule that matches the cardiovascular chest-pain
    scenario so the model is strongly encouraged to cite it.
    """
    from db.engine import AsyncSessionLocal
    from db.crud.doctor import _ensure_doctor_exists
    from db.models.doctor import DoctorKnowledgeItem
    from domain.knowledge.doctor_knowledge import invalidate_knowledge_cache

    doctor_id = f"sniff_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        await _ensure_doctor_exists(db, doctor_id)
        item = DoctorKnowledgeItem(
            doctor_id=doctor_id,
            content="胸痛患者首诊必须完善12导联心电图，排除急性冠脉综合征",
            category="diagnosis",
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        kb_id = item.id

    invalidate_knowledge_cache(doctor_id)
    return doctor_id, kb_id


async def _seed_record(doctor_id: str, structured: Dict[str, str]) -> int:
    """Insert a MedicalRecordDB row carrying the scenario's structured
    fields. Returns record_id."""
    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB, RecordStatus

    async with AsyncSessionLocal() as db:
        # MedicalRecordDB has a nullable content column; build a minimal
        # text blob from the structured fields for traceability.
        content = "\n".join(f"{k}: {v}" for k, v in structured.items())
        rec = MedicalRecordDB(
            doctor_id=doctor_id,
            record_type="visit",
            status=RecordStatus.pending_review.value,
            content=content,
            **{k: v for k, v in structured.items()},
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return rec.id


# ── Tests ─────────────────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS],
)
async def test_diagnosis_sniff(scenario: Dict[str, Any], doctor_with_kb):
    """Run one scenario through run_diagnosis and assert structural caps."""
    from domain.diagnosis import run_diagnosis

    doctor_id, kb_id = doctor_with_kb

    # Force DIAGNOSIS_LLM so provider resolution is deterministic — the
    # test-collection phase already validated that the key is present.
    os.environ["DIAGNOSIS_LLM"] = _PROVIDER or os.environ.get(
        "DIAGNOSIS_LLM", ""
    )

    record_id = await _seed_record(doctor_id, scenario["structured"])

    result = await run_diagnosis(doctor_id=doctor_id, record_id=record_id)

    # The pipeline returns {"error": ..., "status": "failed"} on provider
    # misconfig or LLM error. Surface that as a clear fail rather than a
    # KeyError on 'differentials'.
    assert result.get("status") == "completed", (
        f"[{scenario['id']}] pipeline did not complete; full result: {result!r}"
    )

    differentials = result["differentials"]
    workup = result["workup"]
    treatment = result["treatment"]

    # Surface counts on stdout — `-s -v` shows these so the operator can
    # eyeball cap behaviour without digging through logs.
    print(
        f"\n[{scenario['id']}] differentials={len(differentials)} "
        f"workup={len(workup)} treatment={len(treatment)}"
    )

    # ── Hard caps (Phase 2b) ──────────────────────────────────────────
    assert len(differentials) == 1, (
        f"[{scenario['id']}] differentials cap violated: got "
        f"{len(differentials)} items, full result: {result!r}"
    )
    assert len(treatment) <= 1, (
        f"[{scenario['id']}] treatment cap violated: got "
        f"{len(treatment)} items, full result: {result!r}"
    )
    assert len(workup) <= 2, (
        f"[{scenario['id']}] workup cap violated: got "
        f"{len(workup)} items, full result: {result!r}"
    )

    # ── Shape / enum checks ───────────────────────────────────────────
    d0 = differentials[0]
    assert d0["condition"].strip() != "", (
        f"[{scenario['id']}] empty differential condition; result: {result!r}"
    )
    assert d0["confidence"] in {"低", "中", "高"}, (
        f"[{scenario['id']}] bad confidence={d0['confidence']!r}; "
        f"result: {result!r}"
    )

    for w in workup:
        assert w["urgency"] in {"常规", "紧急", "急诊"}, (
            f"[{scenario['id']}] bad workup.urgency={w['urgency']!r}; "
            f"result: {result!r}"
        )

    for t in treatment:
        assert t["intervention"] in {"手术", "药物", "观察", "转诊"}, (
            f"[{scenario['id']}] bad treatment.intervention="
            f"{t['intervention']!r}; result: {result!r}"
        )

    # ── Scenario-specific checks ──────────────────────────────────────
    if scenario["expect_kb_citation"]:
        marker = f"[KB-{kb_id}]"
        all_details = " ".join(
            [d.get("detail", "") for d in differentials]
            + [w.get("detail", "") for w in workup]
            + [t.get("detail", "") for t in treatment]
        )
        assert marker in all_details, (
            f"[{scenario['id']}] expected KB citation {marker} in any "
            f"detail; concatenated details={all_details!r}; "
            f"full result: {result!r}"
        )
