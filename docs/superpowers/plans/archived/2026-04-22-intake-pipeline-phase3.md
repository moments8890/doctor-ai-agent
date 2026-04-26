# Intake Pipeline Extensibility — Phase 3 (First Form Template)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `form_satisfaction_v1` — the first non-medical template — end-to-end. Proves the Phase 1/2 seams hold for a template whose `kind="form"`, stores to `form_responses` (not `medical_records`), has no diagnosis hook, and uses a different prompt composition path than the medical flow.

**Architecture:** New `src/domain/intake/templates/form_satisfaction.py` with `FormSatisfactionTemplate`, `FormSatisfactionExtractor`, and `FormResponseWriter` (can share the writer with any `kind="form"` template). Prompt composition bypasses `prompt_composer` entirely — forms don't need doctor persona / KB layers, just a structured Q&A prompt. Two new REST endpoints (`GET /api/form_responses/{id}`, `GET /api/patients/{id}/form_responses`) serve the read path. Backend only — frontend UI is a separate effort.

**Tech Stack:** Pydantic 2.x, SQLAlchemy async, FastAPI.

**Reference:** Spec §6a Phase 3 row, §4e (read-back endpoints), §7e (new-template gate).

---

## Preconditions

- Phase 2 landed (7 commits, ending at `078e310b`).
- 477/477 tests pass.
- Alembic head: `c9f8d2e14a20` (unchanged — `form_responses` table already exists from Phase 0).
- `GeneralMedicalTemplate` is fully declarative (Task 4 of Phase 2).

## Behavior-preservation bar

- Full test suite matches post-Phase-2 baseline (477 passed).
- No change to `medical_general_v1` behavior (verified by the existing ~80 Phase 1/2 tests).
- New tests exclusively cover the form template + new endpoints.

## File map

**Create:**
- `src/domain/intake/writers.py` — `FormResponseWriter` (reusable across any `kind="form"` template).
- `src/domain/intake/templates/form_satisfaction.py` — `FormSatisfactionTemplate`, `FormSatisfactionExtractor`, `FORM_SATISFACTION_FIELDS`.
- `src/channels/web/form_responses.py` — GET endpoints for form responses.
- `tests/core/test_form_satisfaction_fields.py`
- `tests/core/test_form_satisfaction_extractor.py`
- `tests/core/test_form_response_writer.py`
- `tests/core/test_form_satisfaction_template.py`
- `tests/channels/test_form_responses_api.py`

**Modify:**
- `src/domain/intake/templates/__init__.py` — register `form_satisfaction_v1` in `TEMPLATES`.
- `src/main.py` (or wherever FastAPI mounts routers) — include the new `form_responses` router.

---

## Task 1: `FormSatisfactionExtractor` + `FORM_SATISFACTION_FIELDS`

**Files:**
- Create: `src/domain/intake/templates/form_satisfaction.py` (partial — extractor only)
- Create: `tests/core/test_form_satisfaction_fields.py`
- Create: `tests/core/test_form_satisfaction_extractor.py`

Satisfaction survey has 5 fields:
- `overall_rating` (enum: "非常满意", "满意", "一般", "不满意", "非常不满意") — required.
- `wait_time_rating` (enum: "很快", "合理", "偏长", "很长") — recommended.
- `doctor_rating` (enum: "非常满意", "满意", "一般", "不满意", "非常不满意") — recommended.
- `recommend` (enum: "一定会", "可能会", "不太会", "不会") — recommended.
- `comments` (text) — optional.

- [ ] **Step 1: Write failing tests**

`tests/core/test_form_satisfaction_fields.py`:

```python
"""FORM_SATISFACTION_FIELDS — 5 declarative fields for the satisfaction survey."""
from __future__ import annotations

from domain.intake.protocols import FieldSpec
from domain.intake.templates.form_satisfaction import FORM_SATISFACTION_FIELDS


def test_has_five_fields():
    assert len(FORM_SATISFACTION_FIELDS) == 5


def test_overall_rating_is_required_enum():
    spec = next(s for s in FORM_SATISFACTION_FIELDS if s.name == "overall_rating")
    assert spec.tier == "required"
    assert spec.type == "enum"
    assert spec.enum_values is not None
    assert "非常满意" in spec.enum_values
    assert "非常不满意" in spec.enum_values


def test_comments_is_optional_text():
    spec = next(s for s in FORM_SATISFACTION_FIELDS if s.name == "comments")
    assert spec.tier == "optional"
    assert spec.type == "text"
    assert spec.appendable is False  # single-turn response


def test_no_carry_forward():
    # Form templates shouldn't carry forward from prior records
    for spec in FORM_SATISFACTION_FIELDS:
        assert spec.carry_forward_modes == frozenset()


def test_all_fields_have_labels_and_descriptions():
    for spec in FORM_SATISFACTION_FIELDS:
        assert spec.label, f"{spec.name}: label required"
        assert spec.description, f"{spec.name}: description required"
```

`tests/core/test_form_satisfaction_extractor.py`:

```python
"""FormSatisfactionExtractor — implements FieldExtractor for a form template."""
from __future__ import annotations

import pytest

from domain.intake.protocols import CompletenessState, SessionState
from domain.intake.templates.form_satisfaction import (
    FormSatisfactionExtractor, FORM_SATISFACTION_FIELDS,
)


@pytest.fixture
def extractor():
    return FormSatisfactionExtractor()


def test_fields_returns_form_fields(extractor):
    assert extractor.fields() is FORM_SATISFACTION_FIELDS


def test_completeness_empty_not_complete(extractor):
    state = extractor.completeness({}, "patient")
    assert state.can_complete is False
    assert "overall_rating" in state.required_missing


def test_completeness_with_required_set(extractor):
    state = extractor.completeness({"overall_rating": "满意"}, "patient")
    assert state.can_complete is True


def test_merge_simple_overwrite(extractor):
    collected = {"overall_rating": "满意"}
    extractor.merge(collected, {"overall_rating": "非常满意"})
    assert collected["overall_rating"] == "非常满意"


def test_merge_ignores_unknown(extractor):
    collected = {}
    extractor.merge(collected, {"not_a_form_field": "x"})
    assert "not_a_form_field" not in collected


def test_next_phase_returns_single_phase(extractor):
    session = SessionState(
        id="s", doctor_id="d", patient_id=1, mode="patient",
        status="active", template_id="form_satisfaction_v1",
        collected={}, conversation=[], turn_count=0,
    )
    assert extractor.next_phase(session, ["default"]) == "default"


@pytest.mark.asyncio
async def test_prompt_partial_returns_messages(extractor):
    """Form templates produce a simple structured survey prompt directly,
    without going through prompt_composer (no doctor persona / KB needed)."""
    result = await extractor.prompt_partial(
        collected={}, history=[], phase="default", mode="patient",
    )
    assert isinstance(result, list)
    assert len(result) >= 1
    # At least one message should describe the survey
    joined = "\n".join(m.get("content", "") for m in result)
    assert "满意" in joined  # mentions satisfaction-related content
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_form_satisfaction_fields.py \
    tests/core/test_form_satisfaction_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 3: Create the template file (extractor only)**

`src/domain/intake/templates/form_satisfaction.py`:

```python
"""Patient satisfaction survey — first non-medical template (kind="form").

Proves the Phase 1/2 seams hold for templates that don't go through the
medical prompt_composer path and persist to form_responses instead of
medical_records.
"""
from __future__ import annotations

from typing import Any

from domain.intake.protocols import (
    CompletenessState, FieldSpec, Mode, Phase, SessionState,
)

# ---- field specs -----------------------------------------------------------

_RATING_FIVE = ("非常满意", "满意", "一般", "不满意", "非常不满意")
_WAIT_RATING = ("很快", "合理", "偏长", "很长")
_RECOMMEND = ("一定会", "可能会", "不太会", "不会")


FORM_SATISFACTION_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="overall_rating", type="enum", tier="required", appendable=False,
        enum_values=_RATING_FIVE,
        label="总体满意度",
        description="本次就诊整体满意度",
    ),
    FieldSpec(
        name="wait_time_rating", type="enum", tier="recommended", appendable=False,
        enum_values=_WAIT_RATING,
        label="等待时间",
        description="候诊时间是否合理",
    ),
    FieldSpec(
        name="doctor_rating", type="enum", tier="recommended", appendable=False,
        enum_values=_RATING_FIVE,
        label="医生服务",
        description="医生沟通与诊疗满意度",
    ),
    FieldSpec(
        name="recommend", type="enum", tier="recommended", appendable=False,
        enum_values=_RECOMMEND,
        label="推荐意愿",
        description="是否愿意向家人朋友推荐",
    ),
    FieldSpec(
        name="comments", type="text", tier="optional", appendable=False,
        label="补充说明",
        description="其他建议或具体反馈（可选）",
    ),
]


# ---- extractor -------------------------------------------------------------

class FormSatisfactionExtractor:
    """FieldExtractor for the satisfaction survey.

    Form extractors don't use prompt_composer — they produce a minimal
    survey-style message list directly. Medical layers (doctor persona, KB,
    patient context) are not loaded.
    """

    def fields(self) -> list[FieldSpec]:
        return FORM_SATISFACTION_FIELDS

    async def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
        **_unused: Any,
    ) -> list[dict[str, str]]:
        """Return a two-message prompt: a system message describing the
        survey, and a user message listing the current state + next question.
        """
        system_lines = [
            "你是满意度调查助手，帮助医院收集患者就诊反馈。",
            "请用友好、简短的中文提问。每次只问1-2个问题。",
            "已有答案不要重复问。当所有必答题回答完毕，确认提交。",
            "",
            "调查问题：",
        ]
        for spec in FORM_SATISFACTION_FIELDS:
            label = spec.label or spec.name
            options = (
                " / ".join(spec.enum_values)
                if spec.enum_values else "（开放回答）"
            )
            tier_hint = {
                "required": "必答",
                "recommended": "建议回答",
                "optional": "可选",
            }.get(spec.tier, "")
            system_lines.append(f"- {label}（{tier_hint}）：{options}")

        missing = [
            s.label or s.name
            for s in FORM_SATISFACTION_FIELDS
            if not collected.get(s.name)
        ]
        user_lines = [
            f"已收集：{collected}",
            f"还未回答：{', '.join(missing) if missing else '无'}",
        ]

        return [
            {"role": "system", "content": "\n".join(system_lines)},
            {"role": "user", "content": "\n".join(user_lines)},
        ]

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        """Form fields are single-answer; always overwrite on update."""
        _fields_by_name = {f.name: f for f in self.fields()}
        for name, value in extracted.items():
            if name not in _fields_by_name:
                continue
            if not value:
                continue
            value = value.strip() if isinstance(value, str) else value
            if value:
                collected[name] = value
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        specs = self.fields()
        required = [s.name for s in specs if s.tier == "required"]
        recommended = [s.name for s in specs if s.tier == "recommended"]
        optional = [s.name for s in specs if s.tier == "optional"]

        required_missing = [f for f in required if not collected.get(f)]
        recommended_missing = [f for f in recommended if not collected.get(f)]
        optional_missing = [f for f in optional if not collected.get(f)]

        next_focus: str | None = None
        if recommended_missing:
            next_focus = recommended_missing[0]
        elif optional_missing:
            next_focus = optional_missing[0]

        return CompletenessState(
            can_complete=len(required_missing) == 0,
            required_missing=required_missing,
            recommended_missing=recommended_missing,
            optional_missing=optional_missing,
            next_focus=next_focus,
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        return phases[0]
```

- [ ] **Step 4: Run, expect all tests pass**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_form_satisfaction_fields.py \
    tests/core/test_form_satisfaction_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Target: 12 passed.

- [ ] **Step 5: Commit**

```
git add src/domain/intake/templates/form_satisfaction.py \
        tests/core/test_form_satisfaction_fields.py \
        tests/core/test_form_satisfaction_extractor.py
git commit -m "feat(intake): add FormSatisfactionExtractor + field specs"
```

---

## Task 2: `FormResponseWriter`

**Files:**
- Create: `src/domain/intake/writers.py`
- Create: `tests/core/test_form_response_writer.py`

A reusable writer for any template with `kind="form"`. Inserts into `form_responses` table (already exists from Phase 0). Returns `PersistRef(kind="form_response", id=...)`.

- [ ] **Step 1: Write failing tests**

`tests/core/test_form_response_writer.py`:

```python
"""FormResponseWriter — persists form template output to form_responses."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient
from domain.intake.protocols import PersistRef, SessionState
from domain.intake.writers import FormResponseWriter


def _session(doctor_id, patient_id, template_id="form_satisfaction_v1"):
    return SessionState(
        id=f"s_{uuid.uuid4().hex[:8]}",
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode="patient",
        status="active",
        template_id=template_id,
        collected={},
        conversation=[],
        turn_count=1,
    )


@pytest.mark.asyncio
async def test_persist_inserts_form_response_row():
    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="张三")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doc_id, pid)
    collected = {
        "overall_rating": "满意",
        "doctor_rating": "非常满意",
        "comments": "医生很耐心",
    }
    ref = await writer.persist(session, collected)

    assert isinstance(ref, PersistRef)
    assert ref.kind == "form_response"

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.id == ref.id)
        )).scalar_one()
    assert row.doctor_id == doc_id
    assert row.patient_id == pid
    assert row.template_id == "form_satisfaction_v1"
    assert row.payload["overall_rating"] == "满意"
    assert row.payload["comments"] == "医生很耐心"
    assert row.status == "draft"  # server_default


@pytest.mark.asyncio
async def test_persist_links_session_id():
    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="李四")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doc_id, pid)
    ref = await writer.persist(session, {"overall_rating": "一般"})

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.id == ref.id)
        )).scalar_one()
    assert row.session_id == session.id


@pytest.mark.asyncio
async def test_persist_requires_patient_id():
    """FormResponseDB.patient_id is NOT NULL — writer must raise if session
    has no patient. (Form templates expect pre-authenticated patients.)"""
    from fastapi import HTTPException

    writer = FormResponseWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doc_id, None)
    with pytest.raises(HTTPException) as excinfo:
        await writer.persist(session, {"overall_rating": "满意"})
    assert excinfo.value.status_code == 422
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement `FormResponseWriter`**

`src/domain/intake/writers.py`:

```python
"""Shared writers for intake templates.

Form templates all persist to the form_responses table — share one writer
across any template with kind="form". Medical templates have their own
writer (MedicalRecordWriter) with specialty-specific column mapping.
"""
from __future__ import annotations

from fastapi import HTTPException

from db.engine import AsyncSessionLocal
from db.crud.doctor import _ensure_doctor_exists
from db.models.form_response import FormResponseDB
from domain.intake.protocols import PersistRef, SessionState


class FormResponseWriter:
    """Persists to form_responses. Reusable across any kind="form" template."""

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef:
        if session.patient_id is None:
            raise HTTPException(
                status_code=422,
                detail="无法提交表单：缺少 patient_id（表单模板要求已认证患者）",
            )

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            row = FormResponseDB(
                doctor_id=session.doctor_id,
                patient_id=session.patient_id,
                template_id=session.template_id,
                session_id=session.id,
                payload=dict(collected),
                # status defaults to "draft" via server_default
            )
            db.add(row)
            await db.commit()
            row_id = row.id

        return PersistRef(kind="form_response", id=row_id)
```

- [ ] **Step 4: Run, expect 3 passed**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/writers.py \
        tests/core/test_form_response_writer.py
git commit -m "feat(intake): add FormResponseWriter — persists to form_responses"
```

---

## Task 3: `FormSatisfactionTemplate` + registry

**Files:**
- Modify: `src/domain/intake/templates/form_satisfaction.py` (append template binding)
- Modify: `src/domain/intake/templates/__init__.py` (register)
- Create: `tests/core/test_form_satisfaction_template.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_form_satisfaction_template.py`:

```python
"""FormSatisfactionTemplate — bindings + registry entry."""
from __future__ import annotations

import pytest

from domain.intake.templates import TEMPLATES, get_template
from domain.intake.templates.form_satisfaction import (
    FormSatisfactionExtractor, FormSatisfactionTemplate,
)
from domain.intake.writers import FormResponseWriter


def test_form_satisfaction_v1_registered():
    t = get_template("form_satisfaction_v1")
    assert isinstance(t, FormSatisfactionTemplate)


def test_kind_is_form_not_medical():
    t = get_template("form_satisfaction_v1")
    assert t.kind == "form"


def test_does_not_require_doctor_review():
    t = get_template("form_satisfaction_v1")
    assert t.requires_doctor_review is False


def test_supported_modes_is_patient_only():
    t = get_template("form_satisfaction_v1")
    assert t.supported_modes == ("patient",)


def test_wires_form_response_writer():
    t = get_template("form_satisfaction_v1")
    assert isinstance(t.writer, FormResponseWriter)


def test_no_batch_extractor():
    """Forms don't need pre-finalize re-extraction — the per-turn collected
    dict is authoritative."""
    t = get_template("form_satisfaction_v1")
    assert t.batch_extractor is None


def test_post_confirm_hooks_are_empty():
    """No diagnosis, no doctor notify — form just records the response."""
    t = get_template("form_satisfaction_v1")
    assert t.post_confirm_hooks["patient"] == []


def test_registry_contains_both_templates():
    assert "medical_general_v1" in TEMPLATES
    assert "form_satisfaction_v1" in TEMPLATES
    assert len(TEMPLATES) == 2
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Append `FormSatisfactionTemplate` to `form_satisfaction.py`**

Append to `src/domain/intake/templates/form_satisfaction.py`:

```python
# ---- template binding ------------------------------------------------------

from dataclasses import dataclass, field

from domain.intake.protocols import (
    BatchExtractor, EngineConfig, FieldExtractor, PostConfirmHook, Template,
    Writer,
)
from domain.intake.writers import FormResponseWriter


@dataclass
class FormSatisfactionTemplate:
    """form_satisfaction_v1 — patient satisfaction survey."""
    id: str = "form_satisfaction_v1"
    kind: str = "form"
    display_name: str = "患者满意度调查"
    requires_doctor_review: bool = False
    supported_modes: tuple[Mode, ...] = ("patient",)
    extractor: FieldExtractor = field(default_factory=FormSatisfactionExtractor)
    batch_extractor: BatchExtractor | None = None
    writer: Writer = field(default_factory=FormResponseWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {"patient": []}
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=10,
        phases={"patient": ["default"]},
    ))
```

- [ ] **Step 4: Register in `TEMPLATES`**

Modify `src/domain/intake/templates/__init__.py`:

```python
"""Template registry. Populated on import."""
from __future__ import annotations

from domain.intake.protocols import Template
from domain.intake.templates.medical_general import GeneralMedicalTemplate
from domain.intake.templates.form_satisfaction import FormSatisfactionTemplate


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
```

- [ ] **Step 5: Run, expect 8 passed. Also ensure existing `test_template_registry.py` still passes — its `test_registry_is_dict_of_exactly_one_template_phase1` test will now FAIL because there are 2 templates.**

Flip that test:

```python
def test_registry_contains_medical_and_form_templates():
    """Phase 3 added form_satisfaction_v1 alongside medical_general_v1."""
    assert set(TEMPLATES.keys()) == {"medical_general_v1", "form_satisfaction_v1"}
```

- [ ] **Step 6: Commit**

```
git add src/domain/intake/templates/form_satisfaction.py \
        src/domain/intake/templates/__init__.py \
        tests/core/test_form_satisfaction_template.py \
        tests/core/test_template_registry.py
git commit -m "feat(intake): register FormSatisfactionTemplate as form_satisfaction_v1"
```

---

## Task 4: Form response read endpoints

**Files:**
- Create: `src/channels/web/form_responses.py`
- Modify: `src/main.py` (or wherever routers are included)
- Create: `tests/channels/test_form_responses_api.py`

Two endpoints:
- `GET /api/form_responses/{id}` — detail, ownership-gated on doctor_id from auth.
- `GET /api/patients/{patient_id}/form_responses?template_id=...` — list for a patient, ownership-gated.

- [ ] **Step 1: Write failing tests**

`tests/channels/test_form_responses_api.py`:

```python
"""GET endpoints for form_responses — ownership-gated."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient


@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)


async def _seed(patient_count: int = 1, template_id: str = "form_satisfaction_v1"):
    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patients = []
        for i in range(patient_count):
            p = Patient(doctor_id=doc_id, name=f"P{i}")
            db.add(p)
            patients.append(p)
        await db.commit()
        patient_ids = [p.id for p in patients]

    async with AsyncSessionLocal() as db:
        for pid in patient_ids:
            row = FormResponseDB(
                doctor_id=doc_id,
                patient_id=pid,
                template_id=template_id,
                payload={"overall_rating": "满意"},
            )
            db.add(row)
        await db.commit()

        rows = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.doctor_id == doc_id)
        )).scalars().all()
        return doc_id, patient_ids, [r.id for r in rows]


@pytest.mark.asyncio
async def test_get_form_response_detail(client):
    doc_id, pids, rids = await _seed(patient_count=1)
    resp = client.get(
        f"/api/form_responses/{rids[0]}",
        headers={"X-Doctor-Id": doc_id},  # test-mode auth bypass
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == rids[0]
    assert body["template_id"] == "form_satisfaction_v1"
    assert body["payload"]["overall_rating"] == "满意"


@pytest.mark.asyncio
async def test_get_form_response_404_for_missing_id(client):
    doc_id, _, _ = await _seed(patient_count=0)
    resp = client.get(
        f"/api/form_responses/999999",
        headers={"X-Doctor-Id": doc_id},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_form_response_403_for_other_doctor(client):
    doc_id_a, _, rids = await _seed(patient_count=1)
    # Different doctor id — should be 403/404
    other_doc = f"doc_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=other_doc))
        await db.commit()
    resp = client.get(
        f"/api/form_responses/{rids[0]}",
        headers={"X-Doctor-Id": other_doc},
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_list_form_responses_for_patient(client):
    doc_id, pids, _ = await _seed(patient_count=1)
    resp = client.get(
        f"/api/patients/{pids[0]}/form_responses",
        headers={"X-Doctor-Id": doc_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["template_id"] == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_list_filter_by_template_id(client):
    doc_id, pids, _ = await _seed(patient_count=1)
    resp = client.get(
        f"/api/patients/{pids[0]}/form_responses?template_id=nonexistent_v1",
        headers={"X-Doctor-Id": doc_id},
    )
    assert resp.status_code == 200
    assert resp.json() == []
```

NOTE: The test auth mechanism (`X-Doctor-Id` header) may not match the project's real auth. Before running, grep for how existing endpoint tests authenticate and copy that pattern:

```
grep -rln "TestClient\|test_client" tests --include="*.py" | head
grep -rn "X-Doctor-Id\|Authorization" src/infra/auth src/channels --include="*.py" | head
```

Adjust the test's auth approach to match.

- [ ] **Step 2: Create the endpoint module**

`src/channels/web/form_responses.py`:

```python
"""GET endpoints for form_responses. Ownership-gated on doctor_id."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models.form_response import FormResponseDB

router = APIRouter()


async def _resolve_doctor_id(
    authorization: Optional[str], x_doctor_id: Optional[str],
) -> str:
    """Resolve the doctor id from auth. Copies the pattern from
    channels.web.doctor_intake.shared._resolve_doctor_id.
    """
    from channels.web.doctor_intake.shared import _resolve_doctor_id as _inner
    return await _inner(x_doctor_id or "", authorization)


@router.get("/api/form_responses/{response_id}")
async def get_form_response(
    response_id: int,
    authorization: Optional[str] = Header(default=None),
    x_doctor_id: Optional[str] = Header(default=None, alias="X-Doctor-Id"),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor = await _resolve_doctor_id(authorization, x_doctor_id)

    row = await db.get(FormResponseDB, response_id)
    if row is None:
        raise HTTPException(404, "form response not found")
    if row.doctor_id != resolved_doctor:
        raise HTTPException(403, "not authorized for this response")

    return {
        "id": row.id,
        "doctor_id": row.doctor_id,
        "patient_id": row.patient_id,
        "template_id": row.template_id,
        "session_id": row.session_id,
        "payload": row.payload,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/api/patients/{patient_id}/form_responses")
async def list_form_responses(
    patient_id: int,
    template_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_doctor_id: Optional[str] = Header(default=None, alias="X-Doctor-Id"),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor = await _resolve_doctor_id(authorization, x_doctor_id)

    q = select(FormResponseDB).where(
        FormResponseDB.patient_id == patient_id,
        FormResponseDB.doctor_id == resolved_doctor,
    )
    if template_id:
        q = q.where(FormResponseDB.template_id == template_id)
    q = q.order_by(FormResponseDB.created_at.desc())

    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "template_id": r.template_id,
            "payload": r.payload,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
```

- [ ] **Step 3: Wire the router into main.py**

```
grep -n "include_router\|app = FastAPI" src/main.py | head
```

Find where other routers are included. Add:

```python
from channels.web.form_responses import router as form_responses_router
app.include_router(form_responses_router)
```

- [ ] **Step 4: Run, expect all 5 API tests pass**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/channels/test_form_responses_api.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

If auth shape divergences, adjust the test's header approach OR add a test-mode override in the endpoint. Don't change the production auth.

- [ ] **Step 5: Commit**

```
git add src/channels/web/form_responses.py \
        src/main.py \
        tests/channels/test_form_responses_api.py
git commit -m "feat(api): add form_responses GET endpoints — detail + list"
```

---

## Task 5: Regression sweep

- [ ] **Step 1: Full suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent --tb=short 2>&1 | tail -20
```

Target: 492+ passed (was 477 + ~15 Phase 3 tests).

- [ ] **Step 2: Invariant checks**

```
# Both templates registered
python -c "from domain.intake.templates import TEMPLATES; print(list(TEMPLATES.keys()))"

# New endpoint responds (optional — requires a running server)
# curl http://localhost:8001/api/form_responses/1  # expect 404 without auth
```

- [ ] **Step 3: Commit history sanity**

```
git log 078e310b..HEAD --oneline
```

Expected: 4 Phase 3 commits.

Phase 3 complete. Frontend UI for viewing form responses is a follow-up.
