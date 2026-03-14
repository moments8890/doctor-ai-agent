# Architecture

**Last updated:** 2026-03-14

## Overview

Doctor AI Agent is a FastAPI backend with a React web frontend for doctor-facing
workflows: patient management, medical record dictation, task management, and
follow-up support.

The architecture is centered on the **ADR 0011 thread-centric conversation
runtime** — a single `process_turn()` function that every channel calls. The
runtime owns the full per-turn pipeline: dedup, context management, draft guard,
LLM conversation, deterministic commit engine, memory patching, and persistence.

Key invariants:

- **One entry point** — all channels call `process_turn(doctor_id, text)`.
  No channel reaches into runtime internals.
- **Single writer** — `DoctorCtx` (one row per doctor) is the authoritative
  state. The commit engine is the only code that writes durable artifacts.
- **Draft-first** — normal record creation produces a pending draft requiring
  explicit confirmation before saving to `medical_records`.
- **Deterministic commits** — the LLM proposes an `ActionRequest`; code
  validates and executes it. LLMs never write directly.
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
│  1. Dedup (in-memory LRU, 5-min TTL)                   │
│  2. Load DoctorCtx from DB                              │
│  3. Draft guard (confirm / abandon / re-prompt)         │
│  4. Conversation model (single LLM call)                │
│  5. Commit engine (validate + execute ActionRequest)    │
│  6. Apply memory patch                                  │
│  7. Persist context + archive turns                     │
│                                                         │
│  Public API:                                            │
│    process_turn()  has_pending_draft()                   │
│    clear_pending_draft_id()  TurnResult                  │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│               SERVICE LAYER                             │
│  ai/        structuring, transcription, vision, LLM     │
│  domain/    confirm_pending, chat_constants              │
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

**WeChat message flow:**
```text
POST /wechat → decrypt → parse XML
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
process_turn(doctor_id, text, *, message_id=None) -> TurnResult
has_pending_draft(doctor_id) -> bool          # lightweight read-only check
clear_pending_draft_id(doctor_id) -> None     # for REST confirm/abandon buttons
TurnResult                                    # reply + optional pending draft info
```

### Pipeline (`turn.py`)

```text
text → strip → dedup check → load DoctorCtx → draft guard
  → conversation model (LLM) → commit engine → memory patch → persist → reply
```

| Stage | Module | Purpose |
|-------|--------|---------|
| Dedup | `dedup.py` | In-memory LRU (500 entries, 5-min TTL); return cached result on duplicate `message_id` |
| Context | `context.py` | Load/save `DoctorCtx` from `doctor_context` table; read/write `chat_archive` |
| Draft guard | `draft_guard.py` | If `pending_draft_id` set: confirm → save record, abandon → discard, other → re-prompt |
| Conversation | `conversation.py` | Build system prompt + recent turns + context block; single LLM call; parse `ModelOutput` |
| Commit engine | `commit_engine.py` | Validate `ActionRequest`; execute: select_patient, create_patient, create_draft, create_patient_and_draft |
| Memory patch | `turn.py` | Apply LLM-suggested memory updates to `DoctorCtx.memory` |
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

ActionRequest
  ├── type: "none"|"clarify"|"select_patient"|"create_patient"
  │         |"create_draft"|"create_patient_and_draft"
  ├── patient_name, patient_gender, patient_age
  └── (type-specific fields)

TurnResult
  ├── reply: str
  ├── pending_id: Optional[str]
  ├── pending_patient_name: Optional[str]
  └── pending_expires_at: Optional[str]  # ISO-8601 UTC
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
| `chat_constants.py` | Shared regex patterns, MIME types |

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
| 0011 | Thread-centric conversation runtime and deterministic commits | **Active** — the current architecture |
| 0002 | Draft-first record persistence | Complete |
| 0003 | Medical record content is the source of truth | Complete |
| 0004 | Prefer official WeCom channel over automation | Complete |
| 0009 | Modality normalization at workflow entry | Complete |
| 0001-0008 | Pre-ADR-0011 decisions | Superseded by ADR 0011 where they conflict |

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
- [ADR index](docs/adr/README.md)
