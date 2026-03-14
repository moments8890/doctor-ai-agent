# ADR 0012: Bounded Operational Actions for the Thread-Centric Runtime

## Status

Proposed

## Date

2026-03-14

## Implementation Status

Not Started

Last reviewed: 2026-03-14

Notes:

- This ADR extends the ADR 0011 runtime for operational doctor workflows that
  are adjacent to note authoring.
- Scope is intentionally narrow: record lookup, patient listing, task
  scheduling, and bounded patient demographic updates.
- This ADR does not introduce a general tool-calling agent, arbitrary DB
  access, or multi-step planning inside one turn.

## Context

ADR 0011 deliberately narrowed the runtime to patient selection, patient
creation, and draft-first record creation. That reduced workflow complexity,
but it also left a product gap: the current doctor chat surface still needs
safe support for common operational actions that are already present elsewhere
in the codebase or in older workflow docs:

- `query_records`
- `list_patients`
- `schedule_appointment` / task scheduling
- `update_patient`

Several problems already exist around these capabilities:

- repositories and CRUD helpers exist for patients, records, and tasks, but
  the ADR 0011 `ActionRequest` contract cannot express these actions
- the current flat `ActionRequest` shape does not scale to filters, task
  fields, or bounded patch semantics
- patient list/read paths outside the runtime have known pagination and audit
  gaps
- `update_patient` is safety-sensitive because stale or weak patient context
  must not be allowed to mutate the wrong patient
- current appointment/task handling overloads `due_at` semantics; an
  appointment time and a reminder fire time are not the same thing
- relative time phrases such as "明天下午2点" require deterministic date
  normalization, not blind model output

The product need is real, but broadening the runtime cannot reintroduce the
older "many intents, many ad hoc handlers, many state models" architecture.

## Decision

Extend the ADR 0011 runtime with a **bounded operational action layer** that
keeps one entry point and one authoritative doctor context, while adding a
small set of typed read/write actions beyond draft creation.

### 1. Keep one entry point and one active patient context

All channels continue to call one runtime entry point.

The runtime continues to enforce:

- one mutable doctor context row
- one active patient binding at a time
- deterministic execution for all durable writes
- draft-first record creation as the only note-writing path

This ADR does not reopen multi-patient active context, multi-turn task plans,
or generic agent tool loops.

### 2. Add a bounded action family

The runtime action surface expands to include:

- `query_records`
- `list_patients`
- `schedule_task`
- `update_patient`

Doctor language such as "预约", "复诊提醒", or "建个任务" may map to
`schedule_task`, but the runtime contract stays canonical and small.
`schedule_appointment` becomes a routing alias, not a separate execution model.

Existing action types remain:

- `none`
- `clarify`
- `select_patient`
- `create_patient`
- `create_draft`
- `create_patient_and_draft`

### 3. Replace the flat action payload with typed action args

The current flat `ActionRequest(type, patient_name, patient_gender, patient_age)`
is sufficient for ADR 0011 but not for operational actions.

The runtime should move to a typed action contract:

- `type`
- `args` object validated against the action type

Examples of bounded args:

- `query_records`
  - `patient_name` optional
  - `limit` optional, bounded, default 5
- `list_patients`
  - no free-form filters in phase 1
  - fixed first-page limit, default 20
- `schedule_task`
  - `task_type` enum
  - `patient_name` optional
  - `title` optional
  - `notes` optional
  - `scheduled_for` optional depending on task type
  - `remind_at` optional
- `update_patient`
  - `patient_name` optional
  - `patch` object with allowlisted fields only

This is still a typed contract, not generic JSON RPC.

### 4. Separate read execution from write commits

The runtime now has two deterministic execution paths after routing:

- **read engine**
  - executes `query_records`, `list_patients`
  - does not write durable clinical artifacts
  - may update active patient binding only when the action explicitly resolves a
    single patient and the switch is allowed
- **commit engine**
  - continues to own durable writes
  - executes `select_patient`, `create_patient`, `create_draft`,
    `create_patient_and_draft`, `schedule_task`, `update_patient`

The commit engine remains the only writer for patient/task mutations created by
chat actions.

### 5. Introduce explicit result payloads for read/list/task actions

`TurnResult` should gain an optional typed `view_payload` field.

Purpose:

- Web can render structured results without parsing assistant prose.
- WeChat and voice can ignore the payload and use the plain-text reply.

Initial payload families:

- `records_list`
- `patients_list`
- `task_created`
- `patient_updated`

The assistant reply remains mandatory for all channels.

### 6. Patient binding rules stay strict

Patient-scoped operational actions must use the same binding discipline as
ADR 0011.

Rules:

- `list_patients` does not change active patient binding
- `query_records`
  - if `patient_name` is explicit and resolves to one patient, it may bind that
    patient as the current patient
  - if no `patient_name` is given, it reads from the current bound patient only
  - if neither is available, the runtime clarifies
- `schedule_task` and `update_patient`
  - require a strong patient target: explicit patient name or current bound
    patient
  - must not use weak memory, stale candidates, or history-only inheritance to
    mutate a patient
- switching to another patient uses the same switch rules as patient selection
  - pending draft for a different patient blocks the switch
  - unsaved working note without a draft is cleared with an explicit warning

### 7. Draft guard becomes read-permissive, write-strict

When a pending draft exists:

- read actions are allowed if they do not require rebinding to another patient
- patient/task writes other than draft confirm/abandon remain blocked
- querying the current patient's prior records is allowed
- querying or mutating a different patient is blocked until the draft is
  confirmed, abandoned, or explicitly discarded through a later extension

This keeps note approval safe without locking the doctor out of readback.

### 8. Scope `query_records` narrowly in phase 1

Phase-1 `query_records` is a bounded read model:

- target current patient or one explicit patient name
- return latest records only, default 5, max 10
- order by newest first
- format a concise summary in text reply
- include structured rows in `view_payload`

Deferred:

- broad semantic cohort queries
- fuzzy patient search
- arbitrary keyword/date reasoning from natural language
- export/report generation from the same action

### 9. Scope `list_patients` narrowly in phase 1

Phase-1 `list_patients` returns the first page only:

- recency-ordered
- DB-level limit, default 20, max 50
- no hidden 200-row ceiling
- concise demographic summary per patient
- optional record count if it can be fetched without post-limit distortion

Cursor pagination is reserved for explicit typed follow-up UI actions, not for
the initial LLM action contract.

### 10. Canonicalize task scheduling under `schedule_task`

Do not introduce separate execution engines for:

- appointments
- follow-up reminders
- generic doctor tasks

Instead, use one bounded `schedule_task` action with `task_type` enum values
such as:

- `appointment`
- `follow_up`
- `general`

Routing language may distinguish "预约" from "提醒", but execution stays on one
task path.

### 11. Stop overloading appointment time and reminder time

`DoctorTask` needs separate temporal semantics:

- the event time itself (`scheduled_for` or `appointment_at`)
- the reminder fire time (`due_at` / `notify_at`)

The runtime must not store only one timestamp and guess which meaning it has.

For `task_type="appointment"`:

- event time is required
- reminder time is optional and defaults deterministically (for example,
  one hour before) when not specified

For non-appointment tasks:

- `due_at` remains the actionable reminder/deadline time

### 12. Date normalization must be deterministic

The model may propose relative-time intent, but code must normalize time with:

- current absolute date
- configured timezone
- validation rules per task type

The runtime must reject or clarify invalid temporal payloads rather than
silently accepting hallucinated ISO strings.

### 13. `update_patient` remains a bounded demographic patch

Phase-1 `update_patient` is intentionally narrow.

Allowed fields:

- `gender`
- `age`

Deferred:

- deleting patients
- merging duplicate patients
- updating portal/auth identifiers
- arbitrary text notes on the patient row
- broad demographic patching without field-specific validation

This aligns with the existing `update_patient_demographics()` helper and
reduces wrong-patient blast radius.

### 14. Add deterministic exact-shape pre-routing for operational commands

To keep the conversation prompt compact and reduce tool confusion on smaller
models, add a narrow pre-router before the LLM for exact operational shapes:

- `患者列表`
- `所有患者`
- `查张三病历`
- `查看李四记录`
- `给张三预约下周三10点`
- `修改张三年龄为50岁`

Rules:

- exact or near-exact command shapes only
- mixed-clause, ambiguous, or semantic cases still go to the conversation model
- deterministic matches emit the same typed action contract as the LLM path

This is a bounded exception to ADR 0011's "one model call per turn" goal and
is justified by accuracy, latency, and prompt-budget constraints.

### 15. Audit all read and write actions

Operational actions handled inside the runtime must emit audit events:

- patient list reads
- record reads
- patient updates
- task creation/scheduling

Chat-driven reads must not be less auditable than web UI reads.

## Consequences

### Positive

- common doctor operations can re-enter the single runtime instead of living in
  router-specific side paths
- task and patient mutations keep deterministic validation and patient-binding
  safety
- web chat can receive structured payloads without inventing a second API
- the action surface remains small enough to keep prompt and parser complexity
  under control
- appointment handling becomes semantically correct instead of overloading one
  timestamp

### Negative

- the runtime contract becomes more complex than ADR 0011's original six-action
  shape
- `TurnResult` and action parsing need a real typed union instead of simple
  flat dataclasses
- a task schema change is required before appointment scheduling is safe
- draft-guard and patient-switch logic gain more branches and must be reviewed
  carefully

### Deferred / not chosen

- no generic tool-calling planner
- no natural-language global patient search in phase 1
- no task completion/cancellation/rescheduling in this ADR
- no broad patient-admin surface beyond bounded demographic patching
- no multi-patient active context or park-and-resume thread model
