# 专科医师AI智能体 — Architecture

> Last updated: 2026-03-02 · Phase 3 in progress

---

## Project Goal

A WeChat-native AI assistant for specialist doctors (cardiology & oncology focus).
Doctors interact naturally via WeChat messages or voice; the system manages patient
records, structures clinical notes into standardised fields, and persists everything
locally — with no mandatory cloud dependency.

---

## Phase Roadmap

| Phase | Status | Focus |
|-------|--------|-------|
| **Phase 1** | ✅ Done | Voice/text → structured medical record via LLM |
| **Phase 2** | ✅ Done | Patient management, DB persistence, WeChat bot |
| **Phase 3** | 🔄 In progress | LLM agent dispatch, conversation memory, specialist corpus, local ASR |

---

## Current Architecture (Phase 3)

```
WeChat Official Account
        │  XML over HTTPS
        ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI App (:8000)                    │
│                                                          │
│  POST /wechat                                            │
│    │                                                     │
│    ├─ stateful flows (priority)                          │
│    │    ├─ pending_create → collect gender/age           │
│    │    └─ interview → guided intake Q&A                 │
│    │                                                     │
│    └─ background task → _handle_intent_bg()             │
│         │                                               │
│         ├─ maybe_compress()  ← memory.py                │
│         ├─ load_context_message()                       │
│         └─ agent_dispatch()  ← agent.py (single LLM)    │
│              ├─ create_patient → DB                     │
│              ├─ add_record                              │
│              │    ├─ structured_fields → MedicalRecord  │
│              │    ├─ (fallback) structuring.py → MR     │
│              │    └─ save_record → DB                   │
│              ├─ query_records → DB                      │
│              ├─ list_patients → DB                      │
│              └─ unknown → chat_reply (natural)          │
│                                                          │
│  POST /api/records/chat      (CLI / REST)                │
│  POST /api/records/from-text                             │
│  POST /api/records/from-audio                            │
│  POST /api/records/from-image                            │
│  GET  /admin  (SQLAdmin UI)                              │
│  POST /wechat/menu  (admin: push menu to WeChat)         │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────┐   ┌──────────────────────────┐   ┌──────────────────┐
│  patients.db  │   │  Ollama (localhost:11434) │   │  faster-whisper  │
│  (SQLite)     │   │  qwen2.5:7b (default)    │   │  large-v3 local  │
└───────────────┘   └──────────────────────────┘   └──────────────────┘
```

---

## Directory Structure

```
├── main.py                   # FastAPI app, lifespan (DB init + warmup), SQLAdmin
├── requirements.txt
├── patients.db               # SQLite (auto-created on startup)
│
├── routers/
│   ├── wechat.py             # WeChat XML handler, stateful flows, background dispatch
│   └── records.py            # REST: /chat, /from-text, /from-audio
│
├── services/
│   ├── agent.py              # LLM function-calling dispatch → IntentResult
│   ├── intent.py             # Intent enum + IntentResult schema
│   ├── intent_rules.py       # Rule-based fallback (jieba + regex), used for reference
│   ├── structuring.py        # LLM → MedicalRecord JSON (specialist-aware prompt)
│   ├── session.py            # In-memory DoctorSession (history, patient, interview)
│   ├── memory.py             # Rolling window compress → DB; context injection
│   ├── interview.py          # Guided intake Q&A state machine (7 steps)
│   ├── transcription.py      # faster-whisper local ASR (falls back to OpenAI)
│   ├── vision.py             # Vision LLM image → extracted clinical text
│   ├── voice.py              # WeChat media download + ffmpeg → 16kHz WAV
│   └── wechat_menu.py        # Doctor-only menu definition + creation API
│
├── db/
│   ├── engine.py             # Async SQLAlchemy engine + AsyncSessionLocal
│   ├── models.py             # Patient, MedicalRecordDB, DoctorContext ORM models
│   ├── init_db.py            # create_tables() called at startup
│   └── crud.py               # All DB operations
│
├── models/
│   └── medical_record.py     # Pydantic schema (8 clinical fields)
│
├── utils/
│   └── log.py                # Timestamped print wrapper
│
├── tools/
│   ├── chat.py               # Interactive CLI tester → POST /api/records/chat
│   ├── db_inspect.py         # CLI: patients / records / record <id>
│   ├── seed_db.py            # CLI: export/import patients.db ↔ dev/seed_data.json
│   └── start_db_ui.sh        # datasette on port 8001
│
├── train/
│   └── data/                 # Training corpus (cardiology + oncology cases)
│
└── tests/
    ├── conftest.py
    ├── test_crud.py
    ├── test_session.py
    ├── test_intent.py
    ├── test_intent_rules.py
    └── test_wechat_intent.py
```

---

## Key Components

### Intent Dispatch (`services/agent.py`)

Primary dispatch uses **LLM function calling** (tool use). The LLM selects one of
four tools based on the doctor's message and any conversation history:

| Tool | Triggered when |
|------|---------------|
| `add_medical_record` | Any clinical content: symptoms, vitals, labs, diagnosis, treatment, specialist content (PCI, chemo, CEA, EGFR…) |
| `create_patient` | Explicit patient registration with no clinical content |
| `query_records` | Doctor asks to view/retrieve past records |
| `list_patients` | Doctor asks for their patient roster |
| *(no tool)* | Casual conversation → `chat_reply` returned directly |

The `ROUTING_LLM` env var selects the LLM backend (defaults to `STRUCTURING_LLM`).

### Specialist Corpus Support

The structuring prompt (`services/structuring.py`) is tuned for:
- **Cardiology**: STEMI, PCI, ablation follow-up, BNP/EF trends, Holter, NYHA, LDL-C
- **Oncology**: chemo cycles, CEA/ANC trends, EGFR/HER2, targeted therapy, G-CSF
- **Trend data**: "BNP 980 (上次 600)", "EF 50% (上次 60%, 趋势下降)"
- **Provisional diagnosis**: "考虑：不稳定型心绞痛；待排：急性心衰"
- **Planned tests** → `treatment_plan`; **existing results** → `auxiliary_examinations`

### Conversation Memory (`services/memory.py`)

Each doctor has a rolling window of up to 10 turns in `DoctorSession.conversation_history`.

```
message received
  → maybe_compress()   # if window full (≥10 turns) OR idle ≥30 min
  │    LLM summarises history → persists to DoctorContext table
  │    clears in-memory window
  └─ load_context_message()  # if window empty, inject last summary as system msg
       → agent_dispatch(text, history=history)
       → push_turn(doctor_id, text, reply)  # append to window
```

### Local Voice Transcription (`services/transcription.py`)

Uses **faster-whisper** with a medical terminology prompt to bias transcription toward
correct drug names, lab values, and disease terms. The model is loaded lazily on first
call and reused across requests.

| Env var | Default | Options |
|---------|---------|---------|
| `WHISPER_MODEL` | `large-v3` | `medium`, `small`, `base` |
| `WHISPER_DEVICE` | `cpu` | `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `float16` (GPU), `float32` |

Falls back to OpenAI Whisper API if `faster-whisper` is not installed.

**Audio pipeline:**
```
WeChat voice (AMR/SILK)
  → ffmpeg (voice.py) → 16kHz mono WAV
  → faster-whisper (transcription.py) → Chinese text
  → agent_dispatch / interview / pending_create
```

**Image pipeline:**
```
WeChat image (JPEG)
  → download_voice() (same WeChat media endpoint, vision.py)
  → vision LLM (qwen2.5vl:7b via Ollama) → extracted clinical text
  → agent_dispatch / interview / pending_create
```

### Guided Interview (`services/interview.py`)

7-step structured intake triggered by menu or "开始问诊":

```
患者姓名 → 主诉 → 持续时间 → 严重程度 → 伴随症状 → 既往史 → 体格检查
  → compile_text() → structure_medical_record() → save_record()
```

Supports voice input at any step. Doctor can cancel with "取消".

### WeChat Message Flow

```
POST /wechat
  │
  ├─ AES decrypt (if encrypted)
  ├─ parse XML
  │
  ├─ event/CLICK → _handle_menu_event() → synchronous XML reply
  ├─ voice → ACK immediately → _handle_voice_bg() [background]
  ├─ image → ACK immediately → _handle_image_bg() [background]
  ├─ pending_create state → _handle_pending_create() → sync reply
  ├─ interview state → _handle_interview_step() → sync reply
  │
  └─ text → ACK "⏳ 正在处理…" → _handle_intent_bg() [background]
                                    └─ result delivered via customer service API
```

All LLM calls run in the background to avoid WeChat's 5-second response timeout.

### Doctor Task Notifications (`services/tasks.py` + APScheduler)

Doctors receive WeChat push notifications for follow-up reminders, emergency records, and appointments.

**Task lifecycle:**
```
add_record (with follow_up_plan or is_emergency)
  → create_follow_up_task() / create_emergency_task()
       ↓ DoctorTask row in doctor_tasks (status=pending)
  → Emergency: send_task_notification() called immediately
  → Follow-up/Appointment: APScheduler job fires every 1 min
       → check_and_send_due_tasks() queries due_at ≤ now AND notified_at IS NULL
       → send_doctor_notification() transport dispatch
       → mark_task_notified() sets notified_at
```

**Task types and triggers:**

| Type | Trigger | due_at |
|------|---------|--------|
| `follow_up` | `record.follow_up_plan` is set after add_record | now + extracted days |
| `emergency` | `intent_result.is_emergency` is True | None (immediate push) |
| `appointment` | Doctor says "预约/安排复诊 + time" | appointment_dt - 1 hour |

**Doctor completes a task:**
- Via WeChat: reply `完成 5` (regex shortcut, bypasses LLM) or say "完成任务5"
- Via REST: `PATCH /api/tasks/5?doctor_id=xxx {"status": "completed"}`

**APScheduler:**
- In-memory `AsyncIOScheduler`, interval=1 minute, started in FastAPI lifespan
- On restart, unnotified tasks are re-queued within 1 minute (queried by `notified_at IS NULL`)

**Notification transport:**
- `NOTIFICATION_PROVIDER=log` (default): local/dev sink, no external dependency
- `NOTIFICATION_PROVIDER=wechat`: WeChat Customer Service API

**WeChat push helper refactoring:**
- `_token_cache`, `_get_config`, `_get_access_token`, `_split_message`, `_send_customer_service_msg`
  moved to `services/wechat_notify.py` to avoid circular imports from `services/tasks.py`

### Patient Risk + Timeline (v1)

Patient-level risk metadata is now persisted and queryable:

- `primary_risk_level` (`low` | `medium` | `high` | `critical`)
- `risk_tags` (JSON text list)
- `risk_score` (integer)
- `follow_up_state` (`not_needed` | `scheduled` | `due_soon` | `overdue`)
- `risk_computed_at`
- `risk_rules_version`

Risk is recomputed after record writes (`db/crud.py::save_record`) using
`services/patient_risk.py` and stored on the patient row.

When `AUTO_FOLLOWUP_TASKS_ENABLED=true`, follow-up plan writes can auto-create
`doctor_tasks` rows with:

- `trigger_source = risk_engine`
- `trigger_reason = ...`

`record_id + task_type + trigger_source + pending` is used for idempotent de-dup.

Timeline view is assembled by `services/patient_timeline.py` and exposed via:

- `GET /api/manage/patients/{patient_id}/timeline`

Manage APIs also support risk-aware filtering/grouping:

- `GET /api/manage/patients?risk=&follow_up_state=&stale_risk=`
- `GET /api/manage/patients/grouped-risk`

### Medical Record Structuring (`services/structuring.py`)

| Provider | Model | Note |
|----------|-------|------|
| `ollama` (default) | `qwen2.5:7b` (or `OLLAMA_MODEL`) | Fully local |
| `deepseek` | `deepseek-chat` | Cloud |
| `groq` | `llama-3.3-70b-versatile` | Cloud |

`max_tokens=1500` to accommodate complex specialist records with multiple diagnoses
and trend data. Compliant with 《病历书写基本规范》（卫医政发〔2010〕11号）.

### Database (`patients.db`)

```
patients
  id · doctor_id · name · gender · age · created_at

medical_records
  id · patient_id (FK→patients) · doctor_id
  chief_complaint · history_of_present_illness · past_medical_history
  physical_examination · auxiliary_examinations · diagnosis
  treatment_plan · follow_up_plan · created_at

doctor_context
  doctor_id (PK) · summary · updated_at
```

### Current Patient Record Data Model (Canonical)

This section reflects the live ORM and API behavior in:
- `db/models.py`
- `db/crud.py`
- `routers/records.py`
- `routers/neuro.py`

#### Entity Relationship (doctor-scoped)

```text
doctor_id (logical tenant key)
   ├─ patients (1:N by doctor_id)
   │    └─ medical_records (1:N via patient_id, nullable)
   ├─ medical_records (direct filter by doctor_id)
   ├─ neuro_cases (direct filter by doctor_id; optional link to patient_id)
   └─ doctor_contexts (1:1 by doctor_id)
```

#### Tables and Fields

`patients`
- `id` (PK, autoincrement)
- `doctor_id` (indexed, required)
- `name` (required)
- `gender` (nullable)
- `age` (nullable)
- `created_at` (UTC timestamp)

`medical_records`
- `id` (PK, autoincrement)
- `patient_id` (FK -> `patients.id`, nullable)
- `doctor_id` (indexed, required)
- `chief_complaint` (nullable in DB; required in Pydantic input model)
- `history_of_present_illness` (nullable)
- `past_medical_history` (nullable)
- `physical_examination` (nullable)
- `auxiliary_examinations` (nullable)
- `diagnosis` (nullable)
- `treatment_plan` (nullable)
- `follow_up_plan` (nullable)
- `created_at` (UTC timestamp)

`neuro_cases`
- `id` (PK, autoincrement)
- `doctor_id` (indexed, required)
- `patient_id` (FK -> `patients.id`, nullable)
- Promoted scalar columns:
  - `patient_name` (nullable)
  - `gender` (nullable)
  - `age` (nullable)
  - `encounter_type` (nullable)
  - `chief_complaint` (nullable)
  - `primary_diagnosis` (nullable)
  - `nihss` (nullable)
- Full payload columns:
  - `raw_json` (nullable, full structured case JSON)
  - `extraction_log_json` (nullable, extraction log JSON)
- `created_at` (UTC timestamp)

`doctor_contexts`
- `doctor_id` (PK)
- `summary` (nullable)
- `updated_at` (UTC timestamp)

`system_prompts`
- `key` (PK)
- `content` (required)
- `updated_at` (UTC timestamp)

#### Runtime Write Paths

`POST /api/records/chat`
- `create_patient` intent: inserts into `patients`.
- `add_record` intent:
  - finds patient by (`doctor_id`, `name`);
  - auto-creates patient if not found;
  - inserts into `medical_records` with resolved `patient_id`.

`POST /api/records/from-text|from-image|from-audio`
- returns structured `MedicalRecord` but does not persist by itself.

`POST /api/neuro/from-text`
- extracts `NeuroCase` + `ExtractionLog`;
- persists to `neuro_cases` (current route saves without `patient_id` link).

Memory and prompt writes
- `services/memory.py` updates `doctor_contexts`.
- Admin/UI prompt edits update `system_prompts`.

#### Constraints and Behavioral Notes

- Multi-tenant boundary is `doctor_id` (logical scope used in all CRUD reads/writes).
- `medical_records.patient_id` is nullable, so orphan records are allowed.
- No DB uniqueness constraint on (`doctor_id`, `name`) in `patients`; duplicates are currently possible.
- `medical_records.chief_complaint` is nullable at DB layer for compatibility, though extraction model expects it.
- `neuro_cases` stores both queryable promoted columns and complete JSON payloads for audit/replay.

---

## Configuration (`.env`)

### LLM Roles

Two independent LLM roles, each configurable separately:

| Variable | Role | Tokens/call | Requirement |
|----------|------|-------------|-------------|
| `ROUTING_LLM` | Single LLM: intent routing + clinical field extraction (8 fields) + natural reply | ~600 | Function calling support |
| `STRUCTURING_LLM` | Standalone: REST direct endpoints, interview completion, fallback | ~800 | JSON mode |
| `VISION_LLM` | Image OCR / text extraction | ~2000 | Vision / multimodal support |

`ROUTING_LLM` falls back to `STRUCTURING_LLM` if not set. Both accept `ollama`, `deepseek`, or `groq`.

> **Single-LLM design (2026-03-02):** `ROUTING_LLM` now performs routing + structuring + natural reply in one call.
> `STRUCTURING_LLM` is used only for REST direct endpoints, guided interview completion, and as a fallback when
> the single-LLM call returns no clinical fields. See the Design Decisions section for full rationale.

```bash
# LLM for intent dispatch & function calling (~300 tokens/call)
ROUTING_LLM=ollama           # ollama | deepseek | groq

# LLM for medical record JSON generation (~800 tokens/call)
STRUCTURING_LLM=ollama       # ollama | deepseek | groq

# Ollama
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen2.5:7b           # or qwen2.5:14b, qwen2.5:32b, llama3.2
OLLAMA_VISION_MODEL=qwen2.5vl:7b  # vision model for image → text extraction

# Vision provider (image → text)
VISION_LLM=ollama            # ollama | openai

# Cloud LLMs (optional)
DEEPSEEK_API_KEY=sk-...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...        # required only when VISION_LLM=openai

# Local voice transcription
WHISPER_MODEL=large-v3       # large-v3 | medium | small | base
WHISPER_DEVICE=cpu           # cpu | cuda
WHISPER_COMPUTE_TYPE=int8    # int8 (CPU) | float16 (GPU)

# WeChat Official Account
WECHAT_TOKEN=
WECHAT_APP_ID=
WECHAT_APP_SECRET=
WECHAT_ENCODING_AES_KEY=

# Notification transport
NOTIFICATION_PROVIDER=log    # log | wechat

# Logging (console + optional rotating files)
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_DIR=logs
LOG_FILE=app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
TASK_LOG_TO_CONSOLE=false       # tasks logger to terminal (default off; still writes logs/tasks.log)
SCHEDULER_LOG_TO_CONSOLE=false  # apscheduler logger to terminal (default off; still writes logs/scheduler.log)
TASK_NOTIFY_RETRY_COUNT=3       # retries when background notification push fails
TASK_NOTIFY_RETRY_DELAY_SECONDS=1
TASK_DEV_ENDPOINT_ENABLED=false # enable POST /api/tasks/dev/run-notifier (dev-only)
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/wechat` | WeChat message webhook |
| `GET` | `/wechat` | WeChat server verification |
| `POST` | `/wechat/menu` | Push doctor menu to WeChat (admin) |
| `POST` | `/api/records/chat` | Agent chat endpoint (used by CLI tester) |
| `POST` | `/api/records/from-text` | Structure a text note directly |
| `POST` | `/api/records/from-audio` | Transcribe + structure audio file |
| `POST` | `/api/records/from-image` | Extract text from image + structure |
| `GET` | `/api/tasks` | List doctor tasks (filter by `doctor_id`, optional `status`) |
| `PATCH` | `/api/tasks/{task_id}` | Update task status (`completed` or `cancelled`) |
| `GET` | `/admin` | SQLAdmin database UI |

---

## Design Decisions

### Single-LLM Architecture (2026-03-02)

**Before:** Two sequential LLM calls per `add_record`:
1. Routing LLM (~300 tokens) → intent + patient meta
2. Structuring LLM (~1500 tokens) → 8-field MedicalRecord JSON
3. Hardcoded template reply string

**After:** Single LLM call per operation:
- Tool call → intent + patient meta + all 8 clinical fields
- `message.content` → natural Chinese reply to doctor
- Business logic (DB write, risk scoring, tasks) fires async

**Why:**
- Eliminates sequential LLM latency
- Natural conversation instead of template strings
- Simpler code, single failure surface
- OpenAI function calling API designed for simultaneous tool use + text response

**`structure_medical_record()` retained for:**
- `/from-text`, `/from-audio`, `/from-image` REST endpoints (direct structuring, no agent)
- Guided interview completion (7-step Q&A compiles to structured text)
- Fallback when LLM tool call returns no clinical fields

**Quality validation:** Re-run `python tools/train.py --clean` after model changes.

---

## Running Locally

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Start Ollama (keep in background)
ollama serve
ollama pull qwen2.5:7b       # recommended; or: ollama pull llama3.2

# 3. Copy and fill in env
cp .env.example .env

# 4. Start the API
uvicorn main:app --reload

# 5. Expose via ngrok for WeChat webhook
ngrok http 8000

# 6. Interactive CLI tester (no WeChat needed)
python tools/chat.py
```

---

## CLI Testing

```bash
# Interactive agent chat
python tools/chat.py                    # connects to localhost:8000
python tools/chat.py http://host:8000  # custom host

# DB inspection
python tools/db_inspect.py patients
python tools/db_inspect.py records
python tools/db_inspect.py record <id>

# DB seed (export / import)
python tools/seed_db.py --export              # dump patients.db → dev/seed_data.json
python tools/seed_db.py --import             # load dev/seed_data.json → patients.db
python tools/seed_db.py --reset --import     # wipe then import (clean dev reset)
python tools/seed_db.py --export --dry-run   # preview without writing

# DB UI
bash tools/start_db_ui.sh              # → http://localhost:8001
open http://localhost:8000/admin
```

---

## Known Limitations

| Issue | Plan |
|-------|------|
| Session lost on server restart | Conversation history in memory only; DoctorContext summary is persisted |
| Single-process (in-memory session) | Acceptable for MVP; needs Redis for multi-worker |
| faster-whisper large-v3 needs ~1.5 GB RAM | Use `WHISPER_MODEL=medium` on low-memory servers |
| No fine-tuned medical ASR model | `initial_prompt` bias covers most common terms; fine-tuning is Phase 4 |

---

## Directory Structure (Detailed)

```
├── main.py                   # FastAPI app + lifespan (DB init, warmup, SQLAdmin)
├── requirements.txt
├── patients.db               # SQLite (auto-created on startup)
├── CHANGELOG.md
├── ARCHITECTURE.md
├── CLAUDE.md                 # Project rules (code style, push workflow)
├── .env / .env.example
│
├── routers/
│   ├── wechat.py             # WeChat XML handler, stateful flows, background dispatch (583 lines)
│   └── records.py            # REST: /chat, /from-text, /from-audio, /from-image
│
├── services/
│   ├── agent.py              # LLM function-calling dispatch → IntentResult (4 tools)
│   ├── intent.py             # Intent enum + IntentResult schema + legacy rule-based fallback
│   ├── structuring.py        # LLM → MedicalRecord JSON (specialist-aware prompt, DB-backed)
│   ├── session.py            # In-memory DoctorSession (history, patient, interview state)
│   ├── memory.py             # Rolling window compress → DB; context injection on new session
│   ├── interview.py          # Guided intake Q&A state machine (7 steps)
│   ├── transcription.py      # faster-whisper local ASR (falls back to OpenAI Whisper API)
│   ├── vision.py             # Vision LLM image → extracted clinical text
│   ├── voice.py              # WeChat media download + ffmpeg → 16kHz WAV
│   └── wechat_menu.py        # Doctor menu definition + WeChat creation API
│
├── db/
│   ├── engine.py             # Async SQLAlchemy engine + AsyncSessionLocal + Base
│   ├── models.py             # ORM: Patient, MedicalRecordDB, DoctorContext, SystemPrompt
│   ├── init_db.py            # create_tables() + seed_prompts() called at startup
│   └── crud.py               # All DB operations (patients, records, context, prompts)
│
├── models/
│   └── medical_record.py     # Pydantic schema (8 clinical fields)
│
├── utils/
│   └── log.py                # Timestamped print wrapper
│
├── tools/
│   ├── chat.py               # Interactive CLI tester → POST /api/records/chat
│   ├── db_inspect.py         # CLI: patients / records / record <id>
│   ├── seed_db.py            # CLI: export/import patients.db ↔ dev/seed_data.json
│   ├── train.py              # Batch corpus training + verification runner
│   └── train_images.py       # Image pipeline training runner
│
├── train/
│   └── data/
│       ├── clinic_raw_cases_cardiology_v1.md   # 20 raw cases
│       ├── clinic_raw_cases_cardiology_v2.md   # 37 raw cases (improved diversity)
│       ├── image_cases_cardiology_v1.md        # Image extraction test cases
│       └── specialist_ai_structured_training_corpus_v2026_1.md
│
├── tests/
│   ├── conftest.py                # Async fixtures, mock LLM/DB, in-memory SQLite
│   ├── test_crud.py
│   ├── test_session.py
│   ├── test_intent.py
│   ├── test_structuring.py
│   ├── test_memory.py
│   ├── test_wechat_intent.py
│   └── integration/
│       ├── conftest.py            # Integration test setup (skips if deps not running)
│       ├── test_text_pipeline.py  # End-to-end text → record
│       └── test_image_pipeline.py # End-to-end image → record
│
├── debug/
│   └── iteration_2026-03-01.md   # Training run analysis, root causes, fixes applied
│
└── archive/                       # Deprecated docs and old code
```

---

## Database Schema (Full)

```
system_prompts
  key (PK)        — e.g. "structuring", "structuring.extension"
  content (Text)  — editable LLM prompt (60-second cache in structuring.py)
  updated_at

doctor_context
  doctor_id (PK)  — WeChat openid or CLI user
  summary (Text)  — LLM-compressed conversation (~120 chars)
  updated_at

patients
  id · doctor_id (indexed) · name · gender · age · created_at

medical_records
  id · patient_id (FK→patients, nullable) · doctor_id (indexed)
  chief_complaint · history_of_present_illness · past_medical_history
  physical_examination · auxiliary_examinations · diagnosis
  treatment_plan · follow_up_plan · created_at

doctor_tasks
  id · doctor_id (indexed) · patient_id (FK→patients, nullable)
  record_id (FK→medical_records, nullable)
  task_type (follow_up | emergency | appointment)
  title · content (nullable)
  status (pending | completed | cancelled)
  due_at (nullable) · notified_at (nullable) · created_at
```

---

## Test Suite

```bash
# Unit tests (no LLM or network needed — always run before push)
.venv/bin/python -m pytest tests/ -v          # 46 tests, all green

# Integration tests (requires uvicorn + ollama serve)
pytest tests/integration/                      # auto-skipped if deps not running

# Corpus validation (optional, expensive)
python tools/train.py --clean [--cases ...]    # requires Ollama
python tools/train_images.py                   # image pipeline validation
```

Key test conventions:
- All LLM calls mocked with `AsyncMock` / `patch`
- DB uses in-memory SQLite (`sqlite+aiosqlite:///:memory:`)
- `_sessions` dict cleared between tests to isolate session state
- `pytest.ini` sets `asyncio_mode = auto`, `testpaths = tests`

**Training results (2026-03-01):**
- `qwen2.5:7b` — 20/20 cardiology v1, 37/37 cardiology v2 ✅
- `llama3.2` — hallucinates Chinese patient names (~2/37 cases) ⚠️

---

## Feature Gaps & Next Phase

| Gap | Impact | Complexity | Phase |
|-----|--------|------------|-------|
| Session history lost on restart (summary only persists) | Medium | Low — persist turns to DB | 4 |
| No audit trail on record creation/edits | Medium | Low — add `created_by` field | 4 |
| Generic "处理失败" error messages | Medium | Low — per-failure-mode messages | 4 |
| Single-process in-memory session | High | High — needs Redis for multi-worker | 5 |
| No bulk export (records → CSV/JSON) | Medium | Medium | 4 |
| No role-based access or patient sharing | Low | High | 5 |
| No fine-tuned medical ASR model | Low | High — Phase 4 scope | 4 |
| Hardcoded Chinese (no i18n) | Low | High | — |
