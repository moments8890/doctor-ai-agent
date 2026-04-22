# Interview Pipeline Extensibility — Design

**Date:** 2026-04-22
**Status:** Draft
**Scope decision:** A1 + B1 (platform-curated templates, patient-only respondents)
**Architectural direction:** Approach 3 (polymorphic pipeline with `Template` / `FieldExtractor` / `OutputWriter` protocols)

---

## 1. Goals and non-goals

### Goals

- Let the same conversational engine drive multiple interview variants: specialty-specific medical intakes (神外 / 骨科 / 心内科 / 眼科) and curated non-medical forms (术前筛查, 满意度调查).
- Isolate domain-specific concerns (field schema, prompts, persistence) from engine-level concerns (turn mechanics, phase transitions, anti-repetition rules).
- Migrate the current medical interview into the new shape with zero user-visible behavior change and no regression in existing tests or sim scenarios.
- Leave clean seams so future work (doctor-authored templates, non-medical tenants, new output sinks) can land without re-architecting.

### Non-goals (for this spec)

- Doctor-authored templates (A3). Authoring surface area and tenant model are explicitly out.
- Anonymous respondents (B2). Every form session still ties to an existing `patients.id`.
- New LLM capabilities or prompt improvements. The refactor preserves today's prompt behavior; optimization is a separate effort.
- Multi-tenant SaaS (C). One deployment, one set of curated templates.

---

## 2. Current state, summarized

- `src/domain/patients/interview_models.py` hardcodes `ExtractedClinicalFields` (17 medical fields) plus module-level `FIELD_LABELS`, `FIELD_META`, `_FIELD_PRIORITY` dicts.
- `src/agent/prompts/intent/patient-interview.md` mixes engine mechanics (2-phase flow, anti-repetition, turn budget, suggestions chips) with medical-specific content and terminology rules in one 109-line prompt. A parallel `interview.md` covers doctor-dictation mode.
- `src/db/models/interview_session.py` (`InterviewSessionDB`) stores `collected` and `conversation` as JSON text blobs — already schema-agnostic at the row level. Medical coupling lives upstream (Pydantic) and downstream (the confirm handler writes to `patient_records` and fires the diagnosis pipeline).
- `src/channels/web/doctor_interview/confirm.py` orchestrates the post-interview side effects: record creation, diagnosis pipeline, follow-up task creation.

**Rigidity points that matter for this work:**

| Layer | Rigidity | Fix |
|---|---|---|
| Pydantic schema | 17 medical fields hardcoded | Template owns its extractor; extractor builds Pydantic dynamically |
| Prompt | Medical phases + rules + content fused | Split into engine-level `shared_rules()` + template `build_prompt()` |
| Confirm handler | Writes medical records directly | Route through `OutputWriter` per template |
| Output storage | Everything goes to `patient_records` / `ai_suggestions` | Forms get a new `form_responses` table |

---

## 3. Core abstractions

All new code lives under `src/domain/interview/`.

```python
# domain/interview/protocols.py

class EngineConfig(BaseModel):
    max_turns: int = 30
    phases: list[Phase]  # ordered; engine advances when current phase's requirements met

class Phase(BaseModel):
    name: str
    required_fields: list[str]               # phase is complete when all these are filled
    advance_on_stuck_rounds: int = 2         # engine force-advances to next phase after N consecutive turns without any required field gaining new info

class Template(Protocol):
    """Registry entry tying schema, prompt, and persistence together."""
    id: str                                   # e.g. "medical_general_v1"
    version: int                              # informational; version lives in id suffix
    kind: Literal["medical", "form"]
    display_name: str
    requires_doctor_review: bool              # medical=True by default, forms may opt out
    extractor: FieldExtractor
    writer: OutputWriter
    config: EngineConfig

class FieldExtractor(Protocol):
    """Schema + prompt for a template. Stateless; receives session state as args."""
    def pydantic_model(self) -> type[BaseModel]: ...
    def build_prompt(self, collected: dict, history: list, phase: Phase, mode: str) -> str: ...
    def merge(self, collected: dict, extracted: BaseModel) -> dict: ...
    def missing_required(self, collected: dict, phase: Phase) -> list[str]: ...
    def is_complete(self, collected: dict) -> bool: ...
    def field_labels(self) -> dict[str, str]: ...
    def field_meta(self) -> dict[str, dict]: ...

class OutputWriter(Protocol):
    """Full-scope persistence and side effects at confirm time. Per-template."""
    async def finalize(self, session: InterviewSession, collected: dict) -> FinalRef: ...

class InterviewEngine:
    """Template-agnostic state machine. Single instance serves every template."""
    def __init__(self, llm: LLMClient): ...
    def shared_rules(self) -> str: ...
    def current_phase(self, session: InterviewSession, template: Template) -> Phase: ...
    async def next_turn(self, session: InterviewSession, user_input: str) -> TurnResult: ...
    async def confirm(self, session: InterviewSession, doctor_edits: dict) -> FinalRef: ...
```

**Responsibility split:**

| Concern | Owner |
|---|---|
| Turn budget, phase advancement logic, conversation append | `InterviewEngine` |
| Anti-repetition and "respond-then-ask" rules | `InterviewEngine.shared_rules()` |
| Which fields this template collects, their hints/examples, tier | `FieldExtractor` |
| Mode-specific prompt partials (patient lay language vs doctor clinical shorthand) | `FieldExtractor.build_prompt(..., mode)` |
| Merging LLM-extracted deltas into running `collected` | `FieldExtractor.merge` |
| What happens at confirm: DB writes, diagnosis pipeline, follow-ups | `OutputWriter.finalize` |

**Prompt split in practice:**

- `InterviewEngine.shared_rules()` returns ~10 lines covering turn mechanics, phase-transition constraints, suggestions chip count — truly template-agnostic.
- `FieldExtractor.build_prompt(collected, history, phase, mode)` returns the domain content: vocabulary rules (medical terms → lay language for `mode=patient`), the active phase's required fields with hints/examples, already-collected snapshot, and any template-specific rules (e.g., "chief_complaint = reason for visit + duration only").
- For medical templates: two partial files per template, `medical_general/patient_partial.md` and `medical_general/doctor_partial.md`. `build_prompt(mode="patient")` picks the patient partial. Schema is identical across modes; only tone/vocabulary differ.

---

## 4. Data model changes

### 4a. `interview_sessions` additions

```sql
ALTER TABLE interview_sessions ADD COLUMN template_id VARCHAR(64);
-- backfill:
UPDATE interview_sessions SET template_id = 'medical_general_v1';
-- then:
ALTER TABLE interview_sessions MODIFY COLUMN template_id VARCHAR(64) NOT NULL;
```

Existing columns (`collected`, `conversation`, `mode`, `turn_count`, `status`) stay unchanged. The `collected` JSON shape already matches `medical_general_v1`'s schema — no JSON reshape needed.

### 4b. New table: `form_responses`

```sql
CREATE TABLE form_responses (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  doctor_id     VARCHAR(64) NOT NULL,
  patient_id    BIGINT NOT NULL,
  template_id   VARCHAR(64) NOT NULL,
  session_id    VARCHAR(36) NULL,
  payload       JSON NOT NULL,
  status        ENUM('draft','confirmed','deleted') NOT NULL DEFAULT 'draft',
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE,
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE SET NULL,
  INDEX ix_form_response_doctor_patient (doctor_id, patient_id, template_id),
  INDEX ix_form_response_patient_template (patient_id, template_id, created_at)
);
```

Medical-kind templates keep writing to `patient_records` and `ai_suggestions` as today. Only form-kind templates write to `form_responses`.

### 4c. `doctors.preferred_template_id`

```sql
ALTER TABLE doctors ADD COLUMN preferred_template_id VARCHAR(64) NULL;
```

Optional. Set during onboarding based on the specialty dropdown via a config map:

```python
SPECIALTY_TO_TEMPLATE = {
    "neurosurgery": "medical_neuro_v1",
    "cardiology":   "medical_cardio_v1",
    # fallback handled by caller
}
```

### 4d. Template registry

Static Python, no DB rows:

```python
# domain/interview/templates/__init__.py

TEMPLATES: dict[str, Template] = {
    "medical_general_v1":   GeneralMedicalTemplate(),
    # added later:
    # "medical_neuro_v1":     NeuroTemplate(),
    # "form_satisfaction_v1": SatisfactionTemplate(),
}

def get_template(template_id: str) -> Template:
    if template_id not in TEMPLATES:
        raise UnknownTemplate(template_id)
    return TEMPLATES[template_id]
```

**Versioning:** version lives in the id suffix. A new version is a new registry entry; old versions stay until no session references them. Retirement policy: observe zero sessions for 90 days → safe to remove from registry.

### 4e. Template selection at session creation

Precedence:

1. Explicit `template_id` param on `POST /api/interview/sessions` (used by doctor-initiated UI flows that want a specific form).
2. `doctors.preferred_template_id` if set.
3. Global fallback: `medical_general_v1`.

### 4f. Read-back endpoints

- `GET /api/patients/{patient_id}/form_responses?template_id=...` — list
- `GET /api/form_responses/{id}` — detail
- Medical-kind records use existing patient-records endpoints.

---

## 5. Runtime flow

### 5a. Session lifecycle

```
create ──▶ interviewing ──▶ reviewing ──▶ confirmed
 (API)    (turn loop)     (doctor gate,   (writer.finalize
                           optional)       side effects complete)
```

`reviewing` is skipped when `template.requires_doctor_review == False`.

### 5b. Turn loop

```python
async def next_turn(session, user_input):
    template = get_template(session.template_id)
    phase = engine.current_phase(session, template)

    prompt = compose(
        engine.shared_rules(),
        template.extractor.build_prompt(
            collected=session.collected,
            history=session.conversation,
            phase=phase,
            mode=session.mode,  # "patient" or "doctor"
        ),
    )
    llm_out = await llm.chat(
        system=prompt,
        messages=session.conversation + [user(user_input)],
        response_schema=template.extractor.pydantic_model(),
    )

    session.collected = template.extractor.merge(session.collected, llm_out.extracted)
    session.conversation += [user(user_input), ai(llm_out.reply, llm_out.suggestions)]
    session.turn_count += 1

    if template.extractor.is_complete(session.collected) or session.turn_count >= template.config.max_turns:
        session.status = "confirmed" if not template.requires_doctor_review else "reviewing"

    await save(session)
    return TurnResult(
        reply=llm_out.reply,
        suggestions=llm_out.suggestions,
        done=session.status != "interviewing",
    )
```

### 5c. Confirm / finalize

```python
async def confirm(session, doctor_edits):
    template = get_template(session.template_id)
    final_collected = template.extractor.merge(session.collected, doctor_edits)
    ref = await template.writer.finalize(session, final_collected)
    session.status = "confirmed"
    await save(session)
    return ref
```

**`MedicalRecordWriter.finalize` is full-scope:**

- Insert into `patient_records`
- Fire diagnosis pipeline (async, returns after enqueue)
- Create follow-up tasks per the diagnosis output
- Any other side effects currently living in `doctor_interview/confirm.py`

**`FormResponseWriter.finalize`:**

- Insert into `form_responses` with `status="confirmed"`
- Return the new row id
- No diagnosis, no follow-up tasks

Writers are isolated — `MedicalRecordWriter` knows nothing about `form_responses` and vice versa.

### 5d. Failure modes

| Failure | Behavior |
|---|---|
| LLM returns malformed extracted | Keep previous `collected`, append `reply` only, log warning. Same as today. |
| Template id not in registry | Session becomes read-only; user-facing error suggests contacting support. 90-day retirement window prevents this in normal ops. |
| `requires_doctor_review=False` + writer fails at finalize | Session stays `interviewing` with `finalize_error` metadata; admin retry endpoint. |
| Diagnosis pipeline fails post-finalize (medical) | Same as today — patient record is already written, pipeline retry separately. |

---

## 6. Migration path

**Principle:** behavior-preserving refactor. After every phase, all existing medical tests and sim scenarios pass unchanged. No user-visible change until Phase 3 ships the first non-medical template.

### 6a. Phases

| Phase | Ships | Risk | Est. |
|---|---|---|---|
| **0. Skeleton** | Alembic: `template_id`, `preferred_template_id`, `form_responses`. Empty `domain/interview/` package. No code path uses it. | Zero — additive DB only. | 0.5–1d |
| **1. Engine extraction** | Move state machine from `interview_turn.py` into `InterviewEngine`. Extract `shared_rules()` from `patient-interview.md`. Still hardwired to medical schema. | Low — internal rename. | 2–3d |
| **2. Medical template extraction** | `GeneralMedicalExtractor` + `MedicalRecordWriter` + `medical_general/{patient,doctor}_partial.md`. Engine calls into template via protocols. `TEMPLATES["medical_general_v1"]` registered. | Medium — seam goes live. Sim tests backstop. | 2–3d |
| **3. First form template** | `form_satisfaction_v1` end-to-end: extractor, prompt, `FormResponseWriter`, list/detail API, minimal doctor-side UI to view responses. | Low — isolated from medical. | 3–5d |
| **4. Specialty variants** | `medical_neuro_v1`, `medical_ortho_v1`, each subclasses `GeneralMedicalExtractor` overriding fields/prompt deltas. | Per-template. | 0.5–1d each |

Phases 0–2 are the refactor. Phase 3 is the proof. Phase 4 is the payoff.

### 6b. Backwards-compat shim

Direct references to `ExtractedClinicalFields` / `FIELD_LABELS` / `FIELD_META` exist in: diagnosis pipeline, record handlers, various serializers. During Phase 2:

```python
# src/domain/patients/interview_models.py (shim, deleted after one release cycle)
import warnings
from domain.interview.templates.medical_general import GeneralMedicalExtractor

warnings.warn(
    "interview_models symbols are re-exported from medical_general template; "
    "import from domain.interview.templates.medical_general directly.",
    DeprecationWarning,
    stacklevel=2,
)

_ext = GeneralMedicalExtractor()
ExtractedClinicalFields = _ext.pydantic_model()
FIELD_LABELS = _ext.field_labels()
FIELD_META = _ext.field_meta()
```

Callers migrate at their own pace. Shim deletion tracked as a separate cleanup task.

### 6c. What stays untouched

- Patient-side UX (InterviewPage, ChatTab) — interview API shape unchanged for medical sessions.
- Doctor-side interview review UI — unchanged for medical-kind; Phase 3 adds a lightweight view for form-kind responses.
- `reply_sim` / `run_reply_sim` scripts — keep running against `medical_general_v1`.
- WeCom / WeChat mini-app handlers — none interact with interview internals.

---

## 7. Testing strategy

### 7a. Behavior-preservation proof (Phase 2)

- Snapshot test: the composed prompt from `engine.shared_rules() + GeneralMedicalExtractor.build_prompt(mode="patient", ...)` is byte-identical (modulo formatting) to the pre-refactor `patient-interview.md`. Same for `mode="doctor"` vs `interview.md`.
- The full medical `reply_sim` suite passes unchanged.
- `parametrize_sessions` test: replay a canned set of real medical interview transcripts through the refactored engine, assert identical final `collected` and identical `ai_reply` sequence.

### 7b. Template-level tests

`parametrize_templates` fixture runs a synthetic 5-turn scripted conversation against every registered template and asserts:

- No crashes
- `collected` non-empty after turn 1
- `reply` within reasonable length bounds
- `suggestions` list length in [2, 4]
- Correct writer dispatch at `confirm` (mock the writer, assert `.finalize` called with right args)

### 7c. New-template gate

Before a new template lands in `TEMPLATES`:

- At least 3 sim scenarios: happy path, mid-abandonment, edge case (e.g., user answers out of order)
- Writer integration test: round-trip through `finalize`, read back via API, assert payload shape
- Prompt snapshot committed for review

---

## 8. Open risks and decisions already deferred

- **Template retirement window** — 90 days of zero sessions as the trigger for deletion. If a session is abandoned mid-flow and never resumed, it sits forever. Need a janitor job to mark long-abandoned sessions, or accept long retention.
- **Phase config expressivity** — current `Phase` model handles linear multi-phase flows. Doesn't handle branching (e.g., "if patient is pregnant, collect pregnancy history"). If a future template needs branching, we extend `Phase` to support conditions; not needed for any A1 template on the horizon.
- **Prompt duplication across specialty variants** — `medical_neuro_v1` and `medical_ortho_v1` will share 80% of their prompt with `medical_general_v1`. Once 2+ specialty variants exist, consider a prompt-fragment library (`_medical_common.md`) that each variant prepends. Defer until we feel the pain.
- **Form-kind UI surface** — this spec assumes a minimal doctor-side "view form responses" list. Real product placement (patient detail timeline? separate tab? cards on MyAI?) is a product decision out of scope here.
- **Session resume mid-turn across template versions** — if a session is in-flight when we publish `medical_neuro_v2`, it keeps running on v1 (registry still has it). Spec commits to keeping old versions around for 90 days.

---

## 9. Summary of decisions made during brainstorming

| Decision | Value |
|---|---|
| Scope | A1 + B1: platform-curated templates, patient-only respondents |
| Approach | 3 — polymorphic pipeline with protocol-based seams |
| Template storage | Static Python registry, version suffixed in id |
| Template ID format | `<kind>_<slug>_v<n>` |
| Prompt split | Engine-level `shared_rules()` + template `build_prompt(mode)` |
| Phases | Config-driven on template; `EngineConfig.phases: list[Phase]` |
| Per-template review gate | `requires_doctor_review: bool`; medical default True |
| Patient vs doctor prompts | One template + `mode` param → different partials |
| Writer scope | Full — owns patient_records + diagnosis pipeline + follow-up tasks |
| Form respondent | Always an existing `patients.id` (B1) |
| Form storage | New `form_responses` table, one payload JSON per row |
| Existing sessions | Backfilled to `medical_general_v1` via Alembic |
| Compat shim | `interview_models` re-exports from medical_general for one release |
