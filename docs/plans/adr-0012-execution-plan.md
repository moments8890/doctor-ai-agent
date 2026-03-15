# ADR 0012: Execution Plan

## Goal

Implement the Understand → Execute → Compose pipeline as specified in
[ADR 0012](../adr/0012-understand-execute-compose-pipeline.md).

## Dependency Graph

```text
A1 (types + args) ─── gate ───┬──→ B (understand)
                               ├──→ C (execute, also needs A2, A3)
                               └──→ D (compose, also needs A5)

A2, A3, A4, A5 can run in parallel with each other after A1.
A4 must land before E1 (both edit turn.py).

B, C, D ─── all complete ───→ E1 (orchestrator)
E1 ──→ E3 (channel updates, fix imports)
E3 ──→ E2 (remove legacy — only after imports are fixed)
```

**A1 is the gate.** Everything else depends on the type definitions. After A1
lands, streams A2-A5, B, C, D can fan out in parallel. Stream E is sequential:
E1 → E3 → E2.

---

## Stream A: Data Layer

### A1. Data types (gate — everything depends on this)

Create `src/services/runtime/types.py`:

- `ActionType` enum (7 values: `query_records`, `list_patients`,
  `schedule_task`, `select_patient`, `create_patient`, `create_draft`, `none`)
- `TaskType` enum (3 values: `appointment`, `follow_up`, `general`)
- `ClarificationKind` — Literal or enum for the 7 kind strings (shared by
  resolve and compose)
- Per-action typed args dataclasses:
  - `SelectPatientArgs(patient_name: str)`
  - `CreatePatientArgs(patient_name: str, gender: Optional[str], age: Optional[int])`
  - `CreateDraftArgs()` (empty — content collected from archive)
  - `QueryRecordsArgs(patient_name: Optional[str], limit: Optional[int])`
  - `ListPatientsArgs()` (empty)
  - `ScheduleTaskArgs(task_type: TaskType, patient_name: Optional[str], title: Optional[str], notes: Optional[str], scheduled_for: Optional[str], remind_at: Optional[str])`
- `UnderstandResult` dataclass (`action_type`, `args: <typed union>`,
  `chat_reply`, `clarification`)
- `Clarification` dataclass (`kind: ClarificationKind`, `missing_fields`,
  `options`, `suggested_question`, `message_key`)
- `ResolvedAction` dataclass (`action_type`, `patient_id`, `patient_name`,
  `args`, `scoped_only`)
- `ReadResult` dataclass (`status`, `data`, `total_count`, `truncated`,
  `message_key`, `error_key`)
- `CommitResult` dataclass (`status`, `data`, `pending_id`, `message_key`,
  `error_key`)
- `RESPONSE_MODE_TABLE`: const dict mapping `ActionType` → response mode
- `READ_ACTIONS` / `WRITE_ACTIONS` const sets

### A2. Schema: chat_archive gains patient_id

Add `patient_id: Optional[int]` to the `ChatArchive` model. Set it during
turn archival when a patient is bound. Required for create_draft's
patient-scoped clinical content collection (ADR §8).

- Model: `src/db/models/doctor.py` (ChatArchive class)
- Write: `src/services/runtime/context.py` (`archive_turns` function)
- Downstream: `src/db/crud/doctor.py` (`append_chat_archive`)
- No Alembic; `create_tables()` + manual `ALTER TABLE` for dev
- **Backfill**: existing rows will have NULL patient_id. Add a one-time
  backfill script that infers patient_id from surrounding context (or
  accept that pre-migration archives use unscoped scan as fallback)

### A3. Schema: DoctorTask temporal fields

Add `scheduled_for: Optional[datetime]` and `remind_at: Optional[datetime]`
to `DoctorTask`. Existing `due_at` is retained for backward compatibility
but not used by the new pipeline (ADR §11).

- Model: `src/db/models/tasks.py`
- CRUD: `src/db/crud/tasks.py` (update create/query functions)
- Repository: `src/db/repositories/tasks.py` (`TaskRepository.create` also
  needs the new fields)

### A4. Dead-field MemoryState (must land before E1)

Stop reading `working_note`, `candidate_patient`, `summary` from
`MemoryState`. The `memory_json` column on `DoctorContext` is retained but
not read by the pipeline (ADR §17).

Affected modules:
- `src/services/runtime/commit_engine.py` — `_collect_clinical_text` reads
  `ctx.memory.working_note`; switch to chat_archive scan
- `src/services/runtime/conversation.py` — context block building reads
  memory fields
- `src/services/runtime/turn.py` — memory patch application logic; remove
- `src/services/runtime/context.py` — `load_context` / `_serialize_memory`
  still read/write these fields; stop reading
- `src/services/runtime/draft_guard.py` — `_confirm_draft` clears
  working_note
- `src/services/runtime/commit_engine.py` — `_handle_patient_switch` reads
  working_note to emit `M.unsaved_notes_cleared`; remove this warning (no
  longer applicable without working_note)

### A5. Templates and messages

Add template strings to `src/messages.py` for:

- All 7 clarification kinds (`missing_field`, `ambiguous_intent`,
  `ambiguous_patient`, `not_found`, `invalid_time`, `blocked`, `unsupported`)
- Action success templates (`select_patient`, `create_patient`,
  `schedule_task` with datetime echo-back, `schedule_task` with noon default)
- `create_patient` template must guide the follow-up: "已创建患者张三。
  您可以继续说'写个记录'来创建病历。" (mitigates create_patient_and_draft
  UX regression)
- Error templates (understand failure, compose failure fallback, execute
  error, structuring LLM failure, TTL expiry "草稿已过期，请重新创建")
- Truncation template ("共N条记录，显示最近M条")
- Compose failure fallback for WeChat/voice: include brief data summary
  (e.g., first record date/title), not just count — "找到5条记录" with no
  content is not actionable on non-web channels where `view_payload` is
  ignored
- Greeting/help templates (for deterministic handler fast path)

---

## Stream B: Understand Phase (depends on A1)

### B1. Understand prompt

Create `src/prompts/understand.md`:

- JSON output matching `UnderstandResult` shape with typed args
- `chat_reply` only for `action_type == none`
- Raw names, no resolution
- No hallucinated args
- `clarification` vs `chat_reply` guidance
- Per-action args examples using typed arg shapes from A1
- Must NOT reference `clarify` or `create_patient_and_draft` action types
  (removed in this ADR)

### B2. Fast-router integration (optimization, deferrable)

The existing `services/ai/fast_router/` can handle patterned inputs (e.g.,
"查张三的病历" → `query_records` with `patient_name=张三`) without an LLM
call, reducing 2-LLM-call reads to 1. Wire the fast router as a pre-LLM
check in the understand caller: if the fast router matches with high
confidence, skip the LLM call and return a synthetic `UnderstandResult`.
If no match, fall through to the LLM.

This is a performance optimization, not a correctness requirement. Can be
deferred to after the pipeline is working end-to-end.

### B3. Understand caller

Create `src/services/runtime/understand.py`:

- `async def understand(text, recent_turns, ctx) -> UnderstandResult`
- Build prompt with recent turns (last 10 from chat_archive)
- Inject `current_date` and `timezone` into prompt context (for date
  normalization in schedule_task — see ADR §12)
- Single LLM call (JSON mode)
- Parse response into `UnderstandResult` with typed args
- **Failure signaling**: on parse failure or LLM timeout, raise
  `UnderstandError` (new exception type). The orchestrator (E1) catches
  this and returns a generic error template. This avoids returning a
  fake `UnderstandResult` that violates the no-prose invariant.
- Precedence: if both `clarification` and `chat_reply` set, clarification
  wins
- **Runtime invariant enforcement** (do not trust the prompt):
  - Strip `chat_reply` to null when `action_type != none`
  - Validate `args` against per-action typed dataclass (A1): reject unknown
    keys, enforce required fields, clamp out-of-bounds values (e.g., limit
    max 10). Invalid args → return `clarification.kind="missing_field"` for
    the missing/invalid field.

---

## Stream C: Execute Phase (depends on A1 for types, A2/A3 for schema)

### C1. Resolve module

Create `src/services/runtime/resolve.py`:

- `async def resolve(result: UnderstandResult, ctx: DoctorCtx) -> ResolvedAction | Clarification`
- Patient matching strategy (ADR §10):
  - Exact match first
  - Prefix fallback (2-char minimum, 5-result cap)
  - **All lookups scoped by `ctx.doctor_id`** — cross-tenant leak prevention
- Context fallback when `patient_name` is null
- Read/write binding asymmetry (reads scope, writes switch)
- Pending draft rules:
  - All reads (including cross-patient): allowed
  - `list_patients` (unscoped): always allowed
  - Same-patient `schedule_task`: allowed (independent operation)
  - `create_draft` during pending: blocked
  - Context-switching writes: blocked
- Date validation for `schedule_task` (normalization done by LLM in
  understand phase — see ADR §12):
  - Validate ISO-8601 format
  - Not in the past
  - Reasonable range (not >1 year out)
  - Validation failure → `clarification.kind="invalid_time"`
- TaskType validation: invalid → `clarification.kind="missing_field"`

### C2. Read engine

Create `src/services/runtime/read_engine.py`:

- `async def read(action: ResolvedAction) -> ReadResult`
- `query_records`: fetch from `medical_records` for patient, apply limit,
  return `total_count` + `truncated`
- `list_patients`: fetch doctor's patient panel, recency-ordered, default 20,
  max 50
- Module-level constraint: no imports from `pending_*`, no write helpers
- `"empty"` status when query returns zero rows
- **Audit**: emit audit event for each read operation (ADR §13)

### C3. Commit engine refactor

Refactor `src/services/runtime/commit_engine.py`:

- `async def commit(action: ResolvedAction, ctx: DoctorCtx) -> CommitResult`
- `schedule_task`: create `DoctorTask` row immediately using new
  `scheduled_for` / `remind_at` fields. Return `status: "ok"`.
- `create_draft`: collect clinical content from `chat_archive` (patient-scoped
  scan per A2; fallback to unscoped scan when `patient_id` is NULL for
  pre-migration rows), call structuring LLM, create pending record. Return
  `status: "pending_confirmation"`. On structuring LLM failure, return
  `status: "error"` (no state mutation).
- `select_patient`: update context binding. Return `status: "ok"`.
- `create_patient`: create patient row (reject duplicates), update context.
  Return `status: "ok"`.
- Remove `create_patient_and_draft` handler
- Remove `_collect_clinical_text` dependency on `working_note` (use
  chat_archive scan instead, per A4)
- Error handling: DB errors → `status: "error"` + `error_key`
- **Audit**: emit audit event for each write operation (ADR §13)

---

## Stream D: Compose Phase (depends on A1 for types, A5 for templates)

### D1. Template composer

Create `src/services/runtime/compose.py`:

- `def compose_template(result: ReadResult | CommitResult, action_type) -> str`
- Format template from A5 using result data
- Handle `pending_confirmation` (draft preview)
- Handle `error` (error template via `error_key`)
- Truncation display for reads

### D2. LLM composer

Add to `src/services/runtime/compose.py`:

- `async def compose_llm(result: ReadResult, user_input: str) -> str`
- Compose prompt: user input + fetched data + "summarize naturally"
- For cross-patient reads during pending draft: include context reminder in
  the reply (e.g., "【张三】的病历记录：... 当前待确认病历为【李四】") so the
  doctor knows which patient they are still working on
- Failure fallback: minimal template with brief data summary (not just count)
  + `view_payload`

### D3. Clarification composer

Add to `src/services/runtime/compose.py`:

- `def compose_clarification(c: Clarification) -> str`
- Deterministic kinds → template (ignore `suggested_question`)
- `ambiguous_intent` + `suggested_question` → use it
- Else → template fallback
- Composition rule from ADR §4

---

## Stream E: Orchestrator Integration (depends on B, C, D; A4 must land first)

**E1 → E3 → E2** (sequential, not parallel)

### E1. Refactor process_turn

Refactor `src/services/runtime/turn.py`:

- Deterministic handler:
  - Typed UI actions (button clicks)
  - `pending_draft_id` set + 确认/取消 regex → commit or discard
    (migrate confirm/cancel DB logic from `draft_guard.py`:
    `_confirm_draft`, `_abandon_draft`)
  - **TTL expiry race**: if `pending_draft_id` set but `pending_records`
    row missing → clear stale ID, return "草稿已过期" template
  - Greeting/help regex fast path → template reply (0 LLM calls, preserves
    existing ~0ms response time)
- Pipeline: understand → resolve → dispatch (read_engine | commit_engine) →
  compose
- Catch `UnderstandError` from B3 → return generic error template
- Response mode routing from `RESPONSE_MODE_TABLE`
- `action_type == none` → return `chat_reply` directly
- Clarification from understand → skip execute, compose clarification
- Clarification from resolve → skip engine, compose clarification
- `view_payload` on TurnResult for reads
- Archive turn to chat_archive (with patient_id per A2)
- **Background tasks**: on draft confirm, trigger CVD extraction and other
  background tasks (same as existing `_confirm_draft` behavior)

### E3. Channel updates (before E2 — fix imports first)

- Web `chat.py`: remove greeting/help fast paths (moved to E1 deterministic
  handler)
- WeChat `router.py`: dedup uses synthetic `msg_id` (UUID), not WeChat XML
  `MsgId`. Ensure dedup logic remains in the channel layer.
- Remove `message_id` parameter from `process_turn()` signature
- Update `TurnResult` to include `view_payload`
- Fix any imports from `draft_guard.py` in WeChat router (e.g.,
  `CONFIRM_RE`, `ABANDON_RE` — move to shared constants or messages)

### E2. Remove legacy single-pass path (last step)

- Delete `src/services/runtime/draft_guard.py` (confirm/cancel logic
  migrated to E1 deterministic handler)
- Delete or archive `src/prompts/conversation.md` (replaced by
  `understand.md` from B1; still teaches removed action types `clarify`
  and `create_patient_and_draft`)
- Remove `conversation.py` `call_conversation_model()` (replaced by
  understand)
- Remove `ModelOutput` type (replaced by `UnderstandResult`)
- Remove `ActionRequest` type (replaced by typed args per action)
- Remove `VALID_ACTION_TYPES` frozenset (replaced by `ActionType` enum)
- Remove `_handle_action()` dispatch (replaced by resolve → engine dispatch)
- Remove memory patch application logic

---

## Prerequisite Checklist

Before starting any stream:

- [ ] Read ADR 0012 (all 17 sections + deferred)
- [ ] Read ADR 0012 architecture diagram
- [ ] Read current `src/services/runtime/` modules for existing patterns

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Understand prompt quality (action classification accuracy) | Iterate prompt in B1 with real doctor inputs from chat_archive corpus |
| LLM date normalization accuracy | LLM normalizes Chinese relative dates in understand phase. Resolve validates the ISO output. If accuracy is poor, fall back to `dateparser` library. |
| create_patient_and_draft UX regression | Known; deferred to follow_up_hint ADR. create_patient template guides follow-up (A5). |
| chat_archive scan performance (full history per patient) | Index on (doctor_id, patient_id, created_at); limit scan to last N turns if needed |
| ChatArchive.patient_id NULL for existing rows | First create_draft post-migration falls back to unscoped scan for NULL patient_id rows. One-time backfill script optional. |
| No rollback mechanism — hard cutover | MVP has single doctor; acceptable. For multi-doctor: add `PIPELINE_VERSION=v1|v2` env flag in E1 to route between old and new paths. Keep old modules until v2 is validated. |
| Greeting/help latency regression | Mitigated: greeting/help regex kept as fast path in E1 deterministic handler (0 LLM calls). Not removed in E3. |
| conversation.md prompt teaches removed action types | Deleted in E2 after understand.md (B1) is in place. During E1 transition, understand.py uses understand.md, not conversation.md. |
