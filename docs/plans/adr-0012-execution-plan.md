# ADR 0012: Execution Plan

## Goal

Implement the Understand → Execute → Compose pipeline as specified in
[ADR 0012](../adr/0012-understand-execute-compose-pipeline.md).

## Parallel Work Streams

Five streams, three of which can run in parallel from the start. Streams are
lettered A–E. Dependencies are explicit.

```text
Stream A: Data Layer ──────────────┐
Stream B: Understand Phase ────────┤
Stream C: Execute Phase ───────────┼──→ Stream E: Orchestrator Integration
Stream D: Compose Phase ───────────┤
                                   │
                              all merge
```

A, B, C, D can all start in parallel. E starts when A–D are complete.

---

## Stream A: Data Layer (no dependencies)

Schema changes and type definitions. No LLM, no runtime logic.

### A1. Data types

Create `src/services/runtime/types.py`:

- `ActionType` enum (7 values: `query_records`, `list_patients`,
  `schedule_task`, `select_patient`, `create_patient`, `create_draft`, `none`)
- `TaskType` enum (3 values: `appointment`, `follow_up`, `general`)
- `UnderstandResult` dataclass (`action_type`, `args`, `chat_reply`,
  `clarification`)
- `Clarification` dataclass (`kind`, `missing_fields`, `options`,
  `suggested_question`, `message_key`)
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
- Write: `src/services/runtime/context.py` (archive_turn)
- No Alembic; `create_tables()` + manual `ALTER TABLE` for dev

### A3. Schema: DoctorTask temporal fields

Add `scheduled_for: Optional[datetime]` and `remind_at: Optional[datetime]`
to `DoctorTask`. Existing `due_at` is retained for backward compatibility
but not used by the new pipeline (ADR §11).

- Model: `src/db/models/tasks.py`
- CRUD: `src/db/crud/tasks.py` (update create/query functions)

### A4. Dead-field MemoryState

Stop reading `working_note`, `candidate_patient`, `summary` from
`MemoryState`. The `memory_json` column on `DoctorContext` is retained but
not read by the pipeline (ADR §17).

Affected modules:
- `src/services/runtime/commit_engine.py` (`_collect_clinical_text`)
- `src/services/runtime/conversation.py` (context block building)
- `src/services/runtime/turn.py` (memory patch application — remove)

### A5. Templates and messages

Add template strings to `src/messages.py` for:

- All 7 clarification kinds (`missing_field`, `ambiguous_intent`,
  `ambiguous_patient`, `not_found`, `invalid_time`, `blocked`, `unsupported`)
- Action success templates (`select_patient`, `create_patient`,
  `schedule_task` with datetime echo-back, `schedule_task` with noon default)
- `create_patient` template must guide the follow-up: "已创建患者张三。
  您可以继续说'写个记录'来创建病历。" (mitigates create_patient_and_draft
  UX regression)
- Error templates (understand failure, compose failure fallback, execute error,
  TTL expiry "草稿已过期，请重新创建")
- Truncation template ("共N条记录，显示最近M条")
- Compose failure fallback for WeChat/voice: include brief data summary
  (e.g., first record date/title), not just count — "找到5条记录" with no
  content is not actionable on non-web channels where `view_payload` is
  ignored

---

## Stream B: Understand Phase (depends on A1 for types)

The LLM call that classifies intent and extracts entities.

### B1. Understand prompt

Create `src/prompts/understand.md`:

- JSON output matching `UnderstandResult` shape
- `chat_reply` only for `action_type == none`
- Raw names, no resolution
- No hallucinated args
- `clarification` vs `chat_reply` guidance
- Per-action args examples

### B2. Fast-router integration (optimization)

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
- Single LLM call (JSON mode)
- Parse response into `UnderstandResult`
- Boundary rule: parse failure → return generic error
- Precedence: if both `clarification` and `chat_reply` set, clarification wins
- **Runtime invariant enforcement** (do not trust the prompt):
  - Strip `chat_reply` to null when `action_type != none`
  - Validate `args` against per-action schema (§8): reject unknown keys,
    enforce required fields, clamp out-of-bounds values (e.g., limit max 10).
    Invalid args → return `clarification.kind="missing_field"` for the
    missing/invalid field, not a silent pass-through to resolve.

---

## Stream C: Execute Phase (depends on A1 for types, A2/A3 for schema)

### C1. Resolve module

Create `src/services/runtime/resolve.py`:

- `async def resolve(result: UnderstandResult, ctx: DoctorCtx) -> ResolvedAction | Clarification`
- Patient matching strategy (ADR §10):
  - Exact match first
  - Prefix fallback (2-char minimum, 5-result cap)
- Context fallback when `patient_name` is null
- Read/write binding asymmetry (reads scope, writes switch)
- Pending draft blocking:
  - Same-patient `schedule_task`: allowed
  - `create_draft` during pending: blocked
  - Context-switching writes: blocked
  - Cross-patient reads: blocked
- Date normalization for `schedule_task`:
  - Relative → absolute using current date + timezone
  - Date-only → noon default
  - Reminder default: 1 hour before `scheduled_for`
  - Past dates → `clarification.kind="invalid_time"`
  - Unparseable → `clarification.kind="invalid_time"`
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

### C3. Commit engine refactor

Refactor `src/services/runtime/commit_engine.py`:

- `async def commit(action: ResolvedAction, ctx: DoctorCtx) -> CommitResult`
- `schedule_task`: create `DoctorTask` row immediately using new
  `scheduled_for` / `remind_at` fields. Return `status: "ok"`.
- `create_draft`: collect clinical content from `chat_archive` (patient-scoped
  scan per A2), call structuring LLM, create pending draft. Return
  `status: "pending_confirmation"`.
- `select_patient`: update context binding. Return `status: "ok"`.
- `create_patient`: create patient row (reject duplicates), update context.
  Return `status: "ok"`.
- Remove `create_patient_and_draft` handler
- Remove `_collect_clinical_text` dependency on `working_note` (use
  chat_archive scan instead, per A4)
- Error handling: DB errors → `status: "error"` + `error_key`

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

## Stream E: Orchestrator Integration (depends on A, B, C, D)

### E1. Refactor process_turn

Refactor `src/services/runtime/turn.py`:

- Deterministic handler (typed UI actions + 確認/取消 during pending)
- Pipeline: understand → resolve → dispatch (read_engine | commit_engine) →
  compose
- Response mode routing from `RESPONSE_MODE_TABLE`
- `action_type == none` → return `chat_reply` directly
- Clarification from understand → skip execute, compose clarification
- Clarification from resolve → skip engine, compose clarification
- `view_payload` on TurnResult for reads
- Archive turn to chat_archive (with patient_id per A2)

### E2. Remove legacy single-pass path

- Remove `conversation.py` `call_conversation_model()` (replaced by
  understand)
- Remove `ModelOutput` type (replaced by `UnderstandResult`)
- Remove `ActionRequest` type (replaced by typed args per action)
- Remove `VALID_ACTION_TYPES` frozenset (replaced by `ActionType` enum)
- Remove `_handle_action()` dispatch (replaced by resolve → engine dispatch)
- Remove memory patch application logic

### E3. Channel updates

- Web `chat.py`: remove greeting/help fast paths (understand handles these
  as `none`)
- WeChat `router.py`: ensure dedup by `MsgId` before `process_turn()`
  (channel-layer responsibility)
- Remove `message_id` parameter from `process_turn()` signature
- Update `TurnResult` to include `view_payload`

---

## Prerequisite Checklist

Before starting any stream:

- [ ] Read ADR 0012 (all 17 sections + deferred)
- [ ] Read ADR 0012 architecture diagram
- [ ] Read current `src/services/runtime/` modules for existing patterns

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Understand prompt quality (action classification accuracy) | Test with real doctor inputs from chat_archive corpus; iterate prompt in B1 |
| Date normalization edge cases (Chinese relative dates) | Use existing `dateparser` or similar library; test with corpus |
| create_patient_and_draft UX regression | Known; deferred to follow_up_hint ADR |
| chat_archive scan performance (full history per patient) | Index on (doctor_id, created_at); limit scan to last N turns if needed |
| No coexistence/rollback mechanism — hard cutover for all doctors | MVP has single doctor; acceptable. For multi-doctor deployment, add an env flag (`PIPELINE_VERSION=v1|v2`) to `process_turn` that routes to old or new path. Implement in E1 if needed before launch. |
