# AI Persona Phase 1: Data Separation + UI Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate persona from knowledge at the data, API, and UI layers. Persona becomes its own table with structured JSON fields. MyAI page shows persona and knowledge as two distinct sections.

**Architecture:** New `DoctorPersona` model replaces the special `DoctorKnowledgeItem` with `category=persona`. Persona stores structured JSON (5 fields, each an array of rules). Prompt composer loads persona from the new table via an explicit `load_persona` flag on `LayerConfig`. Frontend splits MyAI page into persona section + knowledge section.

**Tech Stack:** SQLAlchemy (async), FastAPI, React + MUI, SQLite dev / MySQL prod

**Spec:** `docs/superpowers/specs/2026-04-10-ai-persona-redesign.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/db/models/doctor_persona.py` | DoctorPersona ORM model |
| Modify | `src/db/models/__init__.py` | Register new model |
| Modify | `src/db/models/doctor.py` | Remove `persona` from KnowledgeCategory enum |
| Create | `src/db/crud/persona.py` | CRUD for doctor_personas table |
| Create | `src/channels/web/doctor_dashboard/persona_handlers.py` | Persona API endpoints |
| Modify | `src/channels/web/doctor_dashboard/knowledge_handlers.py` | Remove persona from knowledge API |
| Modify | `src/domain/knowledge/knowledge_context.py` | Load persona from new table |
| Modify | `src/domain/knowledge/teaching.py` | Remove old persona lifecycle |
| Modify | `src/agent/prompt_config.py` | Add `load_persona` to LayerConfig |
| Modify | `src/agent/prompt_composer.py` | Use `load_persona` flag, render structured JSON |
| Create | `src/scripts/migrate_persona.py` | One-shot migration script |
| Create | `frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx` | Persona detail/edit page |
| Modify | `frontend/web/src/pages/doctor/MyAIPage.jsx` | Split into persona + knowledge sections |
| Modify | `frontend/web/src/api.js` | Add persona API functions |
| Modify | `frontend/web/src/lib/doctorQueries.js` | Add usePersona query hook |
| Modify | `frontend/web/src/lib/queryKeys.js` | Add persona query key |
| Test | `tests/test_persona_model.py` | Model + CRUD tests |
| Test | `tests/test_persona_api.py` | API endpoint tests |
| Test | `tests/test_prompt_composer_persona.py` | Prompt composition with new persona |

---

### Task 1: DoctorPersona Model

**Files:**
- Create: `src/db/models/doctor_persona.py`
- Modify: `src/db/models/__init__.py`

- [ ] **Step 1: Write the model test**

```python
# tests/test_persona_model.py
"""Tests for the DoctorPersona model and CRUD operations."""
import json
import pytest
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS

def test_empty_persona_fields_structure():
    """EMPTY_PERSONA_FIELDS has all 5 field keys as empty lists."""
    fields = EMPTY_PERSONA_FIELDS()
    assert set(fields.keys()) == {"reply_style", "closing", "structure", "avoid", "edits"}
    for v in fields.values():
        assert v == []

def test_persona_model_defaults():
    """DoctorPersona has correct defaults."""
    p = DoctorPersona(doctor_id="doc_1")
    assert p.status == "draft"
    assert p.onboarded is False
    assert p.edit_count == 0
    assert p.version == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_persona_model.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `ModuleNotFoundError: No module named 'db.models.doctor_persona'`

- [ ] **Step 3: Create the model**

```python
# src/db/models/doctor_persona.py
"""Doctor persona model — structured AI behavior preferences."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


def EMPTY_PERSONA_FIELDS() -> dict:
    """Return the default empty persona fields structure."""
    return {
        "reply_style": [],
        "closing": [],
        "structure": [],
        "avoid": [],
        "edits": [],
    }


class DoctorPersona(Base):
    """Per-doctor AI persona — structured behavior preferences.

    Each rule in a field has: {"id": "ps_N", "text": "...", "source": "...", "usage_count": 0}
    """
    __tablename__ = "doctor_personas"

    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        primary_key=True,
    )
    fields_json: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: json.dumps(EMPTY_PERSONA_FIELDS()),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    onboarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    @property
    def fields(self) -> dict:
        """Parse fields_json into a dict."""
        try:
            return json.loads(self.fields_json)
        except (json.JSONDecodeError, TypeError):
            return EMPTY_PERSONA_FIELDS()

    @fields.setter
    def fields(self, value: dict):
        """Serialize dict to fields_json."""
        self.fields_json = json.dumps(value, ensure_ascii=False)

    def all_rules(self) -> list[dict]:
        """Return a flat list of all rules across all fields."""
        rules = []
        for field_rules in self.fields.values():
            rules.extend(field_rules)
        return rules

    def render_for_prompt(self, max_rules: int = 15, max_chars: int = 500) -> str:
        """Render persona rules into the prompt format with [P-id] markers.

        Prioritizes by field order: avoid > structure > reply_style > closing > edits.
        Within each field, prioritizes by usage_count descending.
        """
        FIELD_ORDER = ["avoid", "structure", "reply_style", "closing", "edits"]
        FIELD_LABELS = {
            "reply_style": "回复风格",
            "closing": "常用结尾语",
            "structure": "回复结构",
            "avoid": "回避内容",
            "edits": "常见修改",
        }
        fields = self.fields
        selected: list[tuple[str, dict]] = []  # (field_key, rule)

        for field_key in FIELD_ORDER:
            field_rules = fields.get(field_key, [])
            # Sort by usage_count descending
            sorted_rules = sorted(field_rules, key=lambda r: r.get("usage_count", 0), reverse=True)
            for rule in sorted_rules:
                if len(selected) >= max_rules:
                    break
                selected.append((field_key, rule))
            if len(selected) >= max_rules:
                break

        if not selected:
            return ""

        # Group selected rules back by field for rendering
        grouped: dict[str, list[dict]] = {}
        for field_key, rule in selected:
            grouped.setdefault(field_key, []).append(rule)

        lines = []
        for field_key in FIELD_ORDER:
            if field_key not in grouped:
                continue
            label = FIELD_LABELS[field_key]
            parts = []
            for rule in grouped[field_key]:
                rid = rule.get("id", "?")
                text = rule.get("text", "")
                parts.append(f"{text} [P-{rid}]")
            lines.append(f"{label}：{'；'.join(parts)}")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars]
        return result
```

- [ ] **Step 4: Register the model in __init__.py**

Add to `src/db/models/__init__.py`:

```python
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS
```

And add `"DoctorPersona", "EMPTY_PERSONA_FIELDS"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_persona_model.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/models/doctor_persona.py src/db/models/__init__.py tests/test_persona_model.py
git commit -m "feat(persona): add DoctorPersona model with structured JSON fields"
```

---

### Task 2: Persona CRUD

**Files:**
- Create: `src/db/crud/persona.py`

- [ ] **Step 1: Write CRUD tests**

```python
# tests/test_persona_crud.py
"""Tests for persona CRUD operations."""
import json
import pytest
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS

# These tests use the shared test DB fixture from conftest.py

@pytest.fixture
def sample_rule():
    return {"id": "ps_1", "text": "口语化回复", "source": "manual", "usage_count": 0}

def test_get_or_create_persona_creates_new():
    """get_or_create returns a new persona with empty fields for unknown doctor."""
    from db.crud.persona import get_or_create_persona_sync
    # Test the pure creation logic
    p = DoctorPersona(doctor_id="test_doc")
    assert p.fields == EMPTY_PERSONA_FIELDS()
    assert p.onboarded is False

def test_add_rule_to_field(sample_rule):
    """add_rule appends to the correct field."""
    from db.crud.persona import add_rule_to_persona
    p = DoctorPersona(doctor_id="test_doc")
    p.fields_json = json.dumps(EMPTY_PERSONA_FIELDS())
    updated = add_rule_to_persona(p, "reply_style", sample_rule)
    assert len(updated.fields["reply_style"]) == 1
    assert updated.fields["reply_style"][0]["text"] == "口语化回复"

def test_remove_rule_from_field(sample_rule):
    """remove_rule removes by rule id."""
    from db.crud.persona import add_rule_to_persona, remove_rule_from_persona
    p = DoctorPersona(doctor_id="test_doc")
    p.fields_json = json.dumps(EMPTY_PERSONA_FIELDS())
    add_rule_to_persona(p, "reply_style", sample_rule)
    updated = remove_rule_from_persona(p, "reply_style", "ps_1")
    assert len(updated.fields["reply_style"]) == 0

def test_generate_rule_id():
    """Rule IDs are unique and start with ps_."""
    from db.crud.persona import generate_rule_id
    ids = {generate_rule_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(rid.startswith("ps_") for rid in ids)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_persona_crud.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement CRUD**

```python
# src/db/crud/persona.py
"""CRUD operations for doctor_personas table."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS


def generate_rule_id() -> str:
    """Generate a unique rule ID like ps_abc123."""
    return f"ps_{uuid.uuid4().hex[:8]}"


async def get_or_create_persona(session: AsyncSession, doctor_id: str) -> DoctorPersona:
    """Get or lazily create a doctor's persona row."""
    result = await session.execute(
        select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    persona = DoctorPersona(doctor_id=doctor_id)
    session.add(persona)
    await session.flush()
    return persona


def add_rule_to_persona(
    persona: DoctorPersona,
    field: str,
    rule: dict,
) -> DoctorPersona:
    """Add a rule to a specific field. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    fields[field].append(rule)
    persona.fields = fields
    persona.version += 1
    return persona


def remove_rule_from_persona(
    persona: DoctorPersona,
    field: str,
    rule_id: str,
) -> DoctorPersona:
    """Remove a rule by ID from a field. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    fields[field] = [r for r in fields[field] if r.get("id") != rule_id]
    persona.fields = fields
    persona.version += 1
    return persona


def update_rule_in_persona(
    persona: DoctorPersona,
    field: str,
    rule_id: str,
    new_text: str,
) -> DoctorPersona:
    """Update a rule's text by ID. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    for rule in fields[field]:
        if rule.get("id") == rule_id:
            rule["text"] = new_text
            break
    persona.fields = fields
    persona.version += 1
    return persona


async def load_active_persona_text(session: AsyncSession, doctor_id: str) -> str:
    """Load the rendered persona text for prompt injection.

    Returns empty string if no persona exists or is not active.
    """
    result = await session.execute(
        select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
    )
    persona = result.scalar_one_or_none()
    if not persona or persona.status != "active":
        return ""
    return persona.render_for_prompt()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_persona_crud.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db/crud/persona.py tests/test_persona_crud.py
git commit -m "feat(persona): add persona CRUD with rule management"
```

---

### Task 3: Update LayerConfig + Prompt Composer

**Files:**
- Modify: `src/agent/prompt_config.py`
- Modify: `src/agent/prompt_composer.py`
- Modify: `src/domain/knowledge/knowledge_context.py`

- [ ] **Step 1: Write prompt composition test**

```python
# tests/test_prompt_composer_persona.py
"""Tests for prompt composition with structured persona."""
import json
import pytest
from agent.prompt_config import LayerConfig, FOLLOWUP_REPLY_LAYERS, DOCTOR_INTAKE_LAYERS

def test_followup_reply_has_load_persona_true():
    assert FOLLOWUP_REPLY_LAYERS.load_persona is True

def test_doctor_intake_has_load_persona_false():
    assert DOCTOR_INTAKE_LAYERS.load_persona is False

def test_layer_config_load_persona_default_false():
    lc = LayerConfig()
    assert lc.load_persona is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_prompt_composer_persona.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `AttributeError: ... has no attribute 'load_persona'`

- [ ] **Step 3: Add `load_persona` to LayerConfig**

In `src/agent/prompt_config.py`, add `load_persona: bool = False` to the `LayerConfig` dataclass, and set it per flow config:

```python
@dataclass(frozen=True)
class LayerConfig:
    system: bool = True
    domain: bool = False
    intent: str = "general"
    load_knowledge: bool = False
    load_persona: bool = False  # NEW: explicitly control persona loading
    patient_context: bool = False
    conversation_mode: bool = False

DOCTOR_INTAKE_LAYERS = LayerConfig(
    domain=False,
    intent="intake",
    load_knowledge=False,
    load_persona=False,  # structured extraction — no style
    patient_context=True,
    conversation_mode=True,
)

REVIEW_LAYERS = LayerConfig(
    domain=True,
    intent="diagnosis",
    load_knowledge=True,
    load_persona=True,  # narrative output — style matters
    patient_context=True,
)

FOLLOWUP_REPLY_LAYERS = LayerConfig(
    domain=True,
    intent="followup_reply",
    load_knowledge=True,
    load_persona=True,  # expression flow — style matters
    patient_context=True,
)

PATIENT_INTAKE_LAYERS = LayerConfig(
    domain=True,
    intent="patient-intake",
    load_knowledge=True,
    load_persona=False,  # structured extraction — no style
    patient_context=True,
    conversation_mode=True,
)
```

- [ ] **Step 4: Update `_load_doctor_knowledge` in prompt_composer.py**

Replace the persona loading logic to use `config.load_persona` and load from the new table:

```python
async def _load_doctor_knowledge(doctor_id: str, config: LayerConfig, query: str = "", patient_context: str = "") -> tuple:
    """Load doctor KB items and active persona. Returns (knowledge_text, persona_text)."""
    knowledge = ""
    persona = ""
    if not doctor_id:
        return knowledge, persona
    if config.load_knowledge:
        try:
            from domain.knowledge.doctor_knowledge import load_knowledge
            knowledge = await load_knowledge(doctor_id, query=query, patient_context=patient_context)
            log(f"[composer] KB loaded: {len(knowledge)} chars")
        except Exception as exc:
            log(f"[composer] KB load failed (non-fatal): {exc}", level="warning")
    if config.load_persona:
        try:
            from db.crud.persona import load_active_persona_text
            from db.engine import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                persona = await load_active_persona_text(session, doctor_id)
            if persona:
                log(f"[composer] persona loaded: {len(persona)} chars")
        except Exception as exc:
            log(f"[composer] persona load failed (non-fatal): {exc}", level="warning")
    return knowledge, persona
```

- [ ] **Step 5: Remove `load_active_persona` from knowledge_context.py**

Delete the `load_active_persona` function from `src/domain/knowledge/knowledge_context.py` (lines 134-153). It's replaced by `db.crud.persona.load_active_persona_text`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_prompt_composer_persona.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All existing tests pass

- [ ] **Step 8: Commit**

```bash
git add src/agent/prompt_config.py src/agent/prompt_composer.py src/domain/knowledge/knowledge_context.py tests/test_prompt_composer_persona.py
git commit -m "feat(persona): add load_persona flag to LayerConfig, load from new table"
```

---

### Task 4: Persona API Endpoints

**Files:**
- Create: `src/channels/web/doctor_dashboard/persona_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/knowledge_handlers.py`

- [ ] **Step 1: Create persona API handlers**

```python
# src/channels/web/doctor_dashboard/persona_handlers.py
"""Persona management API — separate from knowledge endpoints."""
from __future__ import annotations

import json
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.crud.persona import (
    get_or_create_persona,
    add_rule_to_persona,
    remove_rule_from_persona,
    update_rule_in_persona,
    generate_rule_id,
)
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/persona")
async def get_persona(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Get the doctor's persona with all fields and rules."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)
    await session.commit()

    return {
        "doctor_id": persona.doctor_id,
        "fields": persona.fields,
        "status": persona.status,
        "onboarded": persona.onboarded,
        "edit_count": persona.edit_count,
        "version": persona.version,
        "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
    }


class AddRuleRequest(BaseModel):
    field: str  # reply_style / closing / structure / avoid / edits
    text: str


@router.post("/api/manage/persona/rules")
async def add_rule(
    body: AddRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Add a new rule to a persona field."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "规则内容不能为空")
    if body.field not in ("reply_style", "closing", "structure", "avoid", "edits"):
        raise HTTPException(400, "无效的字段名")

    persona = await get_or_create_persona(session, resolved)
    rule = {"id": generate_rule_id(), "text": text, "source": "manual", "usage_count": 0}
    add_rule_to_persona(persona, body.field, rule)
    if persona.status == "draft":
        persona.status = "active"
    await session.commit()
    return {"status": "ok", "rule": rule}


class UpdateRuleRequest(BaseModel):
    field: str
    rule_id: str
    text: str


@router.put("/api/manage/persona/rules")
async def update_rule(
    body: UpdateRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Update a rule's text."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "规则内容不能为空")

    persona = await get_or_create_persona(session, resolved)
    update_rule_in_persona(persona, body.field, body.rule_id, text)
    await session.commit()
    return {"status": "ok"}


class DeleteRuleRequest(BaseModel):
    field: str
    rule_id: str


@router.delete("/api/manage/persona/rules")
async def delete_rule(
    body: DeleteRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Delete a rule from a persona field."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)
    remove_rule_from_persona(persona, body.field, body.rule_id)
    await session.commit()
    return {"status": "ok"}


class ActivateRequest(BaseModel):
    action: str  # "activate" or "deactivate"


@router.post("/api/manage/persona/activate")
async def activate_persona(
    body: ActivateRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Activate or deactivate the persona."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)

    if body.action == "activate":
        persona.status = "active"
    elif body.action == "deactivate":
        persona.status = "draft"
    else:
        raise HTTPException(400, "action must be 'activate' or 'deactivate'")

    await session.commit()
    return {"status": "ok", "persona_status": persona.status}
```

- [ ] **Step 2: Register the router**

Find where routers are registered (likely `src/channels/web/doctor_dashboard/__init__.py` or the main app file) and add:

```python
from channels.web.doctor_dashboard.persona_handlers import router as persona_router
app.include_router(persona_router)
```

- [ ] **Step 3: Remove persona from knowledge_handlers.py list_knowledge**

In `src/channels/web/doctor_dashboard/knowledge_handlers.py`, remove the persona loading block (lines 96-119). The `list_knowledge` endpoint should only return `{"items": result}` without the `persona` field.

Also remove the `confirm_persona` endpoint (lines 164-185) — replaced by persona_handlers.

- [ ] **Step 4: Run existing tests**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: PASS (knowledge tests should still work since we only removed the persona portion)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/doctor_dashboard/persona_handlers.py src/channels/web/doctor_dashboard/knowledge_handlers.py
git commit -m "feat(persona): add persona API endpoints, remove persona from knowledge API"
```

---

### Task 5: Remove Old Persona from KnowledgeCategory + Teaching

**Files:**
- Modify: `src/db/models/doctor.py`
- Modify: `src/domain/knowledge/teaching.py`

- [ ] **Step 1: Remove `persona`, `preference`, `communication` from KnowledgeCategory**

In `src/db/models/doctor.py`, update the enum:

```python
class KnowledgeCategory(str, Enum):
    custom = "custom"
    diagnosis = "diagnosis"
    followup = "followup"
    medication = "medication"
```

Remove `communication`, `preference`, and `persona`.

- [ ] **Step 2: Remove `persona_status` column from DoctorKnowledgeItem**

In `src/db/models/doctor.py`, remove line 40:

```python
    persona_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
```

Note: The column stays in the DB for now (no Alembic migrations). We just remove it from the ORM model. SQLAlchemy will ignore the extra DB column.

- [ ] **Step 3: Clean up teaching.py**

Remove from `src/domain/knowledge/teaching.py`:
- `PERSONA_TEMPLATE` constant (lines 123-130)
- `get_or_create_persona` function (lines 133-159)
- `_EXTRACTION_THRESHOLD` constant (line 163)
- `_check_persona_extraction` function (lines 166-188)
- `extract_persona` function (lines 191-249)

Keep:
- `should_prompt_teaching` function
- `log_doctor_edit` function
- `create_rule_from_edit` function — but update it to use `KnowledgeCategory.custom` instead of `KnowledgeCategory.preference`:

```python
    rule = await save_knowledge_item(
        session,
        doctor_id=doctor_id,
        text=row.edited_text,
        source="teaching",
        confidence=1.0,
        category=KnowledgeCategory.custom,
    )
```

- [ ] **Step 4: Update any imports of removed functions**

Search for all imports of `get_or_create_persona` from `teaching` and update to use `db.crud.persona.get_or_create_persona`:

```bash
grep -rn "from domain.knowledge.teaching import" src/
```

Update each reference.

- [ ] **Step 5: Run all tests**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/models/doctor.py src/domain/knowledge/teaching.py
git commit -m "refactor(persona): remove persona from KnowledgeCategory, clean up teaching.py"
```

---

### Task 6: Migration Script

**Files:**
- Create: `src/scripts/migrate_persona.py`

- [ ] **Step 1: Write the migration script**

```python
# src/scripts/migrate_persona.py
"""One-shot migration: move persona data from doctor_knowledge_items to doctor_personas.

Usage: python -m scripts.migrate_persona [--dry-run]

1. Creates the doctor_personas table if it doesn't exist.
2. For each doctor_knowledge_items row with category='persona':
   - Parses the 5-field text format into structured JSON rules
   - Creates a DoctorPersona row with those rules
3. Migrates 'preference' and 'communication' KB items to 'custom'.
4. Does NOT delete the old rows (safe migration — old code can still read them).
"""
import asyncio
import json
import re
import sys

from db.engine import engine, AsyncSessionLocal
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS
from db.crud.persona import generate_rule_id
from sqlalchemy import text, select


FIELD_LABELS = {
    "回复风格": "reply_style",
    "常用结尾语": "closing",
    "回复结构": "structure",
    "回避内容": "avoid",
    "常见修改": "edits",
}


def parse_persona_text(content: str) -> dict:
    """Parse old-format persona text into structured rules."""
    fields = EMPTY_PERSONA_FIELDS()
    if not content:
        return fields

    for label, field_key in FIELD_LABELS.items():
        pattern = re.compile(rf"{label}[：:]\s*(.*)", re.MULTILINE)
        match = pattern.search(content)
        if match:
            value = match.group(1).strip()
            if value and value != "（待学习）":
                fields[field_key].append({
                    "id": generate_rule_id(),
                    "text": value,
                    "source": "migrated",
                    "usage_count": 0,
                })

    return fields


async def migrate(dry_run: bool = False):
    """Run the migration."""
    # Create table if needed
    async with engine.begin() as conn:
        await conn.run_sync(DoctorPersona.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 1. Migrate persona items
        rows = (await session.execute(
            text("SELECT doctor_id, content, persona_status FROM doctor_knowledge_items WHERE category = 'persona'")
        )).fetchall()

        print(f"Found {len(rows)} persona items to migrate")
        for row in rows:
            doctor_id, content, status = row
            fields = parse_persona_text(content)
            has_rules = any(len(v) > 0 for v in fields.values())

            if dry_run:
                print(f"  [DRY RUN] {doctor_id}: status={status}, rules={sum(len(v) for v in fields.values())}")
                continue

            # Check if persona already exists
            existing = (await session.execute(
                select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
            )).scalar_one_or_none()

            if existing:
                print(f"  SKIP {doctor_id}: persona already exists")
                continue

            persona = DoctorPersona(
                doctor_id=doctor_id,
                status="active" if status == "active" and has_rules else "draft",
                onboarded=has_rules,
                edit_count=0,
            )
            persona.fields = fields
            session.add(persona)
            print(f"  MIGRATED {doctor_id}: status={persona.status}, rules={sum(len(v) for v in fields.values())}")

        # 2. Migrate preference/communication items to custom
        if not dry_run:
            result = await session.execute(
                text("UPDATE doctor_knowledge_items SET category = 'custom' WHERE category IN ('preference', 'communication')")
            )
            print(f"Migrated {result.rowcount} preference/communication items to custom")

        if not dry_run:
            await session.commit()
            print("Migration complete.")
        else:
            print("[DRY RUN] No changes made.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry_run))
```

- [ ] **Step 2: Test with dry run**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && ENVIRONMENT=development .venv/bin/python -m scripts.migrate_persona --dry-run`
Expected: Lists persona items without making changes

- [ ] **Step 3: Commit**

```bash
git add src/scripts/migrate_persona.py
git commit -m "feat(persona): add migration script from old persona to new table"
```

---

### Task 7: Frontend — API + Query Hooks

**Files:**
- Modify: `frontend/web/src/api.js`
- Modify: `frontend/web/src/lib/queryKeys.js`
- Modify: `frontend/web/src/lib/doctorQueries.js`

- [ ] **Step 1: Add persona API functions to api.js**

Add after the `updateDoctorProfile` function (around line 612):

```javascript
export async function getPersona(doctorId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona?${qs.toString()}`);
}

export async function addPersonaRule(doctorId, field, text) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, text }),
  });
}

export async function updatePersonaRule(doctorId, field, ruleId, text) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, rule_id: ruleId, text }),
  });
}

export async function deletePersonaRule(doctorId, field, ruleId) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/rules?${qs.toString()}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, rule_id: ruleId }),
  });
}

export async function activatePersona(doctorId, action) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/persona/activate?${qs.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
}
```

- [ ] **Step 2: Add query key to queryKeys.js**

```javascript
persona: (did) => ["doctor", did, "persona"],
```

- [ ] **Step 3: Add usePersona hook to doctorQueries.js**

```javascript
export function usePersona() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.persona(doctorId),
    queryFn: () => api.getPersona(doctorId),
    enabled: !!doctorId,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api.js frontend/web/src/lib/queryKeys.js frontend/web/src/lib/doctorQueries.js
git commit -m "feat(persona): add persona API client and React Query hook"
```

---

### Task 8: Frontend — MyAI Page Split

**Files:**
- Modify: `frontend/web/src/pages/doctor/MyAIPage.jsx`

- [ ] **Step 1: Add persona import and data hook**

Add to imports:

```javascript
import { usePersona } from "../../lib/doctorQueries";
```

In the component, add:

```javascript
const { data: personaData, isLoading: pLoading } = usePersona();
```

Update `loading`:

```javascript
const loading = kLoading || qLoading || aLoading || pLoading;
```

- [ ] **Step 2: Replace the "我的知识库" section with two sections**

Replace section C (lines ~272-332) with:

```jsx
{/* ── C1. 我的AI人设 (Persona) ─────────────────────── */}
<Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", pr: 1.5 }}>
  <SectionLabel>
    <Box component="span">我的AI人设</Box>
    <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 1 }}>
      决定AI怎么说话
    </Typography>
  </SectionLabel>
  <Typography
    onClick={() => navigate(dp("settings/persona"))}
    sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
  >
    编辑 ›
  </Typography>
</Box>
<Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
  {pLoading && <SectionLoading />}
  {!pLoading && personaData && (() => {
    const allRules = Object.values(personaData.fields || {}).flat();
    const hasRules = allRules.length > 0;
    const previewText = hasRules
      ? allRules.slice(0, 3).map(r => r.text).join("；") + (allRules.length > 3 ? "…" : "")
      : "尚未设置，点击编辑开始配置";
    return (
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: hasRules ? COLOR.text2 : COLOR.text4, lineHeight: 1.7 }}>
          {previewText}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 1 }}>
          已学习 {personaData.edit_count || 0} 次编辑
        </Typography>
      </Box>
    );
  })()}
</Box>

{/* ── C2. 我的知识库 (Knowledge) ───────────────────── */}
<Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", pr: 1.5 }}>
  <SectionLabel>
    <Box component="span">我的知识库</Box>
    <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 1 }}>
      决定AI知道什么
    </Typography>
  </SectionLabel>
  {knowledgeList.length > 0 && (
    <Typography
      onClick={() => navigate(dp("settings/knowledge"))}
      sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer" }}
    >
      全部 {knowledgeList.length} 条 ›
    </Typography>
  )}
</Box>
<Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
  {knowledgeList.length === 0 && !loading && (
    <>
      <ListCard
        avatar={<IconBadge config={ICON_BADGES.upload} />}
        title="上传指南"
        subtitle="PDF / Word 文档"
        onClick={() => navigate(dp("settings/knowledge/add"))}
        chevron
      />
      <ListCard
        avatar={<IconBadge config={ICON_BADGES.new_record} />}
        title="粘贴常用回复"
        subtitle="你常用的回复模板"
        onClick={() => navigate(dp("settings/knowledge/add"))}
        chevron
        sx={{ borderBottom: "none" }}
      />
    </>
  )}
  {loading && knowledgeList.length === 0 && <SectionLoading />}
  {knowledgeList.slice(0, 3).map((rule, idx) => (
    <KnowledgeCard
      key={rule.id || idx}
      title={rule.title || rule.text?.slice(0, 20) || "规则"}
      summary={rule.summary || rule.text?.slice(0, 40) || ""}
      referenceCount={rule.reference_count || 0}
      source={rule.source}
      date={rule.created_at ? formatRelativeDate(rule.created_at) : ""}
      onClick={() => navigate(`${dp("settings/knowledge")}/${rule.id}`)}
      sx={idx === Math.min(knowledgeList.length, 3) - 1 ? { borderBottom: "none" } : {}}
    />
  ))}
</Box>
```

- [ ] **Step 3: Remove persona from knowledge count and topRules**

Remove the `knowledgePersona` variable and the logic that prepends persona to `topRules` (lines 130-138). Knowledge count should only count knowledge items, not persona:

```javascript
const knowledgeCount = knowledgeList.length;
```

- [ ] **Step 4: Update the hero subtitle**

Change "已学会 X 条知识" to only count knowledge:

```javascript
<Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5 }}>
  {knowledgeCount > 0 ? `已学会 ${knowledgeCount} 条知识` : "尚未添加知识"}
</Typography>
```

- [ ] **Step 5: Update CTA buttons**

Replace the CTA row (lines 215-229):

```jsx
<Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5 }}>
  <AppButton
    variant="primary" size="md" fullWidth
    onClick={() => navigate(dp("settings/persona"))}
  >
    编辑人设
  </AppButton>
  <AppButton
    variant="secondary" size="md" fullWidth
    onClick={() => navigate(dp("settings/knowledge/add"))}
    sx={{ border: `0.5px solid ${COLOR.border}` }}
  >
    添加知识
  </AppButton>
</Box>
```

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/pages/doctor/MyAIPage.jsx
git commit -m "feat(persona): split MyAI page into persona + knowledge sections"
```

---

### Task 9: Frontend — PersonaSubpage

**Files:**
- Create: `frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx`
- Modify: `frontend/web/src/pages/doctor/SettingsPage.jsx` (add route)

- [ ] **Step 1: Create PersonaSubpage**

```jsx
// frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx
/**
 * PersonaSubpage -- detail view for the doctor's AI persona.
 *
 * Shows structured persona rules grouped by field, each individually
 * editable and deletable. Bottom entry point for "教AI新偏好".
 *
 * @see /doctor/settings/persona
 */
import { useCallback, useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { TYPE, COLOR, RADIUS, ICON } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLabel from "../../../components/SectionLabel";
import SectionLoading from "../../../components/SectionLoading";
import EmptyState from "../../../components/EmptyState";
import SheetDialog from "../../../components/SheetDialog";
import DialogFooter from "../../../components/DialogFooter";
import ConfirmDialog from "../../../components/ConfirmDialog";
import StatColumn from "../../../components/StatColumn";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { usePersona } from "../../../lib/doctorQueries";

const FIELD_CONFIG = [
  { key: "reply_style", label: "回复风格", hint: "例：口语化回复，像微信聊天" },
  { key: "closing", label: "常用结尾语", hint: "例：有问题随时联系我" },
  { key: "structure", label: "回复结构", hint: "例：先给结论再简短解释" },
  { key: "avoid", label: "回避内容", hint: "例：不主动展开罕见风险" },
  { key: "edits", label: "常见修改", hint: "例：把建议改成直接指令" },
];

const SOURCE_LABELS = {
  manual: "手动",
  onboarding: "引导",
  edit: "学习",
  teach: "示例",
  migrated: "迁移",
};

export default function PersonaSubpage({ doctorId, onBack, isMobile }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const { data: persona, isLoading } = usePersona();

  const [addOpen, setAddOpen] = useState(false);
  const [addField, setAddField] = useState("");
  const [addText, setAddText] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editField, setEditField] = useState("");
  const [editRuleId, setEditRuleId] = useState("");
  const [editText, setEditText] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteField, setDeleteField] = useState("");
  const [deleteRuleId, setDeleteRuleId] = useState("");
  const [saving, setSaving] = useState(false);

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
  }, [queryClient, doctorId]);

  async function handleAdd() {
    if (!addText.trim()) return;
    setSaving(true);
    try {
      await api.addPersonaRule(doctorId, addField, addText.trim());
      invalidate();
      setAddOpen(false);
      setAddText("");
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit() {
    if (!editText.trim()) return;
    setSaving(true);
    try {
      await api.updatePersonaRule(doctorId, editField, editRuleId, editText.trim());
      invalidate();
      setEditOpen(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setSaving(true);
    try {
      await api.deletePersonaRule(doctorId, deleteField, deleteRuleId);
      invalidate();
      setDeleteOpen(false);
    } finally {
      setSaving(false);
    }
  }

  const fields = persona?.fields || {};
  const totalRules = Object.values(fields).flat().length;

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {isLoading && <SectionLoading />}

      {!isLoading && (
        <>
          {FIELD_CONFIG.map((fc) => {
            const rules = fields[fc.key] || [];
            return (
              <Box key={fc.key}>
                <Box sx={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  px: 2, pt: 2, pb: 0.5,
                }}>
                  <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
                    {fc.label}
                  </Typography>
                  <Box
                    onClick={() => { setAddField(fc.key); setAddText(""); setAddOpen(true); }}
                    sx={{ display: "flex", alignItems: "center", gap: 0.25, cursor: "pointer", "&:active": { opacity: 0.6 } }}
                  >
                    <AddCircleOutlineIcon sx={{ fontSize: ICON.sm, color: COLOR.primary }} />
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary }}>添加</Typography>
                  </Box>
                </Box>

                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {rules.length === 0 && (
                    <Box sx={{ px: 2, py: 1.5 }}>
                      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
                        {fc.hint}
                      </Typography>
                    </Box>
                  )}
                  {rules.map((rule, idx) => (
                    <Box key={rule.id} sx={{
                      display: "flex", alignItems: "flex-start", gap: 1, px: 2, py: 1.5,
                      borderBottom: idx < rules.length - 1 ? `0.5px solid ${COLOR.borderLight}` : "none",
                    }}>
                      <Box sx={{ flex: 1 }}>
                        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.6 }}>
                          {rule.text}
                        </Typography>
                        <Box sx={{ display: "flex", gap: 1, mt: 0.5 }}>
                          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                            {SOURCE_LABELS[rule.source] || rule.source}
                          </Typography>
                          {rule.usage_count > 0 && (
                            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                              引用 {rule.usage_count} 次
                            </Typography>
                          )}
                        </Box>
                      </Box>
                      <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0, mt: 0.5 }}>
                        <EditOutlinedIcon
                          onClick={() => {
                            setEditField(fc.key);
                            setEditRuleId(rule.id);
                            setEditText(rule.text);
                            setEditOpen(true);
                          }}
                          sx={{ fontSize: ICON.sm, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}
                        />
                        <DeleteOutlineIcon
                          onClick={() => {
                            setDeleteField(fc.key);
                            setDeleteRuleId(rule.id);
                            setDeleteOpen(true);
                          }}
                          sx={{ fontSize: ICON.sm, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}
                        />
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            );
          })}

          {/* Stats */}
          <Box sx={{ bgcolor: COLOR.white, mt: 1, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            <Box sx={{ display: "flex", py: 1.5, px: 2 }}>
              <StatColumn value={totalRules} label="规则数" />
              <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
              <StatColumn value={persona?.edit_count || 0} label="已学习编辑" />
            </Box>
          </Box>

          <Box sx={{ height: 40 }} />
        </>
      )}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="我的AI人设"
        onBack={onBack}
        isMobile={isMobile}
        listPane={listContent}
      />

      {/* Add rule dialog */}
      <SheetDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title={`添加${FIELD_CONFIG.find(f => f.key === addField)?.label || "规则"}`}
        desktopMaxWidth={480}
        mobileMaxHeight="60vh"
        footer={
          <DialogFooter
            onCancel={() => setAddOpen(false)}
            onConfirm={handleAdd}
            confirmLabel="添加"
            confirmDisabled={!addText.trim() || saving}
            confirmLoading={saving}
          />
        }
      >
        <TextField
          fullWidth
          multiline
          minRows={2}
          maxRows={4}
          size="small"
          placeholder={FIELD_CONFIG.find(f => f.key === addField)?.hint || ""}
          value={addText}
          onChange={(e) => setAddText(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
      </SheetDialog>

      {/* Edit rule dialog */}
      <SheetDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="编辑规则"
        desktopMaxWidth={480}
        mobileMaxHeight="60vh"
        footer={
          <DialogFooter
            onCancel={() => setEditOpen(false)}
            onConfirm={handleEdit}
            confirmLabel="保存"
            confirmDisabled={!editText.trim() || saving}
            confirmLoading={saving}
          />
        }
      >
        <TextField
          fullWidth
          multiline
          minRows={2}
          maxRows={4}
          size="small"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
      </SheetDialog>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title="确认删除"
        message="删除后该规则将不再影响AI行为，确定要删除吗？"
        cancelLabel="保留"
        confirmLabel="删除"
        confirmTone="danger"
      />
    </>
  );
}
```

- [ ] **Step 2: Add route for PersonaSubpage**

In `src/pages/doctor/SettingsPage.jsx`, add the persona subpage route alongside the existing knowledge routes. Find where knowledge detail is routed and add a parallel route for `settings/persona` that renders `PersonaSubpage`.

- [ ] **Step 3: Verify the app builds**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx frontend/web/src/pages/doctor/SettingsPage.jsx frontend/web/src/pages/doctor/MyAIPage.jsx
git commit -m "feat(persona): add PersonaSubpage, split MyAI page into persona + knowledge"
```

---

### Task 10: Integration Verification

- [ ] **Step 1: Run all backend tests**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All tests pass

- [ ] **Step 2: Run frontend build**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build`
Expected: Build succeeds

- [ ] **Step 3: Run the migration (if dev DB has data)**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && ENVIRONMENT=development .venv/bin/python -m scripts.migrate_persona`
Expected: Migration completes, persona data moved

- [ ] **Step 4: Start dev server and verify manually**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && ./dev.sh`
Verify:
- MyAI page shows two separate sections (人设 + 知识库)
- Persona subpage shows 5 field groups
- Can add/edit/delete individual rules
- Knowledge list no longer includes persona card
- Prompt composition still works (test a follow-up reply)

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(persona): integration fixes for phase 1"
```
