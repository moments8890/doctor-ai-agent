# Architecture Overview
**Last updated:** 2026-03-12

---

## System Overview

A FastAPI backend + React SPA serving doctors through three channels:
**Web dashboard** (primary MVP surface), **WeChat/WeCom** (primary mobile
interface), and **voice** (audio transcription + shared workflow). A WeChat
Mini Program uses dedicated `/api/mini/*` endpoints and shares the same core
doctor workflow and persistence model.

All three doctor-facing channels (Web, WeChat, voice) run through the same
5-layer intent workflow pipeline and dispatch to unified shared handlers.

---

## Channels & Entry Points

```
Web Dashboard ──► POST /api/records/chat    routers/records.py
                  (React SPA)               → shared 5-layer workflow

WeChat/WeCom ──► POST /wechat               routers/wechat.py
                                             ↓ async background task
                                             → shared 5-layer workflow

Voice ────────► POST /api/voice/chat        routers/voice.py
                (audio upload → transcribe   → shared 5-layer workflow
                 → draft-first workflow)

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

## Intent Workflow Pipeline (5-Layer)

Every doctor message (Web, WeChat, and voice) flows through a shared 5-layer
intent workflow defined in `services/intent_workflow/`:

```
message
  │
  ▼
services.intent_workflow.run()
  │
  ├─ 1. CLASSIFY   classifier.py
  │    fast_route() — deterministic Tiers 0-2 (no LLM)
  │      Tier 0: import markers ([PDF:], [Word:], [Image:], help)
  │      Tier 1: exact keyword sets (list patients, list tasks)
  │      Tier 2: regex + extraction (create/delete/query/schedule/export/...)
  │    agent_dispatch() — LLM fallback when fast_route returns None
  │      ROUTING_LLM provider registry (Ollama / DeepSeek / OpenAI / ...)
  │      Fallback chain: primary → cloud → regex heuristic
  │
  ├─ 2. EXTRACT    entities.py
  │    Resolve patient/gender/age with provenance tracking.
  │    Sources: followup → fast_route → llm → text_leading_name →
  │             history → session → candidate → not_found
  │    Clinical content detection and reminder signal extraction.
  │
  ├─ 3. BIND       binder.py
  │    Read-only patient binding (no DB writes).
  │    Status: bound | has_name | no_name | not_applicable
  │    Weak sources (candidate, not_found) flagged needs_review=True.
  │
  ├─ 4. PLAN       planner.py
  │    Annotate compound actions:
  │      create_patient + clinical content → create + add_record
  │      create_patient + reminder text → create + create_task
  │      auto-create + add_record (single-patient shortcut)
  │
  └─ 5. GATE       gate.py
       Safety check before execution.
       Blocks: write intents without patient, not_found without location context.
       Allows: read-only intents, weak attribution with pending-draft confirmation.
  │
  ▼
WorkflowResult → IntentResult (backward-compatible) → handler dispatch
```

**Intents:** `add_record`, `query_records`, `update_record`, `create_patient`, `delete_patient`, `list_patients`, `list_tasks`, `complete_task`, `schedule_appointment`, `schedule_follow_up`, `export_records`, `import_history`, `help`, `unknown`

### Hook Stages

The workflow emits events at each layer boundary via `services/hooks.py`.
External modules register callbacks without modifying core workflow code.

| Stage | Fires after | Payload includes |
|---|---|---|
| `POST_CLASSIFY` | Layer 1 | decision, raw_intent, latency_ms |
| `POST_EXTRACT` | Layer 2 | decision, entities, latency_ms |
| `POST_BIND` | Layer 3 | decision, entities, binding, latency_ms |
| `POST_PLAN` | Layer 4 | decision, entities, binding, plan, latency_ms |
| `POST_GATE` | Layer 5 | decision, entities, binding, plan, gate, latency_ms |
| `PRE_REPLY` | Before response | (available for response-time hooks) |

Built-in hooks (`services/hooks_builtin.py`):
- `_log_classification` (POST_CLASSIFY, priority 50) -- logs intent routing decisions
- `_log_gate` (POST_GATE, priority 50) -- logs gate blocks for debugging

Hooks are non-blocking: exceptions are logged but never propagate to the caller.

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
| `services/intent_workflow/` | 5-layer intent pipeline: classify, extract, bind, plan, gate. Shared by all channels. |
| `services/ai/` | fast_router, agent dispatch, structuring LLM, vision OCR, transcription, memory compression |
| `services/ai/turn_context.py` | `DoctorTurnContext` assembly -- two-tier authoritative/advisory model, narrow lock scope, provenance tracking |
| `services/hooks.py` | Lightweight hook mechanism for workflow pipeline (register/emit at POST_CLASSIFY through POST_GATE) |
| `services/hooks_builtin.py` | Built-in observability hooks (classification logging, gate-block logging) |
| `services/session.py` | In-memory session, lock registry, hydration (`hydrate_session_state` called before workbench context reads) |
| `services/domain/intent_handlers/` | Shared handlers: `_add_record`, `_create_patient`, `_query_records`, `_simple_intents`, `_confirm_pending` |
| `services/domain/adapters/` | Channel adapter protocol + implementations (`WebAdapter`, `WeChatAdapter`). See Adapter Status below. |
| `services/domain/message.py` | `Message` dataclass (channel-agnostic inbound) + `ChannelAdapter` Protocol |
| `services/domain/` | `record_ops.py`, `patient_ops.py` -- cross-cutting business logic |
| `services/knowledge/` | Doctor KB, PDF/Word/image import, OCR, `knowledge_cache.py` (per-doctor TTL cache) |
| `services/wechat/` | WeChat domain logic, media pipeline, KF sync, notifications, patient pipeline |
| `services/auth/` | JWT (miniprogram), PBKDF2 (patient access codes), rate limiting, `request_auth.py` (doctor-scope resolution) |
| `services/patient/` | NL search, risk scoring, CVD scale interview, prior visit detection |
| `services/export/` | PDF export, outpatient report |
| `services/notify/` | Task scheduling, APScheduler jobs, notify preferences |
| `services/observability/` | Audit log, routing metrics, turn log, per-layer latency spans |

### Knowledge-Context Cache

`services/knowledge/knowledge_cache.py` provides a shared, per-doctor TTL cache
for knowledge-base context used during intent routing:

- `load_cached_knowledge_context(doctor_id, text)` -- returns cached or freshly
  loaded knowledge snippet (5-minute TTL, per-doctor asyncio lock).
- `invalidate_knowledge_cache(doctor_id)` -- clears cache for one doctor.
- Both Web and WeChat call this before entering the workflow pipeline.

### Adapter Status

The `ChannelAdapter` protocol (`services/domain/message.py`) defines five
methods: `parse_inbound`, `format_reply`, `send_reply`, `send_notification`,
`get_history`.

| Method | WebAdapter | WeChatAdapter | Status |
|---|---|---|---|
| `parse_inbound` | Wired (records.py) | Wired (wechat.py) | Production |
| `format_reply` | Wired (records.py) | Wired (wechat_flows.py) | Production |
| `send_reply` | Stub (sync HTTP cycle) | Stub (delegates to `_send_customer_service_msg` directly) | Deferred |
| `send_notification` | Stub (client polling) | Stub (delegates to `_send_customer_service_msg`) | Deferred |
| `get_history` | No-op (history in request body) | Reads from session | Production |

**What is wired:** `parse_inbound` normalizes platform payloads into `Message`,
and `format_reply` converts `HandlerResult` to channel wire format. Both are
called in production router code.

**What is deferred:** `send_reply` and `send_notification` are documented stubs.
Web has no async push channel yet (replies are in the HTTP response). WeChat
send-path calls go through `services/wechat/wechat_notify.py` directly, not
through the adapter. Full adapter integration for the send path is deferred
until the next cycle.

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
| `voice.py` | `/api/voice` | Voice transcription + shared 5-layer workflow (draft-first safety model) |
| `export.py` | `/api/export` | PDF / report export |
| `neuro.py` | `/api/neuro` | Neurology/CVD specialist endpoints |
| `ui/` | `/ui` | Admin + debug UI endpoints |
