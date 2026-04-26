# Interview Pipeline Extensibility — Phase 4 r2 (Neuro-Only + Foundation Fixes)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Supersedes:** `2026-04-23-interview-pipeline-phase4.md` (r1). r1 tried to ship two templates and used `project_extras` as a schema-silent shortcut. Independent review by Claude + Codex surfaced 3 blockers and 5 pre-existing integration bugs that r1 would drag into production. r2 drops the therapy intake template (re-scoped into a future Phase 5 with dedicated safety design), does a proper Alembic migration for neuro fields, and fixes 4 of the 5 pre-existing bugs that neuro actually trips.

**Goal:** Ship `medical_neuro_v1` on a clean foundation.

- Proper schema for neuro-specific fields (no `project_extras` dict-shuffling).
- Safety screening split into its own `SafetyScreenHook` (distinct from the full diagnosis pipeline).
- Patient-portal entrypoint actually routes non-default templates.
- Engine persistence integrity fixed (post-confirm state matches DB).
- Doctor inline-edit validation widened to active template's field set.
- Resume/current readiness runs through `template.extractor.completeness`, not legacy helpers.

**Explicitly deferred (Phase 5):** `form_therapy_intake_v1`, `CrisisAlertHook`, form-kind review queue, `confirm_interview` return contract for `PersistRef(kind="form_response")`. Therapy intake needs a proper safety design pass (tiered alerts, keyword + LLM backstop, structured alert payload, audit trail, therapist paging UI) that doesn't fit a blocker-fix sprint.

**§8 resolution (final):** per-template hook lists. `medical_general_v1` stays asymmetric (patient fires diagnosis, doctor does not). `medical_neuro_v1` adds a `SafetyScreenHook` that runs on **both** modes — not an overloaded diagnosis trigger. Doctor-mode diagnosis remains off for neuro too; if product wants to turn it on, that's a one-line hook-list change later.

**Reference:** design spec §4d (versioning), §6a Phase 4 row, §8 bullet 1 (doctor-mode diagnosis), §3b (per-template hooks), §7e (new-template gate), §7f (FieldSpec semantic tests). Plus codex/claude review notes in [/tmp/phase4-review-zh.html](file:///tmp/phase4-review-zh.html).

---

## Preconditions

- Phase 3 landed. `TEMPLATES` contains `medical_general_v1` + `form_satisfaction_v1`.
- Full suite green (492+ tests).

## Behavior-preservation bar

- `medical_general_v1` behavior unchanged. Every existing test still passes.
- reply_sim Tier-2 pass rate within ±2% of post-Phase-3 baseline.
- New tests cover: engine integrity fix, Alembic migration, neuro extractor, neuro writer, SafetyScreenHook, patient-portal template routing, inline-edit widening, resume completeness routing.

## File map

**Create:**
- `alembic/versions/NNNN_neuro_medical_record_columns.py` — adds `onset_time`, `neuro_exam`, `vascular_risk_factors` to `medical_records`.
- `src/domain/interview/templates/medical_neuro.py` — `GeneralNeuroExtractor`, `GeneralNeuroTemplate`, `NEURO_EXTRA_FIELDS`.
- `src/domain/interview/hooks/safety.py` — `SafetyScreenHook`.
- `tests/core/test_medical_neuro_fields.py`
- `tests/core/test_medical_neuro_extractor.py`
- `tests/core/test_medical_neuro_template.py`
- `tests/core/test_safety_screen_hook.py`
- `tests/core/test_engine_confirm_persistence.py` — regression test for bug E.
- `tests/channels/test_patient_portal_template_routing.py` — integration test for bug A.
- `tests/channels/test_doctor_inline_edit_neuro.py` — integration test for bug C.
- `tests/channels/test_patient_resume_template_completeness.py` — integration test for bug B.

**Modify:**
- `src/db/models/records.py` — add 3 nullable columns to `MedicalRecordDB`.
- `src/channels/web/doctor_interview/shared.py` — extend `FIELD_LABELS` with 3 neuro entries; `_build_clinical_text` gains neuro rendering.
- `src/domain/interview/engine.py` — fix `confirm` to save reconciled `collected` back to session row (bug E).
- `src/domain/interview/templates/medical_general.py` — `MedicalRecordWriter` reads all `MEDICAL_FIELDS` + subclass's extras from `collected` generically (no hardcoded column list); `GeneralMedicalExtractor.prompt_partial` takes template id from `session_state.template_id` not a hardcoded literal.
- `src/channels/web/patient_interview_routes.py` — accepts `template_id` on session create; resume/current use `template.extractor.completeness` (bug A + bug B).
- `src/domain/patients/interview_session.py` — `create_session()` threads `template_id`.
- `src/channels/web/doctor_interview/turn.py` — inline-edit validation uses active template's field names (bug C).
- `src/domain/interview/templates/__init__.py` — register `medical_neuro_v1`.
- `tests/core/test_template_registry.py` — assert 3 templates registered.

**Not touched (deferred):**
- `form_therapy_intake_v1` — Phase 5.
- `confirm_interview` return contract for `PersistRef(kind="form_response")` (bug D) — Phase 5; neuro persists as `medical_record` so the current contract works.
- Therapist form-kind review queue / confirm mutation — Phase 5.

---

## Task 0: Fix engine.confirm persistence (bug E)

**Files:**
- Modify: `src/domain/interview/engine.py`
- Create: `tests/core/test_engine_confirm_persistence.py`

**Why first:** this is a pre-existing integrity bug that predates Phase 4. `InterviewEngine.confirm()` currently merges doctor edits and runs batch re-extraction, but never saves the reconciled `collected` back to the session row. The session JSON diverges from the persisted record from that moment forward. Neuro triggers a fresh regression test for this, but the fix applies equally to `medical_general_v1`.

- [ ] **Step 1: Regression test proves the bug**

`tests/core/test_engine_confirm_persistence.py`:

```python
"""engine.confirm must save reconciled collected back to the session row.

Bug E regression test. Pre-fix behavior: session.collected stays at the
pre-edit, pre-batch-extract value; rendered record uses the reconciled
value. Post-fix: both are equal.
"""
from __future__ import annotations

import pytest

from domain.interview.engine import InterviewEngine
# ... fixtures for a session with mocked batch extractor that returns
# a dict different from the session's current collected


@pytest.mark.asyncio
async def test_confirm_persists_reconciled_collected_to_session():
    # Arrange: session with collected={"chief_complaint":"old"}, doctor_edits
    # patches it to "new", batch_extractor returns {"chief_complaint":"newer"}.
    # Act: engine.confirm(...)
    # Assert: reload session from DB, collected["chief_complaint"] == "newer"
    ...
```

- [ ] **Step 2: Run, expect failure** (pre-fix, session keeps old value).

- [ ] **Step 3: Fix**

In `engine.py` `confirm()`, after batch extraction and before hook dispatch, write `sess.collected = collected` and call `_save_session_state(sess)`. The save must happen before hooks so hook failures don't roll back the persisted reconciled state.

- [ ] **Step 4: Run, expect pass.** Also run the full interview test suite — no regressions.

- [ ] **Step 5: Commit**

```
git commit -m "fix(interview): engine.confirm persists reconciled collected to session (bug E)"
```

---

## Task 1: Alembic migration — 3 neuro columns + FIELD_LABELS extension

**Files:**
- Create: `alembic/versions/NNNN_neuro_medical_record_columns.py`
- Modify: `src/db/models/records.py`
- Modify: `src/channels/web/doctor_interview/shared.py`

Migration adds three nullable `TEXT` columns. All existing rows get NULL — no backfill. Template at `medical_general_v1` never writes these columns.

- [ ] **Step 1: Write the Alembic migration**

```python
def upgrade():
    op.add_column("medical_records", sa.Column("onset_time", sa.Text, nullable=True))
    op.add_column("medical_records", sa.Column("neuro_exam", sa.Text, nullable=True))
    op.add_column("medical_records", sa.Column("vascular_risk_factors", sa.Text, nullable=True))

def downgrade():
    op.drop_column("medical_records", "vascular_risk_factors")
    op.drop_column("medical_records", "neuro_exam")
    op.drop_column("medical_records", "onset_time")
```

- [ ] **Step 2: Add columns to `MedicalRecordDB` ORM model**

`src/db/models/records.py` — three new `Column(Text, nullable=True)` fields.

- [ ] **Step 3: Extend `FIELD_LABELS` and `_build_clinical_text`**

`src/channels/web/doctor_interview/shared.py`:
- `FIELD_LABELS` gains `onset_time → "发病时间"`, `neuro_exam → "神经系统查体"`, `vascular_risk_factors → "血管危险因素"`.
- `_build_clinical_text` iterates `FIELD_LABELS` as today; new fields render in dictionary order. Ordering tweak if we want `onset_time` right after `chief_complaint`: insertion order in the dict literal.

- [ ] **Step 4: Run the migration on the dev DB**

```
alembic upgrade head
```

- [ ] **Step 5: Smoke test — write a record with all 17 fields, read it back, confirm `_build_clinical_text` renders all three new labels**

- [ ] **Step 6: Commit**

```
git commit -m "feat(db): add neuro-specific columns to medical_records (onset_time, neuro_exam, vascular_risk_factors)"
```

---

## Task 2: Generic `MedicalRecordWriter` column mapping

**Files:**
- Modify: `src/domain/interview/templates/medical_general.py` (MedicalRecordWriter)

Today `MedicalRecordWriter.persist` hand-names every column in the INSERT. That was fine for 14 fields but now we want specialty variants to append extras without writer changes. Refactor to build column kwargs from `MEDICAL_FIELDS` + the active extractor's extras.

- [ ] **Step 1: Write failing test**

`tests/core/test_medical_record_writer_generic.py`:

```python
"""MedicalRecordWriter must write any field whose name matches a
MedicalRecordDB column. Neuro extras (onset_time, neuro_exam,
vascular_risk_factors) are written because the columns exist after Task 1.
"""

@pytest.mark.asyncio
async def test_writer_maps_neuro_fields_to_new_columns():
    writer = MedicalRecordWriter()
    session = _session_for_neuro(...)
    collected = {
        "chief_complaint": "左侧肢体无力",
        "onset_time": "2小时前",
        "neuro_exam": "GCS 15，左上肢肌力3级",
        "vascular_risk_factors": "高血压10年",
    }
    ref = await writer.persist(session, collected)
    row = await _fetch_record(ref.id)
    assert row.onset_time == "2小时前"
    assert row.neuro_exam == "GCS 15，左上肢肌力3级"
    assert row.vascular_risk_factors == "高血压10年"
```

- [ ] **Step 2: Refactor `MedicalRecordWriter.persist`**

Collect column names from `inspect(MedicalRecordDB).c` ∩ keys in `collected`. Build kwargs dynamically. `record_type`, `status`, `content` stay hand-wired. Everything else flows through `collected`.

- [ ] **Step 3: Run. All existing medical writer tests must still pass + new neuro test passes.**

- [ ] **Step 4: Commit**

```
git commit -m "refactor(interview): MedicalRecordWriter maps collected keys to columns generically"
```

---

## Task 3: `GeneralNeuroExtractor` + `NEURO_FIELDS`

**Files:**
- Create: `src/domain/interview/templates/medical_neuro.py` (extractor + fields only)
- Create: `tests/core/test_medical_neuro_fields.py`
- Create: `tests/core/test_medical_neuro_extractor.py`

3 extra fields. `onset_time` required (thrombolysis window). `neuro_exam` and `vascular_risk_factors` recommended+appendable.

- [ ] **Step 1: Write failing tests** (same shapes as the r1 plan's Task 1 — see that file for test content)

- [ ] **Step 2: Implement**

`src/domain/interview/templates/medical_neuro.py`:

```python
"""medical_neuro_v1 — 神外 cerebrovascular variant."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.interview.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.interview.hooks.safety import SafetyScreenHook
from domain.interview.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PostConfirmHook, SessionState, Writer,
)
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS, MedicalBatchExtractor,
    MedicalRecordWriter,
)

NEURO_EXTRA_FIELDS: list[FieldSpec] = [
    FieldSpec(name="onset_time", type="string", tier="required", appendable=False,
              label="发病时间",
              description="症状首次出现的时间（绝对时间或相对现在的小时数）",
              example="今晨7:30，约2小时前"),
    FieldSpec(name="neuro_exam", type="text", tier="recommended", appendable=True,
              label="神经系统查体",
              description="GCS、瞳孔、肌力、反射、脑神经、病理征",
              example="GCS 15，双侧瞳孔等大等圆，左上肢肌力3级，巴氏征（+）"),
    FieldSpec(name="vascular_risk_factors", type="text", tier="recommended",
              appendable=True, carry_forward_modes=frozenset({"doctor"}),
              label="血管危险因素",
              description="高血压/糖尿病/房颤/吸烟/家族卒中史",
              example="高血压10年，房颤，吸烟20年"),
]

NEURO_FIELDS: list[FieldSpec] = [*MEDICAL_FIELDS, *NEURO_EXTRA_FIELDS]


_NEURO_GUIDANCE = (
    "【神外重点】本次问诊为神经外科（脑血管方向），重点关注："
    "(1) 发病时间（溶栓窗）；(2) 神经系统查体（GCS/肌力/瞳孔/脑神经/病理征）；"
    "(3) 血管危险因素（高血压/糖尿病/房颤/吸烟/家族史）；"
    "(4) 危险信号：突发剧烈头痛、意识障碍、单侧肢体无力、言语不清、视物改变、呕吐、抽搐。"
    "若任一危险信号出现，立即提示就医。"
)


class GeneralNeuroExtractor(GeneralMedicalExtractor):
    """Neuro variant. Overrides fields() and injects neuro guidance into
    the prompt partial. All merge/completeness/extract-metadata/
    post-process behavior inherited unchanged — the extra FieldSpec entries
    participate in the shared FieldSpec-driven logic.
    """

    def fields(self) -> list[FieldSpec]:
        return NEURO_FIELDS

    async def prompt_partial(
        self,
        session_state: SessionState,
        completeness_state: CompletenessState,
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        messages = await super().prompt_partial(
            session_state, completeness_state, phase, mode,
        )
        if messages and messages[0].get("role") == "system":
            messages[0] = {
                **messages[0],
                "content": messages[0]["content"] + "\n\n" + _NEURO_GUIDANCE,
            }
        return messages
```

**Parent prompt_partial must pass session_state.template_id through:** in the same task, change `GeneralMedicalExtractor.prompt_partial` so its `compose_for_patient_interview` / `compose_for_doctor_interview` calls use `template_id=session_state.template_id` instead of the hardcoded `"medical_general_v1"`. This is a one-line change, required so neuro sessions log as neuro.

- [ ] **Step 3: Run, expect tests pass**

- [ ] **Step 4: Commit**

```
git commit -m "feat(interview): add GeneralNeuroExtractor + NEURO_FIELDS, thread template_id through prompt_partial"
```

---

## Task 4: `SafetyScreenHook`

**Files:**
- Create: `src/domain/interview/hooks/safety.py`
- Create: `tests/core/test_safety_screen_hook.py`

Keyword-based danger-signal screener for neuro records. Runs in BOTH patient-mode and doctor-mode post-confirm. Logs a structured alert and sends a doctor notification with a `【危险信号】` prefix (distinct from the therapy `【危机预警】`; safety_screen = clinical danger signals, crisis_alert = suicidality risk).

**Why keyword not LLM:** safety screening must be deterministic, fast, free to run, and auditable. A keyword pass + field inspection catches the clear cases. An LLM classifier can be slotted in later behind the same hook signature if false-negative rate is high.

- [ ] **Step 1: Write failing tests**

Scenarios:
- No danger keywords → no notification, no log warning.
- Danger keyword in `chief_complaint` → notification fired, structured log with matched keyword + field name.
- Danger keyword in `neuro_exam` → notification fired.
- Multiple matches → single notification (deduped), all matches logged.
- Notification backend failure → log warning, swallow exception (hooks are best-effort).

- [ ] **Step 2: Implement**

```python
"""Neuro safety-screen hook. Keyword-based danger-signal screener.

Fires a doctor notification if any danger keyword appears in relevant
fields. Hook is best-effort — failures log and don't unwind persist.
"""
from __future__ import annotations

from domain.interview.protocols import PersistRef, SessionState
from domain.tasks.notifications import (
    send_doctor_notification as _send_doctor_notification,
)
from utils.log import log


_DANGER_KEYWORDS = (
    "突发剧烈头痛", "剧烈头痛", "意识障碍", "意识不清", "昏迷",
    "单侧肢体无力", "偏瘫", "偏身麻木", "言语不清", "失语", "构音障碍",
    "视物重影", "视物模糊", "复视", "抽搐", "癫痫发作",
    "喷射性呕吐", "颈项强直",
)
_SCAN_FIELDS = ("chief_complaint", "present_illness", "neuro_exam")


class SafetyScreenHook:
    name = "safety_screen"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        hits: list[tuple[str, str]] = []  # (field, keyword)
        for field_name in _SCAN_FIELDS:
            text = collected.get(field_name) or ""
            for kw in _DANGER_KEYWORDS:
                if kw in text:
                    hits.append((field_name, kw))

        if not hits:
            return

        patient_name = collected.get("_patient_name") or "患者"
        keywords = "、".join(sorted({kw for _, kw in hits}))
        body = (
            f"【危险信号】患者【{patient_name}】记录中出现神外危险信号：{keywords}。"
            f"请尽快评估。记录 ID={ref.id}"
        )
        log(
            f"[safety] danger signals detected: doctor={session.doctor_id} "
            f"record={ref.id} hits={hits}"
        )
        try:
            await _send_doctor_notification(session.doctor_id, body)
        except Exception as e:
            log(f"[safety] notification failed (non-blocking): {e}", level="warning")
```

- [ ] **Step 3: Run, expect all tests pass**

- [ ] **Step 4: Commit**

```
git commit -m "feat(interview): add SafetyScreenHook — neuro danger-signal keyword screener"
```

---

## Task 5: Patient-portal template_id routing (bug A)

**Files:**
- Modify: `src/domain/patients/interview_session.py` — `create_session` accepts optional `template_id`.
- Modify: `src/channels/web/patient_interview_routes.py` — `/start` endpoint accepts `template_id` query param OR reads from doctor's `preferred_template_id`; threads into `create_session`.
- Create: `tests/channels/test_patient_portal_template_routing.py`

**Why:** a patient can't reach `medical_neuro_v1` from the patient portal today — `create_session()` hardcodes the default. Neuro supports patient mode (patient-side intake), so this path must work.

- [ ] **Step 1: Write failing test**

```python
"""Patient portal must honor an explicit template_id on /start, and
must fall back to the doctor's preferred_template_id when omitted.
"""

@pytest.mark.asyncio
async def test_start_session_with_explicit_template_id():
    # doctor_id + invite, POST /api/patient/interview/start?template_id=medical_neuro_v1
    # assert created session has template_id = medical_neuro_v1

@pytest.mark.asyncio
async def test_start_session_falls_back_to_doctor_preferred_template():
    # doctor has preferred_template_id = medical_neuro_v1, no query param
    # assert created session has template_id = medical_neuro_v1

@pytest.mark.asyncio
async def test_start_session_falls_back_to_default_when_both_empty():
    # doctor has preferred_template_id = NULL, no query param
    # assert created session has template_id = medical_general_v1
```

- [ ] **Step 2: Implement**

- [ ] **Step 3: Run**

- [ ] **Step 4: Commit**

```
git commit -m "fix(patient-portal): thread template_id through /start (bug A)"
```

---

## Task 6: Patient resume/current readiness via template extractor (bug B)

**Files:**
- Modify: `src/channels/web/patient_interview_routes.py` — `/current` and the completeness check in `/turn` use `template.extractor.completeness(session.collected, "patient")` instead of the legacy `get_completeness_state`.
- Create: `tests/channels/test_patient_resume_template_completeness.py`

**Why:** without this, a neuro patient session will be judged complete using the `medical_general_v1` required-field set — `onset_time` won't be required at the patient route layer, and transitions to `reviewing` will fire at the wrong moment.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_neuro_patient_session_requires_onset_time_to_complete():
    # Create neuro session, patient submits turns filling chief_complaint only
    # Assert /current returns can_complete=False
    # Patient adds onset_time in next turn
    # Assert /current returns can_complete=True
```

- [ ] **Step 2: Implement — route completeness check through active template's extractor**

- [ ] **Step 3: Run**

- [ ] **Step 4: Commit**

```
git commit -m "fix(patient-portal): resume readiness routed through template extractor (bug B)"
```

---

## Task 7: Doctor inline-edit widening (bug C)

**Files:**
- Modify: `src/channels/web/doctor_interview/turn.py` — replace hardcoded `FIELD_LABELS` check with `template.extractor.fields()` field-name membership check.
- Create: `tests/channels/test_doctor_inline_edit_neuro.py`

**Why:** doctor editing `onset_time` / `neuro_exam` / `vascular_risk_factors` returns 422 today.

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_inline_edit_onset_time_on_neuro_session_succeeds():
    # Create neuro session, PATCH /field with onset_time=...
    # Assert 200 and session.collected["onset_time"] updated
```

- [ ] **Step 2: Implement**

- [ ] **Step 3: Run**

- [ ] **Step 4: Commit**

```
git commit -m "fix(doctor-interview): inline-edit validates against active template fields (bug C)"
```

---

## Task 8: `GeneralNeuroTemplate` + registry

**Files:**
- Modify: `src/domain/interview/templates/medical_neuro.py` (append template binding)
- Modify: `src/domain/interview/templates/__init__.py` (register)
- Create: `tests/core/test_medical_neuro_template.py`
- Modify: `tests/core/test_template_registry.py` (3 templates now)

Final hook composition for `medical_neuro_v1`:

| Mode | Hooks | Rationale |
|---|---|---|
| patient | `TriggerDiagnosisPipelineHook`, `NotifyDoctorHook`, `SafetyScreenHook` | Preserves `medical_general_v1` patient-mode semantics + adds safety screen. |
| doctor | `GenerateFollowupTasksHook`, `SafetyScreenHook` | Preserves `medical_general_v1` doctor-mode semantics (no diagnosis) + adds safety screen. |

`SafetyScreenHook` runs on **both** modes — that's the whole point of splitting it from `TriggerDiagnosisPipelineHook`. Safety screening applies regardless of who dictated. Diagnosis pipeline stays patient-only for now, matching `medical_general_v1`.

- [ ] **Step 1: Write failing tests**

Tests assert: registration, supported_modes, extractor/writer types, hook lists per mode (specifically that `SafetyScreenHook` appears in both and `TriggerDiagnosisPipelineHook` is patient-only), 3 templates in registry.

- [ ] **Step 2: Append template binding**

```python
@dataclass
class GeneralNeuroTemplate:
    id: str = "medical_neuro_v1"
    kind: str = "medical"
    display_name: str = "神外问诊（脑血管）"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralNeuroExtractor)
    batch_extractor: BatchExtractor | None = field(
        default_factory=MedicalBatchExtractor,
    )
    writer: Writer = field(default_factory=MedicalRecordWriter)  # reused, now generic
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
                SafetyScreenHook(),
            ],
            "doctor": [
                GenerateFollowupTasksHook(),
                SafetyScreenHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
```

- [ ] **Step 3: Register in `TEMPLATES`**

```python
TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "medical_neuro_v1": GeneralNeuroTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
}
```

- [ ] **Step 4: Run**

- [ ] **Step 5: Commit**

```
git commit -m "feat(interview): register medical_neuro_v1 (diagnosis patient-only, safety screen both modes)"
```

---

## Task 9: Regression sweep + sim + integration coverage

- [ ] **Step 1: Full suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent --tb=short 2>&1 | tail -20
```

Target: post-Phase-3 baseline + ~50 new tests, no regressions.

- [ ] **Step 2: reply_sim Tier-2 — medical_general_v1 unchanged**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python scripts/run_reply_sim.py \
    --tier 2 --template medical_general_v1
```

Delta within ±2% of post-Phase-3 baseline.

- [ ] **Step 3: Neuro sim scenarios (§7e new-template gate)**

3 scenarios minimum:

- `sim/scenarios/neuro_happy_path.yaml` — stroke-onset intake completes with all required neuro fields populated; `TriggerDiagnosisPipelineHook` + `SafetyScreenHook` both fire on patient confirm.
- `sim/scenarios/neuro_danger_signal_triggered.yaml` — patient says "突发剧烈头痛" in `chief_complaint`; `SafetyScreenHook` fires a doctor notification with `【危险信号】` prefix.
- `sim/scenarios/neuro_no_onset_time_recall.yaml` — edge case: patient says "不清楚" for `onset_time`; extractor accepts "不清楚" as a non-empty value satisfying the required tier; session still reaches `reviewing`.

- [ ] **Step 4: Integration test sweep (Codex's 6 cases, scoped to neuro-only)**

New or extended tests (most already covered by Tasks 0–7 above; this step is the consolidation):

| Case | Test |
|---|---|
| Patient portal start on non-default template | `test_patient_portal_template_routing.py::test_start_session_with_explicit_template_id` (Task 5) |
| Patient resume readiness uses template extractor | `test_patient_resume_template_completeness.py` (Task 6) |
| Doctor PATCH field for neuro extras | `test_doctor_inline_edit_neuro.py::test_inline_edit_onset_time_on_neuro_session_succeeds` (Task 7) |
| Session JSON == persisted artifact after confirm | `test_engine_confirm_persistence.py` (Task 0) |
| SafetyScreenHook fires on danger signal in both modes | `test_safety_screen_hook.py::test_fires_in_patient_mode` + `test_fires_in_doctor_mode` (Task 4) |
| `MedicalRecordWriter` writes neuro columns | `test_medical_record_writer_generic.py::test_writer_maps_neuro_fields_to_new_columns` (Task 2) |

- [ ] **Step 5: Commit**

```
git commit -m "test(sim): neuro scenarios + integration coverage"
```

- [ ] **Step 6: Commit history sanity**

```
git log <phase3-head>..HEAD --oneline
```

Expected: 10 Phase 4 r2 commits.

---

## Phase 5 hand-off (not this phase)

When we come back to therapy intake, it should include all of:

- `form_therapy_intake_v1` template (kind="form", 6 fields with required `crisis_risk`).
- Tiered `CrisisAlertHook` with 3 levels (passive → review-queue flag, active → in-app page, plan_or_intent → page + SMS + audit log entry).
- Chinese keyword backstop over the transcript as a false-negative safety net.
- Structured alert payload (code / severity / source / evidence / session_id) — not a string prefix.
- Therapist form-kind review queue. New API: `POST /api/form_responses/{id}/confirm`, list filter on `form_responses.status`, UI surface.
- `confirm_interview` return-contract fix for `PersistRef(kind="form_response")` (bug D).
- Audit trail schema — all crisis-related decisions logged with immutable timestamp + acting user.
- Legal/compliance review sign-off. (Out of scope for engineering alone.)

---

## Out of scope

- Frontend UI to select `medical_neuro_v1` at session create — Phase 5 ships the doctor-side chooser; for now neuro is reachable via explicit `template_id` query param or doctor `preferred_template_id`.
- Prompt hash stamping of `template_id` in `prompt_composer` — r2 threads the id through the function call, but the composer itself still ignores it. Full integration when prompt-hash tracking lands.
- Hook composition helpers (should-fix item #5 from the review) — acknowledged but not addressed here; deferred until a 3rd medical specialty template ships and the copy-paste pressure is real.

## Risk notes

- **Migration on prod.** The Alembic migration adds nullable columns; safe under MySQL and SQLite. Deploy order: migrate → code deploy. Neuro sessions can't land until both are in place; `medical_general_v1` unaffected.
- **MedicalRecordWriter generic refactor.** Broader blast radius than neuro itself. Every existing medical_general_v1 flow runs through it. The regression test gate is the full test suite + reply_sim ±2% — if either regresses, revert the refactor and hand-wire neuro columns instead. Acceptable fallback.
- **SafetyScreenHook keyword false positives.** A patient saying "我没有突发剧烈头痛" still hits the keyword. Mitigation: start with notification-only (no blocking action); monitor false-positive rate over first 2 weeks; iterate. If noise is unacceptable, add negation check or move to LLM classifier behind the same hook interface.
- **§8 hook rationale now clean.** Diagnosis remains patient-only for all medical templates. Safety is a separate, explicit concern. If product later wants doctor-mode diagnosis for any template, it's a single hook-list change with clear semantics.

