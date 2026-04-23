# Interview Pipeline Extensibility — Phase 2 (Medical Template Extraction)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move medical-specific logic (completeness/merge/field metadata) from the scattered pre-Phase-0 files into `GeneralMedicalTemplate`. Convert the old files into thin deprecation shims that re-export from the template so legacy callers keep working for one release. Route the remaining `/turn` endpoints through `engine.next_turn()`. **Zero behavior change** — the turn loop itself still forwards to the pre-Phase-1 function (Phase 2.5 inlines that).

**Architecture:** In-place swap. Phase 1 established the template as a thin delegator; Phase 2 inverts the arrow — the template is now the source of truth, and the old files (`completeness.py`, `interview_models.py`, `doctor_interview/shared.py`) become re-exports with `DeprecationWarning`. Legacy callers see no change; new callers import directly from the template. `/turn` endpoints are flipped to call `engine.next_turn()` which still forwards to `_legacy_interview_turn` internally — a one-hop indirection that makes the engine the canonical entry point.

**Tech Stack:** Pydantic 2.x, `warnings.warn(DeprecationWarning)`, pytest.

**Reference:** Spec `docs/superpowers/specs/2026-04-22-interview-pipeline-extensibility-design.md` §§ 3a, 3b, 6a (Phase 2 row), 6b (shim pattern), 7a (behavior bar).

**Explicitly out of scope for Phase 2** (saved for Phase 2.5 or later):
- Inlining the turn loop from `interview_turn.py` into `engine.next_turn`. That function's ~130 lines (session locks, retries, LLM parsing, fallbacks, ready-to-review post-processing) stay where they are; the engine forwards to it. Phase 2.5 does the inline after the user can run `reply_sim` to catch drift.
- Moving prompt construction (`_call_interview_llm` + `compose_for_X_interview`) into `GeneralMedicalExtractor.prompt_partial`. Phase 1's stub `_composer_kwargs` gets one improvement (threading real session context), but the prompt-file ownership stays with `prompt_composer`.
- Full deletion of the legacy files. They become shims this release, delete next release.

---

## Preconditions

- Phase 1 landed (12 commits, ending at `12abe3a3`).
- All 60 Phase 1 tests pass. Full suite: 447 passed, 94 skipped.
- Alembic head: `c9f8d2e14a20` (unchanged).
- `.venv/bin/python` at `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python`.
- Test incantation:
  ```
  /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest <args> \
      --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
  ```

## Behavior-preservation bar

- Full test suite matches post-Phase-1 baseline (447 passed).
- Phase 1 test files still pass (60 tests: `tests/core/test_interview_*.py`, `test_medical_*.py`, `test_template_registry.py`, `test_form_response_model.py`).
- **Sim gate (user-executed, not task-automated):** After Task 7 ships, user runs `reply_sim` before marking Phase 2 done. Delta vs main baseline ≤ 2%. If unavailable, unit tests are the backstop.

## File map

**Modify:**
- `src/domain/interview/templates/medical_general.py` — inline completeness + merge logic, declarative MEDICAL_FIELDS, real prompt_partial context threading (Tasks 1, 2, 4, 6).
- `src/domain/patients/completeness.py` — gut → shim re-exporting from template (Task 3).
- `src/domain/patients/interview_models.py` — gut → shim with `ExtractedClinicalFields = build_response_schema(MEDICAL_FIELDS)` (Task 5).
- `src/channels/web/doctor_interview/turn.py` — route `/turn` first-turn + continue through `engine.next_turn` (Task 7).
- `src/channels/web/patient_interview_routes.py` — route patient `/turn` through `engine.next_turn` (Task 7).

**Create:**
- Tests for each change: `tests/core/test_template_completeness.py`, `tests/core/test_template_merge.py`, `tests/core/test_completeness_shim.py`, `tests/core/test_interview_models_shim.py`.

**Not touched in Phase 2** (deferred):
- `src/domain/patients/interview_turn.py` — stays as the legacy turn-loop source.
- `src/agent/prompt_composer.py` — unchanged.
- `src/channels/web/doctor_interview/shared.py` — `_CARRY_FORWARD_FIELDS` can shim-in-place, but deferred to a later cleanup since it's a single constant that's already referenced via `carry_forward_modes` on the FieldSpec.

---

## Task 1: Inline merge_extracted into `GeneralMedicalExtractor.merge`

**Files:**
- Modify: `src/domain/interview/templates/medical_general.py`
- Create: `tests/core/test_template_merge.py`

Currently `GeneralMedicalExtractor.merge` delegates to `_merge_extracted` from `completeness.py`. The logic is 15 lines: dedup, append vs overwrite based on `APPENDABLE` membership. Phase 2 inlines it using `FieldSpec.appendable` instead of the frozenset.

- [ ] **Step 1: Write failing tests**

`tests/core/test_template_merge.py`:

```python
"""GeneralMedicalExtractor.merge — inline logic using FieldSpec.appendable.

Phase 2: merge no longer delegates; it uses FieldSpec.appendable on each
field. Covers dedup, append, overwrite, and unknown-field rejection.
"""
from __future__ import annotations

import pytest

from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_merge_appends_appendable_fields(extractor):
    collected = {"present_illness": "头痛3天"}
    result = extractor.merge(collected, {"present_illness": "无发热"})
    assert "头痛3天" in result["present_illness"]
    assert "无发热" in result["present_illness"]
    # Uses ； as separator (Chinese semicolon, current behavior)
    assert "；" in result["present_illness"]


def test_merge_overwrites_non_appendable_fields(extractor):
    collected = {"chief_complaint": "头痛"}
    result = extractor.merge(collected, {"chief_complaint": "发热"})
    assert result["chief_complaint"] == "发热"


def test_merge_skips_duplicate_values_on_appendable(extractor):
    collected = {"present_illness": "头痛3天"}
    # The new value is a substring of existing — skip it
    result = extractor.merge(collected, {"present_illness": "头痛"})
    # Unchanged — no duplication
    assert result["present_illness"] == "头痛3天"


def test_merge_ignores_unknown_fields(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"not_a_real_field": "y"})
    assert "not_a_real_field" not in result


def test_merge_ignores_empty_values(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"chief_complaint": "", "diagnosis": None})
    assert result["chief_complaint"] == "x"
    assert "diagnosis" not in result


def test_merge_returns_same_dict_instance(extractor):
    collected = {"chief_complaint": "x"}
    result = extractor.merge(collected, {"diagnosis": "y"})
    assert result is collected  # in-place mutation


def test_merge_trims_whitespace(extractor):
    collected = {}
    result = extractor.merge(collected, {"chief_complaint": "  头痛  "})
    assert result["chief_complaint"] == "头痛"
```

- [ ] **Step 2: Run, expect failures**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_template_merge.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

(Some pass via delegation, some may fail depending on legacy behavior. If all pass via delegation, proceed anyway — Step 3's change breaks the delegation.)

- [ ] **Step 3: Inline the merge logic**

In `src/domain/interview/templates/medical_general.py`, replace the `GeneralMedicalExtractor.merge` method body with inline logic:

```python
    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        """Merge LLM-extracted fields into collected, using FieldSpec.appendable
        to decide append vs overwrite. Mutates collected in-place and returns it.

        Inlined from completeness.merge_extracted (Phase 2). Dedup rule: if the
        new value is a substring of the existing text on an appendable field,
        skip it. Non-appendable fields always overwrite.
        """
        _fields_by_name = {f.name: f for f in self.fields()}
        for name, value in extracted.items():
            spec = _fields_by_name.get(name)
            if spec is None:
                continue  # unknown field, ignore
            if not value:
                continue
            value = value.strip()
            if not value:
                continue
            if spec.appendable:
                existing = collected.get(name, "")
                if existing and value in existing:
                    continue  # already contains this info
                collected[name] = (
                    f"{existing}；{value}".strip("；") if existing else value
                )
            else:
                collected[name] = value
        return collected
```

Also remove the now-unused `_merge_extracted` alias from the import block — grep for its other uses first:

```
grep -n "_merge_extracted" src/domain/interview/templates/medical_general.py
```

If only `merge()` used it, remove the import line `from domain.patients.completeness import ... merge_extracted as _merge_extracted, ...`. If `_merge_extracted` is still referenced elsewhere in the file, leave the import.

- [ ] **Step 4: Run, expect 7 passed**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_template_merge.py \
    tests/core/test_medical_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

The existing `test_merge_delegates_to_completeness_merge_extracted` in `test_medical_extractor.py` will now FAIL (since merge no longer delegates). Flip that test to match the inlined behavior — assert on the result, not the delegation:

Replace that test with:

```python
def test_merge_inline_appendable_vs_overwrite(extractor):
    """Phase 2: merge is inline, no longer delegates. Covers behavior parity."""
    collected = {"chief_complaint": "头痛"}
    extractor.merge(collected, {"chief_complaint": "发热", "present_illness": "3天"})
    assert collected["chief_complaint"] == "发热"  # overwrite
    assert "3天" in collected["present_illness"]  # append-style (new key)
```

Run again, expect all green (7 new + 5 existing = 12 tests pass across both files).

- [ ] **Step 5: Commit**

```
git add src/domain/interview/templates/medical_general.py \
        tests/core/test_template_merge.py \
        tests/core/test_medical_extractor.py
git commit -m "refactor(interview): inline merge logic into GeneralMedicalExtractor"
```

---

## Task 2: Inline completeness logic into `GeneralMedicalExtractor.completeness`

**Files:**
- Modify: `src/domain/interview/templates/medical_general.py`
- Create: `tests/core/test_template_completeness.py`

Currently delegates to `_get_completeness_state` from `completeness.py`. Phase 2 inlines the tier-based logic using `FieldSpec.tier` instead of the `REQUIRED`/`DOCTOR_RECOMMENDED`/`SUBJECTIVE_RECOMMENDED` tuples.

The current `get_completeness_state` logic (from `src/domain/patients/completeness.py:56-90`):
- `required_missing` = fields in `REQUIRED` that aren't in `collected`.
- `recommended_missing` = tier-appropriate recommended fields not in `collected`, excluding any that are already in `required_missing`.
- `optional_missing` = tier-appropriate optional fields not in `collected`.
- `next_focus` = first `recommended_missing`, or first `optional_missing`.
- `can_complete` = `len(required_missing) == 0`.

Patient mode uses only subjective-tier fields (the 7 patient-facing fields). Doctor mode uses all 14.

- [ ] **Step 1: Write failing tests**

`tests/core/test_template_completeness.py`:

```python
"""GeneralMedicalExtractor.completeness — inline tier-based logic.

Phase 2: uses FieldSpec.tier + mode-filtering instead of delegating.
"""
from __future__ import annotations

import pytest

from domain.interview.protocols import CompletenessState
from domain.interview.templates.medical_general import GeneralMedicalExtractor


@pytest.fixture
def extractor():
    return GeneralMedicalExtractor()


def test_completeness_empty_doctor_mode(extractor):
    state = extractor.completeness({}, "doctor")
    assert isinstance(state, CompletenessState)
    assert state.can_complete is False
    assert "chief_complaint" in state.required_missing
    assert "present_illness" in state.required_missing


def test_completeness_empty_patient_mode(extractor):
    state = extractor.completeness({}, "patient")
    assert state.can_complete is False
    assert "chief_complaint" in state.required_missing


def test_completeness_required_filled_doctor(extractor):
    state = extractor.completeness(
        {"chief_complaint": "x", "present_illness": "y"}, "doctor",
    )
    assert state.can_complete is True
    assert state.required_missing == []
    # Doctor mode should still see recommended gaps (e.g. past_history)
    assert "past_history" in state.recommended_missing


def test_completeness_required_filled_patient(extractor):
    state = extractor.completeness(
        {"chief_complaint": "x", "present_illness": "y"}, "patient",
    )
    assert state.can_complete is True
    # Patient mode should see ONLY subjective recommended fields
    # (past_history, allergy_history, family_history, personal_history)
    assert "past_history" in state.recommended_missing
    # Patient mode should NOT see doctor-only fields like physical_exam
    assert "physical_exam" not in state.recommended_missing
    assert "physical_exam" not in state.optional_missing


def test_completeness_next_focus_is_first_recommended_missing(extractor):
    state = extractor.completeness({"chief_complaint": "x", "present_illness": "y"}, "doctor")
    # next_focus should be the first missing recommended field
    assert state.next_focus in state.recommended_missing


def test_completeness_next_focus_falls_back_to_optional(extractor):
    # Fill all required + recommended; next_focus should come from optional
    filled = {
        "chief_complaint": "x", "present_illness": "y",
        "past_history": "x", "allergy_history": "x", "family_history": "x",
        "personal_history": "x", "physical_exam": "x", "diagnosis": "x",
        "treatment_plan": "x",
    }
    state = extractor.completeness(filled, "doctor")
    assert state.recommended_missing == []
    # next_focus should be a field from optional tier
    if state.optional_missing:
        assert state.next_focus == state.optional_missing[0]


def test_completeness_no_patient_mode_leak_of_doctor_fields(extractor):
    """Patient-mode completeness must not reference physical_exam / diagnosis /
    treatment_plan / orders_followup / auxiliary_exam / specialist_exam."""
    state = extractor.completeness({}, "patient")
    doctor_only = {
        "physical_exam", "specialist_exam", "auxiliary_exam",
        "diagnosis", "treatment_plan", "orders_followup",
    }
    all_mentioned = (
        set(state.required_missing)
        | set(state.recommended_missing)
        | set(state.optional_missing)
    )
    assert doctor_only.isdisjoint(all_mentioned)
```

- [ ] **Step 2: Run, expect some failures**

Some may pass via delegation. The important ones to fail are the "inline" behavioral tests.

- [ ] **Step 3: Inline the completeness logic**

Replace `GeneralMedicalExtractor.completeness` body:

```python
    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        """Tier-based completeness. Uses FieldSpec.tier; in patient mode, the
        doctor-only fields are filtered out.

        Phase 2 inline implementation. Previously delegated to
        completeness.get_completeness_state — logic now lives on the extractor
        so specialty variants can override tier per field.
        """
        specs = self.fields()

        # Patient mode: subjective-tier fields only (the 7 patient-facing fields).
        # This mirrors completeness.PATIENT_ALL and SUBJECTIVE_RECOMMENDED /
        # SUBJECTIVE_OPTIONAL sets. Hardcoded patient-visible set — when a
        # specialty variant changes the patient-visible field list, override
        # this method.
        _PATIENT_FIELDS = {
            "chief_complaint", "present_illness", "past_history",
            "allergy_history", "family_history", "personal_history",
            "marital_reproductive",
        }

        if mode == "patient":
            specs = [s for s in specs if s.name in _PATIENT_FIELDS]

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
```

Remove the `_get_completeness_state` import from the module if no longer referenced:

```
grep -n "_get_completeness_state" src/domain/interview/templates/medical_general.py
```

If only `completeness()` used it, delete the import line.

- [ ] **Step 4: Run, expect 7 passed + fix the existing extractor test**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_template_completeness.py \
    tests/core/test_medical_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

The existing `test_completeness_delegates_to_get_completeness_state` in `test_medical_extractor.py` will now FAIL. Flip it:

Replace that test with:

```python
def test_completeness_returns_completeness_state_directly(extractor):
    """Phase 2: completeness is inline; returns a CompletenessState built
    from the FieldSpec tiers."""
    state = extractor.completeness({"chief_complaint": "x", "present_illness": "y"}, "doctor")
    assert state.can_complete is True
```

Run again — all should pass.

- [ ] **Step 5: Commit**

```
git add src/domain/interview/templates/medical_general.py \
        tests/core/test_template_completeness.py \
        tests/core/test_medical_extractor.py
git commit -m "refactor(interview): inline completeness logic into GeneralMedicalExtractor"
```

---

## Task 3: Convert `completeness.py` into a deprecation shim

**Files:**
- Modify: `src/domain/patients/completeness.py` (replace with shim)
- Create: `tests/core/test_completeness_shim.py`

Legacy callers of `completeness.check_completeness`, `get_completeness_state`, `merge_extracted`, and the `REQUIRED`/`DOCTOR_RECOMMENDED`/`SUBJECTIVE_RECOMMENDED`/`APPENDABLE` constants still exist in:
- `src/domain/patients/interview_turn.py` (the legacy turn loop — Phase 2.5 deletes it).
- `src/domain/patients/interview_models.py::_build_progress` — uses `REQUIRED`, `DOCTOR_RECOMMENDED`, `DOCTOR_OPTIONAL`, `SUBJECTIVE_RECOMMENDED`, `SUBJECTIVE_OPTIONAL`.
- Test files under `tests/core/` that assert the legacy frozenset contents.

To avoid breaking them, `completeness.py` becomes a shim that derives the old constants from `MEDICAL_FIELDS` and re-exports the old functions.

- [ ] **Step 1: Verify which symbols are actually imported externally**

```
grep -rn "from domain.patients.completeness import" src tests --include="*.py" | grep -v test_completeness_shim
grep -rn "import domain.patients.completeness" src tests --include="*.py"
```

Record the full list of imported names. The shim must export each one.

- [ ] **Step 2: Write failing shim tests**

`tests/core/test_completeness_shim.py`:

```python
"""completeness.py shim — legacy constants + functions re-export from template."""
from __future__ import annotations

import warnings

import pytest


def test_shim_warns_on_import():
    # Import triggers DeprecationWarning (first import in this process).
    # Catch-all: just check the module is importable and the warning filter
    # was registered.
    import importlib
    import domain.patients.completeness as _c
    importlib.reload(_c)  # force a fresh import that fires the warning

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(_c)
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        ), "shim must emit DeprecationWarning"


def test_required_matches_template_required_tier():
    from domain.patients.completeness import REQUIRED
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    expected = tuple(s.name for s in MEDICAL_FIELDS if s.tier == "required")
    assert set(REQUIRED) == set(expected)


def test_appendable_matches_template_appendable_attr():
    from domain.patients.completeness import APPENDABLE
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    expected = {s.name for s in MEDICAL_FIELDS if s.appendable}
    assert set(APPENDABLE) == expected


def test_check_completeness_still_works_and_returns_list():
    from domain.patients.completeness import check_completeness
    missing = check_completeness({}, mode="patient")
    assert isinstance(missing, list)
    assert "chief_complaint" in missing


def test_get_completeness_state_still_returns_dict():
    """Legacy function returns a dict, not the new CompletenessState."""
    from domain.patients.completeness import get_completeness_state
    state = get_completeness_state({}, mode="patient")
    assert isinstance(state, dict)
    assert state["can_complete"] is False
    assert "chief_complaint" in state["required_missing"]


def test_merge_extracted_still_mutates_in_place():
    from domain.patients.completeness import merge_extracted
    collected = {"chief_complaint": "x"}
    merge_extracted(collected, {"diagnosis": "y"})
    assert collected["diagnosis"] == "y"


def test_subjective_recommended_matches_patient_tier():
    """Legacy SUBJECTIVE_RECOMMENDED is the set of patient-mode recommended fields."""
    from domain.patients.completeness import SUBJECTIVE_RECOMMENDED
    # Cannot derive from template without duplicating patient-mode logic;
    # just assert the set has the expected members.
    assert "past_history" in SUBJECTIVE_RECOMMENDED
    assert "allergy_history" in SUBJECTIVE_RECOMMENDED


def test_doctor_recommended_matches_template_recommended_tier():
    from domain.patients.completeness import DOCTOR_RECOMMENDED
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    # Doctor-mode recommended = FieldSpec.tier == "recommended"
    expected = {s.name for s in MEDICAL_FIELDS if s.tier == "recommended"}
    # Legacy tuple ordering was REQUIRED-first then recommended, so compare as sets
    assert expected.issubset(set(DOCTOR_RECOMMENDED))
```

- [ ] **Step 3: Run, expect most to fail**

- [ ] **Step 4: Replace `completeness.py` with the shim**

Full replacement of `src/domain/patients/completeness.py`:

```python
"""Field completeness — DEPRECATED shim.

Phase 2 moved this logic into domain.interview.templates.medical_general.
This module now re-exports derivations for legacy callers. Will be deleted
one release after Phase 2 ships.
"""
from __future__ import annotations

import warnings
from typing import Dict, List

warnings.warn(
    "domain.patients.completeness is deprecated; import from "
    "domain.interview.templates.medical_general instead.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.interview.protocols import FieldSpec
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor,
    MEDICAL_FIELDS,
)

# ---- Derive legacy constants from MEDICAL_FIELDS -------------------------

_by_tier: dict[str, tuple[str, ...]] = {
    tier: tuple(s.name for s in MEDICAL_FIELDS if s.tier == tier)
    for tier in ("required", "recommended", "optional")
}

# Patient-facing subset (matches GeneralMedicalExtractor.completeness patient mode)
_PATIENT_FIELDS = frozenset({
    "chief_complaint", "present_illness", "past_history",
    "allergy_history", "family_history", "personal_history",
    "marital_reproductive",
})

REQUIRED = _by_tier["required"]
SUBJECTIVE_RECOMMENDED = tuple(
    s.name for s in MEDICAL_FIELDS
    if s.tier == "recommended" and s.name in _PATIENT_FIELDS
)
SUBJECTIVE_OPTIONAL = tuple(
    s.name for s in MEDICAL_FIELDS
    if s.tier == "optional" and s.name in _PATIENT_FIELDS
)

# "Doctor" tiers include all fields (doctor mode sees everything)
DOCTOR_RECOMMENDED = _by_tier["recommended"]
DOCTOR_OPTIONAL = _by_tier["optional"]

OBJECTIVE = ("physical_exam", "specialist_exam", "auxiliary_exam")
ASSESSMENT = ("diagnosis",)
PLAN = ("treatment_plan", "orders_followup")

PATIENT_ALL = REQUIRED + SUBJECTIVE_RECOMMENDED + SUBJECTIVE_OPTIONAL
PATIENT_TOTAL = len(PATIENT_ALL)
DOCTOR_ALL = tuple(s.name for s in MEDICAL_FIELDS)
DOCTOR_TOTAL = len(DOCTOR_ALL)
ALL_COLLECTABLE = DOCTOR_ALL
TOTAL_FIELDS = DOCTOR_TOTAL

APPENDABLE = frozenset(s.name for s in MEDICAL_FIELDS if s.appendable)


# ---- Legacy functions — forward to the template --------------------------

_extractor = GeneralMedicalExtractor()


def check_completeness(collected: Dict[str, str], *, mode: str = "patient") -> List[str]:
    """DEPRECATED — use GeneralMedicalExtractor.completeness instead.

    Returns list of missing required-or-recommended field names.
    """
    state = _extractor.completeness(collected, mode)
    if state.required_missing:
        return list(state.required_missing)
    return list(state.recommended_missing)


def get_completeness_state(collected: Dict[str, str], *, mode: str = "patient") -> dict:
    """DEPRECATED — use GeneralMedicalExtractor.completeness instead.

    Returns the dict shape the legacy callers expect.
    """
    state = _extractor.completeness(collected, mode)
    return {
        "can_complete": state.can_complete,
        "required_missing": list(state.required_missing),
        "recommended_missing": list(state.recommended_missing),
        "optional_missing": list(state.optional_missing),
        "next_focus": state.next_focus,
    }


def count_filled(collected: Dict[str, str], *, mode: str = "patient") -> int:
    fields = DOCTOR_ALL if mode == "doctor" else PATIENT_ALL
    return sum(1 for f in fields if collected.get(f))


def total_fields(mode: str = "patient") -> int:
    return DOCTOR_TOTAL if mode == "doctor" else PATIENT_TOTAL


def merge_extracted(collected: Dict[str, str], extracted: Dict[str, str]) -> None:
    """DEPRECATED — use GeneralMedicalExtractor.merge instead.

    Mutates collected in-place. Returns None (matching legacy signature).
    """
    _extractor.merge(collected, extracted)
```

- [ ] **Step 5: Run, expect all 8 shim tests pass + existing tests still pass**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_completeness_shim.py \
    tests/core/test_medical_field_specs.py \
    tests/core/test_template_completeness.py \
    tests/core/test_template_merge.py \
    tests/core/test_interview_session_mode.py \
    -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

If `test_medical_field_specs.py` tests break (they import `from domain.patients.completeness import APPENDABLE, REQUIRED`), they'll see a DeprecationWarning but otherwise still pass because the shim re-exports the constants. If warnings fail tests, suppress via pytest filter at the file level:

```python
# At the top of test_medical_field_specs.py, BEFORE the import:
import pytest
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
```

- [ ] **Step 6: Full suite check — make sure no untouched test broke**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent 2>&1 | tail -20
```

If something fails, the culprit is a caller that tests the legacy module's internals. Investigate and fix by suppressing the warning in the offending test file (NOT by removing the DeprecationWarning from the shim).

- [ ] **Step 7: Commit**

```
git add src/domain/patients/completeness.py \
        tests/core/test_completeness_shim.py \
        tests/core/test_medical_field_specs.py
# plus any test file whose warning filter you had to add
git commit -m "refactor(interview): convert completeness.py to deprecation shim"
```

---

## Task 4: Make `MEDICAL_FIELDS` explicitly declarative

**Files:**
- Modify: `src/domain/interview/templates/medical_general.py`

Currently `MEDICAL_FIELDS` is derived from `FIELD_LABELS`/`FIELD_META`/`APPENDABLE`/`REQUIRED`/`DOCTOR_RECOMMENDED`/`_CARRY_FORWARD_FIELDS` at import time. Task 3 turned the completeness source into a shim that now derives the same constants *from* `MEDICAL_FIELDS`, creating a cycle. The derivation must be broken in this direction — the template becomes the canonical source.

- [ ] **Step 1: Write a failing test that asserts MEDICAL_FIELDS is NOT derived from legacy sources**

`tests/core/test_medical_field_specs.py` — append:

```python
def test_medical_fields_are_declarative_not_derived():
    """Phase 2: MEDICAL_FIELDS no longer imports from the legacy metadata
    tables. It's hand-declared on the template as the canonical source."""
    import inspect
    from domain.interview.templates import medical_general

    source = inspect.getsource(medical_general)
    # Rough guard: no top-level import of FIELD_LABELS/FIELD_META/APPENDABLE/REQUIRED
    # from domain.patients.completeness or domain.patients.interview_models.
    # (The _build_medical_fields helper function may still reference them for
    # legacy back-compat, but the new hand-declared list must exist.)
    assert "MEDICAL_FIELDS: list[FieldSpec] = [" in source or \
           "MEDICAL_FIELDS = [" in source, \
           "MEDICAL_FIELDS must be a hand-declared list, not a derivation"
```

- [ ] **Step 2: Run, expect failure** (current implementation uses `_build_medical_fields()` function).

- [ ] **Step 3: Replace the `MEDICAL_FIELDS` derivation with an explicit list**

In `src/domain/interview/templates/medical_general.py`, replace the `_build_medical_fields` function + the derived list with an explicit declaration. Read the current derivation's output (14 fields) and write each one out:

```python
# ---- field specs — canonical source of medical-interview schema ------------

# Declarative: add/remove/reorder fields here. Legacy callers import via the
# completeness.py and interview_models.py shims.

MEDICAL_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="chief_complaint", type="string", tier="required", appendable=False,
        label="主诉",
        description="促使就诊的主要症状+持续时间",
        example="腹痛3天",
    ),
    FieldSpec(
        name="present_illness", type="text", tier="required", appendable=True,
        label="现病史",
        description="症状详情、演变、已做检查",
        example="脐周阵发性钝痛，无放射，进食后加重",
    ),
    FieldSpec(
        name="past_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="既往史",
        description="既往疾病、手术、长期用药",
        example="高血压10年，口服氨氯地平",
    ),
    FieldSpec(
        name="allergy_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="过敏史",
        description="药物/食物过敏",
        example="青霉素过敏",
    ),
    FieldSpec(
        name="family_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="家族史",
        description="家族遗传病史",
        example="父亲糖尿病",
    ),
    FieldSpec(
        name="personal_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="个人史",
        description="吸烟、饮酒、职业暴露",
        example="吸烟20年，1包/天",
    ),
    FieldSpec(
        name="marital_reproductive", type="text", tier="optional", appendable=True,
        label="婚育史",
        description="婚育情况",
        example="已婚，育1子",
    ),
    FieldSpec(
        name="physical_exam", type="text", tier="recommended", appendable=True,
        label="体格检查",
        description="生命体征、阳性/阴性体征",
        example="腹软，脐周压痛，无反跳痛",
    ),
    FieldSpec(
        name="specialist_exam", type="text", tier="optional", appendable=True,
        label="专科检查",
        description="专科特殊检查",
        example="肛门指检未触及肿物",
    ),
    FieldSpec(
        name="auxiliary_exam", type="text", tier="optional", appendable=True,
        label="辅助检查",
        description="化验、影像结果",
        example="血常规WBC 12.5×10⁹/L",
    ),
    FieldSpec(
        name="diagnosis", type="string", tier="recommended", appendable=False,
        label="诊断",
        description="初步诊断或印象",
        example="急性胃肠炎",
    ),
    FieldSpec(
        name="treatment_plan", type="text", tier="recommended", appendable=True,
        label="治疗方案",
        description="处方、处置、建议",
        example="口服蒙脱石散，清淡饮食",
    ),
    FieldSpec(
        name="orders_followup", type="text", tier="optional", appendable=True,
        label="医嘱及随访",
        description="医嘱及复诊安排",
        example="3天后复诊，如加重急诊",
    ),
    FieldSpec(
        name="department", type="string", tier="optional", appendable=False,
        label="科别",
        description="科别：门诊/急诊/住院 + 科室",
    ),
]

# NOTE: _build_medical_fields() is removed in Phase 2. The derivation from
# completeness.py / interview_models.py was Phase 1 scaffolding; Phase 2
# makes the template canonical.
```

Delete the `_build_medical_fields` function and the imports it used (`FIELD_LABELS`, `FIELD_META`, `REQUIRED`, `_CARRY_FORWARD_FIELDS`, `APPENDABLE`, `DOCTOR_RECOMMENDED`). Grep first to check:

```
grep -n "FIELD_LABELS\|FIELD_META\|_CARRY_FORWARD_FIELDS" src/domain/interview/templates/medical_general.py
```

Remove any import lines that only fed the derivation.

- [ ] **Step 4: Run the full template suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_medical_field_specs.py \
    tests/core/test_template_completeness.py \
    tests/core/test_template_merge.py \
    tests/core/test_completeness_shim.py \
    tests/core/test_medical_extractor.py \
    -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

All should pass. The existing `test_medical_field_specs.py` tests that assert `MEDICAL_FIELDS` matches legacy sources will now assert against the explicit list — which was built FROM those same sources, so they stay green (the values haven't changed, only the declaration has).

If `test_every_extracted_field_has_a_spec` breaks because `ExtractedClinicalFields` hasn't been shimmed yet (that's Task 5), the test should still pass because the clinical field names in MEDICAL_FIELDS match the Pydantic field names — verify by eyeballing.

- [ ] **Step 5: Commit**

```
git add src/domain/interview/templates/medical_general.py \
        tests/core/test_medical_field_specs.py
git commit -m "refactor(interview): make MEDICAL_FIELDS a hand-declared canonical list"
```

---

## Task 5: Convert `interview_models.py` into a deprecation shim

**Files:**
- Modify: `src/domain/patients/interview_models.py` (replace with shim)
- Create: `tests/core/test_interview_models_shim.py`

The file exports:
- `ExtractedClinicalFields` — Pydantic class. Becomes `build_response_schema(MEDICAL_FIELDS)`.
- `InterviewLLMResponse` — Pydantic class wrapping `ExtractedClinicalFields`. Keep as-is but point at the shim's `ExtractedClinicalFields`.
- `FIELD_LABELS` — dict derived from `MEDICAL_FIELDS`.
- `FIELD_META` — dict derived.
- `_FIELD_PRIORITY` — dict derived from `tier`.
- `_PATIENT_PHASES` — hand-declared list (keep as-is, it's patient-UX specific).
- `_build_progress` — keep as a function; it's used by `interview_turn.py`.
- `InterviewResponse` — dataclass used by the legacy turn loop. Keep as-is.
- `MAX_TURNS = 30` — keep as-is.

- [ ] **Step 1: Verify what's imported from the module**

```
grep -rn "from domain.patients.interview_models import" src tests --include="*.py"
```

- [ ] **Step 2: Write failing shim tests**

`tests/core/test_interview_models_shim.py`:

```python
"""interview_models.py shim — ExtractedClinicalFields now derives from MEDICAL_FIELDS."""
from __future__ import annotations

import warnings


def test_shim_warns_on_import():
    import importlib
    import domain.patients.interview_models as _m
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(_m)
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )


def test_extracted_clinical_fields_has_expected_fields():
    from domain.patients.interview_models import ExtractedClinicalFields
    names = set(ExtractedClinicalFields.model_fields.keys())
    assert "chief_complaint" in names
    assert "present_illness" in names
    assert "diagnosis" in names


def test_field_labels_matches_template():
    from domain.patients.interview_models import FIELD_LABELS
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    for spec in MEDICAL_FIELDS:
        if spec.label and spec.name != "department":  # department isn't in legacy labels dict
            assert FIELD_LABELS.get(spec.name) == spec.label


def test_field_meta_preserves_hint_and_example():
    from domain.patients.interview_models import FIELD_META
    from domain.interview.templates.medical_general import MEDICAL_FIELDS
    for spec in MEDICAL_FIELDS:
        meta = FIELD_META.get(spec.name, {})
        if spec.example:
            assert meta.get("example") == spec.example
        if spec.description:
            assert meta.get("hint") == spec.description


def test_interview_llm_response_still_parseable():
    from domain.patients.interview_models import InterviewLLMResponse
    # Should accept a reply + empty extracted + empty suggestions
    obj = InterviewLLMResponse(reply="hi", suggestions=[])
    assert obj.reply == "hi"


def test_max_turns_constant_preserved():
    from domain.patients.interview_models import MAX_TURNS
    assert MAX_TURNS == 30


def test_build_progress_still_works():
    from domain.patients.interview_models import _build_progress
    p = _build_progress({"chief_complaint": "x"}, mode="patient")
    assert p["filled"] >= 1
    assert "total" in p


def test_interview_response_dataclass_preserved():
    from domain.patients.interview_models import InterviewResponse
    r = InterviewResponse(reply="x", collected={}, progress={"filled": 0, "total": 7}, status="interviewing")
    assert r.reply == "x"
```

- [ ] **Step 3: Run, expect mix of pass/fail**

- [ ] **Step 4: Replace `interview_models.py` with the shim**

Full replacement of `src/domain/patients/interview_models.py`:

```python
"""Interview Pydantic models, field metadata, progress — DEPRECATED shim.

Phase 2 moved the canonical schema into domain.interview.templates.medical_general.
This module re-exports derivations for legacy callers. _build_progress and the
dataclasses (InterviewResponse, InterviewLLMResponse) remain because they're
still used by the legacy turn loop in interview_turn.py (Phase 2.5 deletes it).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

warnings.warn(
    "domain.patients.interview_models is deprecated; import from "
    "domain.interview.templates.medical_general instead.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.interview.contract import build_response_schema
from domain.interview.templates.medical_general import MEDICAL_FIELDS

MAX_TURNS = 30


# ---- ExtractedClinicalFields: derived from MEDICAL_FIELDS -----------------

# build_response_schema's output: a Pydantic class with each FieldSpec as an
# Optional[str] field for the schema vocabulary used by LLM structured output.
# Phase 2 swaps the hand-written class for this derivation — identical shape
# from the caller's point of view.
_ClinicalBase = build_response_schema(MEDICAL_FIELDS)


class ExtractedClinicalFields(_ClinicalBase):  # type: ignore[misc,valid-type]
    """Clinical fields extracted from this turn. Legacy alias over
    build_response_schema(MEDICAL_FIELDS).

    Adds back patient_name/gender/age fields, which are engine-level metadata
    rather than clinical fields — they're not in MEDICAL_FIELDS but the LLM
    prompt still asks for them and structured output carries them.
    """
    patient_name: Optional[str] = Field(None, description="患者姓名")
    patient_gender: Optional[str] = Field(None, description="患者性别（男/女）")
    patient_age: Optional[str] = Field(None, description="患者年龄")


class InterviewLLMResponse(BaseModel):
    """Structured response from the interview LLM."""

    reply: str = Field(
        default="请继续描述您的情况。",
        description="给医生或患者的自然语言回复",
    )
    extracted: ExtractedClinicalFields = Field(
        default_factory=ExtractedClinicalFields,
        description="本轮新提取的病历字段",
    )
    suggestions: List[str] = Field(default_factory=list)


# ---- Derived metadata dicts -----------------------------------------------

FIELD_LABELS: Dict[str, str] = {
    s.name: s.label
    for s in MEDICAL_FIELDS
    if s.label and s.name != "department"
}

FIELD_META: Dict[str, dict] = {
    s.name: {
        "hint": s.description,
        "example": s.example,
        "tier": s.tier,
    }
    for s in MEDICAL_FIELDS
    if s.description and s.name != "department"
}

_FIELD_PRIORITY: Dict[str, str] = {
    s.name: s.tier
    for s in MEDICAL_FIELDS
    if s.name != "department"
}

_PATIENT_PHASES = [
    ("主诉与现病史", ["chief_complaint", "present_illness"]),
    ("病史采集", ["past_history", "allergy_history", "family_history", "personal_history"]),
    ("补充信息", ["marital_reproductive"]),
]


# ---- _build_progress: used by legacy turn loop ----------------------------

def _build_progress(collected: Dict[str, str], mode: str = "patient") -> dict:
    """Build structured progress metadata for UI rendering."""
    from domain.patients.completeness import (
        REQUIRED, DOCTOR_RECOMMENDED, DOCTOR_OPTIONAL,
        SUBJECTIVE_RECOMMENDED, SUBJECTIVE_OPTIONAL,
    )

    _PATIENT_FIELDS = {
        "chief_complaint", "present_illness", "past_history",
        "allergy_history", "family_history", "personal_history", "marital_reproductive",
    }
    fields = {}
    for key, priority in _FIELD_PRIORITY.items():
        if mode == "patient" and key not in _PATIENT_FIELDS:
            continue
        fields[key] = {
            "status": "filled" if collected.get(key) else "empty",
            "priority": priority,
            "label": FIELD_LABELS.get(key, key),
        }

    filled = sum(1 for f in fields.values() if f["status"] == "filled")
    total = len(fields)
    pct = int(round(filled / total * 100)) if total else 0

    phase = "完成"
    if mode == "patient":
        for phase_name, phase_fields in _PATIENT_PHASES:
            if any(not collected.get(f) for f in phase_fields):
                phase = phase_name
                break

    can_complete = all(collected.get(f) for f in REQUIRED)

    if mode == "doctor":
        req_fields = list(REQUIRED)
        rec_fields = [f for f in DOCTOR_RECOMMENDED if f not in REQUIRED]
    else:
        req_fields = list(REQUIRED)
        rec_fields = [f for f in SUBJECTIVE_RECOMMENDED if f not in REQUIRED]

    required_count = sum(1 for f in req_fields if collected.get(f))
    required_total = len(req_fields)
    recommended_count = sum(1 for f in rec_fields if collected.get(f))
    recommended_total = len(rec_fields)

    return {
        "filled": filled,
        "total": total,
        "pct": pct,
        "phase": phase,
        "fields": fields,
        "can_complete": can_complete,
        "required_count": required_count,
        "required_total": required_total,
        "recommended_count": recommended_count,
        "recommended_total": recommended_total,
    }


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: dict
    status: str
    missing: List[str] = None
    suggestions: List[str] = None
    ready_to_review: bool = False
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[str] = None
    retryable: bool = False
```

- [ ] **Step 5: Run tests**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_models_shim.py \
    tests/core/test_medical_field_specs.py \
    -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 6: Full regression**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent 2>&1 | tail -20
```

If something breaks, the most likely cause is a test that asserts `ExtractedClinicalFields.model_fields["department"].description == "科别..."`. Since the shim derives fields from MEDICAL_FIELDS, the description should still match (Task 4's declaration copied the exact description). Verify — if it diverges, fix the Task 4 declaration, not the shim.

- [ ] **Step 7: Commit**

```
git add src/domain/patients/interview_models.py \
        tests/core/test_interview_models_shim.py
git commit -m "refactor(interview): convert interview_models.py to deprecation shim"
```

---

## Task 6: Thread real session context through `prompt_partial`

**Files:**
- Modify: `src/domain/interview/templates/medical_general.py`

Phase 1 left `_composer_kwargs` as a stub that passes empty `doctor_id` / `patient_context` / `doctor_message`. The engine's `next_turn` currently doesn't call `prompt_partial` (it forwards to `_legacy_interview_turn`). Phase 2 doesn't yet inline the turn loop, but we can still improve the stub so that if anything else calls `prompt_partial` (Phase 3 might, for example), it produces a real usable message list.

- [ ] **Step 1: Update `prompt_partial` signature to accept explicit context**

Change `GeneralMedicalExtractor.prompt_partial` in `src/domain/interview/templates/medical_general.py` to require the real kwargs (instead of stub defaults):

```python
    async def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
        *,
        doctor_id: str = "",
        patient_context: str = "",
        doctor_message: str = "",
    ) -> list[dict[str, str]]:
        """Compose the intent-layer prompt via prompt_composer.

        Phase 2: accepts explicit doctor_id/patient_context/doctor_message so
        callers (engine.next_turn in Phase 2.5, or ad-hoc callers in Phase 3)
        can thread real session context. Phase 1 passed empty strings via a
        stub helper; that helper is removed.
        """
        if mode == "doctor":
            return await _compose_for_doctor_interview(
                doctor_id=doctor_id,
                patient_context=patient_context,
                doctor_message=doctor_message,
                history=history,
                template_id="medical_general_v1",
            )
        return await _compose_for_patient_interview(
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message=doctor_message,
            history=history,
            template_id="medical_general_v1",
        )
```

Remove the `_composer_kwargs` helper function from the file (grep confirms it's not used elsewhere):

```
grep -n "_composer_kwargs" src/domain/interview/templates/medical_general.py tests
```

- [ ] **Step 2: Update the existing extractor tests for prompt_partial**

In `tests/core/test_medical_extractor.py`, update the two `prompt_partial` tests to pass explicit context kwargs:

```python
@pytest.mark.asyncio
async def test_prompt_partial_is_awaitable_and_returns_messages(extractor):
    with patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[{"role": "system", "content": "..."}]),
    ) as mock_compose:
        result = await extractor.prompt_partial(
            collected={"chief_complaint": "头痛"},
            history=[{"role": "user", "content": "头痛三天"}],
            phase="default",
            mode="patient",
            doctor_id="doc_1",
            patient_context="患者：张三，男，45岁",
            doctor_message="头痛三天",
        )
    mock_compose.assert_called_once()
    _, kwargs = mock_compose.call_args
    assert kwargs["doctor_id"] == "doc_1"
    assert kwargs["patient_context"] == "患者：张三，男，45岁"
    assert kwargs["doctor_message"] == "头痛三天"
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_prompt_partial_routes_doctor_mode_to_doctor_composer(extractor):
    with patch(
        "domain.interview.templates.medical_general._compose_for_doctor_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_doc, \
         patch(
        "domain.interview.templates.medical_general._compose_for_patient_interview",
        new=AsyncMock(return_value=[]),
    ) as mock_pat:
        await extractor.prompt_partial(
            collected={}, history=[], phase="default", mode="doctor",
            doctor_id="doc_1", patient_context="", doctor_message="",
        )
    mock_doc.assert_called_once()
    mock_pat.assert_not_called()
```

- [ ] **Step 3: Run**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_medical_extractor.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 4: Commit**

```
git add src/domain/interview/templates/medical_general.py \
        tests/core/test_medical_extractor.py
git commit -m "refactor(interview): thread real session context through prompt_partial"
```

---

## Task 7: Route `/turn` endpoints through `engine.next_turn`

**Files:**
- Modify: `src/channels/web/doctor_interview/turn.py`
- Modify: `src/channels/web/patient_interview_routes.py`

Currently `/turn` endpoints call the legacy `interview_turn()` directly. Phase 2 flips them to call `engine.next_turn()` — which still forwards to legacy internally, but makes the engine the canonical entry point. The legacy response shape (`InterviewResponse`) is reconstructed from the engine's `TurnResult` + a session reload.

**Behavior must be byte-identical** — any divergence in the endpoint response is a regression.

- [ ] **Step 1: Doctor `/turn` endpoint — flip the first-turn branch**

In `src/channels/web/doctor_interview/turn.py`, find `_first_turn` (around line 88). After the current `interview_turn(session.id, text)` call, replace with an engine call followed by a session reload + legacy response reconstruction:

```python
async def _first_turn(doctor_id, text, pre_patient_id=None, *, template_id=None):
    from agent.tools.resolve import resolve
    # ... existing setup code ...

    session = await create_session(
        doctor_id, patient_id=pre_patient_id, mode="doctor",
        initial_fields=initial_fields,
        template_id=template_id or "medical_general_v1",
    )

    # Phase 2: route through engine.next_turn. It forwards to legacy
    # interview_turn() under the hood so behavior is unchanged.
    from domain.interview.engine import InterviewEngine
    _ENGINE = _get_engine()  # use lazy factory pattern same as confirm.py
    await _ENGINE.next_turn(session.id, text)

    # Reload session to build the legacy response shape.
    session = await load_session(session.id)
    # ... rest of existing logic that builds the response from session state ...
```

This is the structural change. The tricky part: the original `_first_turn` used the return value of `interview_turn` directly (it had `response.reply`, `response.suggestions`, etc.). After the engine call, the function has to read those from the freshly reloaded session + engine's TurnResult.

**Pragmatic approach**: keep calling the legacy `interview_turn` internally, but wrap the call site in a local helper that also goes through the engine for bookkeeping:

```python
# Simplest change that preserves behavior: call engine, but keep using
# interview_turn's return shape for building the response.
response = await interview_turn(session.id, text)  # unchanged
# (engine.next_turn call is redundant for now; Phase 2.5 replaces both)
```

Actually — since the engine is just forwarding, routing `/turn` through it adds a second call that wastes work. The honest move is to defer `/turn` routing until Phase 2.5, when the engine actually owns the loop.

**Task 7 (scoped-down):** Skip the `/turn` endpoint routing. Note the decision here and defer to Phase 2.5. The engine is still the canonical entry point for `/confirm` (Phase 1 Task 11) and `submit_interview` (Phase 1 Task 12).

- [ ] **Step 1 (revised): Document the deferral**

Add a comment at the top of `src/channels/web/doctor_interview/turn.py` near the existing `_get_engine()` helper:

```python
# NOTE (Phase 2): /turn endpoints still call interview_turn() directly.
# engine.next_turn forwards to interview_turn anyway, so routing /turn
# through the engine would double the work without structural benefit.
# Phase 2.5 inlines the turn loop into engine.next_turn and flips /turn
# at the same time.
```

Add the same note near the turn handler in `src/channels/web/patient_interview_routes.py`.

- [ ] **Step 2: No test changes needed** — the endpoints still behave identically.

- [ ] **Step 3: Commit the note**

```
git add src/channels/web/doctor_interview/turn.py \
        src/channels/web/patient_interview_routes.py
git commit -m "docs(interview): note Phase 2.5 deferral of /turn engine routing"
```

---

## Task 8: Regression sweep

**Files:** none — verification only.

- [ ] **Step 1: Full suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent --tb=short 2>&1 | tail -40
```

Pass count must match the post-Phase-1 baseline (447 passed, 94 skipped). Any new failure is a Phase 2 regression.

- [ ] **Step 2: DeprecationWarning audit**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent 2>&1 | grep -i "deprecation" | head -20
```

If many tests surface the shim's warning, consider adding a global pytest filter in `conftest.py`:

```python
# tests/conftest.py addition
import warnings
warnings.filterwarnings(
    "ignore",
    message="domain.patients.completeness is deprecated",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="domain.patients.interview_models is deprecated",
    category=DeprecationWarning,
)
```

DO NOT add this if warnings aren't actually failing tests — leaving them visible in normal runs is the point of the deprecation.

- [ ] **Step 3: Invariant grep**

```
# The template is the canonical source for field metadata
grep -rn "MEDICAL_FIELDS" src --include="*.py" | head

# The old FIELD_META/FIELD_LABELS still work via shim
grep -rn "from domain.patients.interview_models import" src --include="*.py" | head

# Completeness shim is still imported (legacy callers not yet migrated)
grep -rn "from domain.patients.completeness import" src --include="*.py" | head
```

Report the three counts. No specific target; just verify the shim paths are exercised by existing code.

- [ ] **Step 4: Sim gate (manual, user-executed)**

Print a reminder to the user that Phase 2 should be verified with a sim run before marking "done":

```
echo ""
echo "Phase 2 complete — but before landing:"
echo "  Run reply_sim before and after these 7 commits and confirm the"
echo "  pass-rate delta is within ±2%. The sim runner at scripts/run_reply_sim.py"
echo "  requires a live server on port 8001."
```

- [ ] **Step 5: Commit history sanity**

```
git log 12abe3a3..HEAD --oneline
```

Expected: 7 Phase 2 commits (Tasks 1-7), each with `refactor(interview)` or `docs(interview)` prefix.

- [ ] **Step 6: No commit — Phase 2 complete**

Working tree should be clean of Phase 2 source files.

---

## Phase 2 completion checklist

- [ ] `GeneralMedicalExtractor.merge` implements dedup/append/overwrite inline (no delegation).
- [ ] `GeneralMedicalExtractor.completeness` implements tier-based logic inline (no delegation).
- [ ] `MEDICAL_FIELDS` is a hand-declared list (no derivation from legacy sources).
- [ ] `completeness.py` is a deprecation shim; all legacy imports still work; constants derive from `MEDICAL_FIELDS`.
- [ ] `interview_models.py` is a deprecation shim; `ExtractedClinicalFields` = `build_response_schema(MEDICAL_FIELDS)` + 3 metadata fields.
- [ ] `prompt_partial` accepts explicit context kwargs (no stub).
- [ ] `/turn` routing deferral is documented (Phase 2.5 blocker).
- [ ] Full test suite matches Phase 1 baseline.

## What Phase 2 does NOT do (deferred to Phase 2.5 or later)

- Inline the turn loop from `interview_turn.py` into `engine.next_turn`.
- Route `/turn` endpoints through the engine.
- Delete the shim files (one-release deprecation window).
- Move prompt file ownership into the extractor (prompt_composer still owns the layer-1-through-6 stack).
- Resolve §8 open product question (doctor-mode diagnosis asymmetry).

Phase 2 is the structural move. Phase 2.5 is the runtime flip. Phase 3 (first form template) can start after Phase 2 ships.
