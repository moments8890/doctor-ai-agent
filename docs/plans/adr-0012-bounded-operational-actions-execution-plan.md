# Goal

Implement the proposed ADR 0012 direction with the smallest rollout that adds
safe operational actions to the ADR 0011 runtime:

- `query_records`
- `list_patients`
- `schedule_task` (`schedule_appointment` as routing alias)
- `update_patient`

# Status

`Not Started`

# Why this plan exists

The codebase already has usable patient, record, and task repositories, but
the current runtime only knows how to bind a patient and create/confirm a draft.

That leaves three bad options:

- keep these features outside the runtime in router-specific handlers
- bloat the current flat `ActionRequest` until it becomes unmaintainable
- reintroduce the older many-intent workflow stack ADR 0011 just replaced

This plan keeps the ADR 0011 architecture intact while adding only the
operational surface the product needs next.

# Scope

- doctor chat/runtime support for:
  - patient list
  - patient record lookup
  - task scheduling with appointment support
  - bounded patient demographic updates
- runtime action/result contract changes needed to support those capabilities
- deterministic exact-shape pre-routing for safe operational commands
- audit coverage for runtime-driven reads and writes
- task schema correction for appointment time vs reminder time

# Out of scope

- general agent tool calling
- delete / merge patient flows
- task completion, cancellation, or postpone through the new runtime path
- export/report actions in the same ADR
- semantic cohort queries like "查最近胸痛患者"
- unit-test expansion by default during the current MVP iteration

# Success criteria

1. A doctor can list patients from chat without using legacy router-only logic.
2. A doctor can query the latest records for the current or explicitly named
   patient from chat.
3. A doctor can schedule an appointment/task from chat without conflating
   appointment time and reminder time.
4. A doctor can update bounded patient demographics from chat without weak
   patient inference.
5. All runtime-driven operational reads/writes emit audit events.
6. The action/result contract remains typed and bounded; no generic JSON-RPC
   tool surface is introduced.

# Affected files

Likely runtime contract and execution:

- `src/services/runtime/models.py`
- `src/services/runtime/turn.py`
- `src/services/runtime/conversation.py`
- `src/services/runtime/draft_guard.py`
- `src/services/runtime/commit_engine.py`
- new read/action execution helper(s) under `src/services/runtime/`

Likely persistence layer:

- `src/db/models/tasks.py`
- `src/db/crud/tasks.py`
- `src/db/repositories/tasks.py`
- `src/db/crud/patient.py`
- `src/db/repositories/patients.py`
- `src/db/crud/records.py`
- `src/db/repositories/records.py`

Likely channel/API surfaces:

- `src/channels/web/chat.py`
- optional task/patient formatting helpers used by web/wechat

Docs:

- `docs/adr/0012-bounded-operational-actions-for-runtime.md`
- `docs/adr/README.md`
- `ARCHITECTURE.md` only after implementation lands

# Execution phases

## Phase 1. Harden the runtime contract

Purpose:

- make the runtime capable of expressing operational actions without turning
  `ActionRequest` into an untyped bag of fields

Implementation steps:

1. Replace the flat action payload with typed `args` per action type.
2. Add optional `view_payload` to `TurnResult`.
3. Keep existing draft fields in `TurnResult` for backward compatibility.
4. Decide the minimal payload shapes for:
   - `records_list`
   - `patients_list`
   - `task_created`
   - `patient_updated`

Exit criteria:

- runtime models can represent all four new features without free-form field
  overloading

## Phase 2. Add a read engine and audit coverage

Purpose:

- keep read-side operations out of the write-oriented commit engine and make
  chat reads auditable

Implementation steps:

1. Add deterministic read execution helpers for:
   - `query_records`
   - `list_patients`
2. Emit audit events for read actions from the runtime path.
3. Keep `list_patients` phase 1 bounded to first-page results only.
4. Keep `query_records` phase 1 bounded to explicit/current patient latest-N
   retrieval.

Exit criteria:

- chat-driven patient/record reads no longer depend on legacy router-only code
- runtime read actions are audited

## Phase 3. Correct task temporal semantics

Purpose:

- make appointment scheduling safe before exposing it in chat

Implementation steps:

1. Add a separate event timestamp for appointment-like tasks.
2. Keep reminder/deadline time distinct from event time.
3. Update task repository/CRUD helpers to read/write the new fields.
4. Preserve current scheduler behavior for non-appointment task types.

Exit criteria:

- an appointment can store both the real appointment time and the reminder time

## Phase 4. Implement `schedule_task`

Purpose:

- unify appointment and simple reminder creation under one bounded action path

Implementation steps:

1. Add `schedule_task` to the runtime write path.
2. Support phase-1 task types:
   - `appointment`
   - `follow_up`
   - `general`
3. Normalize relative dates deterministically using current date and timezone.
4. Clarify when a required time or patient target is missing.

Exit criteria:

- doctor chat can create appointment/general tasks without unsafe date parsing

## Phase 5. Implement bounded `update_patient`

Purpose:

- allow small demographic corrections without broad patient-admin scope

Implementation steps:

1. Add `update_patient` to the runtime write path.
2. Restrict the patch allowlist to:
   - `gender`
   - `age`
3. Require explicit patient name or current bound patient.
4. Reject weak-candidate or history-only patient inference for this action.

Exit criteria:

- demographic patching works only on strongly resolved patients

## Phase 6. Add deterministic operational pre-routing

Purpose:

- keep prompt pressure down and improve exact-command reliability on smaller
  models

Implementation steps:

1. Add exact-shape command matching for safe operational phrases.
2. Emit the same typed action contract as the LLM path.
3. Leave ambiguous, mixed, or semantic requests to the conversation model.
4. Keep the rules narrow; do not rebuild the old large intent router.

Exit criteria:

- exact operational commands can bypass the LLM without fragmenting the action
  model

## Phase 7. Channel and UI integration

Purpose:

- let richer surfaces use structured payloads while keeping text-first channels
  unchanged

Implementation steps:

1. Surface `view_payload` through web chat responses.
2. Keep WeChat and voice on the plain-text reply path initially.
3. If needed later, add typed UI actions for pagination or follow-up "more"
   flows rather than asking the LLM to invent cursor tokens.

Exit criteria:

- web can render structured operational results without parsing assistant text

# Risks and watchpoints

- the typed action/result model is the main leverage point; if it stays flat,
  the rollout will get messy fast
- `schedule_task` should not ship before task temporal semantics are corrected
- `update_patient` is the highest wrong-target risk and should be implemented
  after read/query flows are stable
- exact-shape pre-routing must stay narrow or it will recreate the old
  maintenance burden ADR 0011 intentionally removed
- chat result payloads should stay optional so WeChat/voice do not become
  coupled to web UI needs

# Recommended order

1. Phase 1: runtime contract
2. Phase 2: read engine + audit
3. Phase 3: task temporal schema correction
4. Phase 4: `schedule_task`
5. Phase 5: `update_patient`
6. Phase 6: deterministic pre-routing
7. Phase 7: channel/UI payload integration
