# Architecture

**Last updated:** 2026-03-14

## Overview

Doctor AI Agent is a FastAPI backend with a React web frontend for doctor-facing
workflows: patient management, medical record dictation, task management, and
follow-up support.

The architecture is centered on a **thread-centric conversation runtime**
(ADR 0011) extended by a **three-phase Understand → Execute → Compose
pipeline** (ADR 0012). Every channel calls `process_turn()`, which runs
pre-pipeline guards, then the UEC pipeline for all turn types.

Key invariants:

- **One entry point** — all channels call `process_turn(doctor_id, text)`.
  No channel reaches into runtime internals.
- **Understand never authors operational replies** — for operational turns
  (reads, writes, patient selection), the LLM emits structured intent only.
  Compose generates the reply from execution results.
- **Execute splits reads from writes** — `read_engine` (SELECT only, no state
  mutation) and `commit_engine` (durable writes, pending state) are separate
  modules with a hard import boundary.
- **Draft-first** — record creation produces a pending draft requiring
  explicit confirmation. `schedule_task` commits immediately (appointments
  are low-stakes and cancellable).
- **Deterministic commits** — the LLM proposes an `UnderstandResult`; resolve
  validates bindings; the commit engine executes. LLMs never write directly.
- **Services are RPC, channels choose transport** — the service layer exposes
  plain async functions (RPC-style). Channels choose the transport protocol
  (REST, webhook, XML reply) appropriate for their consumer.

---

## Layer Diagram

```text
┌─────────────────────────────────────────────────────────┐
│                    CHANNEL LAYER                        │
│  Web (chat.py)  │  WeChat (router.py)  │  Voice (.py)  │
│  normalize input → call process_turn()                  │
└──────────────────────────┬──────────────────────────────┘
                           │
                  process_turn(doctor_id, text)
                           │
┌──────────────────────────▼──────────────────────────────┐
│                 RUNTIME (services/runtime/)              │
│                                                         │
│  1. Load DoctorCtx from DB                              │
│  2. Deterministic handler (button clicks, 确认/取消)     │
│  3. UNDERSTAND — LLM → UnderstandResult (structured)    │
│  4. EXECUTE                                             │
│     ├── Resolve (patient lookup, binding, dates)        │
│     ├── Read engine (SELECT only, no writes)            │
│     └── Commit engine (durable writes, pending state)   │
│  5. COMPOSE — template or LLM from execution results    │
│  6. Persist context + archive turns                     │
│                                                         │
│  Public API:                                            │
│    process_turn()  has_pending_draft()                   │
│    clear_pending_draft_id()  TurnResult                  │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│               SERVICE LAYER                             │
│  ai/        structuring, transcription, vision, LLM     │
│  domain/    confirm_pending                              │
│  patient/   risk scoring, search, timeline               │
│  knowledge/ PDF/Word extraction, doctor knowledge        │
│  notify/    task scheduling, notifications               │
│  export/    PDF generation                               │
│  auth/      JWT, rate limiting                           │
│  observability/  audit, metrics, tracing                 │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    DATA LAYER (db/)                      │
│  models/     SQLAlchemy ORM (Doctor, Patient, Record…)  │
│  crud/       Async CRUD functions                        │
│  repositories/  Higher-level query wrappers              │
│  engine.py   AsyncEngine + session factory               │
└─────────────────────────────────────────────────────────┘
```

---

## Channel Layer

All channels normalize input and delegate to `process_turn()`. No channel
imports runtime internals.

### Web (`src/channels/web/`)

| File | Route | Role |
|------|-------|------|
| `chat.py` | `POST /api/records/chat` | Main chat; greeting/help fast paths, then `process_turn()` |
| `chat.py` | `POST /api/records/pending/{id}/confirm` | REST confirm draft (button click) |
| `chat.py` | `POST /api/records/pending/{id}/abandon` | REST abandon draft (button click) |
| `chat.py` | `POST /api/records/from-{text,image,audio}` | Media import (OCR/transcribe then import) |
| `auth.py` | `/api/auth/*` | JWT login, invite codes |
| `tasks.py` | `/api/tasks/*` | Task CRUD |
| `voice.py` | — | See Voice channel below |
| `export.py` | `/api/export/*` | PDF/report export |
| `neuro.py` | `/api/neuro/*` | Specialty CVD/neuro endpoints |
| `patient_portal.py` | `/api/patient_portal/*` | Patient self-service (read-only) |
| `ui/` | `/ui/*` | Admin dashboard, debug, invites |

### WeChat (`src/channels/wechat/`)

| File | Role |
|------|------|
| `router.py` | WeChat/WeCom webhook; text → `process_turn()`; voice → transcribe → `process_turn()`; draft confirm/abandon → `process_turn()` synchronously; image/PDF/Word → extraction pipelines |
| `flows.py` | Menu events, notify control, media background handlers |
| `infra.py` | Signature verification, token refresh, KF cursor persistence |
| `patient_pipeline.py` | Patient (non-doctor) message handling |
| `wechat_notify.py` | Customer service API (message delivery) |
| `wechat_voice.py` | Voice download and conversion |
| `wechat_media_pipeline.py` | Image/PDF/document extraction pipeline |
| `wechat_domain.py` | Formatting, XML parsing, menu event logic |
| `wecom_kf_sync.py` | WeCom KF message sync |

**WeChat message flow** (dedup by `MsgId` before entering pipeline):
```text
POST /wechat → decrypt → parse XML → dedup (MsgId LRU cache)
  ├── KF event → background sync
  ├── non-doctor → patient_pipeline
  ├── voice → transcribe → process_turn() (background, via CS API)
  ├── image/PDF/Word → extraction → process_turn() (background)
  ├── text + draft pending + confirm/abandon → process_turn() (synchronous XML reply)
  └── text (normal) → process_turn() (background, via CS API)
```

### Voice (`src/channels/voice.py`)

| Route | Role |
|-------|------|
| `POST /api/voice/chat` | Transcribe audio → `process_turn()` |
| `POST /api/voice/consultation` | Same, with `consultation_mode=True` transcription hint |

---

## Runtime Layer (`src/services/runtime/`)

The runtime is the sole orchestrator for doctor turns. All internal modules are
implementation details — channels import only from the package root.

### Public API (`__init__.py`)

```python
process_turn(doctor_id, text) -> TurnResult
has_pending_draft(doctor_id) -> bool          # lightweight read-only check
clear_pending_draft_id(doctor_id) -> None     # for REST confirm/abandon buttons
TurnResult                                    # reply + optional pending draft info
```

### Pipeline (`turn.py`)

```text
text → strip → load DoctorCtx → deterministic handler
  → Understand (LLM) → Execute (resolve → read/commit engine) → Compose → persist → reply
```

Dedup is a channel-layer concern, not a runtime concern. Channels that use
retrying transports (e.g., WeChat webhooks) filter duplicates before calling
`process_turn()`. The runtime trusts that each call represents a unique turn.

| Stage | Module | Purpose |
|-------|--------|---------|
| Context | `context.py` | Load/save `DoctorCtx` from `doctor_context` table; read/write `chat_archive` |
| Deterministic handler | `turn.py` | Typed UI actions (button clicks) and 确认/取消 regex during pending draft → deterministic response, no LLM. All blocking logic is in execute.resolve. |
| Understand | `understand.py` | LLM → `UnderstandResult` (structured intent, no prose for operational turns) |
| Resolve | `resolve.py` | Patient DB lookup, binding, date normalization; shared by read and write paths |
| Read engine | `read_engine.py` | SELECT only, no writes; returns `ReadResult` with data + truncation info |
| Commit engine | `commit_engine.py` | Durable writes: select_patient, create_patient, create_draft, schedule_task; returns `CommitResult` |
| Compose | `compose.py` | Template or LLM reply from execution results; never from understand's output |
| Persist | `turn.py` | Best-effort save context + archive turns (never raises) |

### Data model

```python
DoctorCtx
  ├── doctor_id: str
  ├── workflow: WorkflowState        # authoritative (code-owned)
  │     ├── patient_id: Optional[int]
  │     ├── patient_name: Optional[str]
  │     └── pending_draft_id: Optional[str]
  └── memory: MemoryState            # provisional (LLM-facing)
        ├── candidate_patient: Optional[dict]
        ├── working_note: Optional[str]
        └── summary: Optional[str]

ActionType (enum):  query_records | list_patients | schedule_task
                    | select_patient | create_patient | create_draft | none

UnderstandResult
  ├── action_type: ActionType
  ├── args: dict (typed per action_type)
  ├── chat_reply: Optional[str]     # only when action_type == none
  └── clarification: Optional[Clarification]

TurnResult
  ├── reply: str
  ├── pending_id: Optional[str]
  ├── pending_patient_name: Optional[str]
  ├── pending_expires_at: Optional[str]  # ISO-8601 UTC
  └── view_payload: Optional[dict]  # structured data for web rendering
```

---

## Service Layer

### AI Services (`src/services/ai/`)

| File | Role |
|------|------|
| `llm_client.py` | Lazy-load OpenAI-compatible client; multi-provider (Ollama, DeepSeek, Groq, etc.) |
| `llm_resilience.py` | Retry with exponential backoff and provider fallback |
| `structuring.py` | Transform raw clinical text into structured medical record |
| `neuro_structuring.py` | Specialty CVD/neuro field extraction (background) |
| `transcription.py` | Audio → text (Ollama/Groq/API, Chinese-optimized) |
| `vision.py` | Image → text (OCR, table, handwriting) |
| `intent.py` | Legacy intent enum (minimal, kept for backward compat) |
| `egress_policy.py` | Compliance guard for outbound LLM calls |

### Domain (`src/services/domain/`)

| File | Role |
|------|------|
| `intent_handlers/_confirm_pending.py` | Save confirmed draft to `medical_records`; trigger background CVD extraction |

### Other Services

| Directory | Role |
|-----------|------|
| `auth/` | JWT, rate limiting, access codes, WeChat ID hashing |
| `patient/` | Risk scoring, NL search, timeline, encounter detection |
| `knowledge/` | PDF/Word extraction, doctor knowledge base |
| `notify/` | Task scheduling (APScheduler), notification delivery |
| `export/` | PDF generation, outpatient reports |
| `observability/` | Audit trail, routing metrics, trace context |

### Legacy: `session.py`

`services/session.py` maintains a parallel in-memory session model
(`DoctorSession`) that predates the ADR 0011 runtime. It is still used by:

- WeChat background intent processing (`hydrate_session_state`, `get_session_lock`)
- Some WeChat-specific flows (blocked writes, pending creates)

This is **architectural debt** scheduled for cleanup as part of the Shared
Workflow Unification plan. New code should not use `session.py`.

---

## Data Layer (`src/db/`)

### Key Models

```text
Doctor
  +-- Patient
  |     +-- MedicalRecordDB (+MedicalRecordVersion, +MedicalRecordExport)
  |     +-- PatientLabel
  |     +-- DoctorTask
  |     +-- PendingRecord
  |     +-- PatientMessage
  |     +-- SpecialtyScore, NeuroCVDContext
  +-- DoctorContext          # ADR 0011 runtime state (workflow + memory JSON)
  +-- ChatArchive            # conversation turn history
  +-- DoctorSessionState     # legacy session persistence
  +-- DoctorNotifyPreference
  +-- DoctorKnowledgeItem
  +-- AuditLog

PendingMessage               # WeChat retry queue
InviteCode                   # doctor registration
SystemPrompt (+Version)      # versioned system prompts
RuntimeConfig, RuntimeCursor, RuntimeToken, SchedulerLease
```

### CRUD (`db/crud/`)

Async functions taking `AsyncSession`. Key modules: `doctor.py` (patient search,
turn archiving), `patient.py` (CRUD), `records.py` (save + versioning),
`pending.py` (draft lifecycle), `tasks.py` (task CRUD), `retention.py`
(compliance cleanup).

### Repositories (`db/repositories/`)

Higher-level query wrappers: `patients.py`, `records.py`, `tasks.py`.

### Storage

SQLite in development, MySQL/PostgreSQL in production. Async via SQLAlchemy.
No Alembic migrations until first production launch; `create_tables()` handles
DDL.

---

## Configuration

**Primary:** `config/runtime.json` (gitignored; sample in `config/runtime.json.sample`)

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | DB connection | `sqlite+aiosqlite:///data/patients.db` |
| `ENVIRONMENT` | `development`/`production` | (required in prod) |
| `ROUTING_LLM` | LLM for routing + structuring | `qwen2.5:14b` (Ollama) |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://192.168.0.123:11434` (LAN) |
| `WECHAT_TOKEN`, `WECHAT_APP_ID` | WeChat credentials | (required for WeChat) |
| `DEEPSEEK_API_KEY` | DeepSeek provider | (optional) |

---

## I18N (`src/i18n/messages.py`)

600+ message strings (Chinese default, English with `RUNTIME_LANG=en`). Contains
regex patterns (`confirm_re`, `abandon_re`, `greeting_re`, `help_re`) and the
system prompt for the conversation model.

---

## Application Entry (`src/main.py`)

- Registers 9 routers (records, wechat, auth, ui, neuro, tasks, voice, export, patient_portal)
- Middleware: request size limit (50 MB), trace ID propagation, CORS
- Health endpoints: `/healthz`, `/readyz`
- Lifespan: create tables → seed prompts → hydrate LLMs → start scheduler + background workers
- APScheduler: task notifications, conversation cleanup, session pruning, audit retention, CVD extraction

---

## Infrastructure

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| ORM | SQLAlchemy async |
| Scheduler | APScheduler |
| Frontend | React + Vite |
| Auth | HS256 JWT |
| LLM providers | Ollama, DeepSeek, OpenAI, Tencent LKEAP, Claude, Gemini, Groq |

---

## Key ADRs

| ADR | Title | Status |
|-----|-------|--------|
| 0011 | Thread-centric conversation runtime and deterministic commits | **Active** — foundation |
| 0012 | Understand / Execute / Compose pipeline for operational actions | **Accepted** — not yet implemented |

---

## Known Debt

1. **`services/session.py`** — legacy parallel session model. Still used by
   WeChat background processing (locks, hydration). Scheduled for removal in
   Shared Workflow Unification.

2. **WeChat fast paths** — task completion (`完成 N`), knowledge add, and notify
   control are handled in `_handle_intent()` before `process_turn()`. These
   could be folded into the runtime as custom action types.

3. **Web fast paths** — greeting and help regex in `chat.py` short-circuit
   before `process_turn()`. Consistent with WeChat but could be runtime-level.

---

## Further Reading

- [ADR 0011 — Architecture and Workflows](docs/adr/0011-architecture-and-workflows.md)
- [ADR 0012 — UEC Pipeline](docs/adr/0012-understand-execute-compose-pipeline.md)
  ([Architecture Diagram](docs/adr/0012-architecture-diagram.md))
- [ADR index](docs/adr/README.md)
