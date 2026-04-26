# Intake Pipeline Extensibility — Phase 4 (Specialty Variants: Neuro + Therapy Intake)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Ship two new templates that exercise the per-template seams built in Phases 1–3, and resolve §8 of the design spec (doctor-mode diagnosis trigger) via option (c) — per-template hook lists.

- `medical_neuro_v1` — 神外 (cerebrovascular-flavored neurosurgery) variant. Same schema as `medical_general_v1` + 3 specialty-specific fields, neuro-emphasized prompt partial, **fires diagnosis on both patient and doctor confirm** (overrides the `medical_general_v1` asymmetry). Reuses `MedicalRecordWriter` and `MedicalBatchExtractor`.
- `form_therapy_intake_v1` — client-facing psychotherapy intake form. `kind="form"`, persists to `form_responses`, **new `CrisisAlertHook`** pages the therapist immediately on elevated suicidality risk. Patient-mode only.

**Resolves §8 open product decision:** doctor-mode now fires diagnosis for `medical_neuro_v1` (because 危险信号 screening matters regardless of who entered the data), stays off for `medical_general_v1` (preserves existing behavior, no regression for non-neuro doctors).

**Reference:** spec §6a Phase 4 row, §8 bullet 1 (doctor-mode diagnosis), §3b (per-template hook lists), §4b (registry), §7e (new-template gate), §7f (FieldSpec semantic tests).

---

## Preconditions

- Phase 3 landed (`TEMPLATES` contains `medical_general_v1` + `form_satisfaction_v1`).
- Alembic head: `c9f8d2e14a20` (unchanged — no schema migration in Phase 4).
- Full suite green (492+ tests).

## Behavior-preservation bar

- `medical_general_v1` behavior unchanged. All existing tests plus the Phase 3 suite still pass.
- reply_sim Tier-2 pass rate stays within ±2% of post-Phase-3 baseline.
- New tests exclusively cover the two new templates + the crisis-alert path.

## File map

**Create:**
- `src/domain/intake/templates/medical_neuro.py` — `GeneralNeuroExtractor`, `GeneralNeuroTemplate`, `NEURO_EXTRA_FIELDS`.
- `src/domain/intake/templates/form_therapy_intake.py` — `FormTherapyIntakeExtractor`, `FormTherapyIntakeTemplate`, `FORM_THERAPY_INTAKE_FIELDS`.
- `src/domain/intake/hooks/therapy.py` — `CrisisAlertHook`.
- `tests/core/test_medical_neuro_fields.py`
- `tests/core/test_medical_neuro_extractor.py`
- `tests/core/test_medical_neuro_template.py`
- `tests/core/test_form_therapy_intake_fields.py`
- `tests/core/test_form_therapy_intake_extractor.py`
- `tests/core/test_form_therapy_intake_template.py`
- `tests/core/test_crisis_alert_hook.py`

**Modify:**
- `src/domain/intake/templates/__init__.py` — register both new templates.
- `tests/core/test_template_registry.py` — assert 4 templates registered.

**Not modified (deliberate):**
- `src/db/models/records.py` — no new columns. Neuro extra fields map into `specialist_exam` (neuro_exam), `present_illness` prefix (onset_time), `past_history` prefix (vascular_risk_factors) at persist time.
- `src/agent/prompt_composer.py` — `template_id` still ignored at the composer level. Neuro-specific prompt text lives in `GeneralNeuroExtractor.prompt_partial` which pre-formats the `patient_context` string with neuro guidance before passing through.
- Alembic — no migration.

---

## Task 1: `GeneralNeuroExtractor` + neuro field specs

**Files:**
- Create: `src/domain/intake/templates/medical_neuro.py` (partial — extractor + fields only)
- Create: `tests/core/test_medical_neuro_fields.py`
- Create: `tests/core/test_medical_neuro_extractor.py`

Neuro extends the base MEDICAL_FIELDS with 3 fields that materially change triage:

| Field | Type / tier | Why it matters |
|---|---|---|
| `onset_time` | string, required | Thrombolysis window is 4.5h from symptom onset, not from arrival. Mandatory for any cerebrovascular-flavored 神外 intake. |
| `neuro_exam` | text, recommended, appendable | GCS + 肌力 + 瞳孔 + 脑神经 查体. Distinct from general `physical_exam`. |
| `vascular_risk_factors` | text, recommended, appendable, carry_forward={doctor} | 高血压 / 糖尿病 / 房颤 / 吸烟 / 家族卒中史. Persistent across visits. |

All 14 base MEDICAL_FIELDS are retained unchanged.

- [ ] **Step 1: Write failing tests**

`tests/core/test_medical_neuro_fields.py`:

```python
"""NEURO_FIELDS — MEDICAL_FIELDS + 3 neuro-specific specs."""
from __future__ import annotations

from domain.intake.templates.medical_neuro import NEURO_EXTRA_FIELDS, NEURO_FIELDS
from domain.intake.templates.medical_general import MEDICAL_FIELDS


def test_neuro_extra_has_three_specs():
    assert len(NEURO_EXTRA_FIELDS) == 3
    names = {f.name for f in NEURO_EXTRA_FIELDS}
    assert names == {"onset_time", "neuro_exam", "vascular_risk_factors"}


def test_neuro_fields_is_base_plus_extras():
    base_names = [f.name for f in MEDICAL_FIELDS]
    all_names = [f.name for f in NEURO_FIELDS]
    # Base fields preserved in order; extras appended at end
    assert all_names[: len(base_names)] == base_names
    assert all_names[len(base_names):] == [f.name for f in NEURO_EXTRA_FIELDS]


def test_onset_time_is_required():
    spec = next(f for f in NEURO_EXTRA_FIELDS if f.name == "onset_time")
    assert spec.tier == "required"
    assert spec.appendable is False


def test_vascular_risk_carry_forward_doctor_only():
    spec = next(f for f in NEURO_EXTRA_FIELDS if f.name == "vascular_risk_factors")
    assert "doctor" in spec.carry_forward_modes
    assert "patient" not in spec.carry_forward_modes


def test_neuro_exam_is_appendable():
    spec = next(f for f in NEURO_EXTRA_FIELDS if f.name == "neuro_exam")
    assert spec.appendable is True
```

`tests/core/test_medical_neuro_extractor.py`:

```python
"""GeneralNeuroExtractor — subclass-like variant of GeneralMedicalExtractor."""
from __future__ import annotations

import pytest

from domain.intake.templates.medical_neuro import (
    GeneralNeuroExtractor, NEURO_FIELDS,
)


@pytest.fixture
def extractor():
    return GeneralNeuroExtractor()


def test_fields_returns_neuro_fields(extractor):
    assert extractor.fields() is NEURO_FIELDS


def test_patient_mode_completeness_requires_onset_and_chief_complaint(extractor):
    # Chief complaint alone is insufficient — neuro adds onset_time as required
    state = extractor.completeness({"chief_complaint": "左侧肢体无力"}, "patient")
    assert state.can_complete is False
    assert "onset_time" in state.required_missing


def test_patient_mode_completeness_satisfied_with_both(extractor):
    state = extractor.completeness(
        {"chief_complaint": "左侧肢体无力", "onset_time": "2小时前"},
        "patient",
    )
    assert state.can_complete is True


def test_neuro_exam_merge_appends(extractor):
    collected = {}
    extractor.merge(collected, {"neuro_exam": "GCS 15"})
    extractor.merge(collected, {"neuro_exam": "左上肢肌力3级"})
    assert "GCS 15" in collected["neuro_exam"]
    assert "左上肢肌力3级" in collected["neuro_exam"]


def test_onset_time_merge_overwrites(extractor):
    collected = {"onset_time": "2小时前"}
    extractor.merge(collected, {"onset_time": "约1小时前（修正）"})
    assert collected["onset_time"] == "约1小时前（修正）"
```

- [ ] **Step 2: Run, expect ModuleNotFoundError**

- [ ] **Step 3: Implement**

`src/domain/intake/templates/medical_neuro.py`:

```python
"""medical_neuro_v1 — 神外 (cerebrovascular) variant of the general medical
template.

Schema: MEDICAL_FIELDS + 3 neuro-specific specs (onset_time, neuro_exam,
vascular_risk_factors). Reuses MedicalRecordWriter — the 3 extras fold into
existing columns at persist time (see GeneralNeuroExtractor.project_extras).

Hook asymmetry: fires diagnosis on BOTH patient and doctor confirm (overrides
medical_general_v1's archaeological asymmetry). Rationale: neuro危险信号
screening applies regardless of who entered the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.intake.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PostConfirmHook, SessionState, Writer,
)
from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS, MedicalBatchExtractor,
    MedicalRecordWriter,
)

NEURO_EXTRA_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="onset_time", type="string", tier="required", appendable=False,
        label="发病时间",
        description="症状首次出现的时间（绝对时间或相对现在的小时数）",
        example="今晨7:30，约2小时前",
    ),
    FieldSpec(
        name="neuro_exam", type="text", tier="recommended", appendable=True,
        label="神经系统查体",
        description="GCS、瞳孔、肌力、反射、脑神经、病理征",
        example="GCS 15，双侧瞳孔等大等圆，左上肢肌力3级，巴氏征（+）",
    ),
    FieldSpec(
        name="vascular_risk_factors", type="text", tier="recommended",
        appendable=True, carry_forward_modes=frozenset({"doctor"}),
        label="血管危险因素",
        description="高血压/糖尿病/房颤/吸烟/家族卒中史",
        example="高血压10年，房颤，吸烟20年",
    ),
]

NEURO_FIELDS: list[FieldSpec] = [*MEDICAL_FIELDS, *NEURO_EXTRA_FIELDS]


_NEURO_GUIDANCE = (
    "【神外重点】本次问诊为神经外科（脑血管/神经重症方向），"
    "重点关注：(1) 发病时间（溶栓窗判断）；(2) 神经系统查体（GCS/肌力/瞳孔/"
    "脑神经/病理征）；(3) 血管危险因素（高血压/糖尿病/房颤/吸烟/家族史）；"
    "(4) 危险信号：突发剧烈头痛、意识障碍、单侧肢体无力、言语不清、视物改变、"
    "呕吐、抽搐。若任一危险信号出现，立即提示就医。"
)


class GeneralNeuroExtractor(GeneralMedicalExtractor):
    """Neuro variant. Overrides fields() and prompt_partial guidance.

    All other behavior (merge, completeness tiering, extract_metadata,
    post_process_reply) is inherited unchanged — the extra fields participate
    in merge/completeness via the shared FieldSpec-driven logic in the base.
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
        # Inject neuro guidance into the first system message (the base
        # composer puts L1+L2+L3 into messages[0]).
        if messages and messages[0].get("role") == "system":
            messages[0] = {
                **messages[0],
                "content": messages[0]["content"] + "\n\n" + _NEURO_GUIDANCE,
            }
        return messages

    @staticmethod
    def project_extras(collected: dict[str, str]) -> dict[str, str]:
        """Fold neuro-only fields into existing MedicalRecordDB columns before
        persist. Called by the writer wrapper below.

        - onset_time → prepended to present_illness ("发病时间: X。" + existing)
        - neuro_exam → specialist_exam (overwrite-first, then append if both set)
        - vascular_risk_factors → appended to past_history
        """
        out = dict(collected)
        onset = (out.pop("onset_time", "") or "").strip()
        neuro = (out.pop("neuro_exam", "") or "").strip()
        vrf = (out.pop("vascular_risk_factors", "") or "").strip()

        if onset:
            prefix = f"发病时间：{onset}。"
            existing = out.get("present_illness", "") or ""
            out["present_illness"] = (
                prefix + existing if existing else prefix
            )
        if neuro:
            existing = out.get("specialist_exam", "") or ""
            out["specialist_exam"] = (
                f"{existing}；{neuro}".strip("；") if existing else neuro
            )
        if vrf:
            existing = out.get("past_history", "") or ""
            out["past_history"] = (
                f"{existing}；血管危险因素：{vrf}".strip("；")
                if existing else f"血管危险因素：{vrf}"
            )
        return out


class NeuroMedicalRecordWriter(MedicalRecordWriter):
    """MedicalRecordWriter that projects neuro-extra fields into base columns
    before delegating to the parent persist."""

    async def persist(self, session, collected):
        projected = GeneralNeuroExtractor.project_extras(collected)
        # Preserve underscore metadata (patient_name/gender/age) that
        # project_extras leaves untouched
        return await super().persist(session, projected)
```

- [ ] **Step 4: Run, expect all tests pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(intake): add GeneralNeuroExtractor — MEDICAL_FIELDS + 3 neuro specs"
```

---

## Task 2: `GeneralNeuroTemplate` + registry

**Files:**
- Modify: `src/domain/intake/templates/medical_neuro.py` (append template binding)
- Modify: `src/domain/intake/templates/__init__.py` (register `medical_neuro_v1`)
- Create: `tests/core/test_medical_neuro_template.py`

- [ ] **Step 1: Write failing tests**

`tests/core/test_medical_neuro_template.py`:

```python
"""medical_neuro_v1 — template binding + registry entry.

Key property under test: §8 resolution — neuro fires diagnosis on BOTH
patient and doctor confirm, unlike medical_general_v1 which fires only on
patient confirm.
"""
from __future__ import annotations

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.intake.templates import TEMPLATES, get_template
from domain.intake.templates.medical_neuro import (
    GeneralNeuroExtractor, GeneralNeuroTemplate, NeuroMedicalRecordWriter,
)


def test_medical_neuro_v1_registered():
    t = get_template("medical_neuro_v1")
    assert isinstance(t, GeneralNeuroTemplate)


def test_supports_both_modes():
    t = get_template("medical_neuro_v1")
    assert set(t.supported_modes) == {"patient", "doctor"}


def test_uses_neuro_extractor_and_writer():
    t = get_template("medical_neuro_v1")
    assert isinstance(t.extractor, GeneralNeuroExtractor)
    assert isinstance(t.writer, NeuroMedicalRecordWriter)


def test_patient_hooks_include_diagnosis():
    t = get_template("medical_neuro_v1")
    hook_types = {type(h) for h in t.post_confirm_hooks["patient"]}
    assert TriggerDiagnosisPipelineHook in hook_types
    assert NotifyDoctorHook in hook_types


def test_doctor_hooks_also_fire_diagnosis():
    """§8 resolution: doctor-mode also fires diagnosis for neuro."""
    t = get_template("medical_neuro_v1")
    hook_types = {type(h) for h in t.post_confirm_hooks["doctor"]}
    assert TriggerDiagnosisPipelineHook in hook_types
    assert GenerateFollowupTasksHook in hook_types
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Append template binding to `medical_neuro.py`**

```python
@dataclass
class GeneralNeuroTemplate:
    """medical_neuro_v1 — 神外 cerebrovascular-flavored variant.

    §8 resolution: doctor-mode fires diagnosis (unlike medical_general_v1).
    Rationale: neuro危险信号 screening applies to any cerebrovascular record.
    """
    id: str = "medical_neuro_v1"
    kind: str = "medical"
    display_name: str = "神外问诊（脑血管）"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralNeuroExtractor)
    batch_extractor: BatchExtractor | None = field(
        default_factory=MedicalBatchExtractor,
    )
    writer: Writer = field(default_factory=NeuroMedicalRecordWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
            ],
            "doctor": [
                TriggerDiagnosisPipelineHook(),     # §8: added vs medical_general_v1
                GenerateFollowupTasksHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
```

- [ ] **Step 4: Register in `TEMPLATES`**

Modify `src/domain/intake/templates/__init__.py`:

```python
from domain.intake.templates.medical_general import GeneralMedicalTemplate
from domain.intake.templates.medical_neuro import GeneralNeuroTemplate
from domain.intake.templates.form_satisfaction import FormSatisfactionTemplate


TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "medical_neuro_v1": GeneralNeuroTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
}
```

- [ ] **Step 5: Run, expect all tests pass + update `test_template_registry.py` (3 templates now)**

- [ ] **Step 6: Commit**

```
git commit -m "feat(intake): register medical_neuro_v1 — §8 doctor-mode fires diagnosis"
```

---

## Task 3: `CrisisAlertHook`

**Files:**
- Create: `src/domain/intake/hooks/therapy.py`
- Create: `tests/core/test_crisis_alert_hook.py`

Alerts the therapist via the existing `send_doctor_notification` channel when `crisis_risk ∈ {"active_ideation", "plan_or_intent"}`. Uses a distinct message prefix so UI can surface it above the normal review queue (frontend filtering is out of scope for this phase).

- [ ] **Step 1: Write failing tests**

`tests/core/test_crisis_alert_hook.py`:

```python
"""CrisisAlertHook — pages the therapist on elevated suicidality risk."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from domain.intake.hooks.therapy import CrisisAlertHook
from domain.intake.protocols import PersistRef, SessionState


def _session(doctor_id="doc_x", patient_id=1):
    return SessionState(
        id="s_1", doctor_id=doctor_id, patient_id=patient_id,
        mode="patient", status="confirmed",
        template_id="form_therapy_intake_v1",
        collected={}, conversation=[], turn_count=3,
    )


@pytest.mark.asyncio
async def test_no_alert_for_none():
    hook = CrisisAlertHook()
    with patch(
        "domain.intake.hooks.therapy._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        await hook.run(
            _session(), PersistRef(kind="form_response", id=1),
            {"crisis_risk": "none"},
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_no_alert_for_passive_ideation():
    """Passive ideation logs but does not page — therapist reviews via
    normal queue. (Policy decision; revisit if feedback says we're under-
    alerting.)"""
    hook = CrisisAlertHook()
    with patch(
        "domain.intake.hooks.therapy._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        await hook.run(
            _session(), PersistRef(kind="form_response", id=1),
            {"crisis_risk": "passive_ideation"},
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_alerts_on_active_ideation():
    hook = CrisisAlertHook()
    with patch(
        "domain.intake.hooks.therapy._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        await hook.run(
            _session(doctor_id="doc_abc"),
            PersistRef(kind="form_response", id=42),
            {"crisis_risk": "active_ideation", "_patient_name": "张三"},
        )
        mock_send.assert_awaited_once()
        args, _ = mock_send.call_args
        assert args[0] == "doc_abc"
        assert "【危机预警】" in args[1]
        assert "张三" in args[1]


@pytest.mark.asyncio
async def test_alerts_on_plan_or_intent():
    hook = CrisisAlertHook()
    with patch(
        "domain.intake.hooks.therapy._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        await hook.run(
            _session(), PersistRef(kind="form_response", id=1),
            {"crisis_risk": "plan_or_intent"},
        )
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_swallows_notification_failure():
    """Hooks are best-effort — failures log, don't raise."""
    hook = CrisisAlertHook()
    with patch(
        "domain.intake.hooks.therapy._send_doctor_notification",
        new_callable=AsyncMock,
        side_effect=RuntimeError("notification backend down"),
    ):
        # Should NOT raise
        await hook.run(
            _session(), PersistRef(kind="form_response", id=1),
            {"crisis_risk": "active_ideation"},
        )
```

- [ ] **Step 2: Implement**

`src/domain/intake/hooks/therapy.py`:

```python
"""Therapy-template post-confirm hooks."""
from __future__ import annotations

from domain.intake.protocols import PersistRef, SessionState
from domain.tasks.notifications import (
    send_doctor_notification as _send_doctor_notification,
)
from utils.log import log


_ALERT_LEVELS = frozenset({"active_ideation", "plan_or_intent"})


class CrisisAlertHook:
    """Pages the therapist immediately if the client's crisis_risk field
    is at or above active_ideation. Below that (none / passive_ideation),
    the intake flows through the normal review queue.

    Message prefix 【危机预警】 is load-bearing — frontend surfaces these
    above the normal notification stream. Do not change without updating
    the reader.
    """
    name = "crisis_alert"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        risk = (collected.get("crisis_risk") or "").strip()
        if risk not in _ALERT_LEVELS:
            return
        patient_name = collected.get("_patient_name") or "来访者"
        body = (
            f"【危机预警】来访者【{patient_name}】在首次心理咨询登记中"
            f"报告了{'主动自杀意念' if risk == 'active_ideation' else '自杀计划或意图'}，"
            f"请立即联系。"
        )
        try:
            await _send_doctor_notification(session.doctor_id, body)
            log(f"[therapy] crisis alert sent: doctor={session.doctor_id} form={ref.id}")
        except Exception as e:
            log(
                f"[therapy] crisis alert notification failed: {e}",
                level="warning",
            )
```

- [ ] **Step 3: Run, expect 5 passed**

- [ ] **Step 4: Commit**

```
git commit -m "feat(intake): add CrisisAlertHook — pages therapist on elevated suicidality risk"
```

---

## Task 4: `FormTherapyIntakeExtractor` + fields

**Files:**
- Create: `src/domain/intake/templates/form_therapy_intake.py` (partial — extractor + fields)
- Create: `tests/core/test_form_therapy_intake_fields.py`
- Create: `tests/core/test_form_therapy_intake_extractor.py`

6 fields:

| Field | Type / tier | Notes |
|---|---|---|
| `presenting_issue` | text, required | 本次寻求咨询的主要困扰 |
| `goals` | text, recommended | 期待通过咨询达到的目标 |
| `mood_baseline` | enum, recommended | `稳定 / 低落 / 焦虑 / 易怒 / 麻木 / 波动大` |
| `prior_therapy` | text, optional | 既往心理咨询/药物治疗史 |
| `support_system` | text, optional | 家人/朋友/工作支持情况 |
| `crisis_risk` | enum, **required** | `none / passive_ideation / active_ideation / plan_or_intent` — drives CrisisAlertHook |

- [ ] **Step 1: Write failing tests**

`tests/core/test_form_therapy_intake_fields.py`:

```python
from __future__ import annotations

from domain.intake.templates.form_therapy_intake import (
    FORM_THERAPY_INTAKE_FIELDS,
)


def test_has_six_fields():
    assert len(FORM_THERAPY_INTAKE_FIELDS) == 6


def test_crisis_risk_is_required_enum_with_four_levels():
    spec = next(
        f for f in FORM_THERAPY_INTAKE_FIELDS if f.name == "crisis_risk"
    )
    assert spec.tier == "required"
    assert spec.type == "enum"
    assert spec.enum_values == (
        "none", "passive_ideation", "active_ideation", "plan_or_intent",
    )


def test_presenting_issue_is_required():
    spec = next(
        f for f in FORM_THERAPY_INTAKE_FIELDS if f.name == "presenting_issue"
    )
    assert spec.tier == "required"


def test_mood_baseline_enum_values():
    spec = next(
        f for f in FORM_THERAPY_INTAKE_FIELDS if f.name == "mood_baseline"
    )
    assert spec.type == "enum"
    assert "低落" in spec.enum_values
    assert "焦虑" in spec.enum_values


def test_no_carry_forward_on_intake():
    """Intake is one-shot per client — prior records never pre-seed."""
    for spec in FORM_THERAPY_INTAKE_FIELDS:
        assert spec.carry_forward_modes == frozenset()
```

`tests/core/test_form_therapy_intake_extractor.py`:

```python
from __future__ import annotations

import pytest

from domain.intake.protocols import SessionState
from domain.intake.templates.form_therapy_intake import (
    FormTherapyIntakeExtractor,
)


@pytest.fixture
def extractor():
    return FormTherapyIntakeExtractor()


def test_completeness_missing_crisis_risk_blocks_completion(extractor):
    state = extractor.completeness(
        {"presenting_issue": "最近失眠严重"}, "patient",
    )
    assert state.can_complete is False
    assert "crisis_risk" in state.required_missing


def test_completeness_with_both_required(extractor):
    state = extractor.completeness(
        {"presenting_issue": "失眠", "crisis_risk": "none"}, "patient",
    )
    assert state.can_complete is True


def test_merge_overwrites_enum(extractor):
    collected = {"crisis_risk": "passive_ideation"}
    extractor.merge(collected, {"crisis_risk": "active_ideation"})
    assert collected["crisis_risk"] == "active_ideation"


@pytest.mark.asyncio
async def test_prompt_partial_mentions_crisis_screening(extractor):
    session = SessionState(
        id="s", doctor_id="d", patient_id=1, mode="patient",
        status="active", template_id="form_therapy_intake_v1",
        collected={}, conversation=[], turn_count=0,
    )
    result = await extractor.prompt_partial(
        session_state=session,
        completeness_state=extractor.completeness({}, "patient"),
        phase="default", mode="patient",
    )
    joined = "\n".join(m.get("content", "") for m in result)
    # System prompt must brief the LLM on tactful crisis screening
    assert "自伤" in joined or "自杀" in joined or "安全" in joined
```

- [ ] **Step 2: Implement**

`src/domain/intake/templates/form_therapy_intake.py` (extractor + fields, template appended in Task 5):

```python
"""form_therapy_intake_v1 — client-facing psychotherapy intake form.

kind="form"; persists to form_responses. Single-shot per client (new
engagement). Required crisis_risk field feeds CrisisAlertHook.
"""
from __future__ import annotations

from typing import Any

from domain.intake.protocols import (
    CompletenessState, FieldSpec, Mode, Phase, SessionState,
)


_MOOD_ENUM = ("稳定", "低落", "焦虑", "易怒", "麻木", "波动大")
_CRISIS_ENUM = ("none", "passive_ideation", "active_ideation", "plan_or_intent")


FORM_THERAPY_INTAKE_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="presenting_issue", type="text", tier="required", appendable=False,
        label="主要困扰",
        description="本次寻求咨询的主要困扰是什么（尽量具体描述）",
        example="最近两个月失眠、对工作失去兴趣",
    ),
    FieldSpec(
        name="goals", type="text", tier="recommended", appendable=False,
        label="咨询目标",
        description="期待通过咨询达到什么",
        example="改善睡眠、找回工作动力",
    ),
    FieldSpec(
        name="mood_baseline", type="enum", tier="recommended", appendable=False,
        enum_values=_MOOD_ENUM,
        label="近期情绪",
        description="过去一周最常出现的情绪状态",
    ),
    FieldSpec(
        name="prior_therapy", type="text", tier="optional", appendable=False,
        label="既往咨询/治疗史",
        description="曾做过心理咨询或服用精神科药物的情况",
        example="2年前因焦虑服舍曲林半年",
    ),
    FieldSpec(
        name="support_system", type="text", tier="optional", appendable=False,
        label="支持系统",
        description="身边可以倾诉或依靠的人",
        example="配偶支持，父母不知情",
    ),
    FieldSpec(
        name="crisis_risk", type="enum", tier="required", appendable=False,
        enum_values=_CRISIS_ENUM,
        label="安全评估",
        description=(
            "过去两周是否出现过以下想法：none=无；"
            "passive_ideation=被动想法（活着没意思但不想主动结束）；"
            "active_ideation=主动想伤害自己或结束生命；"
            "plan_or_intent=有具体计划或意图"
        ),
    ),
]


_SYSTEM_PREAMBLE = (
    "你是心理咨询首次登记助手，帮咨询师在首次咨询前了解来访者基本情况。"
    "请用温和、共情、非评判的中文对话。每次只问1个问题，避免诊断性或"
    "权威性语气。关键注意：\n"
    "- 需要完成一次简短的安全评估（是否有自伤/自杀相关想法）。"
    "提问时用具体、开放、非羞辱的表达，例如『过去两周有没有出现过"
    "活着没意思或不想再活下去的想法？』。根据回答定位到 none / "
    "passive_ideation / active_ideation / plan_or_intent 其中之一。\n"
    "- 不要做诊断，不要给治疗建议，不要承诺保密边界之外的内容。\n"
    "- 必答项：主要困扰、安全评估。其它项来访者可选择不答。"
)


class FormTherapyIntakeExtractor:
    """FieldExtractor for the therapy intake form."""

    def fields(self) -> list[FieldSpec]:
        return FORM_THERAPY_INTAKE_FIELDS

    async def prompt_partial(
        self,
        session_state: SessionState,
        completeness_state: CompletenessState,
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        collected = session_state.collected
        missing = [
            s.label or s.name
            for s in FORM_THERAPY_INTAKE_FIELDS
            if not collected.get(s.name)
        ]
        user_lines = [
            f"已收集：{collected}",
            f"还未回答：{', '.join(missing) if missing else '无'}",
        ]
        return [
            {"role": "system", "content": _SYSTEM_PREAMBLE},
            {"role": "user", "content": "\n".join(user_lines)},
        ]

    def extract_metadata(self, extracted: dict[str, str]) -> dict[str, str]:
        return {}

    def post_process_reply(
        self, reply: str, collected: dict[str, str], mode: Mode,
    ) -> str:
        return reply

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        names = {f.name for f in self.fields()}
        for name, value in extracted.items():
            if name not in names:
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
        if required_missing:
            next_focus = required_missing[0]
        elif recommended_missing:
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

- [ ] **Step 3: Run, expect all tests pass**

- [ ] **Step 4: Commit**

```
git commit -m "feat(intake): add FormTherapyIntakeExtractor + 6 field specs"
```

---

## Task 5: `FormTherapyIntakeTemplate` + registry

**Files:**
- Modify: `src/domain/intake/templates/form_therapy_intake.py` (append template binding)
- Modify: `src/domain/intake/templates/__init__.py` (register `form_therapy_intake_v1`)
- Create: `tests/core/test_form_therapy_intake_template.py`

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations

from domain.intake.hooks.therapy import CrisisAlertHook
from domain.intake.templates import TEMPLATES, get_template
from domain.intake.templates.form_therapy_intake import (
    FormTherapyIntakeExtractor, FormTherapyIntakeTemplate,
)
from domain.intake.writers import FormResponseWriter


def test_form_therapy_intake_v1_registered():
    t = get_template("form_therapy_intake_v1")
    assert isinstance(t, FormTherapyIntakeTemplate)


def test_kind_is_form():
    t = get_template("form_therapy_intake_v1")
    assert t.kind == "form"


def test_requires_doctor_review_is_true():
    """Therapy intake IS reviewed by the therapist before the first session
    — differs from the satisfaction form."""
    t = get_template("form_therapy_intake_v1")
    assert t.requires_doctor_review is True


def test_patient_only_modes():
    t = get_template("form_therapy_intake_v1")
    assert t.supported_modes == ("patient",)


def test_uses_form_response_writer():
    t = get_template("form_therapy_intake_v1")
    assert isinstance(t.writer, FormResponseWriter)


def test_crisis_alert_hook_in_patient_chain():
    t = get_template("form_therapy_intake_v1")
    assert any(
        isinstance(h, CrisisAlertHook)
        for h in t.post_confirm_hooks["patient"]
    )


def test_registry_has_four_templates():
    assert set(TEMPLATES.keys()) == {
        "medical_general_v1",
        "medical_neuro_v1",
        "form_satisfaction_v1",
        "form_therapy_intake_v1",
    }
```

- [ ] **Step 2: Append template binding**

```python
from dataclasses import dataclass, field

from domain.intake.hooks.therapy import CrisisAlertHook
from domain.intake.protocols import (
    BatchExtractor, EngineConfig, FieldExtractor, PostConfirmHook, Writer,
)
from domain.intake.writers import FormResponseWriter


@dataclass
class FormTherapyIntakeTemplate:
    """form_therapy_intake_v1 — client-facing psychotherapy intake.

    Differences from form_satisfaction_v1:
    - requires_doctor_review=True (therapist reviews before first session)
    - CrisisAlertHook fires on elevated suicidality risk
    - max_turns slightly higher (intake is more exploratory than a survey)
    """
    id: str = "form_therapy_intake_v1"
    kind: str = "form"
    display_name: str = "心理咨询首次登记"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient",)
    extractor: FieldExtractor = field(default_factory=FormTherapyIntakeExtractor)
    batch_extractor: BatchExtractor | None = None
    writer: Writer = field(default_factory=FormResponseWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {"patient": [CrisisAlertHook()]},
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=15,
        phases={"patient": ["default"]},
    ))
```

- [ ] **Step 3: Register in `TEMPLATES`**

```python
TEMPLATES: dict[str, Template] = {
    "medical_general_v1": GeneralMedicalTemplate(),
    "medical_neuro_v1": GeneralNeuroTemplate(),
    "form_satisfaction_v1": FormSatisfactionTemplate(),
    "form_therapy_intake_v1": FormTherapyIntakeTemplate(),
}
```

- [ ] **Step 4: Run, expect all tests pass + update `test_template_registry.py` (4 templates)**

- [ ] **Step 5: Commit**

```
git commit -m "feat(intake): register form_therapy_intake_v1 with CrisisAlertHook"
```

---

## Task 6: Regression sweep + parametrized template gate

**Files:**
- Modify: any existing `parametrize_templates`-based test (spec §7b/§7f) to include both new template ids.
- Create (if not yet present from Phase 3): `tests/core/test_templates_parametrized.py` covering §7f semantic tests (append, carry-forward, required-tier completeness, contract synthesis) across all 4 registered templates.

- [ ] **Step 1: Full suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent --tb=short 2>&1 | tail -20
```

Target: **Phase-3-baseline + ~30** new tests passing. No existing test regressed.

- [ ] **Step 2: reply_sim tier-2 pass rate**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python \
    scripts/run_reply_sim.py --tier 2 --template medical_general_v1
```

Compare pass rate against the post-Phase-3 baseline captured in `docs/eval/`. Delta must be within ±2%.

- [ ] **Step 3: Sim scenarios per new template (spec §7e gate)**

≥3 sim scenarios each — happy path, mid-abandonment, edge case:

- `sim/scenarios/neuro_happy_path.yaml` — stroke-onset conversation ends with `onset_time` + `chief_complaint` populated and diagnosis pipeline triggered.
- `sim/scenarios/neuro_abandoned_mid_intake.yaml` — patient drops off after 2 turns; session stays `active`, no hooks fire.
- `sim/scenarios/neuro_no_onset_time.yaml` — edge: patient can't recall onset; must still be completable with explicit "不清楚".
- `sim/scenarios/therapy_intake_no_risk.yaml` — happy path, `crisis_risk=none`, no alert hook call.
- `sim/scenarios/therapy_intake_active_ideation.yaml` — active ideation mentioned mid-conversation; confirm fires `CrisisAlertHook` with exact message prefix `【危机预警】`.
- `sim/scenarios/therapy_intake_declines_required.yaml` — edge: client declines to answer `presenting_issue`; completeness stays `False`.

- [ ] **Step 4: Commit scenario files**

```
git commit -m "test(sim): neuro + therapy-intake scenario coverage (§7e gate)"
```

- [ ] **Step 5: Final commit sanity**

```
git log <phase3-head>..HEAD --oneline
```

Expected: ~6 Phase 4 commits.

Phase 4 complete. §8 resolved via option (c): `medical_neuro_v1` fires diagnosis on both modes, `medical_general_v1` preserved as-is.

---

## Out of scope (deferred)

- Frontend UI to select `medical_neuro_v1` at session create. Today it's accessible only via explicit API param; specialty-to-template mapping for auto-selection is a product decision.
- Frontend to view therapy intake responses (extend the existing form-response view added in Phase 3).
- `form_therapy_session_v1` (ongoing session notes). Design paragraph in spec §8 if we greenlight.
- Retirement-window janitor (spec §8 bullet 2). Phase 2 committed to it; still not shipped.
- Expanding CrisisAlertHook to include patient contact info, therapist paging via SMS/phone (not just in-app). Start with the in-app channel.
- DSM-lite field for psychiatric variant (`medical_psychiatry_v1`) — distinct from therapy-counseling path, deferred pending product decision.

## Risk notes

- **Crisis alert false negatives.** LLM may extract `crisis_risk=none` when the client was actually ambivalent. The required-tier screening + system prompt briefing is the primary mitigation; the sim scenario `therapy_intake_active_ideation.yaml` is the integration gate. If we see false negatives in reply_sim, escalate to explicit two-pass extraction (per-turn + batch-extract of full transcript filtered for risk keywords).
- **Neuro hook symmetry may surprise doctors.** Doctors using `medical_general_v1` don't expect diagnosis to fire on their own dictation; `medical_neuro_v1` does. Without UI to distinguish the two, a neuro doctor who doesn't realize they were auto-routed to `medical_neuro_v1` could be confused. Mitigation: display `display_name` prominently on the intake header ("神外问诊（脑血管）") so the template choice is visible.
- **Reuse of MedicalRecordWriter with `project_extras`.** The neuro writer mutates the dict by folding three fields into existing columns. This works as long as the engine treats `collected` as an opaque dict post-confirm; if any downstream code reads `collected["onset_time"]` after persist, it will find it gone. Today no such reader exists — `collected` is serialized into `session.collected` JSON before persist, and the medical record rows only expose the projected columns. Verified by grepping for `collected.get("onset_time")` in the whole codebase as part of Task 1 Step 1.
