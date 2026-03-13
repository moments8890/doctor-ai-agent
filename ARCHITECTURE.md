# Architecture

**Last updated:** 2026-03-12

## Overview

Doctor AI Agent is a FastAPI backend with a React web frontend for doctor-facing
workflows: patient management, medical record dictation, task management,
appointments, and follow-up support.

The current architecture is centered on one shared workflow core:

- a shared 5-layer intent workflow in `services/intent_workflow/`
- shared domain handlers in `services/domain/intent_handlers/`
- draft-first persistence for normal record creation
- separate DB sessions per operation within a turn (no single-transaction
  guarantee across knowledge, patient, and pending-draft writes)

The important nuance is that convergence is still partial. Web, WeChat, and
voice chat all use the same workflow core, but they still differ in
advisory-context richness, surrounding orchestration, and channel adapter
wiring.

---

## What Is Shipped Now

### Stable architectural decisions

- `medical_records.content` remains the source of truth for doctor-facing notes.
- Normal `add_record` flows are draft-first and require explicit confirmation.
- Blocked-write continuation is stateful and shared across web, WeChat, and
  voice chat (in-memory only; not yet crash-durable).
- Normal `add_record` note generation uses routing for control flow and
  structuring for final note content.
- Compound `create_patient + add_record` routes through
  `shared_handle_add_record` → pending draft on all channels.
- Official WeCom integration is the supported messaging channel model.
- The workflow uses a shared classify -> extract -> bind -> plan -> gate stack.

### Still in transition

- `DoctorTurnContext` is assembled and passed through the workflow on all three
  channels (web, WeChat, voice). Advisory-context richness still varies by
  channel.
- `update_record` still keeps a narrow correction-oriented
  `structured_fields` compatibility path separate from the normal `add_record`
  write flow.
- Channel adapters exist, but only some adapter methods are part of the main
  runtime path today.

See [ADR 0001](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0001-turn-context-authority.md),
[ADR 0002](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0002-draft-first-record-persistence.md),
[ADR 0007](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0007-stateful-blocked-write-continuations.md),
and [ADR 0008](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0008-minimal-routing-and-structuring-only-note-generation.md).

---

## Directory Structure

```text
routers/              Channel entry points (FastAPI routers)
  records.py            Web doctor chat + record endpoints
  wechat.py             WeChat / WeCom webhook + doctor message handling
  voice.py              Voice chat + consultation recording endpoints
  miniprogram.py        Mini-program REST endpoints
  patient_portal.py     Patient self-service portal
  auth.py               Doctor login, invite codes
  tasks.py              Task management endpoints
  export.py             PDF / report export
  neuro.py              Specialist / CVD endpoints
  wechat_flows.py       WeChat multi-turn flow helpers
  wechat_infra.py       WeChat platform infrastructure
  ui/                   Admin + workbench endpoints
  # Note: media endpoints (from-image, from-audio) live in records.py

services/
  intent_workflow/      Shared 5-layer intent workflow
  domain/
    intent_handlers/    Shared intent handlers (add_record, create_patient, ...)
    adapters/           WebAdapter + WeChatAdapter
    message.py          Unified Message model + ChannelAdapter protocol
    record_ops.py       Record assembly and clinical-context building
    patient_ops.py      Patient resolution helpers
    chat_handlers.py    Legacy shared chat helpers still used in some flows
    chat_constants.py   Shared replies and patterns
    compound_normalizer.py  Compound-intent normalization
    name_utils.py       Name parsing and continuation helpers
    text_cleanup.py     Text normalization
  ai/
    fast_router/        Deterministic routing rules
    agent.py            Routing LLM dispatch
    agent_fallback.py   Conservative fallback behavior
    agent_tools.py      Tool definitions for LLM agent
    intent.py           Intent enum and mapping
    llm_client.py       Unified LLM client wrapper
    llm_resilience.py   LLM retry and fallback logic
    memory.py           Context compression
    multi_intent.py     Multi-intent detection
    neuro_structuring.py  Specialty structuring (neuro/CVD)
    provider_registry.py  LLM provider configuration registry
    router.py           Legacy router compatibility
    structuring.py      Structuring LLM for readable notes
    transcription.py    Voice transcription
    turn_context.py     DoctorTurnContext assembly
    vision.py           Vision / OCR LLM helpers
  session.py            Per-doctor session state, locks, hydration, blocked writes
  auth/                 JWT, PBKDF2, rate limiting
  knowledge/            Doctor knowledge base, import, OCR
  wechat/               WeChat domain logic, media, notifications
  patient/              Search, risk scoring, interview flows
  export/               PDF export and reports
  notify/               Task scheduling and APScheduler jobs
  observability/        Audit, routing metrics, spans

db/
  models/               SQLAlchemy models
  crud/                 CRUD functions
  repositories/         Repository wrappers
  engine.py             Async engine + session factory
  init_db.py            Table creation

frontend/              React web app (Vite)
e2e/                   Integration, replay, and unit tests (consolidated)
scripts/               Dev and CI scripts
docs/                  ADRs, plans, reviews, product docs
```

---

## Doctor Message Flow

There is one shared workflow core, but the entry path varies by channel.

### Pre-workflow fast paths

Several deterministic checks short-circuit the workflow entirely:

- **Greeting regex** (web)
- **Patient-count regex** (web)
- **Delete-by-ID / context-save commands** (web)
- **Task completion** (`完成 N`) (web, WeChat)
- **Knowledge-base add command** (web, WeChat)
- **Notify control** (web, WeChat)
- **Menu number selection** (web)
- **Pending-draft correction** — detects correction patterns and edits the
  pending draft in-place via routing extraction (`agent.dispatch()` +
  `structured_fields` merge) (web)
- **Blocked-write precheck** — resolves bare-name / name+supplement
  continuations from session state (web, WeChat, voice)
- **Stateful flow resume** — pending_record, pending_create, pending_cvd,
  interview (WeChat)

### Web chat

`POST /api/records/chat`

```text
request body
-> WebAdapter.parse_inbound()
-> rate limit check
-> endpoint fast paths (notify control, greeting, menu number, 完成 N)
-> chat_core():
   -> deterministic fast paths (patient count, delete, context save, knowledge)
   -> pending-draft correction check
   -> blocked-write precheck / cancel detection
   -> assemble DoctorTurnContext (authoritative + advisory)
   -> load knowledge context
   -> services.intent_workflow.run(turn_context=...)
   -> gate check (always returns clarification on block)
   -> shared domain handler dispatch
-> WebAdapter.format_reply()
-> JSON response
```

### WeChat / WeCom doctor chat

Main doctor message handling in `routers/wechat.py`

```text
webhook message
-> session-aware router orchestration
-> fast paths (task complete, knowledge, notify)
-> blocked-write precheck
-> assemble DoctorTurnContext (authoritative workflow state)
-> stateful flow detection (pending record/create/cvd/interview)
-> load knowledge context
-> services.intent_workflow.run(turn_context=...)
-> gate check (no_patient_name falls through to handler)
-> shared domain handler dispatch
-> WeChat helper formatting / customer-service send path
```

WeChat assembles `DoctorTurnContext` (authoritative + advisory) under lock and
passes it into the workflow, same as web and voice.

On workflow failure, WeChat falls back to `structure_medical_record()` and
replies with formatted text as a resilience fallback.

### Voice chat

`POST /api/voice/chat`

```text
audio upload
-> transcribe_audio()
-> hydrate session state
-> blocked-write precheck / cancel detection
-> assemble DoctorTurnContext
-> services.intent_workflow.run(turn_context=...)
-> gate check (no_patient_name falls through to handler)
-> shared domain handler dispatch (including compound create+record)
-> JSON response
```

Voice chat shares the same draft-first semantics as web and WeChat for normal
record creation. Unlike web and WeChat, voice does not currently load doctor
knowledge context before the workflow call, so routing decisions that depend on
knowledge-base context may behave differently.

### Modality normalization (ADR 0009)

All non-text inputs are normalized before workflow entry:

- **Voice** (including `/api/voice/consultation`): transcribed then enters the
  same 5-layer workflow as typed text. `consultation_mode=True` is a
  transcription hint only, not a workflow bypass.
- **Image** (`/from-image`): OCR-extracted text dispatches to `import_history`
  for chunking, dedup, and persistence.
- **Audio** (`/from-audio`): transcribed text dispatches to `import_history`.
- **PDF**: goes through `/extract-file`, which extracts text for UI preview or
  further processing. There is no dedicated `/from-pdf` endpoint.
- **Extraction-only helpers** (`/ocr`, `/extract-file`, `/transcribe`): remain
  as stateless utilities for UI preview.

---

## Workflow Types and LLM Integration

The repo now uses LLMs in two distinct roles:

- **routing LLM** in `services/ai/agent.py`
  - decides semantic intent
  - extracts coarse routing entities
  - does not author the final `add_record` note
- **structuring LLM** in `services/ai/structuring.py`
  - turns clinical text into readable doctor-facing note content
  - is used only on note-producing or structuring-specific paths

Deterministic state and code still own:

- blocked-write continuation
- patient-binding approval
- gate checks
- pending-draft confirmation
- final persistence decisions

### Workflow map

| Workflow | Routing LLM | Structuring LLM | Notes |
| --- | --- | --- | --- |
| Read/query/task | When `fast_route()` misses | No | Handler executes directly after bind/gate |
| Standard `add_record` | Yes (intent + coarse entities) | Yes (`assemble_record()`) | Gate may block; non-emergency → pending draft; emergency → direct-save |
| Blocked-write continuation | No (precheck resumes) | Yes | `precheck_blocked_write()` resolves from session state |
| `create_patient` only | Yes unless deterministic match | No | Normal handler logic |
| `create_patient` + clinical compound | Yes (create intent + entities) | Yes | Planner detects compound; dispatcher calls `shared_handle_create_patient` then `shared_handle_add_record` → normal pending-draft flow |
| `update_record` correction | Yes (double duty) | Indirect / compat | Uses routing `structured_fields` or re-calls LLM for field extraction; narrow correction path |
| Voice consultation (ADR 0009) | Yes (via workflow) | Yes (via workflow) | `consultation_mode` is a transcription hint only |
| WeChat workflow failure | No | Yes (fallback) | Falls back to `structure_medical_record()` and replies with formatted text |

### Failure handling

| Channel | Behavior on workflow failure |
| --- | --- |
| Web | Returns HTTP error (429/503 for rate limits, 500 for unhandled) |
| WeChat | Falls back to `structure_medical_record()` on the raw text; replies with formatted text as resilience fallback |
| Voice | Returns HTTP error in JSON response |

---

## 5-Layer Intent Workflow

Defined in `services/intent_workflow/`.

| Layer | Module | Purpose |
| --- | --- | --- |
| 1. Classify | `classifier.py` | menu shortcut or `fast_route()` or routing LLM |
| 2. Extract | `entities.py` | resolve patient, age, gender, provenance |
| 3. Bind | `binder.py` | decide patient binding strength |
| 4. Plan | `planner.py` | annotate bounded compound actions |
| 5. Gate | `gate.py` | block unsafe writes and request clarification |

The workflow returns `WorkflowResult`, which can still be converted to
`IntentResult` for backward-compatible handler dispatch.

### Classification

Current order:

1. `effective_intent` if the channel already resolved one
2. deterministic `fast_route()`
3. routing LLM in `services/ai/agent.py`

`fast_route()` is intentionally narrower than the old semantic clinical router.
The intended contract is:

- keep only exact or near-exact operational commands in deterministic routing
- keep explicit workflow-state guards such as confirm / cancel / continuation
- defer free-form, semantic, mixed-clause, and specialty-specific phrasing to
  the routing LLM

Examples that should stay deterministic:

- help, list, and task-id commands
- explicit export / report commands
- exact record-query commands like `查张三病历`
- explicit appointment / follow-up commands with explicit patient + time
- explicit delete / demographic-update commands
- explicit continuation prefixes such as `补充：...`

Examples that should defer to the routing LLM:

- broad query wording like `查张三` or `查李梦妍既往胸痛记录`
- patientless follow-up wording like `明天复查`
- free-text create-patient phrasing like `新收顾清妍`
- semantic note cues like `记录一下` or `顺便记今日随诊`
- mixed-clause override logic and long-text import heuristics

The detailed fast-route boundary is documented in
[message-routing-pipeline.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/product/message-routing-pipeline.md).

### Routing LLM

Current routing behavior:

- decides intent
- extracts coarse routing entities such as patient name, age, gender, task
  fields, appointment data, emergency flag
- does not generate final note content for `add_record`

Important compatibility nuance:

- `add_record` no longer depends on router-generated clinical
  `structured_fields`
- `update_record` correction flows still use `structured_fields` compatibility
  to identify corrected fields

That closes the main ADR 0008 rollout for normal doctor-authored record
creation, while keeping a narrower correction-specific compatibility path for
`update_record`.

### Binding and Gate

The binder and gate separate "what the model thinks the message means" from
"whether the system has enough authoritative context to proceed."

Gate rules:

- `create_patient` with no name → **approved** (handler sets pending-create)
- other write intent with no patient name → blocked, ask for name
- not-found patient without location context (ICU/bed/ward) → blocked
- weak attribution (candidate/not_found with review flag) → approved with
  confirmation warning on the draft

Gate bypass: when the gate blocks with `no_patient_name`, web always returns
the clarification immediately. WeChat and voice store blocked-write context but
let `no_patient_name` fall through to handler dispatch, allowing the handler to
attempt resolution. This is the most visible behavioral difference between
channels.

This is the main safety boundary before persistence.

### Compound planning

The planner intentionally supports only bounded same-turn compounds:

- `create_patient + add_record` (clinical content detected alongside create)
- `create_patient + create_task` (reminder detected, no clinical content)
- `create_patient + add_record + create_task` (clinical + reminder)
- `add_record + create_task` (add_record with reminder keywords)

General multi-intent free-text execution is not part of the current model.

Note: post-save follow-up task creation (e.g. from 随访/复诊 keywords) is a
background side effect in `_confirm_pending.py`, not a planner compound action.
Auto-creation of not-found patients during `add_record` is handler-level logic
in `_add_record.py`, not a planner compound.

---

## Blocked-Write Continuations

Blocked-write continuation is the main new workflow-state addition from ADR
0007.

Current model:

- if `add_record` is blocked for missing patient name, the system stores
  blocked-write context in session state
- the next turn can resume deterministically on:
  - bare patient name
  - patient name plus clinical supplement
  - explicit cancel
- blocked-write state is held in-memory on `DoctorSession.blocked_write`.
  The DB schema (`DoctorSessionState.blocked_write_json`) and serializer exist,
  but the runtime setter does not schedule persistence, so blocked-write
  context does not survive process restart.

Current rollout status:

- shared precheck logic exists in `services/intent_workflow/precheck.py`
- web, WeChat, and voice chat all call that precheck
- blocked-write state is in-memory only (not crash-durable)

This workflow is now the authoritative continuation path for blocked writes.

---

## Shared Domain Layer

### Intent handlers

Main handlers live in `services/domain/intent_handlers/`.

| Module | Main responsibility |
| --- | --- |
| `_add_record.py` | add_record draft creation, emergency direct save |
| `_create_patient.py` | create or reuse patient |
| `_query_records.py` | query records using explicit name or session scope |
| `_confirm_pending.py` | pending draft confirmation side effects |
| `_simple_intents.py` | list/query/task/update/delete/export/help flows |

### Record assembly

`services/domain/record_ops.py` is the main shared record assembly layer.

Current behavior:

- `add_record` note generation flows through structuring / `assemble_record()`
- emergency records may still save immediately by explicit rule
- non-emergency records create pending drafts
- update/correction flows still retain some structured-field compatibility logic

### Channel adapters

The adapter layer exists, but runtime wiring is partial.

| Adapter method | Web | WeChat | Current reality |
| --- | --- | --- | --- |
| `parse_inbound` | used in `routers/records.py` | implemented but not main runtime entry | partial convergence |
| `format_reply` | used in web handler conversion | used in `routers/wechat_flows.py` helpers | partial convergence |
| `send_reply` | stub | stub | not production send path |
| `send_notification` | stub | delegates to WeChat customer-service send | partial convergence |
| `get_history` | no-op | session-backed | utility support only |

Current production transport paths:

- Web replies return in the HTTP response body.
- WeChat replies are sent through `_send_customer_service_msg()`, which
  selects between WeCom KF, WeCom app messaging, or WeChat OA custom-send
  depending on config.
- Voice replies return in the HTTP response body.

---

## Session and Context Model

`services/session.py` maintains per-doctor state.

### Authoritative workflow state

These fields directly affect workflow progression and write safety:

- `current_patient_id`
- `current_patient_name`
- `pending_record_id`
- `pending_create_name`
- `pending_cvd_scale`
- `interview`
- `blocked_write`
- `candidate_patient_name` (ephemeral — cleared on patient resolve)
- `candidate_patient_gender` (ephemeral)
- `candidate_patient_age` (ephemeral)
- `patient_not_found_name` (ephemeral)

### Advisory state

These fields are useful LLM context but should not silently override workflow
decisions:

- `conversation_history`
- `specialty`
- `doctor_name`
- compressed memory / knowledge snippets assembled per turn

### Turn context

`services/ai/turn_context.py` assembles `DoctorTurnContext`:

- `WorkflowState` is authoritative
- `AdvisoryContext` is advisory only

Current rollout status:

- all three channels (web, WeChat, voice) assemble `DoctorTurnContext` and
  pass it into the workflow
- advisory-context richness still varies by channel (web is most complete)

ADR 0001 is nearing complete; the remaining gap is advisory-context parity.

---

## Persistence Model

Key entities in `db/models/`:

```text
Core domain
  Doctor
    +-- Patient
    |     +-- MedicalRecordDB
    |     |     +-- MedicalRecordVersion
    |     |     +-- SpecialtyScore
    |     |     +-- NeuroCVDContext
    |     |     +-- MedicalRecordExport
    |     +-- PatientLabel
    |     +-- DoctorTask
    |     +-- PendingRecord
    |     +-- PatientMessage
    +-- DoctorContext
    +-- DoctorConversationTurn
    +-- DoctorKnowledgeItem
    +-- DoctorSessionState
    +-- DoctorNotifyPreference
    +-- ChatArchive
    +-- AuditLog

Communication
  PendingMessage

Doctor config
  InviteCode

System
  SystemPrompt +-- SystemPromptVersion

Infrastructure
  RuntimeConfig, RuntimeCursor, RuntimeToken, SchedulerLease
```

Storage is SQLite in development and MySQL/PostgreSQL in production, via
SQLAlchemy async.

Important persistence rules:

- readable note content remains authoritative
- pending drafts are persisted separately from final medical records
- session hydration supports multi-device recovery of current patient and
  pending draft (blocked-write context is in-memory only and does not survive
  restart)

---

## Infrastructure

- Framework: FastAPI
- ORM: SQLAlchemy async
- Scheduler: APScheduler
- Frontend: React + Vite
- Auth: HS256 JWT
- LLM providers: Ollama, DeepSeek, OpenAI, Tencent LKEAP, Claude, Gemini, Groq

Configuration is driven by `config/runtime.json` with the checked-in sample
template alongside it.

---

## Key ADRs

Architecture decision records live in `docs/adr/`.

| ADR | Title | Rollout |
| --- | --- | --- |
| [0001](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0001-turn-context-authority.md) | Turn Context Authority | Partial |
| [0002](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0002-draft-first-record-persistence.md) | Draft-First Record Persistence | Complete |
| [0003](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0003-record-content-source-of-truth.md) | Medical Record Content Is the Source of Truth | Complete |
| [0004](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0004-prefer-official-wecom-channel-over-automation.md) | Prefer Official WeCom Channel Over Automation | Complete |
| [0005](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0005-bound-single-turn-compound-intents.md) | Bound Single-Turn Compound Intents | Complete |
| [0006](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0006-one-patient-scope-per-turn.md) | One Patient Scope Per Turn | Partial |
| [0007](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0007-stateful-blocked-write-continuations.md) | Stateful Blocked-Write Continuations | Complete |
| [0008](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0008-minimal-routing-and-structuring-only-note-generation.md) | Minimal Routing and Structuring-Only Note Generation | Complete |
| [0009](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0009-modality-normalization-at-workflow-entry.md) | Modality Normalization at Workflow Entry | Complete |

---

## Further Reading

- [docs/product/message-routing-pipeline.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/product/message-routing-pipeline.md)
- [docs/adr/README.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/README.md)
- [docs/review/architecture-overview.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/review/architecture-overview.md)
