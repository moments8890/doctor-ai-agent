# Intake Pipeline Extensibility — Phase 1 (Engine Extraction)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `IntakeEngine` + the 5 protocol seams (`FieldSpec`, `FieldExtractor`, `BatchExtractor`, `Writer`, `PostConfirmHook`, `Template`) and route the existing medical pipeline through them. **Zero behavior change** — the medical logic stays where it lives today (`intake_models.py`, `completeness.py`, `batch_extract_from_transcript`, the insert in `confirm.py`, the diagnosis/notify/tasks side effects). Phase 1 is the thin indirection layer that makes Phase 2 (real extraction of that logic into the template) possible.

**Architecture:** New `src/domain/intake/` package holds the protocol surface (`protocols.py`), the LLM contract synthesis helper (`contract.py`), the generic engine (`engine.py`), hooks (`hooks/medical.py`), and a medical template (`templates/medical_general.py`) whose methods *delegate* to the existing codepaths — not re-implement them. The doctor `/turn`, `/confirm`, `/cancel` endpoints and the patient intake route flip from calling `intake_turn()` / `confirm.py` logic directly to calling `engine.next_turn()` / `engine.confirm()`. The existing `intake_turn` / `batch_extract_from_transcript` / `submit_intake` functions stay reachable for the shim; Phase 2 will inline-delete them.

**Tech Stack:** Python 3.13, `typing.Protocol`, Pydantic 2.x `BaseModel` + `create_model`, SQLAlchemy 2.x async, pytest + pytest-asyncio.

**Reference:** Spec `docs/superpowers/specs/2026-04-22-intake-pipeline-extensibility-design.md` §§ 3a, 3b, 3e, 5c, 5d, 6a (Phase 1 row), 7a.

---

## Preconditions

- Phase 0 is landed. Alembic head = `c9f8d2e14a20`. `template_id` threaded through ORM + dataclass + `/turn` endpoint. Empty `src/domain/intake/` package exists (commit `8ac87a4c`).
- Working tree clean. Branch = `main`.
- All 14 Phase 0 tests pass (`tests/core/test_intake_session_*.py`, `tests/db/test_migration_intake_template_id.py`, `tests/core/test_form_response_model.py`, `tests/core/test_doctor_first_turn_template_id.py`).
- `.venv/bin/python` at `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python`.
- Test harness incantation (pinned):
  ```
  /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest <args> \
      --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
  ```

## Behavior-preservation bar (spec §7a)

- `reply_sim` pass-rate delta ≤ 2% vs main at task 13's gate.
- `test_diagnosis_prompt_sniff.py` stays green.
- Existing intake tests in `tests/core/` stay green.
- No user-visible change. The doctor `/turn`, patient `/start` and `/turn`, and `/confirm` endpoints produce byte-compatible responses (tolerance: 2% sim delta).
- The asymmetric confirm-path side effects are preserved intentionally (spec §5d + §8 open question): patient confirm fires `TriggerDiagnosisPipelineHook` + `NotifyDoctorHook`; doctor confirm fires `GenerateFollowupTasksHook` only. Phase 4 revisits.

## File map

**Create:**
- `src/domain/intake/protocols.py` — `FieldSpec`, `FieldExtractor`, `BatchExtractor`, `Writer`, `PostConfirmHook`, `Template`, `SessionState`, `PersistRef`, `Phase`, `Mode`, `CompletenessState`, `TurnResult`.
- `src/domain/intake/contract.py` — `build_response_schema(fields) -> type[BaseModel]`.
- `src/domain/intake/engine.py` — `IntakeEngine` class with `next_turn()` and `confirm()`.
- `src/domain/intake/templates/__init__.py` — `TEMPLATES: dict[str, Template]`, `get_template(id)`, `UnknownTemplate`.
- `src/domain/intake/templates/medical_general.py` — `GeneralMedicalTemplate`, `GeneralMedicalExtractor`, `MedicalBatchExtractor`, `MedicalRecordWriter`, `MEDICAL_FIELDS` list.
- `src/domain/intake/hooks/__init__.py` — empty package.
- `src/domain/intake/hooks/medical.py` — `TriggerDiagnosisPipelineHook`, `GenerateFollowupTasksHook`, `NotifyDoctorHook`.

**Test files (create):**
- `tests/core/test_intake_protocols.py`
- `tests/core/test_intake_contract.py`
- `tests/core/test_medical_field_specs.py`
- `tests/core/test_medical_extractor.py`
- `tests/core/test_medical_batch_extractor.py`
- `tests/core/test_medical_writer.py`
- `tests/core/test_medical_hooks.py`
- `tests/core/test_template_registry.py`
- `tests/core/test_intake_engine_turn.py`
- `tests/core/test_intake_engine_confirm.py`

**Modify:**
- `src/channels/web/doctor_intake/confirm.py` — inline logic → `engine.confirm()` call + thin HTTP glue (Task 11).
- `src/domain/patients/intake_summary.py` — `submit_intake` becomes a thin wrapper around `engine.confirm()` (Task 12).

**Not modified in Phase 1** (all four `/turn` endpoint files stay as-is — `engine.next_turn` exists but wiring `/turn` through it is a Phase 2 concern when the turn loop is inlined):
- `src/channels/web/doctor_intake/turn.py`
- `src/channels/web/patient_intake_routes.py`

**Do NOT modify in Phase 1** (these move in Phase 2):
- `src/domain/patients/intake_models.py`
- `src/domain/patients/completeness.py`
- `src/channels/web/doctor_intake/shared.py`
- Prompt files in `src/agent/prompts/intent/`

---

## Task 1: Protocol surface — types, dataclasses, Protocol classes

**Files:**
- Create: `src/domain/intake/protocols.py`
- Create: `tests/core/test_intake_protocols.py`

- [ ] **Step 1: Write failing protocol-shape tests**

`tests/core/test_intake_protocols.py`:

```python
"""Protocol surface smoke tests — shapes only, not behavior."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.intake.protocols import (
    FieldSpec, Mode, Phase,
    CompletenessState, PersistRef, TurnResult, SessionState,
)


def test_fieldspec_minimal_string_field():
    spec = FieldSpec(name="chief_complaint", description="Patient's main complaint.")
    assert spec.name == "chief_complaint"
    assert spec.type == "string"
    assert spec.tier == "optional"
    assert spec.appendable is False
    assert spec.carry_forward_modes == frozenset()


def test_fieldspec_enum_requires_values():
    with pytest.raises(ValidationError):
        FieldSpec(name="severity", type="enum", description="", enum_values=None)


def test_fieldspec_carry_forward_is_frozenset():
    spec = FieldSpec(
        name="past_history", description="",
        carry_forward_modes=frozenset({"doctor"}),
    )
    assert "doctor" in spec.carry_forward_modes
    # Immutable by construction
    with pytest.raises(AttributeError):
        spec.carry_forward_modes.add("patient")


def test_fieldspec_tier_vocabulary_is_frozen():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", description="", tier="urgent")  # not in Literal


def test_fieldspec_type_vocabulary_is_frozen():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", description="", type="datetime")  # not in Literal


def test_mode_literal():
    # Mode should be an alias usable in annotations
    from typing import get_args
    assert set(get_args(Mode)) == {"patient", "doctor"}


def test_completenessstate_shape():
    state = CompletenessState(
        can_complete=True,
        required_missing=[],
        recommended_missing=["past_history"],
        optional_missing=[],
        next_focus="past_history",
    )
    assert state.can_complete is True
    assert state.next_focus == "past_history"


def test_turnresult_shape():
    state = CompletenessState(
        can_complete=False, required_missing=["chief_complaint"],
        recommended_missing=[], optional_missing=[], next_focus="chief_complaint",
    )
    result = TurnResult(reply="ok", suggestions=[], state=state)
    assert result.reply == "ok"


def test_persistref_shape():
    ref = PersistRef(kind="medical_record", id=42)
    assert ref.kind == "medical_record"
    assert ref.id == 42
```

- [ ] **Step 2: Run, confirm all 8 fail with ModuleNotFoundError**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_protocols.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... ModuleNotFoundError: No module named 'domain.intake.protocols'`.

- [ ] **Step 3: Create the protocol module**

`src/domain/intake/protocols.py`:

```python
"""Polymorphic intake pipeline — protocol surface.

Spec: docs/superpowers/specs/2026-04-22-intake-pipeline-extensibility-design.md §3a.

This file defines shapes only — no runtime behavior. Runtime impl lives in
engine.py (generic) and templates/<name>.py (per-template).
"""
from __future__ import annotations

from typing import Any, Awaitable, Literal, Protocol, Union

from pydantic import BaseModel, Field, model_validator

# ---- aliases ----------------------------------------------------------------

Mode = Literal["patient", "doctor"]
Phase = str  # templates define their own phase tokens; engine treats opaque


# ---- data types -------------------------------------------------------------

class FieldSpec(BaseModel):
    """Declarative per-field metadata. Constrained vocabulary — widening
    requires a PR to contract.py + a matching test."""
    name: str
    type: Literal["string", "text", "number", "enum"] = "string"
    description: str                                    # LLM-facing
    example: str | None = None
    enum_values: tuple[str, ...] | None = None
    label: str | None = None                            # human label
    tier: Literal["required", "recommended", "optional"] = "optional"
    appendable: bool = False
    carry_forward_modes: frozenset[Mode] = frozenset()

    @model_validator(mode="after")
    def _enum_requires_values(self) -> "FieldSpec":
        if self.type == "enum" and not self.enum_values:
            raise ValueError(
                f"FieldSpec({self.name}): type='enum' requires enum_values"
            )
        return self


class CompletenessState(BaseModel):
    can_complete: bool
    required_missing: list[str]
    recommended_missing: list[str]
    optional_missing: list[str]
    next_focus: str | None


class PersistRef(BaseModel):
    """Reference to the persisted artifact a confirm produced. `id` is
    template-kind-specific — medical writers return medical_records.id,
    form writers return form_responses.id."""
    kind: Literal["medical_record", "form_response"]
    id: int


class TurnResult(BaseModel):
    reply: str
    suggestions: list[str] = Field(default_factory=list)
    state: CompletenessState
    # Passthrough for metadata the endpoint surfaces today (patient_name,
    # patient_gender, patient_age). Keep loose dict to avoid leaking medical
    # concepts into the engine's public type surface.
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class SessionState(BaseModel):
    """Read-model view of an intake session exposed to the engine + templates.
    Templates MUST NOT mutate this directly; the engine owns writes."""
    id: str
    doctor_id: str
    patient_id: int | None
    mode: Mode
    status: str
    template_id: str
    collected: dict[str, str]
    conversation: list[dict[str, Any]]
    turn_count: int

    model_config = {"arbitrary_types_allowed": True}


# ---- protocols --------------------------------------------------------------

class FieldExtractor(Protocol):
    """Per-template. Schema, prompt, merge, and completeness semantics.
    Schema lives in fields(); everything else is behavior on top of it."""

    def fields(self) -> list[FieldSpec]: ...

    def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
    ) -> Awaitable[list[dict[str, str]]] | list[dict[str, str]]:
        ...

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]: ...

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState: ...

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase: ...


class BatchExtractor(Protocol):
    """Optional per-template. Pre-finalize re-extraction from full transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None: ...


class Writer(Protocol):
    """Per-template. Pure persistence. No LLM calls, no post-confirm side
    effects (those are hooks)."""

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef: ...


class PostConfirmHook(Protocol):
    name: str

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None: ...


class EngineConfig(BaseModel):
    max_turns: int = 30
    phases: dict[Mode, list[Phase]] = Field(default_factory=dict)


class Template(Protocol):
    """Registry entry. Attributes only — templates are typically dataclasses
    or plain classes with instance attributes named below."""
    id: str
    kind: Literal["medical", "form"]
    display_name: str
    requires_doctor_review: bool
    supported_modes: tuple[Mode, ...]
    extractor: FieldExtractor
    batch_extractor: BatchExtractor | None
    writer: Writer
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]]
    config: EngineConfig
```

- [ ] **Step 4: Run the protocol tests, confirm all pass**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_protocols.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add src/domain/intake/protocols.py tests/core/test_intake_protocols.py
git commit -m "feat(intake): add protocol surface — FieldSpec + 5 protocols"
```

---

## Task 2: LLM contract synthesis helper

**Files:**
- Create: `src/domain/intake/contract.py`
- Create: `tests/core/test_intake_contract.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_intake_contract.py`:

```python
"""build_response_schema — synthesizes a per-call Pydantic class from FieldSpec list.

Spec: §3e. Class is throwaway; callers parse LLM output through it then
convert to dict before anything downstream touches the value.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.intake.contract import build_response_schema
from domain.intake.protocols import FieldSpec


def _spec(**kw):
    kw.setdefault("description", "")
    return FieldSpec(**kw)


def test_build_accepts_empty_list():
    Model = build_response_schema([])
    obj = Model()
    assert obj.model_dump() == {}


def test_string_field_nullable_when_not_required():
    Model = build_response_schema([
        _spec(name="chief_complaint", type="string", tier="optional"),
    ])
    # None is allowed because tier != "required"
    obj = Model(chief_complaint=None)
    assert obj.chief_complaint is None


def test_required_field_rejects_missing():
    Model = build_response_schema([
        _spec(name="chief_complaint", type="string", tier="required"),
    ])
    with pytest.raises(ValidationError):
        Model()  # missing required field


def test_enum_field_rejects_out_of_vocabulary():
    Model = build_response_schema([
        _spec(
            name="severity", type="enum",
            enum_values=("mild", "moderate", "severe"),
            tier="required",
        ),
    ])
    with pytest.raises(ValidationError):
        Model(severity="extreme")

    obj = Model(severity="moderate")
    assert obj.severity == "moderate"


def test_number_field_coerces_string_digits():
    Model = build_response_schema([
        _spec(name="age", type="number", tier="optional"),
    ])
    # Pydantic's int coercion accepts digit strings
    obj = Model(age="42")
    assert obj.age == 42


def test_text_field_same_as_string_for_validation():
    # type="text" is a hint to the LLM (long-form). Validation is string.
    Model = build_response_schema([
        _spec(name="present_illness", type="text", tier="optional"),
    ])
    obj = Model(present_illness="long paragraph...")
    assert obj.present_illness == "long paragraph..."


def test_description_is_carried_to_field_info():
    Model = build_response_schema([
        _spec(
            name="chief_complaint", type="string", tier="optional",
            description="Patient's primary symptom in their own words.",
        ),
    ])
    info = Model.model_fields["chief_complaint"]
    assert info.description == "Patient's primary symptom in their own words."


def test_repeated_calls_produce_independent_classes():
    fields = [_spec(name="x", type="string", tier="optional")]
    A = build_response_schema(fields)
    B = build_response_schema(fields)
    assert A is not B
    assert A.model_fields.keys() == B.model_fields.keys()


def test_unknown_type_raises_at_build_time():
    # We should catch drift early, not at LLM call time.
    # FieldSpec vocab is already Literal-constrained, but if someone extends
    # the vocab in FieldSpec without updating build_response_schema, the
    # helper must explode loudly.
    bad = FieldSpec.model_construct(
        name="x", type="unsupported_type",
        description="", tier="optional", appendable=False,
        carry_forward_modes=frozenset(), enum_values=None, label=None,
        example=None,
    )
    with pytest.raises(ValueError, match="unsupported"):
        build_response_schema([bad])
```

- [ ] **Step 2: Run, confirm all fail with ModuleNotFoundError**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_contract.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 3: Implement `contract.py`**

`src/domain/intake/contract.py`:

```python
"""LLM structured-output contract synthesis.

Spec §3e. This is the single point where FieldSpec becomes a Pydantic class
for validating an LLM response. The class is throwaway — every caller
converts the validated instance back to dict before returning.

Vocabulary is frozen. To add a new type, update `_SPEC_TO_PY_TYPE` here and
add a FieldSpec.type literal + a test.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from domain.intake.protocols import FieldSpec

# Frozen mapping. Widen only via PR + tests.
_SPEC_TO_PY_TYPE: dict[str, type] = {
    "string": str,
    "text": str,      # same validation; distinction is an LLM hint
    "number": int,
}


def _enum_type(name: str, values: tuple[str, ...]) -> type:
    """Build a str-Enum so Pydantic validates inputs to the vocabulary set."""
    return Enum(f"{name}_enum", {v: v for v in values}, type=str)


def build_response_schema(fields: list[FieldSpec]) -> type[BaseModel]:
    """Return a throwaway Pydantic class whose attributes mirror `fields`.

    Required tier fields become non-nullable; recommended/optional are
    `Optional[...]` with `None` default. The class is created fresh on every
    call — no caching — so that repeated builds never alias each other.
    """
    attrs: dict[str, Any] = {}
    for f in fields:
        if f.type == "enum":
            assert f.enum_values is not None  # FieldSpec validator guarantees
            py_type: type = _enum_type(f.name, f.enum_values)
        else:
            try:
                py_type = _SPEC_TO_PY_TYPE[f.type]
            except KeyError as e:
                raise ValueError(
                    f"build_response_schema: unsupported type {f.type!r} on "
                    f"field {f.name!r}. Add it to _SPEC_TO_PY_TYPE."
                ) from e

        if f.tier == "required":
            default = ...
            anno = py_type
        else:
            default = None
            anno = Optional[py_type]

        attrs[f.name] = (anno, Field(default, description=f.description))

    return create_model("ExtractedFields", **attrs)
```

- [ ] **Step 4: Run, confirm all 9 pass**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_contract.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 5: Commit**

```
git add src/domain/intake/contract.py tests/core/test_intake_contract.py
git commit -m "feat(intake): add build_response_schema — throwaway Pydantic from FieldSpec"
```

---

## Task 3: Medical field specs — derive from ExtractedClinicalFields

**Files:**
- Create: `src/domain/intake/templates/__init__.py` (empty placeholder)
- Create: `src/domain/intake/templates/medical_general.py` (partial — only `MEDICAL_FIELDS` list in this task)
- Create: `tests/core/test_medical_field_specs.py`

The medical extractor's `fields()` must return a `list[FieldSpec]` that describes the 17 fields already present in `src/domain/patients/intake_models.py::ExtractedClinicalFields`. Metadata (labels, descriptions, examples, appendability, carry-forward) is already embedded in the existing `FIELD_LABELS`, `FIELD_META`, and `completeness.APPENDABLE` + `doctor_intake/shared._CARRY_FORWARD_FIELDS`. This task translates those scattered sources into one declarative list — no behavior change.

- [ ] **Step 1: Inspect the existing sources**

Before writing the failing test, read:
- `src/domain/patients/intake_models.py` — confirm the 17 field names on `ExtractedClinicalFields` and the contents of `FIELD_LABELS` + `FIELD_META`.
- `src/domain/patients/completeness.py` — confirm the `APPENDABLE` frozenset and `REQUIRED` tuple.
- `src/channels/web/doctor_intake/shared.py` — confirm `_CARRY_FORWARD_FIELDS`.

Do not copy the exact constants into the plan — derive them from the actual files so later drift doesn't silently bit-rot the spec.

- [ ] **Step 2: Write failing tests that assert the translation preserves semantics**

`tests/core/test_medical_field_specs.py`:

```python
"""MEDICAL_FIELDS translates scattered medical metadata into a FieldSpec list.

No behavior change vs. the pre-phase-1 code — these tests lock the semantics
so Phase 2 refactors can't accidentally drop a field or flip an append rule.
"""
from __future__ import annotations

import pytest

from domain.intake.templates.medical_general import MEDICAL_FIELDS
from domain.patients.completeness import APPENDABLE, REQUIRED
from domain.patients.intake_models import (
    ExtractedClinicalFields, FIELD_LABELS, FIELD_META,
)
from channels.web.doctor_intake.shared import _CARRY_FORWARD_FIELDS


def test_every_extracted_field_has_a_spec():
    pydantic_names = {
        n for n in ExtractedClinicalFields.model_fields.keys()
        # patient_name/gender/age are metadata, not clinical fields
        if not n.startswith("patient_")
    }
    spec_names = {s.name for s in MEDICAL_FIELDS}
    assert pydantic_names <= spec_names, (
        f"Fields missing a FieldSpec: {pydantic_names - spec_names}"
    )


def test_no_extra_clinical_specs():
    clinical_spec_names = {
        s.name for s in MEDICAL_FIELDS if not s.name.startswith("_")
    }
    pydantic_names = set(ExtractedClinicalFields.model_fields.keys())
    pydantic_names |= {"patient_name", "patient_gender", "patient_age"}
    assert clinical_spec_names <= pydantic_names, (
        f"Spurious FieldSpecs: {clinical_spec_names - pydantic_names}"
    )


def test_required_tier_matches_completeness_required():
    required_spec_names = {s.name for s in MEDICAL_FIELDS if s.tier == "required"}
    assert required_spec_names == set(REQUIRED)


def test_appendable_flag_matches_completeness_appendable():
    appendable_spec_names = {s.name for s in MEDICAL_FIELDS if s.appendable}
    assert appendable_spec_names == set(APPENDABLE)


def test_carry_forward_matches_shared_carry_forward():
    carry_spec_names = {
        s.name for s in MEDICAL_FIELDS if "doctor" in s.carry_forward_modes
    }
    assert carry_spec_names == set(_CARRY_FORWARD_FIELDS)


def test_every_spec_has_label():
    for s in MEDICAL_FIELDS:
        assert s.label, f"FieldSpec({s.name}): label required for UI"


def test_every_spec_has_description():
    for s in MEDICAL_FIELDS:
        assert s.description, f"FieldSpec({s.name}): description required for LLM prompt"


def test_labels_match_field_labels_dict():
    for s in MEDICAL_FIELDS:
        if s.name in FIELD_LABELS:
            assert s.label == FIELD_LABELS[s.name], (
                f"{s.name}: label drift vs FIELD_LABELS"
            )


def test_descriptions_prefer_field_meta_hint():
    # When FIELD_META has a hint for the field, the FieldSpec's description
    # must incorporate that hint (substring match) so LLM prompt behavior
    # stays identical.
    for s in MEDICAL_FIELDS:
        meta = FIELD_META.get(s.name)
        if meta and meta.get("hint"):
            assert meta["hint"] in s.description, (
                f"{s.name}: description missing FIELD_META hint text"
            )


def test_examples_prefer_field_meta_example():
    for s in MEDICAL_FIELDS:
        meta = FIELD_META.get(s.name)
        if meta and meta.get("example"):
            assert s.example == meta["example"]
```

- [ ] **Step 3: Run, confirm ModuleNotFoundError**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_medical_field_specs.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 4: Create the templates package placeholder**

`src/domain/intake/templates/__init__.py`:

```python
"""Template registry. Populated by templates/medical_general.py + future variants."""
from __future__ import annotations

from domain.intake.protocols import Template


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
```

- [ ] **Step 5: Build `MEDICAL_FIELDS` in `medical_general.py`**

`src/domain/intake/templates/medical_general.py`:

```python
"""GeneralMedicalTemplate — Phase 1 thin-stub implementation.

Every method delegates to pre-Phase-1 codepaths. Phase 2 inlines the logic
here and deletes the legacy sources. Phase 1 keeps the legacy sources live.
"""
from __future__ import annotations

from typing import Any

from domain.intake.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PersistRef, PostConfirmHook, SessionState, Template, Writer,
)

# ---- field specs ------------------------------------------------------------

from domain.patients.completeness import APPENDABLE, REQUIRED
from domain.patients.intake_models import FIELD_LABELS, FIELD_META
from channels.web.doctor_intake.shared import _CARRY_FORWARD_FIELDS


def _build_medical_fields() -> list[FieldSpec]:
    """Translate the existing scattered metadata into a single FieldSpec list.

    Order follows FIELD_LABELS insertion order. Each field's
    - tier   = "required" if in REQUIRED else "recommended" if in DOCTOR_RECOMMENDED-
               equivalent (we approximate by: non-REQUIRED fields that are in
               the Subjective/Objective/Assessment/Plan set) else "optional"
    - label  = FIELD_LABELS[name]
    - description = FIELD_META[name]["hint"] (fallback to label)
    - example = FIELD_META[name]["example"] if present
    - appendable = name in APPENDABLE
    - carry_forward_modes = frozenset({"doctor"}) if name in _CARRY_FORWARD_FIELDS
                            else frozenset()
    """
    from domain.patients.completeness import DOCTOR_RECOMMENDED

    specs: list[FieldSpec] = []
    for name, label in FIELD_LABELS.items():
        meta = FIELD_META.get(name, {})
        hint = meta.get("hint") or label
        example = meta.get("example")

        if name in REQUIRED:
            tier = "required"
        elif name in DOCTOR_RECOMMENDED:
            tier = "recommended"
        else:
            tier = "optional"

        specs.append(FieldSpec(
            name=name,
            type="text" if name in APPENDABLE else "string",
            description=hint,
            example=example,
            label=label,
            tier=tier,
            appendable=(name in APPENDABLE),
            carry_forward_modes=(
                frozenset({"doctor"}) if name in _CARRY_FORWARD_FIELDS
                else frozenset()
            ),
        ))
    return specs


MEDICAL_FIELDS: list[FieldSpec] = _build_medical_fields()
```

- [ ] **Step 6: Run the tests — expect `9 passed`**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_medical_field_specs.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

If any test fails, the mismatch is between the derivation rules above and the actual sources. Adjust `_build_medical_fields` — **do not** adjust the test assertions, those lock the spec.

- [ ] **Step 7: Commit**

```
git add src/domain/intake/templates/__init__.py \
        src/domain/intake/templates/medical_general.py \
        tests/core/test_medical_field_specs.py
git commit -m "feat(intake): derive MEDICAL_FIELDS from scattered medical metadata"
```

---

## Task 4: `GeneralMedicalExtractor` — delegating FieldExtractor

**Files:**
- Modify: `src/domain/intake/templates/medical_general.py` (append class)
- Create: `tests/core/test_medical_extractor.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_medical_extractor.py`:

```python
"""GeneralMedicalExtractor — delegation tests.

Phase 1: every method forwards to the pre-Phase-1 codepath. These tests
verify the forwarding is wire-correct. Phase 2 moves the impl inline and
these tests are updated to assert the direct implementation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from domain.intake.protocols import CompletenessState, SessionState
from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_fields_returns_medical_fields_list(extractor):
    assert extractor.fields() is MEDICAL_FIELDS


def test_merge_delegates_to_completeness_merge_extracted(extractor):
    # merge_extracted mutates in-place; the delegating wrapper returns the
    # same dict after mutation.
    with patch(
        "domain.intake.templates.medical_general._merge_extracted",
    ) as mock_merge:
        collected = {"chief_complaint": "头痛"}
        extracted = {"present_illness": "3天"}
        result = extractor.merge(collected, extracted)

    mock_merge.assert_called_once_with(collected, extracted)
    assert result is collected  # returns same dict (mutated)


def test_completeness_delegates_to_get_completeness_state(extractor):
    fake_state = {
        "can_complete": True,
        "required_missing": [],
        "recommended_missing": ["past_history"],
        "optional_missing": [],
        "next_focus": "past_history",
    }
    with patch(
        "domain.intake.templates.medical_general._get_completeness_state",
        return_value=fake_state,
    ) as mock_get:
        state = extractor.completeness({"chief_complaint": "x"}, "patient")

    mock_get.assert_called_once_with({"chief_complaint": "x"}, mode="patient")
    assert isinstance(state, CompletenessState)
    assert state.can_complete is True
    assert state.next_focus == "past_history"
    assert state.recommended_missing == ["past_history"]


def test_next_phase_returns_single_default_phase_for_now(extractor):
    session = SessionState(
        id="s1", doctor_id="d", patient_id=None, mode="patient",
        status="active", template_id="medical_general_v1",
        collected={}, conversation=[], turn_count=0,
    )
    # Phase 1 doesn't implement real phase transitions — it returns the
    # one-and-only phase the template declares. See template.config.phases.
    assert extractor.next_phase(session, ["default"]) == "default"


@pytest.mark.asyncio
async def test_prompt_partial_is_awaitable_and_returns_messages(extractor):
    """prompt_partial must produce the messages list that prompt_composer
    would have produced. Phase 1 forwards to the composer directly so the
    output is byte-identical."""
    with patch(
        "domain.intake.templates.medical_general._compose_for_patient_intake",
    ) as mock_compose:
        mock_compose.return_value = [
            {"role": "system", "content": "..."},
        ]
        result = await extractor.prompt_partial(
            collected={"chief_complaint": "头痛"},
            history=[{"role": "user", "content": "头痛三天"}],
            phase="default",
            mode="patient",
        )
    # The wrapper is just a named pass-through; whatever kwargs the composer
    # expects, we pass.
    assert mock_compose.called
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_prompt_partial_routes_doctor_mode_to_doctor_composer(extractor):
    with patch(
        "domain.intake.templates.medical_general._compose_for_doctor_intake",
    ) as mock_doc, \
         patch(
        "domain.intake.templates.medical_general._compose_for_patient_intake",
    ) as mock_pat:
        mock_doc.return_value = []
        await extractor.prompt_partial(
            collected={}, history=[], phase="default", mode="doctor",
        )
    mock_doc.assert_called_once()
    mock_pat.assert_not_called()
```

- [ ] **Step 2: Run, confirm failures (class/imports don't exist)**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_medical_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 3: Append `GeneralMedicalExtractor` to `medical_general.py`**

Append to `src/domain/intake/templates/medical_general.py`:

```python
# ---- extractor -------------------------------------------------------------

from domain.patients.completeness import (
    get_completeness_state as _get_completeness_state,
    merge_extracted as _merge_extracted,
)
from agent.prompt_composer import (
    compose_for_doctor_intake as _compose_for_doctor_intake,
    compose_for_patient_intake as _compose_for_patient_intake,
)


class GeneralMedicalExtractor:
    """Phase 1 thin-stub FieldExtractor. Every method forwards to legacy code."""

    def fields(self) -> list[FieldSpec]:
        return MEDICAL_FIELDS

    async def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        """Forward to the existing prompt composer. Phase 2 will absorb the
        intent-layer prompt loading into the extractor; Phase 1 preserves
        the current composition exactly."""
        # NOTE: the current composer pulls the session's patient_context,
        # doctor_id, and history from call-site parameters that Phase 1
        # doesn't yet plumb through. The engine.next_turn() implementation
        # (Task 10) calls this helper with the full set of kwargs the
        # composer expects, threaded from the SessionState it already has.
        if mode == "doctor":
            return await _compose_for_doctor_intake(**_composer_kwargs(
                collected, history, phase, mode,
            ))
        return await _compose_for_patient_intake(**_composer_kwargs(
            collected, history, phase, mode,
        ))

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        _merge_extracted(collected, extracted)
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        raw = _get_completeness_state(collected, mode=mode)
        return CompletenessState(
            can_complete=raw["can_complete"],
            required_missing=raw["required_missing"],
            recommended_missing=raw["recommended_missing"],
            optional_missing=raw["optional_missing"],
            next_focus=raw["next_focus"],
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        # Phase 1: template declares a single phase. This returns it.
        # Phase 3+ may introduce real branching; keep the protocol ready for that.
        return phases[0]


def _composer_kwargs(
    collected: dict[str, str],
    history: list[dict[str, Any]],
    phase: Phase,
    mode: Mode,
) -> dict[str, Any]:
    """Minimal kwargs the composer needs. The engine passes the full
    context via SessionState at call time (Task 10); this helper is the
    current no-op stub used during unit-level tests where Task 10 hasn't
    wired the real kwargs yet."""
    return {
        "doctor_id": "",
        "patient_context": "",
        "doctor_message": "",
        "history": history,
        "template_id": "medical_general_v1",
    }
```

- [ ] **Step 4: Run, expect `6 passed`**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/templates/medical_general.py \
        tests/core/test_medical_extractor.py
git commit -m "feat(intake): add GeneralMedicalExtractor — thin-stub delegator"
```

---

## Task 5: `MedicalBatchExtractor`

**Files:**
- Modify: `src/domain/intake/templates/medical_general.py`
- Create: `tests/core/test_medical_batch_extractor.py`

The existing `batch_extract_from_transcript` lives in `src/domain/patients/intake_summary.py`. It takes `(conversation, patient_info, mode)` and returns either a dict of extracted fields or `None` on failure. The `MedicalBatchExtractor.extract` protocol signature matches almost directly — only the `context` → `patient_info` name differs.

- [ ] **Step 1: Write failing test**

`tests/core/test_medical_batch_extractor.py`:

```python
"""MedicalBatchExtractor — delegates to batch_extract_from_transcript."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.templates.medical_general import MedicalBatchExtractor


@pytest.mark.asyncio
async def test_extract_delegates_with_patient_info_rename():
    with patch(
        "domain.intake.templates.medical_general._batch_extract_from_transcript",
        new=AsyncMock(return_value={"chief_complaint": "头痛"}),
    ) as mock_batch:
        be = MedicalBatchExtractor()
        out = await be.extract(
            conversation=[{"role": "user", "content": "头痛"}],
            context={"name": "张三", "gender": "男", "age": "45"},
            mode="doctor",
        )

    mock_batch.assert_called_once_with(
        [{"role": "user", "content": "头痛"}],
        {"name": "张三", "gender": "男", "age": "45"},
        mode="doctor",
    )
    assert out == {"chief_complaint": "头痛"}


@pytest.mark.asyncio
async def test_extract_propagates_none_on_empty_result():
    with patch(
        "domain.intake.templates.medical_general._batch_extract_from_transcript",
        new=AsyncMock(return_value=None),
    ):
        be = MedicalBatchExtractor()
        out = await be.extract(
            conversation=[], context={}, mode="patient",
        )
    assert out is None
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Append `MedicalBatchExtractor` to `medical_general.py`**

```python
# ---- batch extractor -------------------------------------------------------

from domain.patients.intake_summary import (
    batch_extract_from_transcript as _batch_extract_from_transcript,
)


class MedicalBatchExtractor:
    """Phase 1 stub. Forwards to the existing batch_extract_from_transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None:
        return await _batch_extract_from_transcript(
            conversation, context, mode=mode,
        )
```

- [ ] **Step 4: Run, expect `2 passed`**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/templates/medical_general.py \
        tests/core/test_medical_batch_extractor.py
git commit -m "feat(intake): add MedicalBatchExtractor — delegates to existing batch extract"
```

---

## Task 6: `MedicalRecordWriter` — persist + deferred patient creation

**Files:**
- Modify: `src/domain/intake/templates/medical_general.py`
- Create: `tests/core/test_medical_writer.py`

The writer absorbs two pre-Phase-1 concerns from `confirm.py`:
1. **Deferred patient creation** — if `session.patient_id is None`, resolve the patient name into a patient row (via `agent.tools.resolve.resolve`) before inserting the record. Raises `HTTPException(422)` on missing name (preserving the pre-Phase-1 422).
2. **Record insert** — build `MedicalRecordDB` from `collected` and save. Status is `completed` vs `pending_review` depending on diagnosis/treatment/followup presence.

The clinical text builder `_build_clinical_text` stays in `shared.py` — writer imports it.

- [ ] **Step 1: Write failing tests**

`tests/core/test_medical_writer.py`:

```python
"""MedicalRecordWriter.persist — integration test against real SQLite.

Uses the existing `db_session` fixture + AsyncSessionLocal pattern from
Task 5 of Phase 0. Hits the dev DB with UUID-suffixed doctor/patient ids.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from domain.intake.protocols import PersistRef, SessionState
from domain.intake.templates.medical_general import MedicalRecordWriter


def _session(**over) -> SessionState:
    defaults = dict(
        id=f"s_{uuid.uuid4().hex[:8]}",
        doctor_id=f"doc_{uuid.uuid4().hex[:8]}",
        patient_id=None,
        mode="doctor",
        status="active",
        template_id="medical_general_v1",
        collected={},
        conversation=[],
        turn_count=1,
    )
    defaults.update(over)
    return SessionState(**defaults)


@pytest.mark.asyncio
async def test_persist_with_existing_patient_id_inserts_record():
    writer = MedicalRecordWriter()

    # Seed doctor + patient
    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="张三")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doctor_id=doc_id, patient_id=pid)
    collected = {
        "chief_complaint": "头痛",
        "present_illness": "3天",
        "diagnosis": "偏头痛",
        "treatment_plan": "布洛芬",
        "orders_followup": "1周后复诊",
    }
    ref = await writer.persist(session, collected)

    assert isinstance(ref, PersistRef)
    assert ref.kind == "medical_record"

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
    assert row.chief_complaint == "头痛"
    assert row.diagnosis == "偏头痛"
    assert row.status == "completed"  # all three of diag/treat/followup set


@pytest.mark.asyncio
async def test_persist_with_missing_all_plans_is_pending_review():
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="李四")
        db.add(patient)
        await db.commit()
        pid = patient.id

    session = _session(doctor_id=doc_id, patient_id=pid)
    ref = await writer.persist(session, {"chief_complaint": "咳嗽"})

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
    assert row.status == "pending_review"


@pytest.mark.asyncio
async def test_persist_deferred_patient_creation():
    """When session.patient_id is None, writer creates a patient row from
    collected["_patient_name"] (and optional gender/age)."""
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doctor_id=doc_id, patient_id=None)
    collected = {
        "_patient_name": "王五",
        "_patient_gender": "男",
        "_patient_age": "58岁",
        "chief_complaint": "胸闷",
    }
    ref = await writer.persist(session, collected)

    # Patient row should now exist
    async with AsyncSessionLocal() as db:
        record = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == ref.id)
        )).scalar_one()
        patient = (await db.execute(
            select(Patient).where(Patient.id == record.patient_id)
        )).scalar_one()
    assert patient.name == "王五"


@pytest.mark.asyncio
async def test_persist_raises_422_when_no_patient_name():
    writer = MedicalRecordWriter()

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = _session(doctor_id=doc_id, patient_id=None)
    with pytest.raises(HTTPException) as excinfo:
        await writer.persist(session, {"chief_complaint": "x"})
    assert excinfo.value.status_code == 422
    assert "姓名" in str(excinfo.value.detail)
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Append `MedicalRecordWriter` to `medical_general.py`**

```python
# ---- writer -----------------------------------------------------------------

from fastapi import HTTPException

from agent.tools.resolve import resolve as _resolve_patient
from channels.web.doctor_intake.shared import _build_clinical_text
from db.crud.doctor import _ensure_doctor_exists
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB, RecordStatus


class MedicalRecordWriter:
    """Phase 1 writer. Persists the confirmed intake to medical_records.

    Absorbs deferred patient creation from confirm.py:72-101. Does NOT fire
    diagnosis / notifications / task generation — those are separate hooks.
    """

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef:
        patient_id = await self._ensure_patient(session, collected)

        clinical_text = _build_clinical_text(collected)
        has_diagnosis = bool(collected.get("diagnosis", "").strip())
        has_treatment = bool(collected.get("treatment_plan", "").strip())
        has_followup = bool(collected.get("orders_followup", "").strip())
        status = (
            RecordStatus.completed.value
            if (has_diagnosis and has_treatment and has_followup)
            else RecordStatus.pending_review.value
        )

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            record = MedicalRecordDB(
                doctor_id=session.doctor_id,
                patient_id=patient_id,
                record_type="intake_summary",
                status=status,
                content=clinical_text,
                chief_complaint=collected.get("chief_complaint"),
                present_illness=collected.get("present_illness"),
                past_history=collected.get("past_history"),
                allergy_history=collected.get("allergy_history"),
                personal_history=collected.get("personal_history"),
                marital_reproductive=collected.get("marital_reproductive"),
                family_history=collected.get("family_history"),
                physical_exam=collected.get("physical_exam"),
                specialist_exam=collected.get("specialist_exam"),
                auxiliary_exam=collected.get("auxiliary_exam"),
                diagnosis=collected.get("diagnosis"),
                treatment_plan=collected.get("treatment_plan"),
                orders_followup=collected.get("orders_followup"),
            )
            db.add(record)
            await db.commit()
            record_id = record.id

        return PersistRef(kind="medical_record", id=record_id)

    async def _ensure_patient(
        self, session: SessionState, collected: dict[str, str],
    ) -> int:
        """If session.patient_id is set, return it. Otherwise resolve from
        collected["_patient_name"] and create the patient row. Mirrors the
        confirm.py:72-101 behavior byte-for-byte."""
        if session.patient_id is not None:
            return session.patient_id

        name = (collected.get("_patient_name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=422,
                detail="无法确认：未检测到患者姓名，请在对话中提供",
            )

        gender = collected.get("_patient_gender")
        age_str = collected.get("_patient_age")
        age: int | None = None
        if age_str:
            try:
                age = int(age_str.rstrip("岁"))
            except (ValueError, AttributeError):
                pass

        resolved = await _resolve_patient(
            name, session.doctor_id, auto_create=True,
            gender=gender, age=age,
        )
        if "status" in resolved:
            raise HTTPException(
                status_code=422,
                detail=resolved.get("message", "Patient creation failed"),
            )
        return resolved["patient_id"]
```

- [ ] **Step 4: Run, expect `4 passed`**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/templates/medical_general.py \
        tests/core/test_medical_writer.py
git commit -m "feat(intake): add MedicalRecordWriter — absorbs deferred patient creation"
```

---

## Task 7: Post-confirm hooks — diagnosis, tasks, notify

**Files:**
- Create: `src/domain/intake/hooks/__init__.py`
- Create: `src/domain/intake/hooks/medical.py`
- Create: `tests/core/test_medical_hooks.py`

Three hooks, one effect each. Each is a thin forward to an existing codepath:
- `TriggerDiagnosisPipelineHook.run` → `safe_create_task(run_diagnosis(...))` (from `intake_summary.py:280-288`)
- `GenerateFollowupTasksHook.run` → `generate_tasks_from_record(...)` (from `confirm.py:160-178`)
- `NotifyDoctorHook.run` → `send_doctor_notification(...)` (from `intake_summary.py:292-299`)

All three must swallow exceptions and log — the engine's loop treats hook failure as non-blocking per spec §5d.

- [ ] **Step 1: Write failing tests**

`tests/core/test_medical_hooks.py`:

```python
"""Post-confirm hooks — all three are thin forwards to existing codepaths.

Each must swallow exceptions and log (engine expects best-effort semantics).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.intake.protocols import PersistRef, SessionState


def _session() -> SessionState:
    return SessionState(
        id="s1", doctor_id="d1", patient_id=42, mode="patient",
        status="confirmed", template_id="medical_general_v1",
        collected={}, conversation=[], turn_count=5,
    )


@pytest.mark.asyncio
async def test_trigger_diagnosis_calls_safe_create_task():
    hook = TriggerDiagnosisPipelineHook()
    with patch(
        "domain.intake.hooks.medical._safe_create_task",
    ) as mock_safe, patch(
        "domain.intake.hooks.medical._run_diagnosis",
    ) as mock_run:
        mock_run.return_value = "coro-sentinel"
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})

    mock_run.assert_called_once_with(doctor_id="d1", record_id=99)
    mock_safe.assert_called_once()
    # safe_create_task wraps the coroutine with a name
    _, kwargs = mock_safe.call_args
    assert kwargs.get("name") == "diagnosis-99"


@pytest.mark.asyncio
async def test_trigger_diagnosis_swallows_exceptions():
    hook = TriggerDiagnosisPipelineHook()
    with patch(
        "domain.intake.hooks.medical._safe_create_task",
        side_effect=RuntimeError("boom"),
    ):
        # Must NOT raise
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})


@pytest.mark.asyncio
async def test_notify_doctor_sends_notification():
    hook = NotifyDoctorHook()
    with patch(
        "domain.intake.hooks.medical._send_doctor_notification",
        new=AsyncMock(),
    ) as mock_notify:
        collected = {"_patient_name": "王五"}
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[0] == "d1"
    assert "王五" in args[1]


@pytest.mark.asyncio
async def test_notify_doctor_swallows_exceptions():
    hook = NotifyDoctorHook()
    with patch(
        "domain.intake.hooks.medical._send_doctor_notification",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})


@pytest.mark.asyncio
async def test_generate_followup_tasks_calls_generator():
    hook = GenerateFollowupTasksHook()
    with patch(
        "domain.intake.hooks.medical._get_patient_for_doctor",
        new=AsyncMock(return_value=type("P", (), {"name": "赵六"})()),
    ), patch(
        "domain.intake.hooks.medical._generate_tasks_from_record",
        new=AsyncMock(return_value=[1, 2, 3]),
    ) as mock_gen:
        collected = {
            "orders_followup": "1周复诊",
            "treatment_plan": "布洛芬",
        }
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), collected)

    mock_gen.assert_called_once()
    _, kwargs = mock_gen.call_args
    assert kwargs["doctor_id"] == "d1"
    assert kwargs["record_id"] == 99
    assert kwargs["orders_followup"] == "1周复诊"
    assert kwargs["treatment_plan"] == "布洛芬"


@pytest.mark.asyncio
async def test_generate_followup_tasks_swallows_exceptions():
    hook = GenerateFollowupTasksHook()
    with patch(
        "domain.intake.hooks.medical._get_patient_for_doctor",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})
```

- [ ] **Step 2: Run, expect failures (module doesn't exist)**

- [ ] **Step 3: Create the hooks package**

`src/domain/intake/hooks/__init__.py`:

```python
"""Post-confirm hooks, split per domain concern."""
```

`src/domain/intake/hooks/medical.py`:

```python
"""Medical template post-confirm hooks.

Each hook wraps one existing side effect from the pre-Phase-1 confirm paths.
Failures are logged and swallowed — the engine treats hooks as best-effort.
"""
from __future__ import annotations

from db.crud.patient import get_patient_for_doctor as _get_patient_for_doctor
from db.engine import AsyncSessionLocal
from domain.diagnosis import run_diagnosis as _run_diagnosis
from domain.intake.protocols import PersistRef, SessionState
from domain.tasks.from_record import (
    generate_tasks_from_record as _generate_tasks_from_record,
)
from domain.tasks.notifications import (
    send_doctor_notification as _send_doctor_notification,
)
from utils.log import log, safe_create_task as _safe_create_task


class TriggerDiagnosisPipelineHook:
    name = "trigger_diagnosis_pipeline"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            _safe_create_task(
                _run_diagnosis(doctor_id=session.doctor_id, record_id=ref.id),
                name=f"diagnosis-{ref.id}",
            )
            log(f"[intake] diagnosis triggered for record={ref.id}")
        except Exception as e:
            log(f"[intake] diagnosis trigger failed: {e}", level="warning")


class NotifyDoctorHook:
    name = "notify_doctor"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            patient_name = collected.get("_patient_name") or "患者"
            await _send_doctor_notification(
                session.doctor_id,
                f"患者【{patient_name}】已完成预问诊，请查看待审核记录。",
            )
        except Exception as e:
            log(f"[intake] doctor notification failed: {e}", level="warning")


class GenerateFollowupTasksHook:
    name = "generate_followup_tasks"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                patient = await _get_patient_for_doctor(
                    db, session.doctor_id, session.patient_id,
                )
            patient_name = patient.name if patient else ""
            task_ids = await _generate_tasks_from_record(
                doctor_id=session.doctor_id,
                patient_id=session.patient_id,
                record_id=ref.id,
                orders_followup=collected.get("orders_followup"),
                treatment_plan=collected.get("treatment_plan"),
                patient_name=patient_name,
            )
            if task_ids:
                log(
                    f"[intake-confirm] auto-created {len(task_ids)} "
                    f"follow-up tasks: {task_ids}"
                )
        except Exception as e:
            log(
                f"[intake-confirm] task generation failed "
                f"(non-blocking): {e}",
                level="warning",
            )
```

- [ ] **Step 4: Run, expect `6 passed`**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/hooks/__init__.py \
        src/domain/intake/hooks/medical.py \
        tests/core/test_medical_hooks.py
git commit -m "feat(intake): add medical post-confirm hooks — diagnosis/notify/followup"
```

---

## Task 8: Template binding + registry

**Files:**
- Modify: `src/domain/intake/templates/medical_general.py`
- Modify: `src/domain/intake/templates/__init__.py`
- Create: `tests/core/test_template_registry.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_template_registry.py`:

```python
"""TEMPLATES registry + medical_general_v1 binding."""
from __future__ import annotations

import pytest

from domain.intake.templates import (
    TEMPLATES, UnknownTemplate, get_template,
)
from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor, GeneralMedicalTemplate, MedicalBatchExtractor,
    MedicalRecordWriter,
)
from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)


def test_medical_general_v1_registered():
    t = get_template("medical_general_v1")
    assert isinstance(t, GeneralMedicalTemplate)


def test_unknown_template_raises():
    with pytest.raises(UnknownTemplate):
        get_template("nonexistent_v1")


def test_template_exposes_correct_id_and_kind():
    t = get_template("medical_general_v1")
    assert t.id == "medical_general_v1"
    assert t.kind == "medical"
    assert t.requires_doctor_review is True
    assert set(t.supported_modes) == {"patient", "doctor"}


def test_template_wires_all_components():
    t = get_template("medical_general_v1")
    assert isinstance(t.extractor, GeneralMedicalExtractor)
    assert isinstance(t.batch_extractor, MedicalBatchExtractor)
    assert isinstance(t.writer, MedicalRecordWriter)


def test_patient_hooks_include_diagnosis_and_notify():
    t = get_template("medical_general_v1")
    patient_hooks = t.post_confirm_hooks["patient"]
    hook_types = {type(h) for h in patient_hooks}
    assert TriggerDiagnosisPipelineHook in hook_types
    assert NotifyDoctorHook in hook_types


def test_doctor_hooks_include_only_followup_tasks():
    """Phase 1 preserves the asymmetric behavior: doctor-mode does NOT fire
    diagnosis. Spec §8 flags this as open product decision; Phase 4 revisits."""
    t = get_template("medical_general_v1")
    doctor_hooks = t.post_confirm_hooks["doctor"]
    hook_types = {type(h) for h in doctor_hooks}
    assert GenerateFollowupTasksHook in hook_types
    # Explicit negative assertions — this is the asymmetry spec §8 flags
    assert TriggerDiagnosisPipelineHook not in hook_types
    assert NotifyDoctorHook not in hook_types


def test_registry_is_dict_of_exactly_one_template_phase1():
    """Phase 1 ships with exactly one template. Phase 3 adds form_satisfaction_v1."""
    assert set(TEMPLATES.keys()) == {"medical_general_v1"}
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Append `GeneralMedicalTemplate` to `medical_general.py`**

```python
# ---- template binding -------------------------------------------------------

from dataclasses import dataclass, field

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)


@dataclass
class GeneralMedicalTemplate:
    """medical_general_v1. Binds all the medical-specific components."""
    id: str = "medical_general_v1"
    kind: str = "medical"
    display_name: str = "通用医学问诊"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralMedicalExtractor)
    batch_extractor: BatchExtractor | None = field(default_factory=MedicalBatchExtractor)
    writer: Writer = field(default_factory=MedicalRecordWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
            ],
            # §8 open question — doctor-mode is deliberately NOT firing
            # diagnosis in Phase 1 because that matches today's confirm.py.
            # Phase 4 revisits.
            "doctor": [
                GenerateFollowupTasksHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
```

- [ ] **Step 4: Register in the registry**

Modify `src/domain/intake/templates/__init__.py`:

```python
"""Template registry. Populated on import."""
from __future__ import annotations

from domain.intake.protocols import Template
from domain.intake.templates.medical_general import GeneralMedicalTemplate


class UnknownTemplate(KeyError):
    """Raised when a session references a template id not in TEMPLATES."""


TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
}


def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
```

- [ ] **Step 5: Run, expect `7 passed`**

- [ ] **Step 6: Commit**

```
git add src/domain/intake/templates/__init__.py \
        src/domain/intake/templates/medical_general.py \
        tests/core/test_template_registry.py
git commit -m "feat(intake): bind GeneralMedicalTemplate + register medical_general_v1"
```

---

## Task 9: `IntakeEngine` skeleton + `next_turn`

**Files:**
- Create: `src/domain/intake/engine.py`
- Create: `tests/core/test_intake_engine_turn.py`

The engine's `next_turn` is a thin reframe of `_intake_turn_inner` from `intake_turn.py`. It:
1. Acquires the session lock (unchanged).
2. Loads the session.
3. Appends user message to conversation, increments turn_count.
4. Checks the turn cap.
5. Calls the extractor's prompt_partial + the LLM (via `structured_call` with a schema from `build_response_schema`).
6. Calls extractor.merge to update `collected`.
7. Checks completeness via extractor.completeness.
8. Persists session.
9. Returns `TurnResult`.

For Phase 1, to avoid rewriting the LLM call loop from scratch (which is 70+ lines of guards, retries, post-processing), the engine's `next_turn` **forwards to the existing `intake_turn()` function** and wraps its response into a `TurnResult`. The protocol is preserved; Phase 2 will inline the loop into the engine using the template's extractor.

- [ ] **Step 1: Write failing tests**

`tests/core/test_intake_engine_turn.py`:

```python
"""IntakeEngine.next_turn — Phase 1 forwards to legacy intake_turn().

These tests confirm the engine's contract (input session_id + text →
TurnResult) and that the legacy function is still the execution engine.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.engine import IntakeEngine
from domain.intake.protocols import CompletenessState, TurnResult


@pytest.fixture
def engine():
    return IntakeEngine()


@pytest.mark.asyncio
async def test_next_turn_returns_turnresult(engine):
    fake_legacy_response = type("R", (), {
        "reply": "ok",
        "collected": {"chief_complaint": "头痛"},
        "progress": {"filled": 1, "total": 14},
        "status": "active",
        "missing": [],
        "suggestions": ["休息"],
        "ready_to_review": False,
        "retryable": False,
        "patient_name": None,
        "patient_gender": None,
        "patient_age": None,
    })()

    with patch(
        "domain.intake.engine._legacy_intake_turn",
        new=AsyncMock(return_value=fake_legacy_response),
    ):
        result = await engine.next_turn(
            session_id="s1", user_input="hello",
        )

    assert isinstance(result, TurnResult)
    assert result.reply == "ok"
    assert result.suggestions == ["休息"]
    assert isinstance(result.state, CompletenessState)


@pytest.mark.asyncio
async def test_next_turn_surfaces_patient_metadata(engine):
    fake = type("R", (), {
        "reply": "", "collected": {}, "progress": {"filled": 0, "total": 7},
        "status": "active", "missing": [], "suggestions": [],
        "ready_to_review": False, "retryable": False,
        "patient_name": "张三", "patient_gender": "男", "patient_age": "50",
    })()
    with patch(
        "domain.intake.engine._legacy_intake_turn",
        new=AsyncMock(return_value=fake),
    ):
        result = await engine.next_turn("s1", "x")
    assert result.metadata.get("patient_name") == "张三"
    assert result.metadata.get("patient_gender") == "男"
    assert result.metadata.get("patient_age") == "50"


@pytest.mark.asyncio
async def test_next_turn_state_reflects_completeness_can_complete(engine):
    fake = type("R", (), {
        "reply": "", "collected": {"chief_complaint": "x", "present_illness": "y"},
        "progress": {"filled": 2, "total": 14},
        "status": "reviewing", "missing": [], "suggestions": [],
        "ready_to_review": True, "retryable": False,
        "patient_name": None, "patient_gender": None, "patient_age": None,
    })()
    with patch(
        "domain.intake.engine._legacy_intake_turn",
        new=AsyncMock(return_value=fake),
    ):
        result = await engine.next_turn("s1", "x")
    assert result.state.can_complete is True
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

- [ ] **Step 3: Create `engine.py`**

`src/domain/intake/engine.py`:

```python
"""IntakeEngine — template-agnostic orchestrator.

Spec §5c (next_turn), §5d (confirm). Phase 1 forwards heavy lifting to
legacy functions; Phase 2 inlines them using the template's protocols.
"""
from __future__ import annotations

from typing import Any

from domain.intake.protocols import (
    CompletenessState, PersistRef, SessionState, Template, TurnResult,
)
from domain.intake.templates import get_template

# Legacy imports — renamed with leading underscore to make Phase 2 sweep obvious.
from domain.patients.intake_turn import intake_turn as _legacy_intake_turn
from domain.patients.intake_session import (
    load_session as _load_session,
    save_session as _save_session,
)


class IntakeEngine:
    """Generic engine. One instance serves every template.

    Phase 1: turn loop forwards to domain.patients.intake_turn.intake_turn.
    Phase 2: inlines the loop using template.extractor.* methods.
    """

    async def next_turn(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResult:
        """Execute one turn. Phase 1 is a structural passthrough."""
        raw = await _legacy_intake_turn(session_id, user_input)

        state = CompletenessState(
            can_complete=bool(raw.ready_to_review),
            required_missing=[],
            recommended_missing=list(raw.missing or []),
            optional_missing=[],
            next_focus=(raw.missing[0] if raw.missing else None),
        )

        metadata: dict[str, Any] = {}
        if raw.patient_name:
            metadata["patient_name"] = raw.patient_name
        if raw.patient_gender:
            metadata["patient_gender"] = raw.patient_gender
        if raw.patient_age:
            metadata["patient_age"] = raw.patient_age

        return TurnResult(
            reply=raw.reply,
            suggestions=list(raw.suggestions or []),
            state=state,
            metadata=metadata,
        )

    async def confirm(
        self,
        session_id: str,
        doctor_edits: dict[str, str] | None = None,
        override_patient_name: str | None = None,
    ) -> PersistRef:
        """Defined in Task 10. Raises NotImplementedError in Task 9."""
        raise NotImplementedError  # Task 10 fills this in
```

- [ ] **Step 4: Run, expect `3 passed`**

- [ ] **Step 5: Commit**

```
git add src/domain/intake/engine.py \
        tests/core/test_intake_engine_turn.py
git commit -m "feat(intake): add IntakeEngine.next_turn — Phase 1 legacy forwarder"
```

---

## Task 10: `IntakeEngine.confirm` — mode-aware orchestration

**Files:**
- Modify: `src/domain/intake/engine.py`
- Create: `tests/core/test_intake_engine_confirm.py`

The engine's `confirm` replaces the hand-rolled logic in `confirm.py` + `intake_summary.submit_intake`. Flow:

1. Load the session; get the template.
2. Merge doctor edits (if any) into `collected` via `template.extractor.merge`.
3. If `template.batch_extractor` is present, call `batch_extractor.extract` with conversation + patient-info context; preserve underscore metadata; replace `collected`.
4. Call `template.writer.persist(session_state, collected)` → `PersistRef`.
5. For each hook in `template.post_confirm_hooks[session.mode]`, call `hook.run(session_state, ref, collected)` — best-effort.
6. Mark session `confirmed` + save. Release lock.
7. Return `PersistRef`.

Special case: `override_patient_name` from the doctor confirm endpoint — if provided, write to `collected["_patient_name"]` before the batch extract (current behavior at `confirm.py:76-77`).

- [ ] **Step 1: Write failing tests**

`tests/core/test_intake_engine_confirm.py`:

```python
"""IntakeEngine.confirm — mode-aware orchestration.

Spec §5d. Patient mode fires diagnosis + notify; doctor mode fires only
follow-up tasks (asymmetric — see §8 open question).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.engine import IntakeEngine
from domain.intake.protocols import PersistRef, SessionState


def _session(mode="doctor", patient_id=42):
    return SessionState(
        id="s1", doctor_id="d1", patient_id=patient_id, mode=mode,
        status="active", template_id="medical_general_v1",
        collected={"_patient_name": "张三", "chief_complaint": "头痛"},
        conversation=[{"role": "user", "content": "头痛"}],
        turn_count=3,
    )


@pytest.fixture
def engine():
    return IntakeEngine()


@pytest.mark.asyncio
async def test_confirm_runs_batch_extract_when_template_has_one(engine):
    sess = _session()
    fake_ref = PersistRef(kind="medical_record", id=99)

    with patch(
        "domain.intake.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.intake.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.intake.engine._release_session_lock",
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "头痛 (batch)"}),
    ) as mock_batch, patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ) as mock_persist, patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ) as mock_hook:
        ref = await engine.confirm(session_id="s1")

    assert ref == fake_ref
    mock_batch.assert_awaited_once()
    mock_persist.assert_awaited_once()
    # Doctor-mode hooks: only the follow-up tasks hook
    mock_hook.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_patient_mode_fires_diagnosis_and_notify(engine):
    sess = _session(mode="patient")
    fake_ref = PersistRef(kind="medical_record", id=100)

    with patch(
        "domain.intake.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.intake.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.intake.engine._release_session_lock",
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value=None),
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.intake.hooks.medical.TriggerDiagnosisPipelineHook.run",
        new=AsyncMock(),
    ) as mock_diag, patch(
        "domain.intake.hooks.medical.NotifyDoctorHook.run",
        new=AsyncMock(),
    ) as mock_notify, patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ) as mock_followup:
        await engine.confirm("s1")

    mock_diag.assert_awaited_once()
    mock_notify.assert_awaited_once()
    mock_followup.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_preserves_underscore_metadata_across_batch_extract(engine):
    """Per confirm.py:64-67 — underscore-prefixed metadata fields must
    survive the re-extraction."""
    sess = _session()
    sess.collected["_patient_gender"] = "男"
    sess.collected["_patient_age"] = "45岁"

    fake_ref = PersistRef(kind="medical_record", id=77)
    persist_called_with: dict = {}

    async def _capture_persist(self, session, collected):
        persist_called_with["collected"] = dict(collected)
        return fake_ref

    with patch(
        "domain.intake.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.intake.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.intake.engine._release_session_lock",
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "NEW"}),
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        _capture_persist,
    ), patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ):
        await engine.confirm("s1")

    assert persist_called_with["collected"]["_patient_name"] == "张三"
    assert persist_called_with["collected"]["_patient_gender"] == "男"
    assert persist_called_with["collected"]["_patient_age"] == "45岁"
    assert persist_called_with["collected"]["chief_complaint"] == "NEW"


@pytest.mark.asyncio
async def test_confirm_hook_failure_does_not_unwind_persist(engine):
    """Per spec §5d: post-confirm hooks are best-effort. A failing hook
    logs a warning and the confirm still returns the PersistRef."""
    sess = _session()
    fake_ref = PersistRef(kind="medical_record", id=88)

    with patch(
        "domain.intake.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.intake.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.intake.engine._release_session_lock",
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value=None),
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        # Must NOT raise
        ref = await engine.confirm("s1")

    assert ref == fake_ref
```

- [ ] **Step 2: Run, expect NotImplementedError + subsequent failures**

- [ ] **Step 3: Implement `confirm` in `engine.py`**

Replace the `NotImplementedError` stub:

```python
    async def confirm(
        self,
        session_id: str,
        doctor_edits: dict[str, str] | None = None,
        override_patient_name: str | None = None,
    ) -> PersistRef:
        """Confirm the session. Runs batch re-extract, persist, then
        best-effort hooks. Marks the session confirmed.

        Doctor-mode callers may pass `override_patient_name` to force the
        patient name into `_patient_name` before batch extract (preserves
        the current behavior at confirm.py:76-77).
        """
        from domain.intake.templates.medical_general import (
            MedicalBatchExtractor, MedicalRecordWriter,
        )

        sess = await _load_session_state(session_id)
        template = get_template(sess.template_id)

        collected = dict(sess.collected)

        if override_patient_name:
            collected["_patient_name"] = override_patient_name.strip()

        if doctor_edits:
            collected = template.extractor.merge(collected, doctor_edits)

        if template.batch_extractor is not None:
            ctx = {
                "name": collected.get("_patient_name", ""),
                "gender": collected.get("_patient_gender", ""),
                "age": collected.get("_patient_age", ""),
            }
            re_extracted = await template.batch_extractor.extract(
                sess.conversation, ctx, sess.mode,
            )
            if re_extracted:
                # Preserve engine-level underscore metadata across re-extract.
                for k, v in collected.items():
                    if k.startswith("_") and k not in re_extracted:
                        re_extracted[k] = v
                collected = re_extracted

        ref = await template.writer.persist(sess, collected)

        for hook in template.post_confirm_hooks[sess.mode]:
            try:
                await hook.run(sess, ref, collected)
            except Exception as e:
                from utils.log import log
                log(
                    f"[engine-confirm] hook {hook.name} failed: {e}",
                    level="warning",
                )

        # Mark confirmed and release lock
        sess_updated = sess.model_copy(update={"status": "confirmed"})
        await _save_session_state(sess_updated)
        _release_session_lock(session_id)

        return ref
```

- [ ] **Step 4: Add `_load_session_state` / `_save_session_state` / `_release_session_lock` helpers**

At the top of `engine.py`, next to the existing legacy imports:

```python
from domain.patients.intake_turn import release_session_lock as _release_session_lock


async def _load_session_state(session_id: str) -> SessionState:
    raw = await _load_session(session_id)
    if raw is None:
        raise LookupError(f"session {session_id} not found")
    return SessionState(
        id=raw.id,
        doctor_id=raw.doctor_id,
        patient_id=raw.patient_id,
        mode=raw.mode,
        status=raw.status,
        template_id=raw.template_id,
        collected=raw.collected,
        conversation=raw.conversation,
        turn_count=raw.turn_count,
    )


async def _save_session_state(sess: SessionState) -> None:
    raw = await _load_session(sess.id)
    if raw is None:
        return
    raw.status = sess.status
    raw.collected = sess.collected
    raw.conversation = sess.conversation
    raw.turn_count = sess.turn_count
    raw.patient_id = sess.patient_id
    await _save_session(raw)
```

- [ ] **Step 5: Run all engine tests, expect `7 passed` (3 from Task 9 + 4 from Task 10)**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_engine_turn.py \
    tests/core/test_intake_engine_confirm.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 6: Commit**

```
git add src/domain/intake/engine.py \
        tests/core/test_intake_engine_confirm.py
git commit -m "feat(intake): add IntakeEngine.confirm — mode-aware orchestration"
```

---

## Task 11: Route doctor `/confirm` through the engine

**Files:**
- Modify: `src/channels/web/doctor_intake/confirm.py`

**Scope note:** Phase 1 routes the `/confirm` path through `engine.confirm()` — that's where the polymorphic fan-out and asymmetric side effects live, so it's where engine routing pays off. The `/turn` endpoints continue calling `intake_turn()` directly in Phase 1; `engine.next_turn` exists (Task 9) and forwards to the same function internally, but wiring `/turn` through it yields zero structural benefit while adding response-shape translation complexity. Phase 2 inlines the turn loop into the engine using the template's extractor — at that point the `/turn` endpoints flip too.

- [ ] **Step 1: Inspect the current `/confirm` endpoint**

```
sed -n '20,185p' src/channels/web/doctor_intake/confirm.py
```

Note the flow: resolve doctor → verify session → guard status/empty-collected → batch extract → deferred patient create → insert record → update patient activity → set status confirmed → release lock → generate follow-up tasks.

After this task, the engine owns everything from "batch extract" through "follow-up tasks". The endpoint body shrinks to: auth, guards, engine call, HTTP response.

- [ ] **Step 2: Replace the body of `/confirm` with `engine.confirm()` + thin HTTP glue**

Rewrite `src/channels/web/doctor_intake/confirm.py` to:

```python
"""Doctor intake — confirm and cancel endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from domain.intake.engine import IntakeEngine
from utils.log import log

from .shared import (
    IntakeConfirmResponse,
    _resolve_doctor_id,
    _verify_session,
    _build_clinical_text,
)

router = APIRouter()

_ENGINE = IntakeEngine()


@router.post("/confirm", response_model=IntakeConfirmResponse)
async def intake_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    patient_name: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(
        session_id, resolved_doctor, candidate_doctor_id=doctor_id,
    )

    if session.status not in ("active",):
        raise HTTPException(
            400, f"Session status is '{session.status}', cannot confirm",
        )

    collected = session.collected or {}
    if not any(v for k, v in collected.items() if not k.startswith("_")):
        raise HTTPException(400, "No collected data to confirm")

    ref = await _ENGINE.confirm(
        session_id=session.id,
        override_patient_name=(patient_name.strip() if patient_name else None),
    )

    # Build the preview + status from the freshly inserted record
    from db.models.records import MedicalRecordDB
    async with db.begin():
        record = await db.get(MedicalRecordDB, ref.id)
    preview = _build_clinical_text({
        k: getattr(record, k, None) for k in (
            "chief_complaint", "present_illness", "diagnosis",
            "treatment_plan", "orders_followup",
        )
    }) if record else None

    return IntakeConfirmResponse(
        status=record.status if record else "confirmed",
        preview=(preview[:200] if preview else None),
        pending_id=str(ref.id),
    )


@router.post("/cancel")
async def intake_cancel_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(
        session_id, resolved_doctor, candidate_doctor_id=doctor_id,
    )

    from domain.patients.intake_session import save_session
    from db.models.intake_session import IntakeStatus

    session.status = IntakeStatus.abandoned
    await save_session(session)

    from domain.patients.intake_turn import release_session_lock
    release_session_lock(session_id)

    return {"status": "abandoned"}
```

Notice: the rewritten `/confirm` reads the freshly-inserted record from the DB after `engine.confirm` returns — the preview is now derived from the persisted row, not from `collected`. This is a deliberate simplification that also closes a latent bug where `collected` could drift from what was actually persisted.

- [ ] **Step 3: Run the full intake suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_intake_session_mode.py \
    tests/core/test_intake_session_template_id.py \
    tests/core/test_intake_engine_turn.py \
    tests/core/test_intake_engine_confirm.py \
    tests/core/test_medical_writer.py \
    tests/core/test_medical_hooks.py \
    tests/core/test_template_registry.py \
    tests/core/test_medical_extractor.py \
    tests/core/test_medical_batch_extractor.py \
    tests/core/test_medical_field_specs.py \
    tests/core/test_intake_protocols.py \
    tests/core/test_intake_contract.py \
    tests/core/test_doctor_first_turn_template_id.py \
    -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

All should pass. If an endpoint-level integration test exists that exercises `/confirm`, run it too — grep `tests/` for `intake_confirm_endpoint` references.

- [ ] **Step 4: Commit**

```
git add src/channels/web/doctor_intake/confirm.py
git commit -m "feat(intake): route doctor /confirm through IntakeEngine"
```

---

## Task 12: Route patient confirm path through the engine

**Files:**
- Modify: `src/domain/patients/intake_summary.py`

The patient-side confirm lives in `submit_intake()` at `src/domain/patients/intake_summary.py` (around line 200-305). It does: batch-extract, insert record, fire diagnosis, notify doctor. All of this is now the engine's job when the session is patient-mode.

Replace the body of `submit_intake` with a thin wrapper around `engine.confirm()`. Preserve the function's return shape (`{"record_id": int, "review_id": None}`) so existing callers don't break.

- [ ] **Step 1: Inspect the current function signature and return shape**

```
grep -n "def submit_intake" src/domain/patients/intake_summary.py
sed -n '200,310p' src/domain/patients/intake_summary.py
```

Note the exact parameters the function takes and the callers:

```
grep -rn "submit_intake" src --include="*.py"
```

- [ ] **Step 2: Rewrite `submit_intake` as a thin engine wrapper**

The function currently takes `(session_id, doctor_id, patient_id, patient_name)`. Keep that signature. Body becomes:

```python
async def submit_intake(
    session_id: str,
    doctor_id: str,
    patient_id: int | None,
    patient_name: str,
) -> dict:
    """Patient-side confirm. Phase 1: delegates to IntakeEngine.confirm.

    Preserves the return shape expected by patient_intake_routes.py.
    """
    from domain.intake.engine import IntakeEngine
    engine = IntakeEngine()
    ref = await engine.confirm(
        session_id=session_id,
        override_patient_name=patient_name or None,
    )
    # review_id was from a review-task entity that no longer exists
    # (commit 4a2eba87). Kept in the response shape for backwards compat.
    return {"record_id": ref.id, "review_id": None}
```

Remove the now-dead code below it (the hand-rolled batch-extract + insert + diagnosis + notify block, lines ~240-299). The imports at the top of the file can stay — other functions in the same file (`batch_extract_from_transcript`, etc.) still use them.

- [ ] **Step 3: Run**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/ tests/db/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

All intake-related tests should still pass.

- [ ] **Step 4: Commit**

```
git add src/domain/patients/intake_summary.py
git commit -m "feat(intake): route patient submit_intake through IntakeEngine"
```

---

## Task 13: Regression sweep — sim baseline, full suite, grep invariants

**Files:** none — verification only.

- [ ] **Step 1: Full suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent 2>&1 | tail -30
```

Expected: same pass count as main baseline. New failures = Phase 1 regression.

- [ ] **Step 2: Diagnosis prompt sniff**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/prompts/test_diagnosis_prompt_sniff.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: green. Phase 1 does not change prompts.

- [ ] **Step 3: Reply-sim baseline (behavior preservation bar)**

If the repo has a sim runner (check `scripts/` or `tests/sim/`), run it against main + against HEAD. Delta ≤ 2%. If there is no scripted runner, note the deferral — the smaller unit-level tests are the backstop.

```
ls scripts/ | grep -i sim
ls tests/sim/ 2>/dev/null
```

- [ ] **Step 4: Invariant grep**

```
# The legacy intake_turn() is still reachable (engine wraps it)
grep -rn "from domain.patients.intake_turn import intake_turn" src

# The engine exists and is wired into confirm paths
grep -rn "IntakeEngine" src --include="*.py"

# No accidental direct import of legacy submit_intake inside the engine
grep -n "submit_intake" src/domain/intake/engine.py
```

Expected: `submit_intake` should NOT appear in `engine.py`. The engine owns confirm; `submit_intake` calls the engine, not the other way around.

- [ ] **Step 5: Alembic head unchanged**

```
cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/alembic heads
```

Expected: `c9f8d2e14a20 (head)`. Phase 1 does not migrate.

- [ ] **Step 6: Commit history sanity**

```
git log fa857fac..HEAD --oneline | head -20
```

Expected: 12 Phase-1 commits plus any Phase-0 commits already on the branch. Each with a `feat(intake)` / `refactor` / `chore` prefix.

- [ ] **Step 7: No commit — Phase 1 complete**

Working tree should be clean of Phase 1 source files. Check:

```
git status
```

---

## Phase 1 completion checklist

- [ ] `src/domain/intake/protocols.py` defines `FieldSpec`, `FieldExtractor`, `BatchExtractor`, `Writer`, `PostConfirmHook`, `Template`, `SessionState`, `PersistRef`, `TurnResult`, `CompletenessState`, `EngineConfig`.
- [ ] `src/domain/intake/contract.py::build_response_schema` round-trips `string | text | number | enum` field types through Pydantic.
- [ ] `src/domain/intake/engine.py::IntakeEngine.next_turn` forwards to legacy `intake_turn` and returns `TurnResult`.
- [ ] `src/domain/intake/engine.py::IntakeEngine.confirm` merges edits, runs batch extract when present, calls writer, fires mode-appropriate hooks, marks session confirmed.
- [ ] `src/domain/intake/templates/medical_general.py` exposes `GeneralMedicalTemplate`, `GeneralMedicalExtractor`, `MedicalBatchExtractor`, `MedicalRecordWriter`, `MEDICAL_FIELDS`.
- [ ] `src/domain/intake/hooks/medical.py` exposes three hooks (diagnosis, notify, follow-up tasks) each swallowing exceptions.
- [ ] `src/domain/intake/templates/__init__.py::TEMPLATES` contains exactly `medical_general_v1`.
- [ ] Doctor `/confirm` endpoint calls `engine.confirm()`.
- [ ] Patient `submit_intake` calls `engine.confirm()`.
- [ ] All unit tests (~40+ new) pass.
- [ ] Full test suite matches main baseline.
- [ ] `reply_sim` (if available) within ±2% of baseline.

## What Phase 1 does NOT do (saved for Phase 2+)

- Move medical logic out of `intake_models.py` / `completeness.py` / `doctor_intake/shared.py` → Phase 2.
- Inline the turn loop from `intake_turn.py` into `engine.next_turn` → Phase 2.
- Wire `doctor.preferred_template_id` fallback into session-create precedence → can ship independently in Phase 1.5 if desired.
- Build specialty variants → Phase 4.
- Change prompt files → separate effort.
- Build the `/form_responses` read-back endpoints → Phase 3.
- Resolve the §8 open product question (doctor-mode diagnosis asymmetry) → before Phase 4 ships.

Phase 1 is the scaffolding. The medical logic still lives in its pre-Phase-1 homes; only the *call graph* changes.
