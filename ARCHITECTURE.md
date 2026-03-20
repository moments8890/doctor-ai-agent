# Architecture

**Last updated:** 2026-03-19

## Overview

Doctor AI Agent is a medical AI assistant built on a **ReAct agent pattern**
using LangChain/LangGraph. It serves both doctors (patient management, medical
record dictation, task scheduling) and patients (pre-consultation interview).
The system uses Chinese-focused LLM providers (DeepSeek, Qwen via Groq/Cerebras/
SambaNova/SiliconFlow) with an OpenAI-compatible API interface, a FastAPI
backend, and a React + MUI web frontend.

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
   | Fast path?        |----yes----> greeting / confirm / abandon (0 LLM)
   | (regex match)     |
   +---------+---------+
             | no
   +---------v---------------------+
   | SessionAgent                  |
   |   in-memory history           |
   |   LangGraph ReAct agent       |
   |   role-based tools + prompt   |
   +------+-----------+-----------+
          |           |
   +------v---+ +----v--------+
   | Doctor    | | Patient     |
   | tools     | | tools       |
   +------+---+ +----+--------+
          |           |
   +------v-----------v----------+
   |         DB Layer             |
   |  SQLAlchemy async            |
   |  SQLite (dev) / MySQL (prod) |
   +------------------------------+
```

---

## Directory Structure

```text
src/
├── agent/                  # ReAct agent core
│   ├── handle_turn.py      # Entry point: fast paths + agent dispatch
│   ├── session.py          # SessionAgent with in-memory history
│   ├── setup.py            # LangGraph agent construction, LLM config, tracing
│   ├── identity.py         # ContextVar for current doctor/patient identity
│   ├── archive.py          # Conversation archive (DB persistence)
│   ├── pending.py          # Pending record helpers
│   ├── tools/
│   │   ├── doctor.py       # Doctor tools: query_records, list_patients, list_tasks,
│   │   │                   #   create_record, update_record, create_task, export_pdf,
│   │   │                   #   search_knowledge, search_patients, get_patient_timeline,
│   │   │                   #   complete_task
│   │   ├── patient.py      # Patient tools: advance_interview
│   │   ├── resolve.py      # Name-to-ID patient resolution
│   │   └── truncate.py     # Tool result size management
│   └── prompts/            # Prompt .md files (see prompts/README.md)
│
├── domain/                 # Business logic (framework-independent)
│   ├── records/            # structuring, confirm_pending, pdf_export,
│   │                       #   vision_import, outpatient_report, schema
│   ├── patients/           # interview_turn, interview_session, categorization,
│   │                       #   completeness, nl_search, timeline, interview_summary
│   ├── knowledge/          # doctor_knowledge, pdf_extract, word_extract, skills/
│   └── tasks/              # task_crud, task_rules, notifications, scheduler
│
├── channels/               # Transport adapters
│   ├── web/                # FastAPI routes
│   │   ├── chat.py         # POST /api/records/chat — main chat endpoint
│   │   ├── auth.py         # JWT login, invite codes
│   │   ├── export.py       # PDF/report export
│   │   ├── patient_portal.py  # Patient self-service
│   │   ├── patient_interview_routes.py
│   │   ├── import_routes.py
│   │   ├── tasks.py        # Task CRUD routes
│   │   ├── unified_auth_routes.py
│   │   └── ui/             # Admin dashboard
│   └── wechat/             # WeChat/WeCom webhook
│       ├── router.py       # Message routing, dedup, background dispatch
│       ├── wechat_notify.py  # Customer service API delivery
│       ├── wechat_import.py  # Image/PDF/document extraction
│       └── ...             # flows, infra, media, export, menu, wecom_kf
│
├── infra/                  # Infrastructure concerns
│   ├── llm/                # client.py (provider registry), vision.py,
│   │                       #   resilience.py (retry/fallback), egress.py
│   ├── auth/               # JWT, rate limiting, miniprogram, unified auth
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

Deterministic regex matching handles without invoking the LLM:
- **Greeting** — `你好`, `hello`, etc.
- **Confirm pending** — `确认`, `yes`, etc. — commits the pending draft record
- **Abandon pending** — `取消`, `cancel`, etc. — discards the pending draft

### SessionAgent

Each doctor/patient gets a persistent `SessionAgent` instance that holds
conversation history in memory (capped at 100 turns). On server restart,
history is bootstrapped from the DB archive.

### LangGraph ReAct Agent

`setup.py` constructs a LangGraph `create_react_agent` (native JSON tool
calls, not text-based ReAct parsing) with:
- **LLM** — `ChatOpenAI` pointed at the configured provider
- **Tools** — filtered by role (doctor or patient)
- **System prompt** — loaded from `prompts/agent-{role}.md` with template
  variable substitution (`{current_date}`, `{timezone}`, `{tools_section}`)
- **Observability** — `AgentTracer` callback logs every LLM call and tool
  invocation; optional LangFuse integration

### Tool List by Role

**Doctor tools** (default set — 6 core tools):

| Tool | Type | Description |
|------|------|-------------|
| `query_records` | Read | Fetch patient medical records |
| `list_patients` | Read | List doctor's patient panel |
| `list_tasks` | Read | List scheduled tasks |
| `create_record` | Write | Structure clinical text into record (pending preview) |
| `update_record` | Write | Modify existing record (pending preview) |
| `create_task` | Write | Schedule task or appointment (immediate commit) |

Extended tools (defined but excluded from default set to reduce token count):
`export_pdf`, `search_knowledge`, `search_patients`, `get_patient_timeline`,
`complete_task`.

**Patient tools** (1 tool):

| Tool | Description |
|------|-------------|
| `advance_interview` | Progress pre-consultation interview state machine |

### Identity and Resolution

- **Identity injection** — `ContextVar` set once in `handle_turn`; all tools
  read it via `get_current_identity()`
- **Name-based LLM interface** — the LLM passes `patient_name` in tool calls
- **ID-based DB internally** — `resolve.py` translates names to
  `(doctor_id, patient_id)` for CRUD operations
- **Auto-create** — write tools can auto-create patients if they don't exist

---

## LLM Providers

Chinese-focused provider registry in `src/infra/llm/client.py`. All providers
expose an OpenAI-compatible API and default to Qwen or DeepSeek models:

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

Provider selection: `CONVERSATION_LLM` env var (falls back to `ROUTING_LLM`,
default `groq`). See [`docs/dev/llm-providers.md`](docs/dev/llm-providers.md)
for full details.

---

## Database

**SQLite** in development, **MySQL/PostgreSQL** in production. Async
SQLAlchemy with `aiosqlite` (dev) or async MySQL driver (prod). No Alembic
migrations until first production launch; `init_db.py` handles DDL.

### Key Tables

| Model | Table | Purpose |
|-------|-------|---------|
| `Doctor` | `doctors` | Doctor profiles, PK: `doctor_id` (str) |
| `Patient` | `patients` | Patient demographics, FK: `doctor_id`, unique `(doctor_id, name)` |
| `MedicalRecordDB` | `medical_records` | Structured medical records |
| `PendingRecord` | `pending_records` | Draft previews awaiting confirmation |
| `DoctorTask` | `tasks` | Tasks, appointments, follow-ups |
| `InterviewSession` | `interview_sessions` | Patient pre-consultation state |
| `ChatArchive` | `chat_archive` | Conversation turn persistence |
| `DoctorKnowledgeItem` | `doctor_knowledge` | Personal knowledge base entries |
| `AuditLog` | `audit_log` | Audit trail |

---

## Prompts

See [`src/agent/prompts/README.md`](src/agent/prompts/README.md) for the full
prompt index, mermaid architecture diagrams, and template variable reference.

Key prompt files:
- `doctor-agent.md` — doctor agent system prompt (clinical collection rules,
  tool usage, examples)
- `patient-agent.md` — patient agent system prompt (interview orchestration)
- `structuring.md` — conversation-to-structured-record (used inside
  `create_record` / `update_record` tools)
- `patient-interview.md` — clinical field extraction for interview tool

---

## Key Design Decisions

1. **No DoctorCtx** — eliminated persistent context (`WorkflowState`,
   `MemoryState`). All state derived from conversation history or queried
   from DB per tool call.

2. **Name-based tool params** — LLM passes `patient_name` (human-readable).
   `resolve.py` translates to `(doctor_id, patient_id)` internally. The LLM
   never sees database IDs.

3. **Pending draft for writes** — `create_record` and `update_record` produce
   a preview in `pending_records`. Doctor must confirm (fast-path regex) before
   permanent save. `create_task` commits immediately.

4. **Interview as tool** — patient pre-consultation is a LangChain tool
   (`advance_interview`), not a separate pipeline. The patient agent decides
   when to invoke it vs. reply to off-topic messages directly.

5. **Agent-per-session** — each identity gets a persistent `SessionAgent`
   with in-memory history. Zero DB reads for history during normal operation;
   archive writes for durability only.

6. **Same agent, different config** — doctor and patient share the same
   pipeline. Role determines prompt + tool set.

---

## Configuration

**Primary config:** `config/runtime.json` (gitignored; sample in
`config/runtime.json.sample`).

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | DB connection string | `sqlite+aiosqlite:///data/patients.db` |
| `ENVIRONMENT` | `development` / `production` | (required in prod) |
| `CONVERSATION_LLM` | LLM provider for agent | falls back to `ROUTING_LLM` |
| `ROUTING_LLM` | Fallback LLM provider | `groq` |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (optional) |
| `GROQ_API_KEY` | Groq API key | (optional) |
| `WECHAT_TOKEN` | WeChat credentials | (required for WeChat) |
| `LANGFUSE_PUBLIC_KEY` | LangFuse tracing | (optional) |

---

## Application Entry (`src/main.py`)

- Registers route modules (chat, wechat, auth, ui, tasks, export,
  patient_portal, patient_interview, import, unified_auth)
- Middleware: request size limit, trace ID propagation, CORS
- Health endpoints: `/healthz`, `/readyz`
- Lifespan: create tables, seed prompts, hydrate LLMs, start scheduler
- APScheduler: task notifications, conversation cleanup, session pruning

---

## Infrastructure

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Agent | LangChain / LangGraph |
| ORM | SQLAlchemy async |
| Scheduler | APScheduler |
| Frontend | React + Vite + MUI |
| Auth | HS256 JWT |
| LLM | OpenAI-compatible (DeepSeek, Qwen, Ollama) |

---

## Design Specs

Design documents in `docs/superpowers/specs/`:

| Spec | Description |
|------|-------------|
| `2026-03-18-react-mcp-architecture-design.md` | ReAct agent architecture (authoritative) |
| `2026-03-17-patient-pre-consultation-design.md` | Patient interview pipeline |
| `2026-03-17-wechat-miniapp-design.md` | WeChat mini-program design |
| `2026-03-16-medical-record-import-export-design.md` | Record import/export |
| `2026-03-15-structured-medical-record-fields-design.md` | Structured record schema |
| `2026-03-15-web-frontend-simplification-design.md` | Frontend simplification |

---

## Further Reading

- [ReAct Architecture Spec](docs/superpowers/specs/2026-03-18-react-mcp-architecture-design.md) — authoritative design document
- [Prompt Architecture](src/agent/prompts/README.md) — prompt index, mermaid diagrams, template vars
- [LLM Providers Guide](docs/dev/llm-providers.md) — provider setup and model selection
- [Product Requirements](docs/product/requirements-and-gaps.md) — 4-phase roadmap
