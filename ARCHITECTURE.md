# Architecture

**Last updated:** 2026-03-24

## Overview

Doctor AI Agent is a medical AI assistant built on a **Plan-and-Act** pattern.
It serves both doctors (patient management, medical record dictation, task
scheduling) and patients (pre-consultation interview). A lightweight routing
LLM classifies each message into one of 6 intents and extracts entities;
deterministic dispatcher code then routes to a dedicated intent handler. Each
handler has focused prompts and scoped context, rather than one LLM with
access to all tools simultaneously. The system uses Chinese-focused LLM
providers (DeepSeek, Qwen via Groq/Cerebras/SambaNova/SiliconFlow) called
via raw `AsyncOpenAI`, a FastAPI backend, and a React + MUI web frontend.

---

## Architecture Diagram

See [`src/agent/prompts/README.md`](src/agent/prompts/README.md) for detailed
mermaid diagrams of the agent pipeline, internal LLM calls, and standalone
prompt flows. The high-level flow:

```text
+--------------------------+
|     CHANNEL LAYER        |
|  Web (chat.py)           |
|  WeChat (router.py)      |
+-----------+--------------+
            |
   handle_turn(text, role, identity)
            |
   +--------v---------+
   | Fast path?        |----yes----> greeting / help (0 LLM)
   | (regex match)     |
   +---------+---------+
             | no
   +---------v-----------------------+
   |  Routing LLM (router.py)        |
   |  → {intent, patient_name,       |
   |     params, deferred}           |
   +---------+-----------------------+
             |
   +---------v-----------------------+
   |  Dispatcher (dispatcher.py)     |
   |  intent → handler module        |
   +---------+-----------------------+
             |
   +---------v------------------------------------------+
   |  Intent Handler (handlers/<intent>.py)             |
   |  loads context + doctor knowledge                  |
   |  calls intent-specific LLM (interview /          |
   |  diagnosis / query / general)                  |
   |  returns HandlerResult                             |
   +--------------------+-------------------------------+
                        |
   +--------------------v----------+
   |         DB Layer               |
   |  SQLAlchemy async              |
   |  SQLite (dev) / MySQL (prod)   |
   +--------------------------------+
```

Two LLM calls per turn (routing + handler), predictable, per-intent prompts.

---

## Directory Structure

```text
src/
├── agent/                  # Plan-and-Act agent core
│   ├── handle_turn.py      # Entry point: fast paths + routing + dispatch
│   ├── router.py           # Routing LLM: message → RoutingResult
│   ├── dispatcher.py       # Intent → handler dispatch
│   ├── types.py            # IntentType enum, RoutingResult, HandlerResult,
│   │                       #   TurnContext (Pydantic models)
│   ├── actions.py          # Action helpers
│   ├── session.py          # Session history (DB-backed with in-memory cache,
│   │                       #   writes to doctor_chat_log, restores on restart)
│   ├── identity.py         # ContextVar for current doctor/patient identity
│   ├── handlers/           # One module per intent
│   │   ├── query_record.py
│   │   ├── create_record.py
│   │   ├── query_task.py
│   │   ├── create_task.py
│   │   ├── query_patient.py
│   │   └── general.py
│   ├── tools/              # Domain tools called by handlers
│   │   ├── doctor.py       # query_records, list_patients, list_tasks,
│   │   │                   #   create_record, create_task, get_patient_timeline,
│   │   │                   #   search_patients
│   │   ├── patient.py      # advance_interview
│   │   ├── diagnosis.py    # run_diagnosis_pipeline
│   │   └── resolve.py      # Name-to-ID patient resolution
│   └── prompts/            # Prompt .md files (see prompts/README.md)
│
├── domain/                 # Business logic (framework-independent)
│   ├── records/            # structuring, confirm_pending, pdf_export,
│   │                       #   vision_import, outpatient_report, schema,
│   │                       #   import_history (bulk record import pipeline)
│   ├── patients/           # interview_turn, interview_session, categorization,
│   │                       #   completeness, nl_search, timeline, interview_summary
│   ├── knowledge/          # doctor_knowledge, pdf_extract, word_extract, skills/
│   └── tasks/              # task_crud, notifications, scheduler
│
├── channels/               # Transport adapters
│   ├── web/                # FastAPI routes
│   │   ├── chat.py         # POST /api/records/chat — main chat endpoint
│   │   ├── auth.py         # JWT login (unified auth for all roles)
│   │   ├── export.py       # PDF/report export
│   │   ├── patient_portal.py  # Patient self-service
│   │   ├── patient_interview_routes.py
│   │   ├── import_routes.py
│   │   ├── tasks.py        # Task CRUD routes
│   │   ├── unified_auth_routes.py  # Phone+YOB login
│   │   └── ui/             # Doctor workbench (patient detail, records,
│   │                       #   knowledge, briefing, profile, admin)
│   └── wechat/             # WeChat/WeCom webhook
│       ├── router.py       # Message routing, dedup, background dispatch
│       ├── wechat_notify.py  # Customer service API delivery
│       ├── wechat_import.py  # Re-exports from domain/records/import_history
│       └── ...             # flows, infra, media, export, menu, wecom_kf
│
├── infra/                  # Infrastructure concerns
│   ├── llm/                # client.py (provider registry), vision.py,
│   │                       #   resilience.py (retry/fallback), egress.py
│   ├── auth/               # Unified JWT auth, rate limiting
│   └── observability/      # audit, turn_log, routing_metrics, observability
│
├── db/                     # Data layer
│   ├── models/             # SQLAlchemy ORM models
│   ├── crud/               # Async CRUD functions
│   ├── repositories/       # Higher-level query wrappers
│   ├── engine.py           # AsyncEngine + session factory
│   └── init_db.py          # Table creation (no Alembic yet)
│
├── utils/                  # Shared utilities
│   ├── runtime_config.py   # Load config/runtime.json, env var management
│   ├── prompt_loader.py    # Load prompt .md files by key
│   ├── app_config.py       # FastAPI app configuration
│   ├── log.py              # Structured logging
│   ├── text_parsing.py     # Text extraction helpers
│   ├── response_formatting.py
│   ├── errors.py           # Error types
│   ├── hashing.py          # Hash utilities
│   └── pdf_utils.py        # PDF generation helpers
│
├── messages.py             # Template strings (Chinese/English)
├── constants.py            # App-wide constants
└── main.py                 # FastAPI app, middleware, lifespan, scheduler

frontend/web/               # React + MUI + Vite
├── src/
│   ├── pages/              # Route pages
│   ├── components/         # Shared UI components
│   ├── api.js              # Backend API client
│   ├── App.jsx             # Router + layout
│   ├── i18n/               # Internationalization
│   └── theme.js            # MUI theme
└── vite.config.js
```

---

## Agent Pipeline

### Entry Point

All channels call `handle_turn(text, role, identity)`. This is the sole entry
point for conversation processing.

### Fast Paths (0 LLM calls)

Deterministic regex matching handles without invoking any LLM:
- **Greeting** — `你好`, `hello`, etc.
- **Help** — `帮助`, `/help`, etc.

### Routing LLM

`router.py` sends the doctor's message to the routing LLM (configured via
`ROUTING_LLM`, default `groq`). The routing LLM returns a `RoutingResult`:

```json
{
  "intent": "query_record",
  "patient_name": "张三",
  "params": {},
  "deferred": "建个随访任务"
}
```

**6 routing intents:**

| Intent | `patient_name` | Key params |
|--------|---------------|------------|
| `query_record` | optional | `limit` (default 5) |
| `create_record` | required | `gender`, `age`, `clinical_text` (all optional) |
| `query_task` | — | `status` (optional: pending\|completed) |
| `create_task` | optional | `title` (required), `content`, `due_at` |
| `query_patient` | — | `query` (NL search string, required) |
| `general` | — | (none — fallback/chitchat) |

**Single intent per turn**: if the message contains multiple intents (e.g.
"查张三病历然后建个随访任务"), routing extracts the first and stores the rest
in `deferred`. The query LLM acknowledges deferred intents in its reply.

**`create_record` is exclusive**: if any intent is `create_record`, it must
be the only intent in that turn. Record creation enters interview mode which
is incompatible with other actions in the same turn.

### Dispatcher

`dispatcher.py` maps the `IntentType` enum value to the corresponding handler
module in `handlers/` and calls `handle(ctx: TurnContext) → HandlerResult`.

### Intent Handlers

Each handler in `handlers/` is responsible for one intent:
- Loads doctor context (history, knowledge, patient records as needed)
- Calls the appropriate domain LLM (interview
  LLM, or diagnosis LLM via `domain/`)
- Returns a `HandlerResult(reply, data)`

**`create_record` handler** enters the multi-turn interview flow. The doctor
is guided through clinical record fields; fields extracted by the routing LLM are
pre-filled. Confirm/abandon happens within the interview API, not via regex
fast paths.

**`query_record` / `query_task` / `query_patient` handlers** fetch DB data
and pass it to a query prompt for natural-language summarization.

**`create_task` handler** persists the task directly — no confirmation gate
(tasks are lightweight).

**`general` handler** responds directly via general prompt with no DB reads.

### Identity and Resolution

- **Identity injection** — `ContextVar` set once in `handle_turn`; all tools
  read it via `get_current_identity()`
- **Name-based LLM interface** — the LLM passes `patient_name` (human-readable)
- **ID-based DB internally** — `resolve.py` translates names to
  `(doctor_id, patient_id)` for CRUD operations
- **Auto-create** — write handlers can auto-create patients via
  `resolve(auto_create=True)` if the patient does not exist

---

## LLM Providers

Chinese-focused provider registry in `src/infra/llm/client.py`. All providers
expose an OpenAI-compatible API and are called via raw `AsyncOpenAI`. Default
to Qwen or DeepSeek models:

| Provider | Default Model | Type |
|----------|--------------|------|
| `deepseek` | `deepseek-chat` | Direct API |
| `groq` | `qwen/qwen3-32b` | Inference cloud |
| `cerebras` | `qwen-3-32b` | Inference cloud |
| `sambanova` | `Qwen2.5-72B-Instruct` | Inference cloud |
| `siliconflow` | `Qwen/Qwen2.5-72B-Instruct` | Inference cloud |
| `openrouter` | `qwen/qwen3.5-9b` | Multi-model router |
| `tencent_lkeap` | `deepseek-v3-1` | China cloud |
| `ollama` | `qwen2.5:7b` | Local / self-hosted |

**LLM role → env var mapping:**

| Role | Env var | Falls back to |
|------|---------|---------------|
| Routing (intent classification) | `ROUTING_LLM` | `groq` |
| Structuring (record fields + interview) | `STRUCTURING_LLM` | `groq` |
| Diagnosis / review pipeline | `DIAGNOSIS_LLM` | `STRUCTURING_LLM` |
| Vision (image/PDF OCR) | `VISION_LLM` | (required if used) |

See [`docs/dev/llm-providers.md`](docs/dev/llm-providers.md) for full
details on provider setup and model selection.

---

## Database

**SQLite** in development, **MySQL/PostgreSQL** in production. Async
SQLAlchemy with `aiosqlite` (dev) or async MySQL driver (prod). No Alembic
migrations until first production launch; `init_db.py` handles DDL.

### 14 Tables

Consolidated from a previous 25-table schema. Tables killed: `pending_records`,
`diagnosis_results`, `case_history`, `review_queue`, `medical_record_versions`,
`medical_record_exports`, `patient_labels`, `system_prompts`, `chat_archive`,
`patient_chat_log` (and related assignment/version tables).

**Core data (8 tables):**

| Table | Purpose |
|-------|---------|
| `doctors` | Doctor profiles, identity only |
| `doctor_wechat` | WeChat channel binding (optional, per-doctor) |
| `patients` | Patient demographics, FK: `doctor_id` |
| `patient_auth` | Patient portal access codes (optional) |
| `medical_records` | Structured clinical records — also serves as version history, diagnosis results, and pending/review queue (`status` enum: `interview_active`, `pending_review`, `completed`) |
| `doctor_tasks` | Tasks (type: general\|review), covers both doctor and patient targets |
| `doctor_knowledge_items` | Personal KB, categorized (interview_guide\|diagnosis_rule\|red_flag\|treatment_protocol\|custom) |
| `doctor_chat_log` | Doctor ↔ AI conversation history (session-grouped, DB-backed with in-memory cache) |

**Patient messaging (1 table):**

| Table | Purpose |
|-------|---------|
| `patient_messages` | Patient ↔ doctor/AI messaging with triage metadata (direction, source, triage_category) |

**Workflow state (1 table):**

| Table | Purpose |
|-------|---------|
| `interview_sessions` | Multi-turn interview state: collected fields, conversation, status |

**System/infra (4 tables):**

| Table | Purpose |
|-------|---------|
| `audit_log` | Compliance audit trail |
| `invite_codes` | Doctor signup gating |
| `runtime_tokens` | WeChat access token cache |
| `scheduler_leases` | Distributed lock for task notification scheduler |

### Key Schema Decisions

- **结构化字段列 on `medical_records`** — `chief_complaint`, `present_illness`,
  `past_history`, `physical_exam`, `diagnosis`, `treatment_plan`, etc. are
  real queryable columns, not a single JSON blob. Replaces `structured_data`
  JSON column from prior schema.
- **Append-only versioning** — record edits create a new row with `version_of`
  pointing to the original. `medical_record_versions` table eliminated.
- **Diagnosis folded in** — `ai_diagnosis`, `doctor_decisions`, `suggested_tasks`
  columns on `medical_records` replace the separate `diagnosis_results` table.
- **Pending records eliminated** — record creation is a multi-turn interview
  (`interview_sessions`), not a one-shot draft with confirm/abandon regex.
  The review queue is `medical_records WHERE status='pending_review'`.
- **Case history absorbed** — `final_diagnosis`, `treatment_outcome`,
  `key_symptoms` columns on `medical_records` replace the `case_history` table.
  "Similar symptom cases" = `SELECT ... WHERE chief_complaint LIKE '%X%'`.

---

## Prompts

See [`src/agent/prompts/README.md`](src/agent/prompts/README.md) for the full
prompt index, mermaid architecture diagrams, and template variable reference.

Key prompt files:

| File | Used by |
|------|---------|
| `routing.md` | Routing LLM — intent classification |
| `doctor-interview.md` | Interview LLM — guided clinical field collection |
| `doctor-extract.md` | Field extraction — clinical text → 14 structured fields |
| `diagnosis.md` | Diagnosis LLM — review pipeline, AI suggestions |
| `query.md` | Query summary — results → natural language |
| `patient-interview.md` | Patient interview orchestration |

---

## Key Design Decisions

1. **Plan-and-Act, not ReAct** — routing LLM classifies intent once (Plan);
   deterministic code dispatches to the right handler (Act). No tool-calling
   loop, no LLM choosing between tools at runtime.

2. **Per-intent prompts** — each handler uses a focused prompt for its domain
   (interview, diagnosis, query, general). Previously one agent prompt covered all
   cases with a tool list. Focused prompts are easier to tune and debug.

3. **Single intent per turn** — routing returns one primary intent. Deferred
   intents are acknowledged in the reply and handled next turn.

4. **Interview-first record creation** — record creation always goes through
   multi-turn interview (`create_record` handler + `interview_sessions` table).
   No confirm/abandon regex fast paths.

5. **Name-based LLM interface** — LLM passes `patient_name` (human-readable).
   `resolve.py` translates to `(doctor_id, patient_id)` for DB operations. The
   LLM never sees database IDs.

6. **Clinical columns, not JSON blob** — medical record fields are real DB columns.
   Queryable by SQL, indexable, renderable directly into PDF without extraction.

7. **Review = completeness gate** — after interview confirm, if `diagnosis`,
   `treatment_plan`, or `orders_followup` are missing, the record `status` becomes
   `pending_review` and a review task is auto-created. Review/diagnosis UI is
   not yet implemented; `status` field is the single source of truth for review state.

---

## Configuration

**Primary config:** `config/runtime.json` (gitignored; sample in
`config/runtime.json.sample`).

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | DB connection string | `sqlite+aiosqlite:///data/patients.db` |
| `ENVIRONMENT` | `development` / `production` | (required in prod) |
| `ROUTING_LLM` | LLM provider for intent routing | `groq` |
| `STRUCTURING_LLM` | LLM provider for voice/paste extraction | `groq` |
| `DIAGNOSIS_LLM` | LLM provider for diagnosis pipeline | falls back to `STRUCTURING_LLM` |
| `VISION_LLM` | LLM provider for image/PDF OCR | (required if used) |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (optional) |
| `GROQ_API_KEY` | Groq API key | (optional) |
| `WECHAT_TOKEN` | WeChat credentials | (required for WeChat) |

---

## Application Entry (`src/main.py`)

- Registers route modules (chat, wechat, auth, unified_auth, ui, tasks,
  export, patient_portal, patient_interview, import)
- Middleware: request size limit, trace ID propagation, CORS
- Health endpoints: `/healthz`, `/readyz`
- Lifespan: create tables, seed data, hydrate LLMs, start scheduler
- APScheduler: task notifications, conversation cleanup, session pruning

---

## Infrastructure

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Agent pattern | Plan-and-Act (routing LLM + dispatcher + handlers) |
| ORM | SQLAlchemy async |
| Scheduler | APScheduler |
| Frontend | React + Vite + MUI |
| Auth | Unified HS256 JWT (`UNIFIED_AUTH_SECRET`) — single token system for all roles and channels |
| LLM | OpenAI-compatible (DeepSeek, Qwen, Ollama) via `AsyncOpenAI` |

---

## Design Specs

Design documents in `docs/`:

| Spec | Description |
|------|-------------|
| `docs/product/domain-operations-design.md` | Plan-and-Act domain operations design (authoritative) |
| `docs/superpowers/specs/2026-03-17-patient-pre-consultation-design.md` | Patient interview pipeline |
| `docs/superpowers/specs/2026-03-17-wechat-miniapp-design.md` | WeChat mini-program design |
| `docs/superpowers/specs/2026-03-16-medical-record-import-export-design.md` | Record import/export |
| `docs/superpowers/specs/2026-03-15-structured-medical-record-fields-design.md` | Structured record schema |
| `docs/superpowers/specs/2026-03-15-web-frontend-simplification-design.md` | Frontend simplification |

---

## Further Reading

- [Domain Operations Design](docs/product/domain-operations-design.md) — authoritative Plan-and-Act design document
- [Prompt Architecture](src/agent/prompts/README.md) — prompt index, mermaid diagrams, template vars
- [LLM Providers Guide](docs/dev/llm-providers.md) — provider setup and model selection
- [Product Requirements](docs/product/requirements-and-gaps.md) — 4-phase roadmap
