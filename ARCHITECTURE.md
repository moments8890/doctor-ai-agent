# Architecture

**Last updated:** 2026-03-12

## Overview

Doctor AI Agent is a FastAPI backend + React SPA that helps doctors manage
patients, medical records, tasks, and appointments through natural-language
conversation. Doctors interact via three channels -- web dashboard, WeChat/WeCom,
and voice -- all of which share the same 5-layer intent workflow pipeline and
dispatch to unified domain handlers.

---

## Directory Structure

```
routers/              Channel entry points (FastAPI routers)
  records.py            Web chat + record CRUD
  wechat.py             WeChat/WeCom webhook
  voice.py              Voice transcription + chat
  miniprogram.py        WeChat Mini Program
  patient_portal.py     Patient self-service portal
  auth.py               Doctor login, invite codes
  tasks.py              Task management
  export.py             PDF / report export
  neuro.py              Neurology/CVD specialist endpoints
  wechat_flows.py       WeChat multi-turn flow helpers
  wechat_infra.py       WeChat platform infrastructure
  records_media.py      Media upload for records
  ui/                   Admin + debug UI endpoints

services/
  intent_workflow/      5-layer intent pipeline (shared by all channels)
  domain/
    intent_handlers/    Shared intent handlers (add_record, create_patient, ...)
    adapters/           Channel adapter protocol + WebAdapter, WeChatAdapter
    message.py          Message dataclass + ChannelAdapter protocol
    record_ops.py       Record assembly, clinical context building
    patient_ops.py      Patient resolution helpers
    chat_handlers.py    Legacy chat handler dispatch (being migrated)
    chat_constants.py   Shared reply templates
    compound_normalizer.py  Compound-intent normalization
    name_utils.py       Chinese name extraction utilities
    text_cleanup.py     Text normalization
  ai/
    fast_router/        Multi-tier deterministic intent router (Tiers 0-2)
    agent.py            LLM dispatch (classification fallback)
    agent_fallback.py   Fallback chain for LLM failures
    turn_context.py     DoctorTurnContext assembly (authoritative/advisory model)
    memory.py           Context compression (structured JSON summaries)
  hooks.py              Lightweight hook mechanism for pipeline events
  hooks_builtin.py      Built-in observability hooks
  session.py            In-memory session, per-doctor locks, hydration
  auth/                 JWT, PBKDF2, rate limiting
  knowledge/            Doctor knowledge base, PDF/Word/image import, OCR
  wechat/               WeChat domain logic, media pipeline, notifications
  patient/              NL search, risk scoring, CVD scale interview
  export/               PDF export, outpatient reports
  notify/               Task scheduling, APScheduler jobs
  observability/        Audit log, routing metrics, per-layer latency spans

db/
  models/               SQLAlchemy model definitions
  crud/                 CRUD operations
  repositories/         Repository pattern wrappers
  engine.py             Async engine + session factory
  init_db.py            Table creation

config/
  runtime.json.sample   Reference configuration template
  runtime.json          Live config (gitignored)

frontend/              React SPA (Vite)
tests/                 Unit tests (all I/O mocked)
e2e/                   Integration + chatlog replay tests
scripts/               Dev/CI scripts
docs/                  Detailed docs, ADRs, plans, reviews
```

---

## Request Flow

All three doctor-facing channels converge on the same pipeline:

```
Doctor message
    |
    v
Channel entry point
  Web:    routers/records.py  -> _chat_for_doctor()
  WeChat: routers/wechat.py   -> _handle_intent()
  Voice:  routers/voice.py    -> _voice_chat_for_doctor() (after transcription)
    |
    v
Channel prechecks (deterministic fast paths)
  - rate limit, greeting, menu shortcut, notify control
  - knowledge-base command interception
  - task completion, pending-draft confirmation
    |
    v
Load doctor knowledge context
  services/knowledge/knowledge_cache.py (per-doctor, 5-min TTL)
    |
    v
services.intent_workflow.run()        <-- shared 5-layer pipeline
    |
    v
WorkflowResult -> IntentResult (backward-compatible)
    |
    v
Shared handler dispatch
  services/domain/intent_handlers/
    |
    v
Channel-specific response formatting
  WebAdapter.format_reply() / WeChatAdapter.format_reply()
```

Web returns the response synchronously in the HTTP body. WeChat sends via
customer-service message API in a background task. Voice `/chat` follows the
same pattern as Web.

**Voice `/consultation` exception:** The `POST /api/voice/consultation` endpoint
is a separate ambient-recording flow that transcribes audio and structures it
into a medical record without using the intent pipeline. It does not create
pending drafts -- if `save=True`, the record is persisted directly. This is
intentional: consultations are complete recordings, not interactive commands.

---

## 5-Layer Intent Pipeline

Defined in `services/intent_workflow/`. Every doctor message passes through
these layers in order:

| Layer | Module | Purpose |
|-------|--------|---------|
| 1. Classify | `classifier.py` | `fast_route()` (deterministic Tiers 0-2) then LLM fallback |
| 2. Extract | `entities.py` | Resolve patient/gender/age with provenance tracking |
| 3. Bind | `binder.py` | Read-only patient binding: bound, has_name, no_name, not_applicable |
| 4. Plan | `planner.py` | Annotate compound actions (create+record, create+task) |
| 5. Gate | `gate.py` | Block unsafe writes without patient context |

**Classification tiers** (in `services/ai/fast_router/`):
- Tier 0: import markers (`[PDF:]`, `[Word:]`, `[Image:]`, help)
- Tier 1: exact keyword sets (list patients, list tasks)
- Tier 2: regex + extraction (create/delete/query/schedule/export/add_record/...)
- LLM fallback: `agent_dispatch()` via configured ROUTING_LLM provider

**Entity provenance sources** (strongest to weakest):
followup, fast_route, llm, text_leading_name, history, session, candidate, not_found

**Hook stages**: POST_CLASSIFY, POST_EXTRACT, POST_BIND, POST_PLAN, POST_GATE,
PRE_REPLY. Registered via `services/hooks.py`; non-blocking, exceptions logged
but never propagated.

For full details see `docs/product/message-routing-pipeline.md`.

---

## Shared Domain Layer

### Intent Handlers (`services/domain/intent_handlers/`)

All channels dispatch to the same handlers:

| Module | Intents |
|--------|---------|
| `_add_record.py` | add_record, update_record |
| `_create_patient.py` | create_patient |
| `_query_records.py` | query_records |
| `_confirm_pending.py` | Pending-draft confirm/cancel |
| `_simple_intents.py` | list_patients, list_tasks, complete_task, delete_patient, schedule_appointment, update_patient, export_records, help |

### Channel Adapters (`services/domain/adapters/`)

The `ChannelAdapter` protocol (`services/domain/message.py`) defines
`parse_inbound`, `format_reply`, `send_reply`, `send_notification`, `get_history`.

| Method | WebAdapter | WeChatAdapter | Status |
|--------|-----------|---------------|--------|
| `parse_inbound` | Production | Production | Wired in routers |
| `format_reply` | Production | Production | Wired in routers |
| `send_reply` | Stub | Stub | Deferred (see below) |
| `send_notification` | Stub | Stub | Deferred |
| `get_history` | No-op | Reads from session | Production |

**Current send paths** (until full adapter integration):
- Web: replies are returned in the HTTP response body (no async push channel).
- WeChat: direct calls to `services/wechat/wechat_notify._send_customer_service_msg()`.
  The `WeChatAdapter.send_notification()` delegates to this function; `send_reply()`
  remains a stub. See ADR 0004 for channel choice rationale.
- Voice: replies are returned in the HTTP response body (same as Web).

### Record Operations (`services/domain/record_ops.py`)

- `assemble_record()` -- builds structured medical record from text + history
- `build_clinical_context()` -- filters conversation history to clinical-only turns
- Emergency records save immediately; all others create a pending draft requiring
  doctor confirmation before persisting

---

## Data Model

Key entities in `db/models/`:

```
Doctor
  +-- Patient (doctor_id FK)
  |     +-- MedicalRecordDB
  |     |     +-- MedicalRecordVersion (audit history)
  |     |     +-- SpecialtyScore (scale scores)
  |     |     +-- NeuroCVDContext (CVD/neuro structured fields)
  |     +-- PatientLabel (M2M)
  |     +-- DoctorTask
  |     +-- PendingRecord (draft, TTL-expired after 30 min)
  +-- DoctorContext (LLM-compressed memory)
  +-- DoctorConversationTurn (rolling 10-turn window)
  +-- DoctorKnowledgeItem (custom knowledge base)
  +-- DoctorSessionState (hydration source)
  +-- AuditLog (7-year retention)
```

Storage: SQLite (dev) / MySQL or PostgreSQL (prod), via SQLAlchemy async.
Table creation handled by `db/init_db.py::create_tables()`.

---

## Configuration

- **`config/runtime.json`** is the sole local configuration file (gitignored)
- **`config/runtime.json.sample`** is the checked-in reference template
- No `.env` files for the main application; scripts under `scripts/` may use
  `python-dotenv` standalone
- Config is reloaded at runtime without restart
- LLM providers: Ollama, DeepSeek, OpenAI, Tencent LKEAP, Claude, Gemini, Groq
- Default local model: `qwen2.5:14b` via Ollama (LAN server preferred over local)

---

## Session and State

`services/session.py` maintains per-doctor in-memory sessions:

- **Authoritative state** (never evicted by TTL, controls write-path decisions):
  `current_patient_id/name`, `pending_record_id`, `pending_create_name`,
  `pending_cvd_scale`, `interview`
- **Advisory state** (background hints for LLM, does not influence binding):
  `conversation_history` (rolling 10-turn window), `specialty`, `doctor_name`
- Per-doctor `asyncio.Lock` acquired before any state read/write
- `hydrate_session_state()` loads from DB with 5-min TTL
- Context compression (`services/ai/memory.py`) triggers at 20 messages,
  1200-token budget, or 30-min idle

See ADR 0001 for the authoritative/advisory separation rationale.

---

## Infrastructure

- **Framework**: FastAPI (async)
- **ORM**: SQLAlchemy async
- **Scheduler**: APScheduler -- task delivery, pending-record expiry (5 min),
  conversation cleanup, audit retention, data redaction
- **Frontend**: React SPA (Vite), Zustand for auth state, HS256 JWT

---

## Key ADRs

Architecture decision records live in `docs/adr/`. Add a new ADR when a decision
changes safety-critical state interpretation, AI routing rules, or persistence
behavior.

| ADR | Title |
|-----|-------|
| [0001](docs/adr/0001-turn-context-authority.md) | Turn Context Authority (authoritative vs. advisory state) |
| [0002](docs/adr/0002-draft-first-record-persistence.md) | Draft-First Record Persistence |
| [0003](docs/adr/0003-record-content-source-of-truth.md) | Medical Record Content Is the Source of Truth |
| [0004](docs/adr/0004-prefer-official-wecom-channel-over-automation.md) | Prefer Official WeCom Channel Over Automation |
| [0005](docs/adr/0005-bound-single-turn-compound-intents.md) | Bound Single-Turn Compound Intents |
| [0006](docs/adr/0006-one-patient-scope-per-turn.md) | One Patient Scope Per Turn |

---

## Further Reading

- `docs/review/architecture-overview.md` -- Comprehensive architecture details
  including hook stages, context compression schema, and frontend structure
- `docs/product/message-routing-pipeline.md` -- Full message routing pipeline
  with per-layer deep dives
- `docs/adr/README.md` -- ADR conventions and index
- `CLAUDE.md` -- Development conventions and workflow rules
