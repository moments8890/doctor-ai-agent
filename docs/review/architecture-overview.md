# Architecture Overview

**Last updated:** 2026-03-23

---

## System Overview

A FastAPI backend + React SPA medical AI agent for doctors. Three channels:
**Web dashboard** (primary), **WeChat/WeCom** (mobile), and **Patient portal**
(pre-consultation). Uses a **Plan-and-Act** agent pipeline with a 6-layer
prompt composer and Pydantic/Instructor structured output.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CHANNELS                                │
│                                                              │
│  Web Dashboard ──► POST /api/records/chat                    │
│  (React SPA)       channels/web/chat.py                      │
│                                                              │
│  WeChat/WeCom ──► POST /wechat                               │
│                    channels/wechat/router.py                  │
│                                                              │
│  Patient Portal ─► POST /api/patient/interview/*             │
│                    channels/web/patient_interview_routes.py   │
│                  ► POST /api/patient/chat (triage pipeline)  │
│                    channels/web/patient_portal.py             │
│                                                              │
│  Doctor Interview ► POST /api/records/interview/*            │
│  (UI-triggered)    channels/web/doctor_interview.py          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  AGENT PIPELINE                              │
│                  (Plan-and-Act)                               │
│                                                              │
│  handle_turn(text, role, identity) → HandlerResult           │
│       │                                                      │
│       ├─ 1. Route: routing LLM → RoutingResult               │
│       │     (6 intents: create_record, query_record,         │
│       │      create_task, query_task, query_patient, general)│
│       │                                                      │
│       ├─ 2. Dispatch: intent → registered handler            │
│       │     dispatcher.py + handlers/*.py                    │
│       │                                                      │
│       └─ 3. Handler: loads context → calls intent LLM        │
│             → returns HandlerResult(reply, data)             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  6-LAYER PROMPT COMPOSER                      │
│                  prompt_composer.py + prompt_config.py        │
│                                                              │
│  Two patterns based on conversation_mode:                    │
│                                                              │
│  Pattern 1 — Single-turn (query, diagnosis, routing):        │
│  ┌──────────────────────────────────────────┐                │
│  │ system: Layers 1-3 (instructions only)   │                │
│  │   1. system/base.md — identity, safety   │                │
│  │   2. common/{specialty}.md — area knowledge│               │
│  │   3. intent/{intent}.md — rules + examples│               │
│  ├──────────────────────────────────────────┤                │
│  │ user: Layers 4-6 (XML-tagged data)       │                │
│  │   4. <doctor_knowledge> KB from DB       │                │
│  │   5. <patient_context> records, history  │                │
│  │   6. <doctor_request> actual message     │                │
│  └──────────────────────────────────────────┘                │
│                                                              │
│  Pattern 2 — Conversation (interview):                       │
│  ┌──────────────────────────────────────────┐                │
│  │ system: Layers 1-5 (instructions + data) │                │
│  │   1-3. same as Pattern 1                 │                │
│  │   4. doctor KB items (as system context) │                │
│  │   5. patient state (collected, missing)  │                │
│  ├──────────────────────────────────────────┤                │
│  │ conversation history (user/assistant)    │                │
│  ├──────────────────────────────────────────┤                │
│  │ user: Layer 6 only (latest input)        │                │
│  └──────────────────────────────────────────┘                │
│                                                              │
│  Config: INTENT_LAYERS maps IntentType → LayerConfig         │
│  (layers, KB categories, patient context, conversation_mode) │
│  KB auto-loaded from DB by composer (async)                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  LLM LAYER                                   │
│                  agent/llm.py                                │
│                                                              │
│  structured_call() → Pydantic model (instructor JSON mode)   │
│    Response models: RoutingResult, InterviewLLMResponse,     │
│    DiagnosisLLMResponse, StructuringLLMResponse              │
│                                                              │
│  llm_call() → raw text (for compose/summary)                 │
│                                                              │
│  Provider: env-driven (default: Groq qwen/qwen3-32b)         │
│    Supports: Groq, DeepSeek, Ollama, OpenAI-compatible       │
│  Retry: instructor retries (structured), circuit breaker (text)│
│  Tracing: trace_block → JSONL observability                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  DOMAIN LAYER                                │
│                                                              │
│  domain/patients/                                            │
│    interview_session.py — create/load/save sessions          │
│    interview_turn.py — multi-turn SOAP field collection      │
│    interview_summary.py — confirm → save to medical_records  │
│    nl_search.py — natural language patient search            │
│    completeness.py — SOAP field completeness check           │
│                                                              │
│  domain/records/                                             │
│    structuring.py — text → structured SOAP record            │
│    vision_import.py — image/PDF → structured record          │
│    pdf_export.py — records → PDF                             │
│                                                              │
│  domain/diagnosis.py — differential diagnosis pipeline       │
│                                                              │
│  domain/tasks/                                               │
│    task_crud.py — create, notify, schedule tasks             │
│    scheduler.py — APScheduler for due-task notifications     │
│                                                              │
│  domain/knowledge/                                           │
│    doctor_knowledge.py — KB CRUD + context loading           │
│    embedding.py — BGE-M3 local embeddings                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  DATABASE (14 tables)                         │
│                  SQLite (dev) / MySQL (prod)                  │
│                                                              │
│  Core Data (9):                                              │
│    doctors            — identity (8 columns)                 │
│    doctor_wechat      — WeChat channel binding               │
│    patients           — identity (7 columns)                 │
│    patient_auth       — portal access code (hashed)          │
│    medical_records    — SOAP columns + status + versioning   │
│    doctor_tasks       — general | review (target: doctor|patient) │
│    doctor_knowledge   — categorized KB items                 │
│    doctor_chat_log    — doctor ↔ AI conversation (session_id)│
│    patient_chat_log   — patient ↔ AI conversation            │
│                                                              │
│  Workflow (1):                                               │
│    interview_sessions — multi-turn SOAP field collection     │
│                                                              │
│  System (4):                                                 │
│    audit_log          — compliance audit trail               │
│    invite_codes       — doctor signup gating                 │
│    runtime_tokens     — WeChat access token cache            │
│    scheduler_leases   — distributed scheduler lock           │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Data Flows

### Doctor Creates a Record (chat)

```
Doctor types: "创建患者张三，男45岁，头痛三天"
  │
  ├─ 1. POST /api/records/chat
  ├─ 2. handle_turn → routing LLM → intent=create_record
  ├─ 3. create_record handler → resolve patient (auto-create)
  ├─ 4. Start interview session → first turn with clinical text
  ├─ 5. Return {reply, view_payload: {session_id}}
  ├─ 6. Frontend detects session_id → navigate to interview UI
  ├─ 7. Doctor continues in interview UI (POST /api/records/interview/turn)
  └─ 8. Doctor confirms → SOAP fields saved to medical_records
         Status: pending_review (if diagnosis/treatment missing)
         or completed (if all fields filled)
```

### Doctor Queries Records (chat)

```
Doctor types: "查张三的病历"
  │
  ├─ 1. routing LLM → intent=query_record, patient=张三
  ├─ 2. query_record handler → resolve patient → fetch records
  ├─ 3. compose_for_intent → 6-layer prompt assembly
  ├─ 4. compose LLM → natural language summary
  └─ 5. Return summary to doctor
```

### Review Record (UI-triggered, not chat)

```
Doctor clicks pending_review record in UI
  │
  ├─ 1. Frontend calls review API directly (no routing LLM)
  ├─ 2. compose_for_review → load knowledge (诊断规则+危险信号+治疗方案)
  ├─ 3. Load patient context (records, similar cases)
  ├─ 4. Diagnosis LLM → {differentials, workup, treatment, suggested_tasks}
  ├─ 5. Doctor reviews: accept/reject/edit suggestions
  └─ 6. Record → completed, suggested tasks auto-created
```

---

## Directory Structure

```
src/
├── agent/                      # Plan-and-Act agent pipeline
│   ├── handle_turn.py          # Main entry: route → dispatch → respond
│   ├── router.py               # Routing LLM → RoutingResult
│   ├── dispatcher.py           # Intent → handler registry
│   ├── types.py                # IntentType, RoutingResult, HandlerResult
│   ├── llm.py                  # structured_call + llm_call (shared LLM helper)
│   ├── prompt_config.py        # LayerConfig + INTENT_LAYERS matrix
│   ├── prompt_composer.py      # 6-layer message assembly with XML tags
│   ├── session.py              # In-memory chat history (plain dicts)
│   ├── identity.py             # ContextVar for current doctor_id
│   ├── actions.py              # IntentType re-export (backward compat)
│   ├── handlers/               # One handler per intent
│   │   ├── create_record.py    # → interview flow
│   │   ├── query_record.py     # → fetch + compose summary
│   │   ├── create_task.py      # → DB insert
│   │   ├── query_task.py       # → fetch + compose summary
│   │   ├── query_patient.py    # → local NL search
│   │   └── general.py          # → fallback greeting
│   ├── tools/                  # Business logic (plain async functions)
│   │   ├── doctor.py           # Record/task/patient operations
│   │   ├── patient.py          # Patient interview tools
│   │   └── resolve.py          # Patient name → ID resolution
│   └── prompts/                # LLM prompt fragments
│       ├── system/base.md      # Layer 1: identity, safety
│       ├── common/neurology.md # Layer 2: specialty knowledge
│       └── intent/*.md         # Layer 3: 11 intent prompts
│
├── channels/                   # HTTP entry points
│   ├── web/
│   │   ├── chat.py             # POST /api/records/chat
│   │   ├── doctor_interview.py # Interview turn/confirm/cancel/session
│   │   ├── patient_interview_routes.py
│   │   ├── patient_portal.py   # Patient auth + records
│   │   ├── tasks.py            # Task CRUD API
│   │   ├── import_routes.py    # Image/PDF import
│   │   └── ui/                 # Admin management handlers
│   └── wechat/
│       ├── router.py           # WeChat webhook
│       └── ...                 # WeChat-specific handlers
│
├── domain/                     # Business logic
│   ├── patients/               # Interview, search, timeline
│   ├── records/                # Structuring, import, export
│   ├── tasks/                  # CRUD, scheduling, notifications
│   ├── knowledge/              # Doctor KB, embeddings
│   ├── diagnosis.py            # Differential diagnosis pipeline
│   └── patient_lifecycle/      # Triage, treatment plans
│
├── db/                         # Database layer
│   ├── models/                 # SQLAlchemy ORM (14 tables)
│   ├── crud/                   # CRUD operations
│   ├── repositories/           # Repository pattern
│   └── engine.py               # Async SQLAlchemy engine
│
├── infra/                      # Infrastructure
│   ├── llm/                    # Provider registry, resilience, vision
│   ├── auth/                   # JWT, rate limiting, access codes
│   └── observability/          # Tracing, metrics, audit
│
└── main.py                     # FastAPI app + middleware + startup
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + uvicorn |
| Frontend | React + MUI (Vite) |
| Database | SQLite (dev) / MySQL (prod), SQLAlchemy async |
| LLM Provider | Env-driven: Groq, DeepSeek, Ollama, OpenAI-compatible |
| Structured Output | Instructor (JSON mode) + Pydantic v2 |
| Embeddings | BGE-M3 via langchain-huggingface |
| Agent Pattern | Plan-and-Act (routing → dispatch → handler) |
| Prompt Assembly | 6-layer composer with XML context tags |
| Observability | JSONL traces + spans, trace_block context manager |
| Task Scheduling | APScheduler with distributed lease |
| WeChat | Custom webhook + KF customer service |

---

## Key Design Decisions

1. **Plan-and-Act over ReAct** — routing LLM classifies intent (1 call), handler
   executes with focused prompt (1 call). 2 LLM calls vs 3-5 with ReAct.
   Predictable, debuggable, works with free-tier Chinese LLMs.

2. **Instructor JSON mode** — Groq/Qwen3 doesn't support tool-calling. Instructor's
   JSON mode uses response_format + Pydantic validation + automatic retries.

3. **6-layer prompt composer** — separates identity/safety (static) from
   knowledge/context (dynamic). XML tags for context injection. Config matrix
   ensures every intent has explicit layer definitions. *(Note: KB loading by
   category is defined in config but handlers currently pass knowledge manually.)*

4. **SOAP columns** — 14 outpatient fields as real DB columns (not JSON blob).
   Queryable, indexable, absorbs case_history table.

5. **Interview-first record creation** — chat-initiated records go through
   multi-turn interview. Import paths (image/PDF/WeChat) still use direct
   structuring. *(Target: all paths through interview.)*

6. **Append-only record versioning** — `version_of` FK column exists on
   medical_records. *(Not yet enforced — edit paths currently mutate in place.
   Target: edits create new rows, originals preserved.)*

7. **Single intent per turn** — routing returns one intent + deferred field for
   multi-intent messages. create_record is exclusive (can't chain).

---

## Benchmark Results

E2E accuracy benchmark: **46/46 active tests passing** (6 intentionally skipped).

| Category | Tests | Status |
|----------|-------|--------|
| create_save | 22 | Pass (routing + interview + confirm) |
| query_history | 4 | Pass (relaxed — LLM summary) |
| clarification | 6 | Pass |
| safety | 3 | Pass |
| task_action | 2 | Pass |
| dedup | 1 | Pass |
| list | 1 | Pass |
| edge_case | 4 | Pass |
| DS/GM series | 8 | Pass |
| update_record | 2 | Skip (UI-only) |
| correction | 2 | Skip (UI-only) |
| compound | 1 | Skip (exclusive rule) |
| schedule | 1 | Skip (removed) |
