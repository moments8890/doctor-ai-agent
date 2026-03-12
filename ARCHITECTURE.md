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
- one patient-scoped transaction per turn

The important nuance is that convergence is still partial. Web, WeChat, and
voice chat all use the same workflow core, but they are not yet identical in
how they assemble turn context, apply deterministic prechecks, and use channel
adapters.

---

## What Is Shipped Now

### Stable architectural decisions

- `medical_records.content` remains the source of truth for doctor-facing notes.
- Normal `add_record` flows are draft-first and require explicit confirmation.
- The system keeps one core patient-scoped transaction per turn.
- Official WeCom integration is the supported messaging channel model.
- The workflow uses a shared classify -> extract -> bind -> plan -> gate stack.

### Still in transition

- `DoctorTurnContext` is implemented, but not passed through every channel in
  the same way yet.
- Blocked-write continuation state is implemented and persisted, but older
  `followup_name` continuation logic still coexists.
- `add_record` now uses structuring as the note-generation path, but
  `structured_fields` compatibility still exists in routing and update/correction
  flows.
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
  records_media.py      Media upload for records
  ui/                   Admin + workbench endpoints

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
    turn_context.py     DoctorTurnContext assembly
    memory.py           Context compression
    structuring.py      Structuring LLM for readable notes
    transcription.py    Voice transcription
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
tests/                 Unit tests
e2e/                   Integration and replay tests
scripts/               Dev and CI scripts
docs/                  ADRs, plans, reviews, product docs
```

---

## Doctor Message Flow

There is one shared workflow core, but the entry path varies by channel.

### Web chat

`POST /api/records/chat`

```text
request body
-> WebAdapter.parse_inbound()
-> web fast paths and workflow-state prechecks
-> blocked-write precheck
-> assemble DoctorTurnContext
-> load knowledge context
-> services.intent_workflow.run(turn_context=...)
-> shared domain handler dispatch
-> WebAdapter.format_reply()
-> JSON response
```

### WeChat / WeCom doctor chat

Main doctor message handling in `routers/wechat.py`

```text
webhook message
-> session-aware router orchestration
-> notify / task / knowledge fast paths
-> blocked-write precheck
-> load knowledge context
-> services.intent_workflow.run(...)
-> shared domain handler dispatch
-> WeChat helper formatting / customer-service send path
```

WeChat also uses `DoctorTurnContext` around some session-orchestration paths,
but the assembled context is not yet passed through the workflow in the same
way as the web path.

### Voice chat

`POST /api/voice/chat`

```text
audio upload
-> transcribe_audio()
-> blocked-write precheck
-> services.intent_workflow.run(...)
-> shared domain handler dispatch
-> JSON response
```

Voice chat shares the same draft-first semantics as web and WeChat for normal
record creation.

### Voice consultation exception

`POST /api/voice/consultation` is a separate explicit recording flow:

```text
audio upload
-> transcribe_audio(consultation_mode=True)
-> structure_medical_record(consultation_mode=True)
-> optional direct save when save=true
```

This endpoint is intentionally outside the main intent workflow and is the main
remaining direct-save exception on the voice side.

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

| Workflow | Routing LLM | Structuring LLM | Deterministic control / notes |
| --- | --- | --- | --- |
| Read/query/task workflows | Usually yes when `fast_route()` does not match | No | Query/task handlers execute directly after bind/gate; no note generation |
| Standard `add_record` | Yes for intent + coarse entities | Yes via `assemble_record()` | Gate may block for missing patient; non-emergency path creates pending draft; emergency can direct-save |
| Blocked-write continuation | No on successful precheck resume | Yes after resume | `precheck_blocked_write()` resolves bare-name / name+supplement continuations from session state |
| `create_patient` only | Yes for intent + name/demographics unless deterministic match hits first | No | Patient create/reuse is normal handler logic |
| `create_patient + clinical content` compound | Yes for create intent + coarse entities | Yes | Current handler still structures and directly saves the compound record; this is not yet unified with the draft-first `add_record` path |
| `update_record` correction | Yes | Indirect / compatibility path | Correction still uses routing `structured_fields` compatibility and may re-call routing LLM for field extraction; this is one of the remaining ADR 0008 transition areas |
| Voice consultation (`/api/voice/consultation`) | No | Yes | Explicit structuring-only recording flow; optional direct save when `save=true` |
| WeChat workflow failure fallback | No after workflow failure | Yes | If workflow execution fails, WeChat may still call `structure_medical_record()` and reply with formatted text as a resilience fallback |

### 1. Standard doctor command workflows

Examples:

- `查一下张三最近病历`
- `列出今天的任务`
- `把 12 号任务推迟一周`

Flow:

```text
message
-> fast_route() or routing LLM
-> extract / bind / gate
-> shared handler
-> direct reply
```

LLM role:

- routing LLM is used when deterministic routing does not confidently match
- structuring LLM is not used because no doctor-facing note body is being built

### 2. Standard add-record workflow

Examples:

- `张三胸痛两天，血压150/90`
- `给李四补一条今天复诊记录`

Flow:

```text
message
-> blocked-write precheck (if applicable)
-> fast_route() or routing LLM
-> extract / bind / plan / gate
-> handle_add_record()
-> assemble_record()
-> structure_medical_record()
-> pending draft or emergency direct save
```

LLM role:

- routing LLM decides `add_record` and extracts coarse fields such as patient
  name and emergency signal
- structuring LLM produces the readable medical note body

Deterministic role:

- gate decides whether patient context is sufficient
- session state decides whether the turn is a continuation
- pending-draft confirmation decides whether the note becomes final

### 3. Blocked-write continuation workflow

Example:

1. `胸痛两天，血压150/90`
2. system asks for patient name
3. `张三`

Flow:

```text
turn 1
-> routing + gate
-> blocked on missing patient name
-> store blocked_write context

turn 2
-> precheck_blocked_write()
-> resume add_record deterministically
-> structuring LLM
-> pending draft
```

LLM role:

- first turn may use routing LLM
- second-turn resume does not need the routing LLM if precheck resolves the
  continuation
- structuring still runs on the clinical text when the write resumes

This is the clearest example of the architecture rule:

- LLM decides **what the doctor means**
- deterministic session state decides **whether this turn is a continuation**

### 4. Compound create-patient workflows

Example:

- `新患者王芳，女，52岁，胸闷一周，明天提醒复诊`

Flow today:

```text
message
-> fast_route() or routing LLM
-> create_patient handler
-> create/reuse patient
-> optional structure_medical_record() for residual clinical content
-> optional task creation
```

LLM role:

- routing LLM resolves the create intent plus demographics
- structuring LLM is used only if the same message also contains clinical
  content that should become a record

Important current-state nuance:

- this compound path still saves the structured record directly inside the
  create-patient handler
- it is not yet fully converged with the pending-draft `add_record` path

### 5. Update-record correction workflow

Example:

- `把张三最近一条病历里的诊断改成不稳定型心绞痛`

Flow today:

```text
message
-> fast_route() or routing LLM
-> handle_update_record()
-> use routing structured_fields if present
-> otherwise re-call routing LLM for correction extraction
-> update latest persisted record
```

LLM role:

- routing LLM is doing double duty here:
  - intent selection
  - correction-field extraction

This is one of the main remaining exceptions to the cleaner ADR 0008 target,
because correction still relies on router-side `structured_fields`
compatibility.

### 6. Voice consultation workflow

Example:

- uploaded ambient consultation recording

Flow:

```text
audio
-> transcribe_audio(consultation_mode=True)
-> structure_medical_record(consultation_mode=True)
-> optional direct save
```

LLM role:

- no routing LLM
- structuring LLM only

This is not a conversational workflow. It is an explicit recording-processing
workflow.

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

`fast_route()` is still broader than the target ADR 0008 end state. It handles
exact operational commands, task operations, queries, some patient CRUD, and a
small number of explicit write/supplement patterns.

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

That means ADR 0008 is directionally implemented, but not fully complete yet.

### Binding and Gate

The binder and gate separate "what the model thinks the message means" from
"whether the system has enough authoritative context to proceed."

Examples:

- write intent with no patient name -> ask for patient name
- not-found patient without stronger location context -> block
- weak attribution -> allow draft generation with confirmation messaging

This is the main safety boundary before persistence.

### Compound planning

The planner intentionally supports only bounded same-turn compounds, such as:

- `create_patient + add_record`
- `create_patient + add_record + create_task`
- `add_record + create_task`

General multi-intent free-text execution is not part of the current model.

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
- blocked-write state is persisted via `DoctorSessionState.blocked_write_json`

Current rollout status:

- shared precheck logic exists in `services/intent_workflow/precheck.py`
- web, WeChat, and voice chat all call that precheck
- legacy `followup_name` behavior still exists in parallel in some paths

So the architecture is already stateful here, but not fully cleaned up yet.

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
- WeChat replies are ultimately sent through the WeCom customer-service API
  helpers.
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

- web passes assembled `DoctorTurnContext` into the workflow
- WeChat assembles turn context for some stateful orchestration, but does not
  yet pass it through the workflow in the same way
- voice chat currently hydrates session state and uses shared workflow, but does
  not yet use the same turn-context path as web

This is why ADR 0001 is still marked partial rather than complete.

---

## Persistence Model

Key entities in `db/models/`:

```text
Doctor
  +-- Patient
  |     +-- MedicalRecordDB
  |     |     +-- MedicalRecordVersion
  |     |     +-- SpecialtyScore
  |     |     +-- NeuroCVDContext
  |     +-- PatientLabel
  |     +-- DoctorTask
  |     +-- PendingRecord
  +-- DoctorContext
  +-- DoctorConversationTurn
  +-- DoctorKnowledgeItem
  +-- DoctorSessionState
  +-- AuditLog
```

Storage is SQLite in development and MySQL/PostgreSQL in production, via
SQLAlchemy async.

Important persistence rules:

- readable note content remains authoritative
- pending drafts are persisted separately from final medical records
- session hydration supports multi-device recovery of current patient, pending
  draft, and blocked-write context

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
| [0007](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0007-stateful-blocked-write-continuations.md) | Stateful Blocked-Write Continuations | Partial |
| [0008](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/0008-minimal-routing-and-structuring-only-note-generation.md) | Minimal Routing and Structuring-Only Note Generation | Partial |

---

## Further Reading

- [docs/product/message-routing-pipeline.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/product/message-routing-pipeline.md)
- [docs/adr/README.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/adr/README.md)
- [docs/review/architecture-overview.md](/Volumes/ORICO/Code/doctor-ai-agent/docs/review/architecture-overview.md)
