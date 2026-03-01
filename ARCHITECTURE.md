# 专科医师AI智能体 — Architecture & Progress

> Last updated: 2026-03-01 · Phase 2 complete

---

## Project Goal

A WeChat-native AI assistant for specialist doctors. Doctors interact naturally via WeChat messages; the system manages patient records, structures clinical notes, and stores everything in a local database — with no dependency on cloud LLMs for production.

---

## Phase Roadmap

| Phase | Status | Focus |
|-------|--------|-------|
| **Phase 1** | ✅ Done | Voice/text → structured medical record via LLM |
| **Phase 2** | ✅ Done | Patient management, DB persistence, intent detection, WeChat bot |
| Phase 3 | Planned | Conversational AI agent (tool calling), proactive follow-up |

---

## Current Architecture (Phase 2)

```
WeChat Official Account
        │  XML over HTTPS
        ▼
┌─────────────────────────────────────────────────────┐
│                   FastAPI App (:8000)                │
│                                                     │
│  /wechat  ──► intent_rules (jieba, <5ms)            │
│               │                                     │
│               ├─ create_patient ──► DB              │
│               ├─ add_record ──────► LLM ──► DB      │
│               ├─ query_records ───► DB              │
│               └─ unknown ─────────► help message    │
│                                                     │
│  /api/patients  (REST CRUD)                         │
│  /api/records   (REST CRUD)                         │
│  /admin         (SQLAdmin UI)                       │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────┐     ┌──────────────────────────┐
│  patients.db  │     │  Ollama (localhost:11434) │
│  (SQLite)     │     │  qwen2.5:7b              │
└───────────────┘     └──────────────────────────┘
```

---

## Directory Structure

```
app/
├── main.py                  # FastAPI app, lifespan (DB init + warmup), SQLAdmin
├── requirements.txt
├── patients.db              # SQLite database (auto-created on startup)
│
├── routers/
│   ├── wechat.py            # WeChat XML handler, intent dispatch, message formatting
│   ├── patients.py          # REST: POST /api/patients, GET /api/patients/{id}/records
│   └── records.py           # REST: POST /api/records/from-text, from-audio
│
├── services/
│   ├── intent.py            # detect_intent() — dispatches to rules or LLM
│   ├── intent_rules.py      # Rule-based: jieba POS + keyword + regex (default)
│   ├── structuring.py       # LLM call → MedicalRecord (Pydantic)
│   ├── session.py           # In-memory current-patient context per doctor
│   ├── transcription.py     # Audio → text (Whisper-compatible)
│   └── wechat_menu.py       # WeChat custom menu definition + creation
│
├── db/
│   ├── engine.py            # Async SQLAlchemy engine + AsyncSessionLocal + Base
│   ├── models.py            # Patient, MedicalRecordDB ORM models
│   ├── init_db.py           # create_tables() called at startup
│   └── crud.py              # create_patient, find_patient_by_name, save_record,
│                            #   get_records_for_patient, get_all_records_for_doctor
│
├── models/
│   └── medical_record.py    # Pydantic schema (8 clinical fields)
│
├── utils/
│   └── log.py               # Timestamped print wrapper
│
├── tools/
│   ├── db_inspect.py        # CLI: patients / records / record <id> / patient <id>
│   └── start_db_ui.sh       # Launches datasette on port 8001
│
└── tests/
    ├── conftest.py           # In-memory SQLite fixture, session reset
    ├── test_crud.py          # 18 DB CRUD tests
    ├── test_session.py       # 7 in-memory session tests
    ├── test_intent.py        # 7 LLM intent tests (mocked)
    ├── test_intent_rules.py  # 21 rule-based intent tests
    ├── test_patients_api.py  # 6 REST API tests
    └── test_wechat_intent.py # 14 WeChat dispatch tests
```

---

## Key Components

### Intent Detection (`INTENT_PROVIDER`)

| Provider | How | Latency | Dependency |
|----------|-----|---------|------------|
| `local` (default) | jieba POS + keyword lists + regex | <5 ms | None |
| `ollama` | Qwen2.5 via Ollama API | ~1–3 s | Ollama running |
| `deepseek` | DeepSeek cloud API | ~1–2 s | API key |
| `groq` | Groq cloud API | ~0.5 s | API key |

Switch via `.env`: `INTENT_PROVIDER=local`

### Intent → Action Dispatch (`routers/wechat.py`)

```
message
  └─► detect_intent()
        ├─ create_patient → create DB row, set session, reply confirmation
        ├─ add_record     → structure via LLM → save DB row linked to patient
        ├─ query_records  → fetch from DB
        │     ├─ patient named in message → that patient's last 5 records
        │     ├─ no name + session set   → session patient's last 5 records
        │     └─ no context             → all doctor's last 10 records
        └─ unknown → instant help message (no LLM call)
```

### Patient Session (`services/session.py`)

In-memory dict keyed by WeChat `openid` (doctor_id). Tracks the "current patient" so doctors don't have to repeat the name every message.

```
set_current_patient(doctor_id, id, name)   # called on create or name match
get_session(doctor_id)                     # returns DoctorSession dataclass
clear_current_patient(doctor_id)
```

### Medical Record Structuring (`LLM_PROVIDER`)

| Provider | Model | Note |
|----------|-------|------|
| `ollama` (default) | `qwen2.5:7b` | Fully local, no data leaves server |
| `deepseek` | `deepseek-chat` | Cloud fallback |
| `groq` | `llama-3.3-70b-versatile` | Cloud fallback |

Switch via `.env`: `LLM_PROVIDER=ollama`

Model is warmed up at startup to avoid cold-start timeout on first request.

### Database (`patients.db`)

```
patients
  id · doctor_id · name · gender · age · created_at

medical_records
  id · patient_id (FK→patients) · doctor_id
  chief_complaint · history_of_present_illness · past_medical_history
  physical_examination · auxiliary_examinations · diagnosis
  treatment_plan · follow_up_plan · created_at
```

`doctor_id` = WeChat openid. Changes if `WECHAT_APP_ID` changes — requires a one-time SQL migration if the App ID is swapped.

---

## Configuration (`.env`)

```bash
# LLM for medical record structuring
LLM_PROVIDER=ollama          # ollama | deepseek | groq

# Intent detection
INTENT_PROVIDER=local        # local | ollama | deepseek | groq

# Ollama
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen2.5:7b      # or qwen2.5:14b, qwen2.5:32b

# Cloud fallbacks (optional)
DEEPSEEK_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# WeChat Official Account
WECHAT_TOKEN=
WECHAT_APP_ID=
WECHAT_APP_SECRET=
WECHAT_ENCODING_AES_KEY=
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/wechat` | WeChat message webhook |
| `GET` | `/wechat` | WeChat server verification |
| `POST` | `/api/records/from-text` | Structure a text note |
| `POST` | `/api/records/from-audio` | Transcribe + structure audio |
| `POST` | `/api/patients` | Create patient (REST) |
| `GET` | `/api/patients/{doctor_id}` | List patients |
| `GET` | `/api/patients/{doctor_id}/{patient_id}/records` | List records |
| `GET` | `/admin` | SQLAdmin database UI |

---

## Database Inspection

```bash
# SQLAdmin web UI (same port as API)
open http://localhost:8000/admin

# datasette (standalone, richer SQL editor)
bash tools/start_db_ui.sh        # → http://localhost:8001

# CLI inspector
python tools/db_inspect.py patients
python tools/db_inspect.py records
python tools/db_inspect.py record <id>
python tools/db_inspect.py patient <id>

# Raw sqlite3
sqlite3 -column -header patients.db "SELECT * FROM patients;"
```

---

## Running Locally

```bash
# 1. Start Ollama (keep in background)
ollama serve

# 2. Pull model (first time only)
ollama pull qwen2.5:7b

# 3. Start the API
.venv/bin/uvicorn main:app --reload

# 4. Expose via ngrok for WeChat webhook
ngrok http 8000
```

---

## Test Suite

```bash
.venv/bin/pytest -v    # 73 tests, all passing
```

| File | Tests | Covers |
|------|-------|--------|
| `test_crud.py` | 18 | DB CRUD, isolation, ordering |
| `test_session.py` | 7 | In-memory session logic |
| `test_intent.py` | 7 | LLM intent path (mocked) |
| `test_intent_rules.py` | 21 | Rule-based: all intents, name/age/gender extraction |
| `test_patients_api.py` | 6 | REST endpoints |
| `test_wechat_intent.py` | 14 | Full dispatch: create/add/query/unknown |

All DB tests use in-memory SQLite. All LLM calls are mocked. No network required to run tests.

---

## Known Limitations & Next Steps

| Issue | Plan |
|-------|------|
| Rule-based intent misses ambiguous phrasing | Upgrade to LLM tool-calling agent (Phase 3) |
| No conversation history | Add per-doctor message buffer for multi-turn context |
| Session lost on server restart | Persist session to DB or Redis |
| Single-process (in-memory session) | Acceptable for MVP; needs Redis for multi-worker |
| WeChat 5 s timeout | Long Ollama calls use customer-service API for async reply |
