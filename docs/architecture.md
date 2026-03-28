# Architecture — Doctor AI Agent

**Last updated: 2026-03-27**

---

## 1. System Architecture Overview

A FastAPI backend + React SPA medical AI agent for doctors. Three channels:
**Web dashboard** (primary), **WeChat/WeCom** (mobile), and **Patient portal**
(pre-consultation). Uses a **Plan-and-Act** agent pipeline with a 6-layer
prompt composer and Pydantic/Instructor structured output.

### High-Level Diagram

```
Channels                        Agent Pipeline                 LLM Layer
───────────                     ──────────────                 ─────────
Web Dashboard ─┐
  (React SPA)  │                handle_turn(text, role, id)
               │  POST          ┌──────────────────────────┐
WeChat/WeCom ──┼──────────────► │ 1. Route: routing LLM    │   structured_call()
               │                │    → RoutingResult        │──► Instructor JSON
Patient Portal ┤                │ 2. Dispatch: intent →     │      + Pydantic v2
  (triage)     │                │    registered handler     │
               │                │ 3. Handler: loads context  │   llm_call()
Doctor         │                │    → intent LLM → result  │──► raw text
  Interview ───┘                └──────────────────────────┘
                                         │
                                         ▼
                                ┌──────────────────────────┐
                                │   6-Layer Prompt Composer  │
                                │   prompt_composer.py       │
                                │   + prompt_config.py       │
                                └──────────────────────────┘
                                         │
                                         ▼
                                ┌──────────────────────────┐
                                │   Domain Layer             │
                                │   patients/ records/       │
                                │   tasks/ knowledge/        │
                                │   diagnosis.py             │
                                └──────────────────────────┘
                                         │
                                         ▼
                                ┌──────────────────────────┐
                                │   Database (15 tables)     │
                                │   SQLite (dev) / MySQL     │
                                └──────────────────────────┘
```

### Key Design Decisions

1. **Plan-and-Act over ReAct** -- routing LLM classifies intent (1 call), handler
   executes with focused prompt (1 call). 2 LLM calls vs 3-5 with ReAct.
   Predictable, debuggable, works with free-tier Chinese LLMs.

2. **Instructor JSON mode** -- Groq/Qwen3 does not support tool-calling. Instructor
   uses `response_format` + Pydantic validation + automatic retries.

3. **6-layer prompt composer** -- separates identity/safety (static) from
   knowledge/context (dynamic). XML tags for context injection. Config matrix
   ensures every intent has explicit layer definitions.

4. **Clinical columns** -- 14 outpatient fields as real DB columns (not JSON blob).
   Queryable, indexable, absorbs former case_history table.

5. **Interview-first record creation** -- chat-initiated records go through
   multi-turn interview for guided field collection.

6. **Single intent per turn** -- routing returns one intent + `deferred` field for
   multi-intent messages. `create_record` is exclusive (cannot chain with
   other intents).

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + uvicorn |
| Frontend | React + MUI (Vite) |
| Database | SQLite (dev) / MySQL (prod), SQLAlchemy async |
| LLM Provider | Env-driven: Groq, DeepSeek, Tencent LKEAP, Ollama, OpenAI-compatible |
| Structured Output | Instructor (JSON mode) + Pydantic v2 |
| Agent Pattern | Plan-and-Act (routing -> dispatch -> handler) |
| Prompt Assembly | 6-layer composer with XML context tags |
| Observability | JSONL traces + spans, `trace_block` context manager |
| Task Scheduling | APScheduler with distributed lease |
| WeChat | Custom webhook + KF customer service |

> **Note on embeddings/RAG:** BGE-M3 local embeddings (`langchain-huggingface`)
> were used for case matching but are currently **disabled**. The `embedding.py`
> module has been deleted. Case matching via `matched_cases` always returns `[]`.
> The concept is retained for future re-enablement when the system migrates to
> `medical_records`-based similarity search.

---

## 2. Directory Structure & Module Map

```
src/
├── agent/                      # Plan-and-Act agent pipeline
│   ├── handle_turn.py          # Main entry: route -> dispatch -> respond
│   ├── router.py               # Routing LLM -> RoutingResult
│   ├── dispatcher.py           # Intent -> handler registry
│   ├── types.py                # IntentType (7), RoutingResult, HandlerResult, TurnContext
│   ├── llm.py                  # structured_call + llm_call (shared LLM helper)
│   ├── prompt_config.py        # LayerConfig + INTENT_LAYERS matrix
│   ├── prompt_composer.py      # 6-layer message assembly with XML tags
│   ├── session.py              # In-memory chat history (plain dicts)
│   ├── identity.py             # ContextVar for current doctor_id
│   ├── actions.py              # IntentType re-export (backward compat)
│   ├── handlers/               # One handler per intent
│   │   ├── create_record.py    # -> interview flow
│   │   ├── query_record.py     # -> fetch + compose summary
│   │   ├── create_task.py      # -> DB insert
│   │   ├── query_task.py       # -> fetch + compose summary
│   │   ├── query_patient.py    # -> local NL search
│   │   ├── daily_summary.py    # -> aggregated daily overview
│   │   └── general.py          # -> fallback greeting
│   ├── tools/                  # Business logic (plain async functions)
│   │   ├── doctor.py           # Record/task/patient operations
│   │   ├── patient.py          # Patient interview tools
│   │   └── resolve.py          # Patient name -> ID resolution
│   └── prompts/                # LLM prompt fragments
│       ├── common/base.md      # Layer 1: identity, safety
│       ├── domain/neurology.md # Layer 2: specialty knowledge
│       └── intent/             # Layer 3: per-intent prompts
│           ├── routing.md
│           ├── interview.md
│           ├── patient-interview.md
│           ├── diagnosis.md
│           ├── query.md
│           ├── general.md
│           ├── doctor-extract.md
│           ├── patient-extract.md
│           ├── vision-ocr.md
│           ├── triage-classify.md
│           ├── triage-escalation.md
│           └── triage-informational.md
│
├── channels/                   # HTTP entry points
│   ├── web/
│   │   ├── chat.py             # POST /api/records/chat
│   │   ├── doctor_interview.py # Interview turn/confirm/cancel/session
│   │   ├── patient_interview_routes.py
│   │   ├── patient_portal.py   # Patient auth + records + triage
│   │   ├── tasks.py            # Task CRUD API
│   │   ├── export.py           # PDF/JSON export
│   │   ├── import_routes.py    # Image/PDF import
│   │   ├── auth.py             # JWT auth
│   │   ├── unified_auth_routes.py  # Unified login for doctor/patient
│   │   └── ui/                 # Admin management handlers
│   └── wechat/
│       ├── router.py           # WeChat webhook
│       └── wechat_notify.py    # KF customer service messaging
│
├── domain/                     # Business logic
│   ├── patients/               # Interview, search, timeline, completeness
│   ├── records/                # Structuring, import, export, schema
│   ├── tasks/                  # CRUD, scheduling, notifications
│   ├── knowledge/              # Doctor KB CRUD + context loading
│   ├── diagnosis.py            # Differential diagnosis pipeline
│   └── patient_lifecycle/      # Triage, treatment plans
│
├── db/                         # Database layer
│   ├── models/                 # SQLAlchemy ORM (15 tables)
│   ├── crud/                   # CRUD operations
│   ├── repositories/           # Repository pattern
│   ├── engine.py               # Async SQLAlchemy engine
│   └── init_db.py              # Table creation + seed data
│
├── startup/                    # Application startup
│   ├── db_init.py              # Table creation, migrations, backfill, seed
│   ├── scheduler.py            # APScheduler registration (tasks, retention)
│   └── warmup.py               # Jieba, Ollama/LKEAP connectivity warmup
│
├── infra/                      # Infrastructure
│   ├── llm/                    # Provider registry, resilience, vision
│   ├── auth/                   # JWT, rate limiting, access codes
│   └── observability/          # Tracing, metrics, audit
│
└── main.py                     # FastAPI app + middleware + lifespan
```

---

## 3. Domain Operations Pipeline

All doctor chat messages follow the same pipeline:

```
message -> router LLM -> {intent, entities} -> dispatcher -> handler
        -> handler loads context + knowledge -> intent LLM -> response
```

### 3.1 Routing

The routing LLM classifies the doctor's message into one of 7 intents and
extracts relevant entities. One LLM call with structured output via Instructor.

**Routing output format:**
```json
{
  "intent": "query_record",
  "patient_name": "张三",
  "params": {},
  "deferred": "建个随访任务"
}
```

If the message contains multiple intents, routing extracts the first and
captures the rest in `deferred`. The compose LLM acknowledges deferred intents
in its response.

### 3.2 Dispatch

`dispatcher.py` maps the `IntentType` enum value to the corresponding handler
function. Simple dict-based dispatch, no dynamic registration.

### 3.3 Handler Execution

Each handler:
1. Loads per-intent context from the database (records, patients, tasks)
2. Builds the prompt via the 6-layer composer
3. Calls the intent-specific LLM (structured or free-text)
4. Returns `HandlerResult(reply, data)`

### 3.4 Two-Stage Context Loading

- **Routing stage:** minimal context (chat history only) -- fast, cheap
- **Execution stage:** full context per intent (DB queries) -- loaded only
  after routing decides what is needed

This avoids loading heavy context (records, knowledge) for every message.

### Key Data Flows

**Doctor creates a record (chat):**
```
Doctor types: "创建患者张三，男45岁，头痛三天"
  1. POST /api/records/chat
  2. handle_turn -> routing LLM -> intent=create_record
  3. create_record handler -> resolve patient (auto-create)
  4. Start interview session -> first turn with clinical text
  5. Return {reply, view_payload: {session_id}}
  6. Frontend detects session_id -> navigate to interview UI
  7. Doctor continues in interview UI (POST /api/records/interview/turn)
  8. Doctor confirms -> clinical fields saved to medical_records
```

**Doctor queries records (chat):**
```
Doctor types: "查张三的病历"
  1. routing LLM -> intent=query_record, patient=张三
  2. query_record handler -> resolve patient -> fetch records
  3. compose_for_intent -> 6-layer prompt assembly
  4. compose LLM -> natural language summary
  5. Return summary to doctor
```

**Review record (UI-triggered, not chat):**
```
Doctor clicks pending_review record in UI
  1. Frontend calls review API directly (no routing LLM)
  2. compose_for_review -> load knowledge (诊断规则+危险信号+治疗方案)
  3. Load patient context (records, similar cases)
  4. Diagnosis LLM -> {differentials, workup, treatment, suggested_tasks}
  5. Doctor reviews: accept/reject/edit suggestions
  6. Record -> completed, suggested tasks auto-created
```

---

## 4. Intent Types & Handler Registry

7 routing intents defined in `agent/types.py` as `IntentType(str, Enum)`:

| Intent | Handler | patient_name | params | Description |
|--------|---------|-------------|--------|-------------|
| `query_record` | `query_record.py` | optional | `limit` (int, default 5) | Fetch + summarize medical records |
| `create_record` | `create_record.py` | required | `gender`, `age`, `clinical_text` (all optional) | Enter interview flow for record creation |
| `query_task` | `query_task.py` | -- | `status` (optional: pending\|completed) | Fetch + summarize doctor tasks |
| `create_task` | `create_task.py` | optional | `title` (required), `content`, `due_at` | Create a new task |
| `query_patient` | `query_patient.py` | -- | `query` (required, NL search string) | Natural language patient search |
| `daily_summary` | `daily_summary.py` | -- | -- | Aggregated daily overview of tasks, patients, records |
| `general` | `general.py` | -- | -- | Fallback greeting / chitchat |

**`review_record` is NOT a routing intent** -- it is a UI-only flow. Doctor
clicks a pending_review record in the UI, frontend calls the review API
directly, no routing LLM involved.

### Non-Routing Flows (UI-Triggered)

These flows bypass routing entirely and have their own `LayerConfig`:

| Flow | Config | Prompt | Description |
|------|--------|--------|-------------|
| Routing | `ROUTING_LAYERS` | `intent/routing.md` | Intent classification (used by the router itself) |
| Review/Diagnosis | `REVIEW_LAYERS` | `intent/diagnosis.md` | Differential diagnosis pipeline |
| Patient Interview | `PATIENT_INTERVIEW_LAYERS` | `intent/patient-interview.md` | Patient pre-consultation interview |

---

## 5. Prompt Architecture

### 6-Layer Prompt Composer

All LLM calls use a shared prompt composer (`agent/prompt_composer.py`) that
assembles messages from 6 layers:

```
Layer 1  system/base.md              Identity, safety, precedence rules
Layer 2  common/{specialty}.md       Specialty knowledge (e.g. neurology)
Layer 3  intent/{intent}.md          Action-specific rules + few-shot examples
Layer 4  Doctor knowledge            Per-intent KB slice from DB (auto-loaded)
Layer 5  Patient context             Records, collected state, history
Layer 6  User message                Actual doctor/patient input
```

### Two Composition Patterns

**Pattern 1 -- Single-turn** (routing, query, diagnosis):
```
system: Layers 1-3 (instructions only)
user:   Layers 4-6 with XML tags (<doctor_knowledge>, <patient_context>, <doctor_request>)
```

**Pattern 2 -- Conversation** (doctor interview, patient interview):
```
system:    Layers 1-5 (instructions + KB + patient state)
history:   user/assistant conversation turns
user:      Layer 6 only (latest input, plain text)
```

Pattern 2 puts KB + context in system because conversation history occupies
the user/assistant turns. KB rules in system = treated as behavioral
constraints across all turns.

### LayerConfig

`agent/prompt_config.py` defines `INTENT_LAYERS` -- a dict mapping each
`IntentType` to a `LayerConfig` dataclass:

```python
@dataclass(frozen=True)
class LayerConfig:
    system: bool = True           # Layer 1: system/base.md
    domain: bool = False          # Layer 2: common/{specialty}.md
    intent: str = "general"       # Layer 3: intent/{intent}.md
    load_knowledge: bool = False  # Layer 4: doctor KB items
    patient_context: bool = False # Layer 5: patient records/state
    conversation_mode: bool = False  # Pattern 1 (False) or Pattern 2 (True)
```

An assert at import time ensures every `IntentType` has a config entry --
adding a new intent without a `LayerConfig` crashes at server startup.

### Layer Usage Matrix

```
Intent             | Pattern | Domain | Intent Prompt    | Dr Knowledge                         | Patient Ctx
-------------------|---------|--------|------------------|--------------------------------------|------------
routing            | single  |        | routing          | all (load_knowledge=True)            |
create_record      | convo   |   Y    | interview        | all (load_knowledge=True)            |    Y
query_record       | single  |        | query            | all (load_knowledge=True)            |    Y
query_task         | single  |        | query            | all (load_knowledge=True)            |
create_task        | single  |        | general          | all (load_knowledge=True)            |
query_patient      | single  |        | query            | all (load_knowledge=True)            |    Y
daily_summary      | single  |        | general          | all (load_knowledge=True)            |
general            | single  |        | general          | all (load_knowledge=True)            |
patient_interview  | convo   |   Y    | patient-interview| all (load_knowledge=True)            |    Y
review/diagnosis   | single  |   Y    | diagnosis        | all (load_knowledge=True)            |    Y
```

### Knowledge Categories

Doctor knowledge items (`doctor_knowledge_items` table) are categorized. Each
category maps to specific LLM intent layers:

| Category | Chinese Name | Injected Into |
|----------|-------------|---------------|
| `interview_guide` | 问诊指导 | Interview LLM |
| `diagnosis_rule` | 诊断规则 | Review/diagnosis LLM |
| `red_flag` | 危险信号 | Interview LLM + Review/diagnosis LLM |
| `treatment_protocol` | 治疗方案 | Review/diagnosis LLM |
| `custom` | 自定义 | All intents (always injected) |

Doctor knowledge outranks patient context in the prompt stack. If the doctor's
KB says "偏头痛首选曲普坦" but a past case used a different drug, the doctor's
stated preference wins (enforced by prompt ordering).

### Structured Output

All LLM calls returning structured data use `instructor` (JSON mode) +
Pydantic response models via `agent/llm.py:structured_call()`. Instructor
handles schema enforcement, validation, and retries. Prompts do NOT contain
JSON format specifications -- Pydantic models are the single source of truth
for output structure.

Key response models:
- `RoutingResult` -- routing LLM output (intent + entities)
- `InterviewLLMResponse` -- interview field collection
- `DiagnosisLLMResponse` -- differential diagnosis + workup + treatment
- `StructuringLLMResponse` -- text -> structured clinical record

---

## 6. Database Schema

**15 tables** across SQLite (dev) / MySQL (prod). All fields with fixed value
sets use `(str, Enum)`.

### Core Data (9 tables)

**`doctors`** -- Doctor identity and profile.
```
doctor_id (PK), name, specialty, department, phone,
year_of_birth, clinic_name, bio, created_at, updated_at
```

**`doctor_wechat`** -- WeChat/WeCom channel binding (optional).
```
doctor_id (PK, FK->doctors), wechat_user_id, mini_openid, created_at
```

**`patients`** -- Patient identity, scoped to a doctor.
```
id (PK), doctor_id (FK->doctors), name, gender (str, Enum),
year_of_birth, phone, created_at
```

**`patient_auth`** -- Portal access credentials (optional).
```
patient_id (PK, FK->patients), access_code (hashed),
access_code_version, created_at
```

**`medical_records`** -- Clinical records with structured fields and outcome data.
```
id (PK), patient_id (FK->patients), doctor_id (FK->doctors),
version_of (FK->medical_records.id, nullable),
record_type (str, Enum: visit|import|interview_summary),
status (str, Enum: interview_active|pending_review|completed),
tags (JSON), department,
-- History (7 fields)
chief_complaint, present_illness, past_history,
allergy_history, personal_history, marital_reproductive, family_history,
-- Examination (3 fields)
physical_exam, specialist_exam, auxiliary_exam,
-- Diagnosis
diagnosis,
-- Orders (3 fields)
treatment_plan, orders_followup, suggested_tasks (JSON),
-- Outcome (absorbs former case_history table)
final_diagnosis, treatment_outcome, key_symptoms,
-- Meta
content (denormalized text summary), created_at, updated_at
```

Design notes:
- Clinical columns replace structured JSON -- queryable and indexable.
- Append-only versioning: edits create new row with `version_of` FK.
- Outcome fields (`final_diagnosis`, `treatment_outcome`, `key_symptoms`)
  absorb the former `case_history` table. "Similar cases" = query
  `medical_records` by `chief_complaint`/`key_symptoms`.
- Review queue = `WHERE status='pending_review'`.
- AI diagnosis fields (`ai_diagnosis`, `doctor_decisions`) have been removed
  from this table, replaced by the `ai_suggestions` table.

**`ai_suggestions`** -- Per-item AI diagnosis suggestions with doctor decisions.
```
id (PK), record_id (FK->medical_records), doctor_id,
section (str, Enum: differential|workup|treatment),
content, detail, confidence, urgency, intervention,
decision (str, Enum: confirmed|rejected|edited|custom),
edited_text, reason, decided_at,
is_custom (boolean), created_at
```

Replaces the former `diagnosis_results` table. Uses a row-per-item approach:
each AI suggestion (differential, workup item, or treatment item) is a
separate row. Doctor decisions are recorded directly on each row.

**`doctor_knowledge_items`** -- Per-doctor reusable knowledge snippets.
```
id (PK), doctor_id (FK->doctors), content,
category (str, Enum: interview_guide|diagnosis_rule|red_flag|
          treatment_protocol|custom),
reference_count, created_at, updated_at
```

**`doctor_chat_log`** -- Doctor <-> AI conversation history.
```
id (PK), doctor_id, session_id (UUID v4), patient_id,
role (str, Enum: user|assistant), content, created_at
```

**`patient_messages`** -- Patient <-> Doctor/AI message history.
```
id (PK), patient_id (FK->patients), doctor_id (FK->doctors),
content, direction (str, Enum: inbound|outbound),
source (str, Enum: patient|ai|doctor), sender_id,
reference_id, triage_category, structured_data (JSON),
ai_handled (boolean), created_at
```

### Workflow State (1 table)

**`interview_sessions`** -- Multi-turn clinical field collection state.
```
id (PK, UUID v4), doctor_id, patient_id,
status (str, Enum: interviewing|confirmed|abandoned),
mode (str, Enum: patient|doctor),
collected (JSON), conversation (JSON),
turn_count, created_at, updated_at
```

### System/Infrastructure (5 tables)

**`audit_log`** -- Compliance audit trail.
```
id (PK), ts, doctor_id, action, resource_type, resource_id,
ip, trace_id, ok
```

**`invite_codes`** -- Doctor signup gating.
```
code (PK), doctor_id, doctor_name, active,
created_at, expires_at, max_uses, used_count
```

**`runtime_tokens`** -- WeChat access token cache.
```
token_key (PK), token_value, expires_at, updated_at
```

**`scheduler_leases`** -- Distributed lock for task notification scheduler.
```
lease_key (PK), owner_id, lease_until, updated_at
```

### Record Lifecycle State Machine

```
(interview_active)
  |
  +-- doctor confirms -> completeness check
  |     +-- all key fields filled -> (completed)
  |     +-- diagnosis/treatment/followup missing -> (pending_review) -> diagnosis pipeline
  |
  +-- doctor abandons -> (deleted, no record saved)
  +-- timeout -> (expired/deleted)

(pending_review)
  |
  +-- doctor accepts some/all suggestions -> (completed)
  +-- doctor rejects all suggestions -> (completed, doctor override)
```

---

## 7. Clinical Decision Support Pipeline

### Diagnosis Pipeline

Triggered when a record's `diagnosis`, `treatment_plan`, or `orders_followup`
fields are incomplete after interview confirmation. The record enters
`pending_review` status.

**Pipeline steps:**
1. Record saved with `status=pending_review`
2. Gather context (parallel):
   - Doctor knowledge: `diagnosis_rule` + `red_flag` + `treatment_protocol` categories
   - Patient's past records
   - Similar symptom records (keyword search on `chief_complaint`/`key_symptoms`)
3. Build prompt via 6-layer composer using `REVIEW_LAYERS` config
4. Call diagnosis LLM (structured output via Instructor) -> `DiagnosisLLMResponse`
5. Save individual items to `ai_suggestions` table (one row per differential/workup/treatment)
6. Update record status -> `pending_review` (with suggestions available)
7. Doctor reviews each suggestion: confirm / reject / edit

**DiagnosisLLMResponse structure:**
```python
differentials: List[DiagnosisDifferential]  # condition, confidence (低/中/高), detail
workup: List[DiagnosisWorkup]               # test, detail, urgency (常规/紧急/急诊)
treatment: List[DiagnosisTreatment]         # drug_class, intervention (手术/药物/观察/转诊), detail
red_flags: List[str]                        # urgent findings requiring immediate action
```

**Execution:** async background task via APScheduler. Record saves immediately,
diagnosis runs asynchronously. Graceful degradation if LLM fails -- record is
available for manual review without AI suggestions.

> **Note:** Case matching via RAG embeddings is **disabled**. The `embedding.py`
> module was deleted and `matched_cases` is always `[]`. "Similar cases" relies
> on keyword-based search of `medical_records` by `chief_complaint` and
> `key_symptoms` columns. Full RAG re-enablement is deferred.

### Safety Guardrails

- Never auto-confirm any diagnosis -- doctor MUST explicitly confirm each item
- Red flag detection triggers prominent UI alerts
- Drug classes only (e.g., "Corticosteroid for cerebral edema") -- no specific doses
- Confidence levels: 低 = consider, 中 = likely, 高 = highly suggestive
- Audit trail: every AI suggestion + doctor decision logged with timestamp
- Fallback: if LLM fails, show structured record without diagnosis
- Disclaimer always present: "AI建议仅供参考，最终诊断由医生决定"

### Knowledge Base

Doctor knowledge items are managed via the admin UI (CRUD only, no chat
commands). Items are categorized and automatically injected into relevant
LLM prompts by the 6-layer composer based on the `INTENT_LAYERS` config.

Categories map to prompt intent layers (see Section 5). `red_flag` spans
both interview and diagnosis intents. `custom` is injected into all prompts.

---

## 8. Channels & API Routes

### Web Dashboard (Primary)

| Route | Handler | Description |
|-------|---------|-------------|
| `POST /api/records/chat` | `channels/web/chat.py` | Doctor chat -> agent pipeline |
| `POST /api/records/interview/*` | `channels/web/doctor_interview.py` | Interview turn, confirm, cancel |
| `GET/POST/DELETE /api/manage/*` | `channels/web/ui/` | Admin: knowledge, profile, patients |
| `GET/POST/PUT/DELETE /api/tasks/*` | `channels/web/tasks.py` | Task CRUD |
| `GET /api/export/*` | `channels/web/export.py` | PDF/JSON export |
| `POST /api/import/*` | `channels/web/import_routes.py` | Image/PDF import |
| `POST /api/auth/*` | `channels/web/auth.py` | JWT authentication |
| `POST /api/unified-auth/*` | `channels/web/unified_auth_routes.py` | Unified login (doctor + patient) |

### Patient Portal

| Route | Handler | Description |
|-------|---------|-------------|
| `POST /api/patient/interview/*` | `channels/web/patient_interview_routes.py` | Patient pre-consultation interview |
| `POST /api/patient/chat` | `channels/web/patient_portal.py` | Patient triage pipeline |
| `GET /api/patient/*` | `channels/web/patient_portal.py` | Patient records, auth |

### WeChat/WeCom

| Route | Handler | Description |
|-------|---------|-------------|
| `POST /wechat` | `channels/wechat/router.py` | WeChat webhook (message receive + verify) |

WeChat messages are routed through the same `handle_turn` pipeline as web
chat. Notifications are sent via customer service (KF) messages.

---

## 9. Task System

### Task Types

5 task types defined in `TaskType(str, Enum)`:

| Type | Description |
|------|-------------|
| `general` | Default: to-dos, reminders, appointments |
| `review` | Auto-created when a record enters `pending_review`. Links to the record. |
| `follow_up` | Follow-up appointments and check-ins |
| `medication` | Medication-related reminders |
| `checkup` | Scheduled examination reminders |

### Task Lifecycle

```
pending -> notified -> completed
                    -> cancelled
```

Tasks can be created via:
- **UI:** doctor fills form directly (no LLM)
- **Chat:** routing LLM -> `intent=create_task` -> handler creates task
- **Diagnosis auto:** review LLM includes `suggested_tasks` in output,
  auto-created when doctor confirms review

### Scheduling

APScheduler runs on an interval (configurable via `TASK_SCHEDULER_INTERVAL_MINUTES`,
default 1 minute) or cron schedule. Checks for due tasks and sends notifications.
Distributed lock via `scheduler_leases` table prevents duplicate notifications
in multi-instance deployments.

---

## 10. Startup & Initialization

Application startup is managed through `src/startup/` and orchestrated by the
FastAPI lifespan handler in `main.py`.

### Startup Sequence

```
1. enforce_production_guards()    # Verify required secrets (HMAC key, portal secret)
2. init_database()                # Create tables, run migrations, backfill doctors, seed prompts
3. run_warmup()                   # Jieba init + Ollama/LKEAP connectivity (background)
4. _startup_background_workers()  # Observability writer + audit drain async tasks
5. _startup_recovery()            # Log pending tasks, re-queue stale messages
6. configure_scheduler()          # Register all APScheduler jobs
7. scheduler.start()              # Begin scheduled job execution
```

### Startup Modules

**`startup/db_init.py`** -- Database initialization:
- `create_tables()` -- creates all SQLAlchemy tables
- `run_alembic_migrations()` -- applies pending Alembic migrations (fails hard in
  production, warns in dev)
- `backfill_doctors_registry()` -- ensures all known doctors exist in the `doctors` table
- `seed_prompts()` -- seeds initial system data
- `enforce_production_guards()` -- verifies `WECHAT_ID_HMAC_KEY` and
  `PATIENT_PORTAL_SECRET` are set in production; refuses to start if missing

**`startup/scheduler.py`** -- APScheduler configuration:
- Task notification timer: interval or cron mode (env-configurable)
- Chat log cleanup: daily at 04:30 (deletes rows older than 365 days)
- Audit log retention: monthly on day 1 at 03:00 (deletes rows older than 7 years)
- Turn log pruning: daily at 05:30

**`startup/warmup.py`** -- Pre-flight connectivity:
- Jieba segmentation dictionary initialization (synchronous, blocks startup)
- Ollama warmup: pings candidate base URLs with retry + exponential backoff,
  selects the first reachable endpoint, overrides env vars if fallback URL used.
  Runs in background (does not block app readiness).
- LKEAP warmup: establishes TCP/TLS connection to Tencent LKEAP for faster
  first request. Runs in background.

### Shutdown

On shutdown, the scheduler is stopped and all background worker tasks
(disk writer, audit drain) are cancelled.
