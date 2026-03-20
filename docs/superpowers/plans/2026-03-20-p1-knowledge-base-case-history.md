# P1: Knowledge Base + Case History — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a case history knowledge base with embedding-based case matching and a skill loader for specialty-specific clinical knowledge, so P2's diagnosis pipeline can reference similar past cases and domain rules.

**Architecture:** CaseHistory ORM model with BGE-M3 embeddings stored as JSON arrays. Embedding provider abstraction (local/Dashscope). Skill loader reads YAML-frontmatter markdown files with 5-min TTL cache. Case creation auto-triggered on review confirm (best-effort). Seed cases loaded from a doctor-readable markdown file.

**Tech Stack:** Python 3.9 / SQLAlchemy async / sentence-transformers (BGE-M3) / numpy + scipy / pyyaml / FastAPI

**Spec:** `docs/superpowers/specs/2026-03-20-p1-knowledge-base-case-history-design.md`

**Testing policy (per AGENTS.md):** No unit tests unless explicitly requested. Integration tests required for safety-critical modules. P1 is knowledge base infrastructure — add integration tests for embedding + case matching.

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `src/db/models/case_history.py` | CaseHistory ORM model |
| `src/domain/knowledge/embedding.py` | Embedding provider abstraction (local BGE-M3 + Dashscope) |
| `src/db/crud/case_history.py` | CRUD: create, confirm, update, match, list |
| `src/domain/knowledge/skill_loader.py` | Skill loader: SkillType enum, load, get, cache, aliases |
| `src/domain/knowledge/skills/neurology/diagnosis.md` | Diagnosis skill (Chinese, ~80 lines) |
| `data/seed_neurosurgery_cases.md` | 20-30 seed cases in markdown |
| `scripts/seed_cases.py` | Seed loader: parse markdown, embed, insert |
| `src/channels/web/ui/case_history_handlers.py` | PATCH endpoint for case enrichment |

### Modified files
| File | Change |
|------|--------|
| `src/db/models/__init__.py` | Import CaseHistory |
| `src/utils/runtime_config.py` | Add embedding keys to `DEFAULT_RUNTIME_CONFIG` |
| `src/utils/runtime_config_meta.py` | Add `embedding` category to `CONFIG_CATEGORIES` |
| `src/channels/web/ui/__init__.py` | Include case_history router |
| `src/channels/web/ui/review_handlers.py` | Best-effort case creation on review confirm (add `log`, `MedicalRecordDB`, `select` to top-level imports) |
| `src/main.py` | Add embedding preload to lifespan (after `run_warmup`) |
| `src/domain/knowledge/skills/README.md` | Fix import paths, add diagnosis type |
| `config/runtime.json.sample` | Auto-updated when defaults change (verify after Task 1) |
| `requirements.txt` | Add sentence-transformers, numpy, scipy, pyyaml |

---

### Task 1: Dependencies + Config Infrastructure

**Files:**
- Modify: `requirements.txt`
- Modify: `src/utils/runtime_config.py`
- Modify: `src/utils/runtime_config_meta.py`

- [ ] **Step 1: Add Python dependencies to requirements.txt**

Append these lines to `requirements.txt`:
```
sentence-transformers>=2.2.0
numpy
scipy
pyyaml
```

- [ ] **Step 2: Add embedding defaults to `src/utils/runtime_config.py`**

In `DEFAULT_RUNTIME_CONFIG` dict (around line 80, before the closing `}`), add:
```python
    "EMBEDDING_PROVIDER": "local",
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "EMBEDDING_PRELOAD": True,
    "DASHSCOPE_API_KEY": "",
    "SKILLS_CACHE_TTL": 300,
```

- [ ] **Step 3: Add embedding category to `src/utils/runtime_config_meta.py`**

In `CONFIG_CATEGORIES` dict, add a new `"embedding"` category after the existing categories:
```python
    "embedding": {
        "description": "Embedding model for case history RAG matching.",
        "keys": [
            "EMBEDDING_PROVIDER",
            "EMBEDDING_MODEL",
            "EMBEDDING_PRELOAD",
            "DASHSCOPE_API_KEY",
            "SKILLS_CACHE_TTL",
        ],
    },
```

Also add to `CONFIG_DESCRIPTIONS` dict:
```python
    "EMBEDDING_PROVIDER": "Embedding provider: 'local' (BGE-M3 via sentence-transformers) or 'dashscope' (Alibaba Cloud).",
    "EMBEDDING_MODEL": "Model name for local embedding provider (default: BAAI/bge-m3).",
    "EMBEDDING_PRELOAD": "Preload embedding model at app startup (default: true).",
    "DASHSCOPE_API_KEY": "API key for Dashscope embedding provider (only if EMBEDDING_PROVIDER=dashscope).",
    "SKILLS_CACHE_TTL": "Skill file cache TTL in seconds (default: 300 = 5 minutes).",
```

And to `CONFIG_DESCRIPTIONS_ZH` dict:
```python
    "EMBEDDING_PROVIDER": "嵌入模型提供商：'local'（本地 BGE-M3）或 'dashscope'（阿里云）。",
    "EMBEDDING_MODEL": "本地嵌入模型名称（默认：BAAI/bge-m3）。",
    "EMBEDDING_PRELOAD": "启动时预加载嵌入模型（默认：true）。",
    "DASHSCOPE_API_KEY": "Dashscope 嵌入提供商 API 密钥。",
    "SKILLS_CACHE_TTL": "技能文件缓存 TTL（秒，默认 300 = 5 分钟）。",
```

- [ ] **Step 4: Install dependencies**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/pip install sentence-transformers numpy scipy pyyaml`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/utils/runtime_config.py src/utils/runtime_config_meta.py
git commit -m "chore(p1): add embedding dependencies and config infrastructure"
```

---

### Task 2: CaseHistory ORM Model

**Files:**
- Create: `src/db/models/case_history.py`
- Modify: `src/db/models/__init__.py`

- [ ] **Step 1: Create the CaseHistory model**

```python
# src/db/models/case_history.py
"""Case history for clinical decision support knowledge base."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class CaseHistory(Base):
    __tablename__ = "case_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False,
    )
    patient_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True,
    )
    record_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True,
    )
    chief_complaint: Mapped[str] = mapped_column(Text, nullable=False)
    present_illness: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    treatment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="preliminary",
    )
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of 1024 floats
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("doctor_id", "record_id", name="uq_case_doctor_record"),
        Index("ix_case_history_doctor_confidence", "doctor_id", "confidence_status"),
    )
```

- [ ] **Step 2: Register in model registry**

In `src/db/models/__init__.py`, add import:
```python
from db.models.case_history import CaseHistory
```
Add `"CaseHistory"` to the `__all__` list.

- [ ] **Step 3: Verify**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "from db.models.case_history import CaseHistory; print('OK:', CaseHistory.__tablename__)"`

- [ ] **Step 4: Commit**

```bash
git add src/db/models/case_history.py src/db/models/__init__.py
git commit -m "feat(p1): add CaseHistory ORM model with embedding + confidence status"
```

---

### Task 3: Embedding Provider Abstraction

**Files:**
- Create: `src/domain/knowledge/embedding.py`

- [ ] **Step 1: Create the embedding module**

```python
# src/domain/knowledge/embedding.py
"""Embedding provider abstraction — local BGE-M3 or cloud Dashscope.

Usage:
    from domain.knowledge.embedding import embed, embed_batch, preload_embedding_model
    preload_embedding_model()  # call at app startup
    vec = embed("头痛2周伴恶心呕吐")  # → list of 1024 floats
"""
from __future__ import annotations

import os
from typing import List, Optional

from utils.log import log

_model = None
_provider: Optional[str] = None


def _get_provider() -> str:
    return os.environ.get("EMBEDDING_PROVIDER", "local")


def _get_model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")


def preload_embedding_model() -> None:
    """Load embedding model at startup. Call once during app lifespan."""
    global _model, _provider
    _provider = _get_provider()

    if _provider == "local":
        try:
            from sentence_transformers import SentenceTransformer
            model_name = _get_model_name()
            log(f"[embedding] loading local model: {model_name}")
            _model = SentenceTransformer(model_name)
            log(f"[embedding] model loaded: {model_name}")
        except Exception as e:
            log(f"[embedding] failed to load model: {e}", level="warning")
            _model = None
    elif _provider == "dashscope":
        log("[embedding] dashscope provider — no preload needed")
    else:
        log(f"[embedding] unknown provider: {_provider}", level="warning")


def embed(text: str) -> List[float]:
    """Embed a single text string. Returns list of floats (1024-d for BGE-M3)."""
    provider = _provider or _get_provider()

    if provider == "local":
        if _model is None:
            raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
        vec = _model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    elif provider == "dashscope":
        import dashscope
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=text,
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        )
        return resp.output["embeddings"][0]["embedding"]

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts. Returns list of embedding vectors."""
    provider = _provider or _get_provider()

    if provider == "local":
        if _model is None:
            raise RuntimeError("Embedding model not loaded. Call preload_embedding_model() first.")
        vecs = _model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    elif provider == "dashscope":
        import dashscope
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=texts,
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        )
        return [e["embedding"] for e in resp.output["embeddings"]]

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def get_model_name() -> str:
    """Return the current embedding model name for storage tracking."""
    provider = _provider or _get_provider()
    if provider == "local":
        return _get_model_name()
    elif provider == "dashscope":
        return "dashscope/text-embedding-v3"
    return f"unknown/{provider}"
```

- [ ] **Step 2: Verify import**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "from domain.knowledge.embedding import embed, embed_batch, preload_embedding_model, get_model_name; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/embedding.py
git commit -m "feat(p1): add embedding provider abstraction (local BGE-M3 + Dashscope)"
```

---

### Task 4: Case History CRUD

**Files:**
- Create: `src/db/crud/case_history.py`

- [ ] **Step 1: Create the CRUD module**

```python
# src/db/crud/case_history.py
"""CRUD operations for case history knowledge base."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.spatial.distance import cosine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.case_history import CaseHistory
from db.models.base import _utcnow
from domain.knowledge.embedding import embed, get_model_name
from utils.log import log

SEED_DOCTOR_ID = "__seed__"


def _build_embed_text(
    chief_complaint: str,
    present_illness: Optional[str] = None,
    final_diagnosis: Optional[str] = None,
    treatment: Optional[str] = None,
) -> str:
    """Build the text to embed from case fields."""
    parts = [chief_complaint]
    if present_illness:
        parts.append(present_illness)
    if final_diagnosis:
        parts.append(f"诊断：{final_diagnosis}")
    if treatment:
        parts.append(f"治疗：{treatment}")
    return " ".join(parts)


async def create_case(
    session: AsyncSession,
    doctor_id: str,
    record_id: Optional[int],
    patient_id: Optional[int],
    chief_complaint: str,
    present_illness: str = "",
) -> CaseHistory:
    """Create a preliminary case. Embedding computed from chief_complaint + present_illness."""
    embed_text = _build_embed_text(chief_complaint, present_illness)
    try:
        vec = embed(embed_text)
        embedding_json = json.dumps(vec)
    except Exception as e:
        log(f"[case_history] embedding failed: {e}", level="warning")
        embedding_json = None
        vec = None

    entry = CaseHistory(
        doctor_id=doctor_id,
        record_id=record_id,
        patient_id=patient_id,
        chief_complaint=chief_complaint,
        present_illness=present_illness or None,
        confidence_status="preliminary",
        embedding=embedding_json,
        embedding_model=get_model_name() if vec else None,
        created_at=_utcnow(),
    )
    session.add(entry)
    return entry


async def confirm_case(
    session: AsyncSession,
    case_id: int,
    doctor_id: str,
    final_diagnosis: str,
    treatment: Optional[str] = None,
    outcome: Optional[str] = None,
    notes: Optional[str] = None,
    key_symptoms: Optional[List[str]] = None,
) -> Optional[CaseHistory]:
    """Promote a case to confirmed. Re-computes embedding with diagnosis text."""
    case = (await session.execute(
        select(CaseHistory).where(
            CaseHistory.id == case_id,
            CaseHistory.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if case is None:
        return None

    case.final_diagnosis = final_diagnosis
    case.treatment = treatment
    case.outcome = outcome
    case.notes = notes
    if key_symptoms:
        case.key_symptoms = json.dumps(key_symptoms, ensure_ascii=False)
    case.confidence_status = "confirmed"
    case.updated_at = _utcnow()

    # Re-embed with diagnosis included
    embed_text = _build_embed_text(
        case.chief_complaint, case.present_illness,
        final_diagnosis, treatment,
    )
    try:
        vec = embed(embed_text)
        case.embedding = json.dumps(vec)
        case.embedding_model = get_model_name()
    except Exception as e:
        log(f"[case_history] re-embedding failed on confirm: {e}", level="warning")

    return case


async def match_cases(
    session: AsyncSession,
    doctor_id: str,
    query_text: str,
    limit: int = 5,
    threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """Find similar confirmed cases by cosine similarity.
    Includes seed cases (__seed__ doctor_id) alongside doctor's own."""
    # Embed query
    try:
        query_vec = np.array(embed(query_text))
    except Exception as e:
        log(f"[case_history] query embedding failed: {e}", level="warning")
        return []

    # Load confirmed cases (doctor's own + seeds)
    result = await session.execute(
        select(CaseHistory).where(
            CaseHistory.doctor_id.in_([doctor_id, SEED_DOCTOR_ID]),
            CaseHistory.confidence_status == "confirmed",
            CaseHistory.embedding.isnot(None),
        )
    )
    cases = result.scalars().all()
    if not cases:
        return []

    # Compute similarities
    matches = []
    for case in cases:
        try:
            case_vec = np.array(json.loads(case.embedding))
            similarity = 1.0 - cosine(query_vec, case_vec)
            if similarity >= threshold:
                matches.append({
                    "id": case.id,
                    "chief_complaint": case.chief_complaint,
                    "final_diagnosis": case.final_diagnosis,
                    "treatment": case.treatment,
                    "outcome": case.outcome,
                    "key_symptoms": json.loads(case.key_symptoms) if case.key_symptoms else [],
                    "similarity": round(similarity, 4),
                    "is_seed": case.doctor_id == SEED_DOCTOR_ID,
                })
        except (json.JSONDecodeError, ValueError):
            continue

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


async def update_case(
    session: AsyncSession,
    case_id: int,
    doctor_id: str,
    **fields: Any,
) -> Optional[CaseHistory]:
    """Edit any field on a case. Re-computes embedding if text fields changed."""
    case = (await session.execute(
        select(CaseHistory).where(
            CaseHistory.id == case_id,
            CaseHistory.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if case is None:
        return None

    text_fields = {"chief_complaint", "present_illness", "final_diagnosis", "treatment"}
    text_changed = False
    for key, value in fields.items():
        if hasattr(case, key):
            setattr(case, key, value)
            if key in text_fields:
                text_changed = True
    case.updated_at = _utcnow()

    if text_changed:
        embed_text = _build_embed_text(
            case.chief_complaint, case.present_illness,
            case.final_diagnosis, case.treatment,
        )
        try:
            vec = embed(embed_text)
            case.embedding = json.dumps(vec)
            case.embedding_model = get_model_name()
        except Exception as e:
            log(f"[case_history] re-embedding failed on update: {e}", level="warning")

    return case


async def list_cases(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[CaseHistory]:
    """List cases for a doctor, optionally filtered by status."""
    q = select(CaseHistory).where(CaseHistory.doctor_id == doctor_id)
    if status:
        q = q.where(CaseHistory.confidence_status == status)
    q = q.order_by(CaseHistory.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())
```

- [ ] **Step 2: Verify import**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "from db.crud.case_history import create_case, confirm_case, match_cases, list_cases; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/db/crud/case_history.py
git commit -m "feat(p1): add case history CRUD with embedding-based matching"
```

---

### Task 5: Skill Loader

**Files:**
- Create: `src/domain/knowledge/skill_loader.py`
- Modify: `src/domain/knowledge/skills/README.md`

- [ ] **Step 1: Create the skill loader**

```python
# src/domain/knowledge/skill_loader.py
"""Skill file loader — reads specialty-specific markdown skills with YAML frontmatter."""
from __future__ import annotations

import os
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from utils.log import log

SKILLS_DIR = Path(__file__).parent / "skills"


class SkillType(str, Enum):
    structuring = "structuring"
    routing = "routing"
    clinical_signals = "clinical_signals"
    diagnosis = "diagnosis"


_SPECIALTY_ALIASES: Dict[str, str] = {
    "神经外科": "neurology",
    "神经内科": "neurology",
    "心内科": "cardiology",
    "心脏科": "cardiology",
}

_skill_cache: Dict[str, Tuple[Dict[SkillType, str], float]] = {}


def _cache_ttl() -> int:
    try:
        return int(os.environ.get("SKILLS_CACHE_TTL", "300"))
    except (TypeError, ValueError):
        return 300


def _resolve_specialty(specialty: str) -> str:
    """Resolve Chinese aliases to English directory names."""
    return _SPECIALTY_ALIASES.get(specialty, specialty)


def _parse_skill_file(path: Path) -> Tuple[Optional[SkillType], str]:
    """Parse a skill markdown file. Returns (skill_type, body_content)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, text

    skill_type_str = meta.get("type", "")
    try:
        skill_type = SkillType(skill_type_str)
    except ValueError:
        skill_type = None

    body = parts[2].strip()
    return skill_type, body


def load_skills(specialty: str) -> Dict[SkillType, str]:
    """Load all skills for a specialty (+ _default). Cached with TTL."""
    resolved = _resolve_specialty(specialty)
    now = time.time()

    if resolved in _skill_cache:
        cached, ts = _skill_cache[resolved]
        if now - ts < _cache_ttl():
            return cached

    skills: Dict[SkillType, str] = {}

    # Load _default skills first
    default_dir = SKILLS_DIR / "_default"
    if default_dir.is_dir():
        for f in sorted(default_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            stype, body = _parse_skill_file(f)
            if stype and body:
                skills[stype] = body

    # Load specialty skills (override/merge with defaults)
    specialty_dir = SKILLS_DIR / resolved
    if specialty_dir.is_dir():
        for f in sorted(specialty_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            stype, body = _parse_skill_file(f)
            if stype and body:
                if stype == SkillType.structuring and stype in skills:
                    # Merge: default + specialty
                    skills[stype] = skills[stype] + "\n\n" + body
                else:
                    skills[stype] = body

    _skill_cache[resolved] = (skills, now)
    return skills


def get_skill(specialty: str, skill_type: SkillType) -> Optional[str]:
    """Get a single skill's content body."""
    skills = load_skills(specialty)
    return skills.get(skill_type)


def get_structuring_skill(specialty: str) -> str:
    """Merged _default/structuring.md + {specialty}/structuring.md."""
    return get_skill(specialty, SkillType.structuring) or ""


def get_clinical_signals(specialty: str) -> Optional[str]:
    """Return {specialty}/clinical_signals.md content."""
    return get_skill(specialty, SkillType.clinical_signals)


def get_diagnosis_skill(specialty: str) -> Optional[str]:
    """Return {specialty}/diagnosis.md content."""
    return get_skill(specialty, SkillType.diagnosis)


def get_routing_hints(specialty: str) -> Optional[str]:
    """Return routing hints (specialty or _default)."""
    return get_skill(specialty, SkillType.routing)


def list_specialties() -> List[str]:
    """List available specialty directories (excluding _default)."""
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "_default" and not d.name.startswith(".")
    )


def invalidate_cache() -> None:
    """Clear the skill cache."""
    _skill_cache.clear()
```

- [ ] **Step 2: Update skills README import paths**

In `src/domain/knowledge/skills/README.md`, replace any references to `services.knowledge.skill_loader` with `domain.knowledge.skill_loader`, and `services/knowledge/skill_loader.py` with `domain/knowledge/skill_loader.py`. Add `diagnosis` to the documented `type` field values.

- [ ] **Step 3: Verify**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "
from domain.knowledge.skill_loader import load_skills, get_structuring_skill, get_clinical_signals, get_diagnosis_skill, list_specialties, SkillType
print('Specialties:', list_specialties())
s = get_structuring_skill('neurology')
print('Structuring skill loaded:', len(s), 'chars')
print('SkillType.diagnosis:', SkillType.diagnosis.value)
"`

- [ ] **Step 4: Commit**

```bash
git add src/domain/knowledge/skill_loader.py src/domain/knowledge/skills/README.md
git commit -m "feat(p1): implement skill loader with SkillType enum, cache, Chinese aliases"
```

---

### Task 6: Neurology Diagnosis Skill

**Files:**
- Create: `src/domain/knowledge/skills/neurology/diagnosis.md`

- [ ] **Step 1: Create the diagnosis skill file**

Write `src/domain/knowledge/skills/neurology/diagnosis.md` with:
- YAML frontmatter: name=neurology-diagnosis, type=diagnosis, specialty=neurology
- Chinese content (~80 lines):
  - Output format section: 鉴别诊断, 检查建议, 治疗方向, 危险信号, 免责声明
  - 10-15 must-not-miss neurosurgery patterns (all in Chinese, medical abbreviations preserved)

Content should follow the spec's must-not-miss patterns list and output format definitions.

- [ ] **Step 2: Verify skill loads**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "
from domain.knowledge.skill_loader import get_diagnosis_skill
content = get_diagnosis_skill('neurology')
print('Loaded:', len(content), 'chars')
print('First 100:', content[:100])
"`

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/skills/neurology/diagnosis.md
git commit -m "feat(p1): add neurology diagnosis skill — output format + must-not-miss patterns"
```

---

### Task 7: Seed Data

**Files:**
- Create: `data/seed_neurosurgery_cases.md`
- Create: `scripts/seed_cases.py`

- [ ] **Step 1: Create seed data markdown**

Write `data/seed_neurosurgery_cases.md` with 20-30 realistic neurosurgery cases in Chinese. Format:
```markdown
# 神经外科种子病例库

## 头痛 — 脑膜瘤

**主诉：** ...
**现病史：** ...
**诊断：** ...
**关键症状：** symptom1, symptom2, symptom3
**治疗：** ...
**转归：** ...

---

## Next case...
```

Cover 6 categories (~5 cases each):
1. 头痛变体 (tension, migraine, mass/meningioma, SAH, subdural)
2. 脑卒中/TIA (ischemic, hemorrhagic, TIA)
3. 脊髓压迫/椎间盘突出 (cervical, lumbar, spinal tumor, cauda equina)
4. 周围神经病变 (carpal tunnel, peripheral neuropathy, ulnar neuropathy)
5. 癫痫/痫性发作 (focal, generalized, status epilepticus)
6. 三叉神经痛/脑积水 (trigeminal neuralgia, NPH, obstructive hydrocephalus)

- [ ] **Step 2: Create seed loader script**

```python
#!/usr/bin/env python
# scripts/seed_cases.py
"""Load seed neurosurgery cases from markdown into case_history table."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.engine import AsyncSessionLocal
from db.models.case_history import CaseHistory
from domain.knowledge.embedding import embed, preload_embedding_model
from sqlalchemy import select

SEED_DOCTOR_ID = "__seed__"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "seed_neurosurgery_cases.md"

FIELD_MAP = {
    "主诉": "chief_complaint",
    "现病史": "present_illness",
    "诊断": "final_diagnosis",
    "关键症状": "key_symptoms",
    "治疗": "treatment",
    "转归": "outcome",
}


def parse_cases(text: str) -> List[Dict[str, str]]:
    """Parse markdown into list of case dicts."""
    cases = []
    # Split by ## headers (case boundaries)
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    for section in sections[1:]:  # skip content before first ##
        lines = section.strip().split("\n")
        if not lines:
            continue
        case: Dict[str, str] = {"_title": lines[0].strip()}
        for line in lines[1:]:
            line = line.strip()
            if not line or line == "---":
                continue
            # Match **field：** value or **field:** value
            m = re.match(r"\*\*(.+?)[：:]\*\*\s*(.*)", line)
            if m:
                zh_field = m.group(1).strip()
                value = m.group(2).strip()
                en_field = FIELD_MAP.get(zh_field)
                if en_field:
                    case[en_field] = value
        if "chief_complaint" in case:
            cases.append(case)
    return cases


async def seed():
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found")
        sys.exit(1)

    text = DATA_FILE.read_text(encoding="utf-8")
    cases = parse_cases(text)
    print(f"Parsed {len(cases)} cases from {DATA_FILE.name}")

    # Preload embedding model
    preload_embedding_model()

    async with AsyncSessionLocal() as session:
        inserted = 0
        for case in cases:
            cc = case.get("chief_complaint", "")
            # Check idempotency
            existing = (await session.execute(
                select(CaseHistory).where(
                    CaseHistory.doctor_id == SEED_DOCTOR_ID,
                    CaseHistory.chief_complaint == cc,
                )
            )).scalar_one_or_none()
            if existing:
                print(f"  SKIP (exists): {cc[:30]}")
                continue

            # Build embedding
            pi = case.get("present_illness", "")
            diag = case.get("final_diagnosis", "")
            treat = case.get("treatment", "")
            embed_text = cc
            if pi:
                embed_text += " " + pi
            if diag:
                embed_text += f" 诊断：{diag}"
            if treat:
                embed_text += f" 治疗：{treat}"

            try:
                vec = embed(embed_text)
                embedding_json = json.dumps(vec)
            except Exception as e:
                print(f"  WARN: embedding failed for {cc[:30]}: {e}")
                embedding_json = None

            # Parse key_symptoms
            ks_raw = case.get("key_symptoms", "")
            ks_list = [s.strip() for s in re.split(r"[,，]", ks_raw) if s.strip()] if ks_raw else []

            entry = CaseHistory(
                doctor_id=SEED_DOCTOR_ID,
                chief_complaint=cc,
                present_illness=pi or None,
                final_diagnosis=diag or None,
                key_symptoms=json.dumps(ks_list, ensure_ascii=False) if ks_list else None,
                treatment=treat or None,
                outcome=case.get("outcome") or None,
                confidence_status="confirmed",
                embedding=embedding_json,
                embedding_model="BAAI/bge-m3",
            )
            session.add(entry)
            inserted += 1
            print(f"  ADD: {cc[:40]}")

        await session.commit()
        print(f"\nDone: {inserted} cases inserted, {len(cases) - inserted} skipped")


if __name__ == "__main__":
    # Load runtime config first
    os.environ.setdefault("EMBEDDING_PROVIDER", "local")
    from utils.runtime_config import load_runtime_json
    load_runtime_json()
    asyncio.run(seed())
```

- [ ] **Step 3: Commit**

```bash
git add data/seed_neurosurgery_cases.md scripts/seed_cases.py
git commit -m "feat(p1): add neurosurgery seed cases (markdown) + seed loader script"
```

---

### Task 8: Case Enrichment Endpoint

**Files:**
- Create: `src/channels/web/ui/case_history_handlers.py`
- Modify: `src/channels/web/ui/__init__.py`

- [ ] **Step 1: Create the endpoint handler**

```python
# src/channels/web/ui/case_history_handlers.py
"""Case history enrichment endpoint: promote preliminary → confirmed."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.case_history import confirm_case
from infra.observability.audit import audit
from infra.auth.rate_limit import enforce_doctor_rate_limit
from channels.web.ui._utils import _resolve_ui_doctor_id
from utils.log import safe_create_task

router = APIRouter(tags=["ui"], include_in_schema=False)


class CaseEnrichment(BaseModel):
    final_diagnosis: str
    treatment: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    key_symptoms: Optional[List[str]] = None


@router.patch("/api/manage/case-history/{case_id}", include_in_schema=True)
async def enrich_case_endpoint(
    case_id: int,
    body: CaseEnrichment,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.case_history.enrich")
    async with AsyncSessionLocal() as db:
        case = await confirm_case(
            db, case_id, resolved,
            final_diagnosis=body.final_diagnosis,
            treatment=body.treatment,
            outcome=body.outcome,
            notes=body.notes,
            key_symptoms=body.key_symptoms,
        )
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        await db.commit()
    safe_create_task(audit(resolved, "case_history.confirmed", "case_history", str(case_id)))
    return {"id": case.id, "status": case.confidence_status}
```

- [ ] **Step 2: Include router in UI __init__**

In `src/channels/web/ui/__init__.py`, add:
```python
from channels.web.ui.case_history_handlers import router as _case_history_router
```
And:
```python
router.include_router(_case_history_router)
```

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/ui/case_history_handlers.py src/channels/web/ui/__init__.py
git commit -m "feat(p1): add case enrichment endpoint (PATCH /case-history/{id})"
```

---

### Task 9: P3 Integration + Startup Preload

**Files:**
- Modify: `src/channels/web/ui/review_handlers.py`
- Modify: `src/main.py`

- [ ] **Step 1: Add best-effort case creation to confirm_review_endpoint**

In `src/channels/web/ui/review_handlers.py`, after the `confirm_review_endpoint` function's `return` statement (around line 73), add the best-effort case creation. The integration code runs AFTER the successful response is prepared but BEFORE it returns. Actually — since FastAPI returns synchronously, the best approach is to add it after `db.commit()` but inside the endpoint, wrapped in try/except:

After `safe_create_task(audit(...))` and before the `return` statement in `confirm_review_endpoint`, add:

```python
    # Best-effort: create case_history entry
    try:
        import json as _json
        from db.crud.case_history import create_case as _create_case
        async with AsyncSessionLocal() as db2:
            _rec = (await db2.execute(
                select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
            )).scalar_one_or_none()
            if _rec and _rec.structured:
                _s = _json.loads(_rec.structured)
                _cc = _s.get("chief_complaint", "")
                if _cc:
                    await _create_case(
                        db2, doctor_id=resolved, record_id=rq.record_id,
                        patient_id=rq.patient_id,
                        chief_complaint=_cc,
                        present_illness=_s.get("present_illness", ""),
                    )
                    await db2.commit()
    except Exception as _e:
        log(f"[review] case_history creation failed (non-blocking): {_e}", level="warning")
```

Add these to the top-level imports of `review_handlers.py` (if not already present):
```python
from sqlalchemy import select
from db.models import MedicalRecordDB
from utils.log import log
```

- [ ] **Step 2: Add embedding preload to startup**

In `src/main.py`, inside the `lifespan()` async context manager (around line 123),
add the embedding preload after `await run_warmup(APP_CONFIG)`:

```python
    # Preload embedding model for case history matching
    try:
        if os.environ.get("EMBEDDING_PRELOAD", "true").lower() in ("true", "1", "yes"):
            from domain.knowledge.embedding import preload_embedding_model
            preload_embedding_model()
    except Exception as e:
        _startup_log.warning(f"Embedding preload failed (non-blocking): {e}")
```

This goes at line 124, after `await run_warmup(APP_CONFIG)` and before
`await _startup_background_workers()`.

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/ui/review_handlers.py src/main.py
git commit -m "feat(p1): integrate case creation on review confirm + embedding preload at startup"
```

---

### Task 10: Integration Test

**Files:**
- Create: `tests/core/test_case_history.py`

- [ ] **Step 1: Create integration tests**

Test the case history CRUD + matching pipeline with in-memory SQLite. Mock the embedding function (don't load BGE-M3 in tests — it's 2GB).

```python
"""P1 Case History integration tests — real DB, mocked embeddings."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from db.models import Doctor, Patient, MedicalRecordDB
from db.models.case_history import CaseHistory
from db.crud.case_history import (
    create_case, confirm_case, match_cases, list_cases, SEED_DOCTOR_ID,
)


def _fake_embed(text):
    """Deterministic fake embedding: hash text to a 1024-d vector."""
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    vec = [float(b) / 255.0 for b in h] * 32  # 32 * 32 = 1024
    # Normalize
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


@pytest.fixture(autouse=True)
def mock_embed():
    with patch("db.crud.case_history.embed", side_effect=_fake_embed):
        with patch("db.crud.case_history.get_model_name", return_value="test-model"):
            yield


async def _seed_doctor(session, doctor_id="test_doctor"):
    session.add(Doctor(doctor_id=doctor_id, name="Dr. Test", specialty="神经外科"))
    await session.flush()
    return doctor_id


@pytest.mark.asyncio
async def test_create_and_list_case(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        case = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛反复发作2周",
            present_illness="前额持续性胀痛",
        )
        await session.commit()
        assert case.confidence_status == "preliminary"
        assert case.embedding is not None

    async with session_factory() as session:
        cases = await list_cases(session, "test_doctor")
        assert len(cases) == 1
        assert cases[0].chief_complaint == "头痛反复发作2周"


@pytest.mark.asyncio
async def test_confirm_case_reembeds(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        case = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛反复发作2周",
        )
        await session.commit()
        old_embedding = case.embedding

    async with session_factory() as session:
        confirmed = await confirm_case(
            session, case.id, "test_doctor",
            final_diagnosis="脑膜瘤",
            treatment="手术切除",
        )
        await session.commit()
        assert confirmed.confidence_status == "confirmed"
        assert confirmed.final_diagnosis == "脑膜瘤"
        assert confirmed.embedding != old_embedding  # re-embedded with diagnosis


@pytest.mark.asyncio
async def test_match_cases_returns_confirmed_only(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        # Create + confirm one case
        c1 = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛伴恶心呕吐",
        )
        await session.flush()
        await confirm_case(session, c1.id, did, final_diagnosis="脑膜瘤")
        # Create preliminary case (should NOT match)
        await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="腰痛伴左下肢放射痛",
        )
        await session.commit()

    async with session_factory() as session:
        matches = await match_cases(session, did, "头痛2周")
        # Only confirmed case should appear
        assert len(matches) >= 1
        assert all(m["final_diagnosis"] is not None for m in matches)


@pytest.mark.asyncio
async def test_match_includes_seed_cases(session_factory):
    async with session_factory() as session:
        await _seed_doctor(session, "test_doctor")
        await _seed_doctor(session, SEED_DOCTOR_ID)
        # Create seed case
        seed = await create_case(
            session, doctor_id=SEED_DOCTOR_ID, record_id=None, patient_id=None,
            chief_complaint="突发剧烈头痛",
        )
        await session.flush()
        await confirm_case(session, seed.id, SEED_DOCTOR_ID, final_diagnosis="SAH")
        await session.commit()

    async with session_factory() as session:
        matches = await match_cases(session, "test_doctor", "突发头痛")
        assert len(matches) >= 1
        assert any(m["is_seed"] for m in matches)


@pytest.mark.asyncio
async def test_data_isolation(session_factory):
    async with session_factory() as session:
        await _seed_doctor(session, "doctor_a")
        await _seed_doctor(session, "doctor_b")
        c = await create_case(
            session, doctor_id="doctor_a", record_id=None, patient_id=None,
            chief_complaint="头痛",
        )
        await session.flush()
        await confirm_case(session, c.id, "doctor_a", final_diagnosis="偏头痛")
        await session.commit()

    async with session_factory() as session:
        # Doctor B should not see doctor A's cases (only seeds)
        cases_b = await list_cases(session, "doctor_b")
        assert len(cases_b) == 0
```

- [ ] **Step 2: Run tests**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_case_history.py -v --tb=short`

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_case_history.py
git commit -m "test(p1): add case history integration tests — CRUD, matching, seeds, isolation"
```
