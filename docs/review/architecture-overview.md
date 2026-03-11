# Architecture Overview
**Last updated:** 2026-03-11

---

## System Overview

A FastAPI backend + React SPA serving doctors through two main channels:
**WeChat/WeCom** (primary mobile interface) and a **web dashboard**. A WeChat
Mini Program uses dedicated `/api/mini/*` endpoints and shares the same core
doctor workflow and persistence model.

---

## Channels & Entry Points

```
WeChat/WeCom ──► POST /wechat               routers/wechat.py
                                             ↓ async background task
Web Dashboard ──► POST /api/records/chat    routers/records.py
                  (React SPA)

Mini Program ──► POST /api/mini/chat        routers/miniprogram.py
                 POST /api/mini/voice/chat

Patient Portal ──► POST /api/patient        routers/patient_portal.py
```

---

## Context Assembly Pipeline

Before routing, each turn assembles a `DoctorTurnContext` that separates authoritative from advisory context:

```
assemble_turn_context(doctor_id)     services/ai/turn_context.py
  │
  ├─ [under session lock]
  │    WorkflowState (AUTHORITATIVE)
  │      current_patient_id/name      — controls patient binding
  │      pending_record_id            — controls confirmation flow
  │      interview / pending_cvd_scale — active workflow state
  │
  └─ [outside session lock]
       AdvisoryContext
         recent_history               — rolling 10-turn window
         context_message              — compressed long-term summary (fresh sessions only)
         knowledge_snippet            — doctor KB snippet
       Provenance
         current_patient_source       — "session" | "none"
         memory_used / knowledge_used — observability flags
```

**Authority rules (from Codex review):**
- `WorkflowState` fields are authoritative — never subject to TTL eviction, never overridden by advisory context
- `AdvisoryContext` fields are advisory — LLM background hints only, must not influence patient binding or write-path decisions

---

## AI Routing Pipeline

Every message (WeChat or web) flows through the same two-stage router:

```
message
  │
  ▼
fast_route()                    services/ai/fast_router/
  Tier 0 — import markers        [PDF:], [Word:], [Image:], help
  Tier 1 — exact keyword sets    list patients, list tasks
  Tier 2 — regex + extraction    create/delete/query/schedule/export/follow-up/task actions
  │
  ▼ (None = uncertain → LLM)
  # Inactive / available if needed:
  #   _mined_rules.py — data-driven JSON rules (data/mined_rules.json)
  #   FAST_ROUTE_CONFIDENCE_THRESHOLD — env var to push low-confidence hits to LLM
agent_dispatch()                services/ai/agent.py
  LLM function-calling           ROUTING_LLM provider registry
  Context: system prompt + [current_patient] + [candidate/not_found]
           + [knowledge] + value-trimmed history + current doctor message
  Tool: IntentResult extraction  8 structured clinical fields
  Fallback chain: primary → cloud → regex heuristic
  │
  ▼
IntentResult { intent, patient_name, structured_fields, confidence, ... }
```

**Intents:** `add_record`, `query_records`, `update_record`, `create_patient`, `delete_patient`, `list_patients`, `list_tasks`, `complete_task`, `schedule_appointment`, `schedule_follow_up`, `export_records`, `import_history`, `help`, `unknown`

---

## Session & State

```
services/session.py
  _sessions: dict[doctor_id → DoctorSession]   (in-memory)
  hydrate_session_state()    DB → memory, 5-min TTL
  per-doctor asyncio.Lock    acquired before any state read/write
  push_turn() / flush_turns() batch-write conversation history to DB

DoctorSession fields:
  current_patient_id/name    active patient context        ← AUTHORITATIVE
  pending_record_id          awaiting doctor confirmation  ← AUTHORITATIVE
  pending_create_name        mid-flow patient creation     ← AUTHORITATIVE
  pending_cvd_scale          CVD scale interview in progress ← AUTHORITATIVE
  interview                  structured interview flow     ← AUTHORITATIVE
  conversation_history       rolling 10-turn window        ← advisory (history)
  specialty / doctor_name    injected into LLM prompt      ← advisory (profile)
```

**Context compression** (`services/ai/memory.py`):
```
maybe_compress()   — must be called inside session lock
  triggers: MAX_TURNS (20 msgs) | MEMORY_TOKEN_BUDGET (1200 tokens, CJK-aware) | 30-min idle
  on success: upsert DoctorContext → clear DB turns → clear in-memory history
  on ValueError (bad LLM JSON): preserve history, do not truncate
  on transient error: preserve history, hard-cap only if severely over limit

Compression schema (structured JSON):
  current_patient      {name, gender, age}
  active_diagnoses     [{name, status: acute|chronic|resolved}]
  current_medications  [{name, dose}]
  key_lab_values       [{name, value, date, abnormal: bool, trend: improving|stable|worsening}]
  recent_action        string
  pending              string
  condition_trend      improving|stable|worsening
```

---

## Record Flow (Pending-Draft Model)

```
add_record intent
  │
  ├─ emergency? ──► save_record() immediately
  │
  └─ normal ──► create_pending_record() [DB, TTL 30min]
                set_pending_record_id()
                doctor receives preview
                │
                ├─ confirm ──► save_pending_record() → MedicalRecordDB
                │              CVD scale follow-up if applicable
                │
                ├─ cancel  ──► abandon_pending_record()
                │
                └─ timeout ──► scheduler marks expired every 5 min
```

Web confirm/abandon: `POST /api/records/pending/{id}/confirm|abandon`
WeChat confirm/abandon: text reply "确认" / "撤销"

---

## Data Model (Key Entities)

```
Doctor
  └─► Patient (doctor_id FK)
        └─► MedicalRecordDB
              └─► MedicalRecordVersion   (audit history)
              └─► SpecialtyScore         (scale scores, doctor-scoped)
              └─► NeuroCVDContext        (CVD/neuro structured fields)
        └─► PatientLabel (M2M)
        └─► DoctorTask
        └─► PendingRecord               (draft, TTL-expired)
  └─► DoctorContext                     (LLM-compressed memory)
  └─► DoctorConversationTurn            (rolling 10-turn window)
  └─► DoctorKnowledgeItem               (doctor's custom knowledge base)
  └─► DoctorSessionState                (hydration source for session)
  └─► AuditLog                          (7-year retention)
```

---

## Services Layer

| Package | Responsibility |
|---|---|
| `services/ai/` | fast_router, agent dispatch, structuring LLM, vision OCR, transcription, memory compression |
| `services/ai/turn_context.py` | `DoctorTurnContext` assembly — two-tier authoritative/advisory model, narrow lock scope, provenance tracking |
| `services/session.py` | In-memory session, lock registry, hydration |
| `services/wechat/` | WeChat domain logic, media pipeline, KF sync, notifications, patient pipeline |
| `services/auth/` | JWT (miniprogram), PBKDF2 (patient access codes), rate limiting, request auth |
| `services/domain/` | `record_ops.py`, `patient_ops.py` — cross-cutting business logic |
| `services/patient/` | NL search, risk scoring, CVD scale interview, prior visit detection |
| `services/export/` | PDF export, outpatient report |
| `services/knowledge/` | Doctor KB, PDF/Word/image import, OCR |
| `services/notify/` | Task scheduling, APScheduler jobs, notify preferences |
| `services/observability/` | Audit log, routing metrics, turn log |

---

## Frontend (React SPA)

```
App.jsx
  └─► DoctorPage.jsx          main shell + nav
        └─► ChatSection         /doctor/chat   — AI chat, pending-draft confirm
        └─► PatientsSection     /doctor/patients — patient list, records
        └─► TasksSection        /doctor/tasks
        └─► SettingsSection     /doctor/settings
        └─► HomeSection         /doctor/home
      Each section wrapped in ErrorBoundary

Auth: Zustand store (persist) → HS256 JWT → set into api.js module
Mini Program: passes token via URL param → stripped immediately after extraction
Patient portal: separate PatientPage.jsx, PBKDF2 access code auth
```

---

## Infrastructure

```
FastAPI (async) + SQLAlchemy async + SQLite (dev) / MySQL/Postgres (prod)
APScheduler — task delivery plus cleanup/retention jobs:
  check_and_send_due_tasks       interval (configurable)
  _expire_stale_pending_records  every 5 min
  _cleanup_old_conversation_turns  interval hours (configurable)
  _cleanup_inactive_session_cache  interval
  _purge_old_pending_data        daily 04:00
  _cleanup_chat_archive          daily 04:30
  _audit_log_retention           monthly
  _record_version_retention      monthly
  _redact_old_conversation_content daily 05:00

LLM providers — Ollama / DeepSeek / OpenAI / Tencent LKEAP / Claude / Gemini / Groq
config/runtime.json — live config reload without restart
```

---

## API Routers

| Router | Prefix | Purpose |
|---|---|---|
| `records.py` | `/api/records` | Chat, CRUD records, pending-draft confirm/abandon |
| `wechat.py` | `/wechat` | WeChat/WeCom webhook handler |
| `auth.py` | `/api/auth` | Doctor login, invite codes |
| `miniprogram.py` | `/api/mini` | Mini Program chat, voice, and doctor workflow endpoints |
| `patient_portal.py` | `/api/patient` | Patient self-service portal |
| `tasks.py` | `/api/tasks` | Task management |
| `voice.py` | `/api/voice` | Voice transcription |
| `export.py` | `/api/export` | PDF / report export |
| `neuro.py` | `/api/neuro` | Neurology/CVD specialist endpoints |
| `ui/` | `/ui` | Admin + debug UI endpoints |
