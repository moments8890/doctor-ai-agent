# ADR 0012: Understand / Execute / Compose Pipeline for Operational Actions

## Status

Accepted

## Date

2026-03-14

## Implementation Status

Not Started

Last reviewed: 2026-03-14

Notes:

- This ADR replaces the original ADR 0012 flat-action-extension approach with a
  three-phase pipeline that separates intent classification from reply
  generation.
- Scope covers three operational actions: `query_records`, `list_patients`,
  `schedule_task`.
- This ADR does not introduce a general tool-calling agent, arbitrary DB access,
  or multi-step planning inside one turn.

## Context

ADR 0011 established a thread-centric runtime where one LLM call per turn
returns both a user-facing reply and an optional action request. That design is
clean for patient selection and draft creation, but breaks down for operational
actions:

- **Read queries** need data the LLM does not have at reply time. The model
  cannot summarize records it has never seen.
- **Write confirmations** generate user-facing prose before execution. If
  execution fails or produces unexpected results, the reply is stale or wrong.
- **Clarification** is unstructured. The LLM authors freeform questions that
  may not match product policy (e.g., asking about fields the system does not
  support yet).

ADR 0011 also introduced `create_patient_and_draft` as a hardcoded composite
action for the first-turn scenario ("帮张三写个门诊记录" where 张三 doesn't
exist). This design does not scale: each valid combination of two actions
would require its own enum value, leading to combinatorial explosion as the
action surface grows. This ADR removes all composite actions. Each turn
produces exactly one action. For the new-patient-plus-draft scenario, the
doctor creates the patient first, then triggers the draft in a follow-up turn.
This is a UX regression for one specific flow, traded for a clean action model
that supports future multi-action sequencing without per-combination enum
values (see Deferred).

The original ADR 0012 (v1) proposed extending the flat `ActionRequest` with
typed args and a read engine, but kept the single-pass "reply + action" model.
This revision replaces that model with a three-phase pipeline that enforces a
hard boundary: **the LLM classifies intent but never authors the final reply
for operational turns**.

## Decision

### 1. Three-phase pipeline: Understand → Execute → Compose

Replace the ADR 0011 single-pass model with three distinct phases:

```text
user_input + DoctorCtx
      |
  Understand     — classify intent, extract entities
  |                output: UnderstandResult (structured, no user-facing prose
  |                for operational turns)
  |
  Execute
  |  ├── Resolve       — patient lookup, binding, validation (shared)
  |  └── dispatch:
  |       ├── read_engine   — SELECT only, no durable writes
  |       └── commit_engine — durable writes, pending state
  |
  Compose        — generate reply FROM execution results
                   template or LLM, never from understand's imagination
```

**Core invariant**: Compose only speaks from execution results. Understand never
produces user-facing text for operational turns.

### 2. Decision table

Not every turn runs all three phases. The runtime selects a path based on input
type:

| Input type | Understand | Execute | Compose | LLM calls |
| --- | --- | --- | --- | --- |
| Deterministic (button click, 确认/取消 during pending) | skip | deterministic handler | template | 0 |
| Read query ("查张三的病历") | LLM → structured | DB fetch | LLM summarize | 2 |
| Write: schedule_task ("帮张三约下周三复诊") | LLM → structured | immediate commit | template success | 1 |
| Write: create_draft ("写个门诊记录") | LLM → structured | collect + structure | template confirm (pending) | 2 |
| Chitchat / help / greeting | LLM → chat_reply | skip | skip | 1 |
| Clarification needed | LLM → structured | skip | template (or understand's suggested_question) | 1 |

The two-LLM-call paths (reads and create_draft) are justified: reads need
real data to summarize; create_draft needs an LLM structuring call to convert
clinical text into a structured medical record. There is no way to do either
correctly in one call.

This table describes routing by **input shape**. Section 3 describes the same
routing by **action_type** — the two must stay consistent.

### 3. Understand output contract

Understand produces a structured result with no user-facing prose for
operational turns. Chitchat and help are the only cases where understand may
produce a direct reply.

```text
ActionType (enum):
  query_records
  list_patients
  schedule_task
  select_patient
  create_patient
  create_draft
  none

UnderstandResult
  action_type: ActionType
  args: dict
    # typed per action_type (see section 8)
  chat_reply: optional str
    # only when action_type == none (chitchat/help)
  clarification: optional Clarification
    # structured clarification (see section 4)
```

**No `memory_patch` in phase 1.** The conversation history (`chat_archive`)
provides sufficient clinical context for MVP session lengths. `create_draft`
collects content from the full archive, not just the understand context window.
Patient binding is tracked deterministically via `patient_id` in
`WorkflowState`. See Deferred for when to revisit.

The runtime — not the LLM — derives the response mode from `action_type`:

| action_type | response_mode | Phases that run |
| --- | --- | --- |
| `none` | `direct_reply` | Understand only; return `chat_reply` |
| `query_records`, `list_patients` | `llm_compose` | Understand → Execute → Compose (LLM) |
| `schedule_task` | `template` | Understand → Execute → Compose (template) |
| `select_patient`, `create_patient`, `create_draft` | `template` | Understand → Execute → Compose (template) |

When `clarification` is set on `UnderstandResult`, the runtime skips execute
entirely and routes to the clarification composer. Clarifications can also
originate from execute.resolve (see section 5a), in which case only act is
skipped — resolve still runs. Both paths produce the same `Clarification` type
and use the same composition rule (section 4).

When `action_type` is `none`, the runtime skips both execute and compose and
returns `chat_reply` directly.

#### Understand prompt contract

The understand prompt is the most implementation-critical artifact. The ADR
does not prescribe prompt text, but the prompt must enforce these constraints:

- **Output format**: JSON matching the `UnderstandResult` shape. No markdown,
  no freeform prose outside `chat_reply`.
- **`chat_reply` only for `none`**: when `action_type` is not `none`, the
  `chat_reply` field must be null. The prompt must explicitly instruct the
  model to never generate user-facing text for operational turns.
- **Raw names, no resolution**: `args.patient_name` should be the name the
  user said, not a guess at which patient they mean. Resolution is
  execute.resolve's job.
- **No hallucinated args**: if the user didn't mention a time, don't invent
  one. Emit null and let resolve request clarification.
- **`clarification` vs `chat_reply`**: if the model is genuinely unsure
  between two action types, it should emit `clarification.kind =
  "ambiguous_intent"` with a `suggested_question`, not write a clarifying
  question in `chat_reply`.

The compose prompt (for `llm_compose` turns) is simpler: it receives the
original user input plus fetched data and returns a natural-language summary.
It has no action output — only a text reply.

### 4. Structured clarification model

Both understand and execute.resolve can produce clarifications. They share a
single `Clarification` type. The runtime — not the LLM — decides how to render
each kind.

#### Clarification kinds

Deterministic kinds (always rendered via template; LLM `suggested_question` is
ignored):

- `missing_field` — a required arg was not extracted
- `ambiguous_patient` — multiple DB matches for patient name
- `not_found` — patient name resolved to zero matches
- `invalid_time` — date/time could not be parsed or is out of range
- `blocked` — pending draft or pending action exists, operation not allowed
- `unsupported` — action not supported in current phase

Semantic kinds (runtime may use LLM-authored `suggested_question`, with
template fallback):

- `ambiguous_intent` — intent is genuinely unclear between valid actions

#### Clarification data shape

```text
Clarification
  kind: str
    # "missing_field" | "ambiguous_intent" | "ambiguous_patient"
    # | "not_found" | "invalid_time" | "blocked" | "unsupported"
  missing_fields: list[str]
    # e.g. ["scheduled_for"] for schedule_task with no time specified
  options: list[dict]
    # e.g. [{"name": "张三", "id": 1}, {"name": "张三丰", "id": 2}]
  suggested_question: optional str
    # LLM-authored in understand; only used for semantic kinds
  message_key: optional str
    # set by execute.resolve for template lookup
```

#### Who produces which kinds

| Kind | Understand | Execute.resolve |
| --- | --- | --- |
| `ambiguous_intent` | yes | no |
| `unsupported` | yes (boundary rule) | no |
| `missing_field` | yes (extraction gap) | yes (binding gap) |
| `ambiguous_patient` | no | yes |
| `not_found` | no | yes |
| `invalid_time` | no | yes |
| `blocked` | no | yes |

#### Composition rule

```text
if kind in {missing_field, ambiguous_patient, not_found, invalid_time,
            blocked, unsupported}:
    use template (message_key if set, else default for kind)
    ignore suggested_question
elif kind == "ambiguous_intent" and suggested_question is not None:
    use suggested_question
else:
    use template fallback
```

This keeps the LLM out of the policy layer. Deterministic clarification is
always template-driven. The LLM may only author prose for genuine semantic
ambiguity.

### 5. Execute phase: resolve → read_engine | commit_engine

Execute is deterministic and has three internal modules. Understand extracts
raw names and args without I/O. Execute does all resolution against the
database and context, then dispatches to either the read engine or the commit
engine.

```text
Execute
  ├── resolve        — patient lookup, binding, date normalization (shared)
  └── dispatch by action classification:
       ├── read_engine   — SELECT only, no durable writes, no state mutation
       └── commit_engine — prepares pending, creates records, sets workflow state
```

Action classification (const table):

```text
READ_ACTIONS  = {query_records, list_patients}
WRITE_ACTIONS = {schedule_task, select_patient, create_patient,
                 create_draft}
```

The split is enforced at the module level: `read_engine.py` never imports
write helpers and never touches `pending_*` tables. This provides a hard
boundary that prevents read handlers from accidentally creating durable state.

#### 5a. Resolve

Resolve takes the raw `UnderstandResult` and `DoctorCtx` and produces a fully
bound action or a clarification. It is the only code that does patient DB
lookup in the pipeline. Shared by both read and write paths.

Resolve responsibilities:

- look up `args.patient_name` in the database (exact match, phase 1)
- fall back to `ctx.workflow.patient_id` when `patient_name` is null
- detect patient switch (explicit name differs from bound patient)
- enforce read/write binding asymmetry (see section 10)
- validate that required bindings exist for the action type
- normalize relative dates using current date and configured timezone

Resolve outcomes:

- **resolved** — patient and args are fully bound, proceed to read or commit
- **clarification** — binding failed, short-circuit to compose with a
  `Clarification` (same type as section 4; resolve sets `message_key` for
  template lookup)

When resolve short-circuits, neither engine runs. Compose renders the
clarification using a template.

#### 5b. Read engine

Read engine receives a fully resolved action and fetches data. It never
creates durable writes and never mutates workflow state.

- `query_records` → fetch patient records from DB
- `list_patients` → fetch doctor's patient panel

Returns a `ReadResult` for compose.

```text
ReadResult
  status: str
    # "ok" | "empty" | "error"
  data: optional any
    # records list, patient list, etc.
  total_count: optional int
    # total matching rows before limit was applied
  truncated: bool
    # true when total_count > len(data)
  message_key: optional str
    # template key for compose
  error_key: optional str
    # template key for error replies (only when status == "error")
```

`"empty"` means the query succeeded but returned no rows (e.g., patient exists
but has no records). This is distinct from resolve's `not_found` (patient name
did not match anyone).

When `truncated` is true, compose includes `total_count` in the reply (e.g.,
"共23条记录，显示最近5条") so the doctor knows results were capped.

#### 5c. Commit engine

Commit engine receives a fully resolved action and executes durable writes.
It never fails on binding — that was already validated by resolve.

- `schedule_task` → create `DoctorTask` row immediately (no confirmation)
- `create_draft` → collect clinical content, structure, create pending draft
- `select_patient` → update context binding
- `create_patient` → create patient row, update context binding

Returns a `CommitResult` for compose.

```text
CommitResult
  status: str
    # "ok" | "pending_confirmation" | "error"
  data: optional any
    # created entity details for template rendering
  pending_id: optional str
    # for confirmation flows (drafts and actions)
  message_key: optional str
    # template key for compose
  error_key: optional str
    # template key for error replies (only when status == "error")
```

`ReadResult` and `CommitResult` are separate types, not a union. Read engine
always returns `ReadResult`; commit engine always returns `CommitResult`. This
enforces the invariant that read handlers cannot produce `pending_id` and
commit handlers cannot produce `total_count` / `truncated`.

For `create_draft`, `status` is `"pending_confirmation"` and the result
contains enough information for compose to render a confirmation prompt.
For immediate actions (`schedule_task`, `select_patient`, `create_patient`),
`status` is `"ok"` and compose renders a success template.

### 6. Phase-1 action types and boundary rule

Supported action types in phase 1:

| action_type | Read/Write | Confirmation | Chat behavior |
| --- | --- | --- | --- |
| `query_records` | Read | No | Fetch + LLM summarize |
| `list_patients` | Read | No | Fetch + LLM summarize |
| `schedule_task` | Write | No (immediate) | Smart extraction + immediate commit |
| `select_patient` | Write (context) | No | Resolve patient, template reply |
| `create_patient` | Write | No | Create patient, template reply |
| `create_draft` | Write | Yes (pending) | Collect + structure, template confirm |
| `none` | — | No | Chitchat / help |

All action types — including those carried forward from ADR 0011 — go through
the full Understand → Execute → Compose pipeline. There is no legacy
single-pass path. The ADR 0011 actions previously returned LLM-authored replies
alongside actions in one call; under this ADR, understand emits a structured
result and compose generates the reply from execution results. This eliminates
the compose-before-execute problem for all action types, not just the new
operational ones.

**Boundary rule**: if the LLM response cannot be parsed into a valid
`ActionType`, the runtime treats it as a parse failure and returns a generic
error template. The LLM never silently invents new capabilities.

### 7. Pre-pipeline deterministic handler

A single deterministic handler runs before the three-phase pipeline. It
intercepts inputs that never need LLM classification:

```text
user_input (already deduped by channel layer)
  |
  deterministic handler
    typed UI action? (button click) → execute directly → template reply
    pending_draft_id set + 确认/取消 regex? → commit or discard → template reply
  |
  Understand → Execute → Compose
```

There is no "draft guard" or "pending guard" as a separate architectural
layer. The deterministic handler intercepts two cases: typed UI actions and
draft confirmation/abandonment. Everything else — including input during a
pending draft — flows through the full pipeline. Execute.resolve owns all
blocking logic:

- **Write during pending draft**: resolve returns
  `clarification.kind="blocked"`.
- **Cross-patient read during pending draft**: resolve returns
  `clarification.kind="blocked"` (see section 10).
- **Chitchat during pending draft**: understand classifies as `none`, returns
  `chat_reply` directly. Not blocked — the doctor can continue conversing.
- **Same-patient read during pending draft**: allowed, resolve scopes the
  query normally.

This eliminates the read-only regex heuristic (which could never be complete)
and the "other → blocked" default (which incorrectly blocked legitimate
chitchat and clinical observations during a pending draft). The trade-off is
one LLM call for write-during-draft inputs before resolve blocks them — an
uncommon path acceptable for MVP.

### 8. Typed action args

Each action type has a bounded args shape. This is a typed contract, not
generic JSON-RPC.

#### select_patient

```text
args:
  patient_name: str (required)
```

#### create_patient

```text
args:
  patient_name: str (required)
  gender: optional str
  age: optional int
```

#### create_draft

```text
args:
  (none — clinical content is collected by the commit engine,
   not from LLM-extracted args)
```

Requires a bound patient in context. Execute.resolve validates this.

Clinical content collection scope: all user-role turns in `chat_archive`
for the current `doctor_id` since the last completed record for the bound
patient (or session start if no prior record). This ensures the structuring
LLM sees all relevant clinical input without noise from prior encounters.
The commit engine passes this content to the structuring LLM (second LLM
call) before creating the pending draft.

#### query_records

```text
args:
  patient_name: optional str
  limit: optional int (default 5, max 10)
```

- If `patient_name` is given and resolves to one patient, scopes the query to
  that patient without switching context (see section 10).
- If `patient_name` is absent, reads from the current bound patient.
- If neither is available, execute.resolve returns
  `clarification.kind="missing_field"`.

#### list_patients

```text
args:
  (none in phase 1)
```

- Returns first page, recency-ordered, default 20, max 50.
- Does not change active patient binding.
- Cursor pagination is reserved for typed UI follow-up actions, not for the
  LLM action contract.

#### schedule_task

```text
TaskType (enum):
  appointment
  follow_up
  general

args:
  task_type: TaskType (required)
  patient_name: optional str
  title: optional str
  notes: optional str
  scheduled_for: optional str (relative or absolute time expression)
  remind_at: optional str (relative or absolute time expression)
```

- `task_type` is required. If the LLM emits a value that cannot be parsed
  into a valid `TaskType`, resolve rejects it with
  `clarification.kind="missing_field"` and `missing_fields=["task_type"]`.
- Requires a strong patient target: explicit name or current bound patient.
- Relative dates are normalized deterministically by the runtime using current
  date and configured timezone — not by trusting model-generated ISO strings.
- For `task_type="appointment"`: a date is required. If the user provides a
  date without a specific time ("下周三"), the runtime defaults to 12:00
  (noon) in the configured timezone. Reminder defaults deterministically
  (one hour before) when not specified.
- For non-appointment tasks: `remind_at` serves as the actionable
  deadline/reminder time.

Routing language ("预约", "复诊提醒", "建个任务") maps to `task_type` values.

### 9. Compose phase detail

Compose generates the user-facing reply from execute results. It never uses
understand's output as prose source. The runtime selects the compose strategy
from the `action_type` → `response_mode` table in section 3.

| response_mode | Compose behavior |
| --- | --- |
| `direct_reply` | Return `understand.chat_reply` verbatim. No execute ran. |
| `template` | Format a template using `execute_result` data. No LLM call. |
| `llm_compose` | Call the LLM with execute results injected as context. |

For `llm_compose` (read queries), the compose prompt receives:

- the original user input
- the fetched data (records, patient list)
- a brief instruction to summarize naturally

The compose LLM call is distinct from the understand call. It has no action
output — only a text reply. This keeps it simple and fast.

#### Template reply examples per action type

| action_type | Template example |
| --- | --- |
| `select_patient` | "已切换到张三" |
| `create_patient` | "已创建患者张三" / "张三已存在，已切换" |
| `create_draft` | existing `M.draft_created` (preview + confirm prompt) |
| `schedule_task` | "已为张三创建随访任务，时间：3月20日下午2点" |
| `schedule_task` (noon default) | "已为张三创建复诊预约，时间：3月18日中午12点" |

All template replies are deterministic and predictable. Only `query_records`
and `list_patients` use LLM compose because their data is variable and benefits
from natural language summarization.

### 10. Patient binding model

Patient binding is handled entirely by execute.resolve. Understand extracts
raw patient names without I/O. The binding rules differ between reads and
writes.

#### Core asymmetry: reads scope, writes switch

- **Read actions** (`query_records`, `list_patients`) scope the query to the
  target patient but **do not switch** the active context. The doctor can peek
  at another patient's data without losing their current working context.
- **Write actions** (`schedule_task`, `select_patient`, `create_patient`)
  **switch** the active context to the target patient before acting, using the
  same switch rules as ADR 0011 (pending draft blocks). `create_draft` is the exception — it requires the current bound
  patient and does not switch.

This matches how a doctor uses a chart: looking up another patient's records is
a glance, not a context switch. But mutating another patient's data means you
are now working on that patient.

#### Resolution rules

| Situation | Read action | Write action |
| --- | --- | --- |
| Explicit name, resolves to 1 patient | Scope query to that patient. Context unchanged. | Switch context to that patient, then act. |
| Explicit name, resolves to N>1 patients | Clarify: `ambiguous_patient` with options | Clarify: `ambiguous_patient` with options |
| Explicit name, resolves to 0 patients | Return `not_found` | Return `not_found` |
| No name, context has patient | Use context patient | Use context patient |
| No name, no context patient | Clarify: `missing_field` | Clarify: `missing_field` |
| Pending draft, same patient | Allowed | Blocked by execute.resolve (`blocked`) |
| Pending draft, different patient | Blocked by execute.resolve (`blocked`) | Blocked by execute.resolve (`blocked`) |
| Pending draft, unscoped (`list_patients`) | Always allowed (no patient target) | N/A |

#### Implicit patient handling

When `args.patient_name` is null, understand is not expected to fill in the
context patient's name. Understand emits what the user said; execute.resolve
applies the context fallback. This avoids understand inventing a name the user
did not say.

#### Unique patient names per doctor

Patient names are unique within a doctor's panel. `create_patient` rejects
duplicates (the existing behavior returns "已存在，已切换" instead of creating
a second patient with the same name). This means exact-match resolution always
returns zero or one result — `ambiguous_patient` only arises from prefix
matching (e.g., "张三" matching both "张三" and "张三丰").

#### No fuzzy matching in phase 1

Resolve uses exact match or prefix match only. Fuzzy/semantic patient search is
deferred. If no match is found, resolve returns `not_found` with a template
message.

#### `list_patients` is unscoped

`list_patients` never changes patient binding. It returns the doctor's full
patient panel (first page). No patient name arg is needed or used. Because it
has no patient target, it is always allowed during a pending draft — there is
no cross-patient conflict to detect.

### 11. Task temporal semantics

`DoctorTask` needs two distinct timestamp fields:

- `scheduled_for` — the event time itself (appointment, follow-up date)
- `remind_at` — the reminder/notification fire time

These names match the `schedule_task` args in section 8. The runtime must not
store only one timestamp and guess which meaning it has.

### 12. Date normalization must be deterministic

The model may propose relative-time expressions in `args`, but the execute
phase normalizes them using:

- current absolute date
- configured timezone
- validation rules per task type

Default fill rules:

- **Date without time** (e.g., "下周三") → default to 12:00 noon
- **Reminder not specified** → default to one hour before `scheduled_for`

The runtime rejects or clarifies invalid temporal payloads (e.g., past dates,
unparseable expressions) rather than silently accepting hallucinated ISO
strings.

### 13. Audit all operational actions

All runtime-driven reads and writes emit audit events. Chat-driven reads must
not be less auditable than web UI reads.

Audited operations:

- patient list reads (`list_patients`)
- record reads (`query_records`)
- task creation/scheduling (`schedule_task`)
- patient creation (`create_patient`)
- patient selection / context switches (`select_patient`)
- draft creation (`create_draft`)

### 14. TurnResult gains optional view_payload

`TurnResult` gains an optional `view_payload` for structured channel rendering:

- Web can render structured results (record tables, patient cards) without
  parsing assistant prose.
- WeChat and voice ignore the payload and use the plain-text reply.

Initial payload families:

- `records_list`
- `patients_list`
- `task_created`

The assistant reply remains mandatory for all channels.

### 15. Pending draft lifecycle

`create_draft` is the only action that uses pending state. Medical records are
permanent clinical documents — the doctor must preview the LLM-structured
output before it is committed. All other write actions (`schedule_task`,
`select_patient`, `create_patient`) commit immediately.

#### Turn 1: create the pending draft

```text
"写个门诊记录"
  → deterministic handler (no match, pass through)
  → Understand → action_type: create_draft
  → Resolve: validate bound patient exists
  → Commit engine:
      1. Collect clinical content from chat_archive
         (user turns since last completed record for bound patient)
      2. Call structuring LLM (2nd LLM call for this turn)
      3. Create pending_drafts row with structured content + TTL
      4. Set ctx.workflow.pending_draft_id
  → Compose: template with structured preview + "确认保存？"
```

#### Turn 2: confirm or cancel

```text
"确认"
  → deterministic handler: pending_draft_id set + 确认 regex → match!
      1. Save pending draft content → medical_records table
      2. Clear ctx.workflow.pending_draft_id
      3. Trigger background tasks (CVD extraction, etc.)
  → template reply "已保存"
  (pipeline never runs)

"取消"
  → deterministic handler: pending_draft_id set + 取消 regex → match!
      1. Delete pending_drafts row
      2. Clear ctx.workflow.pending_draft_id
  → template reply "已取消"
  (pipeline never runs)
```

#### During pending: other input

All non-confirm/cancel input during a pending draft flows through the full
pipeline (see section 7). Execute.resolve blocks writes and cross-patient
reads; chitchat and same-patient reads are allowed.

#### State

`WorkflowState` retains only `pending_draft_id` — no `pending_action_id`,
no mutex. The pending draft is persistent state that bridges two independent
pipeline runs.

```text
WorkflowState
  patient_id: optional int
  patient_name: optional str
  pending_draft_id: optional str    # only pending state
```

#### Storage

The `pending_drafts` table holds the structured content with a TTL. On
expiry, the row is deleted and `pending_draft_id` is cleared. The payload
contains the fully structured record — confirmation commits it without
re-running the structuring LLM.

### 16. LLM failure fallbacks

Two pipeline phases involve LLM calls that can fail (timeout, invalid JSON,
provider error). The runtime must degrade gracefully.

#### Understand failure

If the understand LLM call fails or returns unparseable output:

- No execute or compose runs.
- Return a generic error template reply (e.g., "抱歉，我没有理解您的意思，请再试一次").
- The turn is still archived for audit/debugging.

#### Compose failure (llm_compose only)

If the compose LLM call fails after execute succeeded (read data was fetched):

- The fetched data is not discarded.
- Fall back to a minimal template reply that acknowledges the data exists
  (e.g., "找到 N 条病历记录" / "共 N 位患者").
- Include `view_payload` so web clients can still render the structured data
  even if the natural-language summary failed.

### 17. MemoryState migration

ADR 0011 introduced `MemoryState` with three LLM-facing fields. This ADR
drops `memory_patch`, which means these fields are no longer written to.
Their fate:

| Field | ADR 0011 purpose | ADR 0012 replacement | Migration |
| --- | --- | --- | --- |
| `working_note` | LLM-accumulated clinical context | `chat_archive` scan (see §8 create_draft) | Dead field. Commit engine's `_collect_clinical_text` must switch from `ctx.memory.working_note` to the chat_archive scan. |
| `candidate_patient` | LLM-proposed patient before binding | Execute.resolve DB lookup (see §5a) | Dead field. Resolve handles all patient binding. |
| `summary` | LLM-authored conversation summary | Not replaced (conversation history is sufficient for MVP) | Dead field. |

`MemoryState` can be emptied in phase 1. The `memory_json` column on
`DoctorContext` is retained for backward compatibility but is not read by the
pipeline. If post-MVP `memory_patch` is re-added, these fields or new ones
can be populated again.

## What changes from ADR 0011

| Aspect | ADR 0011 (current) | ADR 0012-v2 (proposed) |
| --- | --- | --- |
| Per-turn model | LLM returns reply + action in one call | Understand → Execute → Compose (up to 2 LLM calls) |
| Reply source | LLM composes before execution | Compose speaks from ExecuteResult only |
| Read queries | Not supported in runtime | Understand → fetch → LLM compose |
| Write confirmation | Draft pattern only | Draft pending unchanged; `schedule_task` commits immediately |
| Clarification | LLM writes freeform reply | Structured: deterministic template or bounded LLM |
| Action validation | `VALID_ACTION_TYPES` frozenset | Same + unsupported fallback for unknown types |
| Patient binding | LLM proposes name, commit engine resolves | Understand extracts raw name, execute.resolve binds |
| Read binding | N/A (reads not supported) | Reads scope without switching context |
| `clarify` action type | LLM returns freeform prose as reply | Removed; replaced by structured `Clarification` field on `UnderstandResult` |
| `create_patient_and_draft` | Hardcoded composite action type | Removed; single actions only (see Context) |
| Understand output | `{ reply, action_request, memory_patch }` | `UnderstandResult` (structured; no `memory_patch` in phase 1) |

## Consequences

### Positive

- the LLM is no longer the policy layer for clarification; deterministic
  templates handle missing fields, ambiguous patients, and unsupported actions
- compose speaks only from real execution results, eliminating stale-reply bugs
- read queries work correctly because data is fetched before the reply is
  composed
- the pipeline naturally accommodates future action types without changing the
  architectural model
- write confirmations are consistent across all mutation types
- the action surface remains small and typed

### Negative

- read-query turns require two LLM calls (understand + compose), increasing
  latency and cost for those turns
- the runtime pipeline is more complex than ADR 0011's single-pass model
- the understand prompt must be carefully designed to emit structured output
  without user-facing prose for operational turns
- two distinct LLM prompts (understand and compose) must be maintained

### Deferred

- no generic tool-calling planner
- no natural-language global patient search in phase 1
- no task completion/cancellation/rescheduling in this ADR
- no compound actions in phase 1 — each turn produces exactly one action.
  `create_patient_and_draft` is removed; the doctor creates the patient first,
  then triggers the draft in a follow-up turn. **This is a known UX
  regression** for the most common first-turn flow ("帮张三写个门诊记录"
  where 张三 doesn't exist). The planned mitigation is a `follow_up_hint:
  optional ActionType` field on `UnderstandResult` — understand emits
  `create_patient` with `follow_up_hint: create_draft`, and the runtime
  auto-chains the second action after the first succeeds. This generalizes
  to `follow_up_actions: list[ActionType]` for arbitrary multi-action
  sequencing without enum explosion. Designed in a separate ADR.
- no `update_patient` in phase 1 — phone and ID number carry identity risk
  through chat/voice; gender and age alone have too little utility to justify
  the action type. Revisit with format validation and digit-level confirmation.
- no `memory_patch` in phase 1 — conversation history (`chat_archive`)
  provides sufficient clinical context for MVP session lengths.
  `create_draft` collects content from the full archive, not just the
  understand context window. Patient binding is deterministic via
  `WorkflowState.patient_id`. Revisit when conversation history truncation
  or summarization is added — that is when early clinical context could be
  lost. If added, prefer deterministic append (raw turn content) over
  LLM-authored extraction.
- no pending confirmation for `schedule_task` — commits immediately. Add
  `pending_action_id` and a generalized pending state machine when there is
  evidence that doctors make scheduling mistakes they cannot self-correct.
- no patient rename in phase 1
- no multi-patient active context or park-and-resume thread model
