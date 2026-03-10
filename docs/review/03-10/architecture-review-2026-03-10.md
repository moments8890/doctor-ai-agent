# Architecture Review — 5-Agent Report
**Date:** 2026-03-10
**Baseline:** v1.0.0 (commit `84b564b`, 911 tests passing)
**Scope:** AI Routing · DB/Models · API/Routers · Session/State · Frontend

---

## Table of Contents
1. [AI Routing](#1-ai-routing)
2. [Database & CRUD Layer](#2-database--crud-layer)
3. [API Routers & Authentication](#3-api-routers--authentication)
4. [Session & State Management](#4-session--state-management)
5. [Frontend](#5-frontend)
6. [Cross-Cutting Summary](#6-cross-cutting-summary)

---

## 1. AI Routing

**Files reviewed:** `services/ai/fast_router/`, `services/ai/router.py`, `services/ai/agent.py`, `services/ai/intent.py`, `services/ai/multi_intent.py`

### Overview

Two-stage precision-first pipeline:

| Stage | Entry point | Latency | Coverage |
|---|---|---|---|
| Fast Router (deterministic) | `fast_route()` `_router.py:389` | <5ms | ~90% of structured messages |
| Agent Dispatch (LLM) | `dispatch()` `agent.py:1001` | 1–3s | remainder + all ambiguous messages |

**Fast Router tiers:**
- **Tier 0** `_router.py:85` — import/help markers (`[PDF:]`, `[Word:]`, `[Image:]`)
- **Tier 1** `_router.py:102` — exact keyword sets (list patients/tasks)
- **Tier 2** `_router.py:118` — regex with name/demographic extraction (create, update, delete, schedule, export…)
- **Mined rules** `_router.py:348` — data-driven JSON rules sorted by priority
- **Tier 3 removed** `_router.py:381` — clinical keyword classifier deleted 2026-03-09; LLM now handles add/query/update record discrimination

### Strengths

- Conservative "false negative is safer than false positive" philosophy — uncertain messages fall through to LLM
- Layered determinism minimises over-reaching
- Single LLM call extracts 8 structured clinical fields
- Provider fallback chain: primary ROUTING_LLM → cloud fallback → regex heuristic `_fallback_intent_from_text()`
- Detailed routing metrics (`record("fast:intent_type")` vs `record("llm")`)

### Weaknesses & Risks

| Priority | Issue | Location | Detail |
|---|---|---|---|
| **P0** | Tier 3 deletion unvalidated | `_router.py:381` | No published benchmark comparing Tier 3 accuracy vs LLM; latency regression for clinical messages; weaker offline fallback |
| **P1** | `confidence` field unused | `intent.py:105` | Defaults to 1.0; mined rules can set 0.7–0.9 but downstream never acts on it |
| **P1** | Mined rules: no schema validation | `_mined_rules.py:63` | Malformed JSON rules fail silently; no pydantic guard at load time |
| **P1** | Name extraction fragility | `_patterns.py:39` | 2–3 char limit; no roster cross-check; `_TIER3_BAD_NAME` blocklist only |
| **P2** | Multi-intent detection gaps | `multi_intent.py:28` | Only 3 pre-check patterns (`先…再`, `另外`, `然后`); semicolons, bare periods missed |
| **P2** | Provider fallback hardcoded | `agent.py:1102` | Fallback chains in Python; adding a provider requires code change |
| **P3** | Patient guard regex explosion | `_patient_guard.py:11` | 11 named groups, 50+ alternations; potential O(n²) backtracking on long messages |

### Recommendations

1. **P0** — Publish a benchmark (≥1000-message corpus) for Tier 3 vs LLM. If Tier 3 achieves ≥95% precision, restore behind `ENABLE_TIER3=true` flag. Document decision either way.
2. **P1** — Add `confidence_threshold` to `route_message()` (default 0.85); fast-route results below threshold fall through to LLM.
3. **P1** — Add pydantic `MiningRule` schema validation at `_mined_rules.py:63`.
4. **P2** — Move provider fallback chains to `config/routing_fallback.json`.
5. **P2** — Expand multi-intent pre-check with semicolon and `一会儿…一会儿` patterns.

---

## 2. Database & CRUD Layer

**Files reviewed:** `db/models/`, `db/crud/`, `db/repositories/`, `alembic/versions/`

### Overview

Core entity graph: `Doctor` → `Patient` → `MedicalRecordDB` → `SpecialtyScore` / `NeuroCVDContext` / `MedicalRecordVersion`. Supporting: `DoctorTask`, `PendingRecord`, `DoctorSessionState`, `DoctorConversationTurn`, `ChatArchive`, `AuditLog`.

### Strengths

- Correct cascade/ondelete on all FK relationships; dual-strategy (code + DB-level) for SQLite compatibility
- Comprehensive composite indexes: `ix_records_doctor_type_created`, `ix_tasks_doctor_status_due`, `ix_pending_records_doctor_status_expires`, etc.
- PBKDF2-SHA256 (600k iterations) for WeChat IDs, mini openids, and patient access codes
- 7-year audit log retention; 30-year medical record retention per MoH regulation
- All CRUD functions are async-first with explicit commit boundaries

### Weaknesses & Risks

| Priority | Issue | Location | Detail |
|---|---|---|---|
| **P0** | Missing doctor auth check in score retrieval | `crud/scores.py:41` | `get_scores_for_record()` has no `doctor_id` filter; any caller can read another doctor's scores |
| **P0** | N+1 in `search_patients_nl()` | `crud/patient.py:294` | Labels not eagerly loaded; accessing `patient.labels` post-query issues per-patient query |
| **P1** | Race in conversation turn rollover | `crud/doctor.py:271` | Query-then-delete rollover is not atomic; concurrent appends can cause data loss |
| **P1** | Promoted column drift in CVD context | `crud/specialty.py:52` | `upsert_cvd_field()` only syncs `diagnosis_subtype`/`surgery_status` when those specific fields are written; others silently diverge |
| **P1** | ORM anti-pattern in `remove_label()` | `crud/patient.py:272` | List comprehension replaces ORM relationship list; risky if labels not fully loaded |
| **P1** | No retry backoff for `PendingMessage` | `crud/pending.py:175` | `increment_pending_message_attempt()` has no max_attempts guard |
| **P2** | Fire-and-forget audit calls | `crud/patient.py:150, 189, 216` | `asyncio.ensure_future()` audit calls; failures silently dropped |
| **P2** | Missing index on `DoctorKnowledgeItem` | `models/doctor.py:24` | Queries sort by `(updated_at DESC, id DESC)` but no composite index |
| **P2** | `uq_patients_id_doctor` intent unclear | `models/patient.py:51` | Composite unique constraint on (id, doctor_id) where id is already PK |

### Recommendations

1. **P0** — Add `SpecialtyScore.doctor_id == doctor_id` to `get_scores_for_record()`.
2. **P0** — Add `selectinload(Patient.labels)` in `search_patients_nl()` at line 340.
3. **P1** — Replace conversation turn rollover with atomic `DELETE … WHERE id NOT IN (SELECT id … ORDER BY … LIMIT N)`.
4. **P1** — After any `upsert_cvd_field()` mutation, always sync both promoted columns from the deserialized JSON.
5. **P2** — Add `Index("ix_doctor_knowledge_items_doctor_updated", "doctor_id", "updated_at")` in `models/doctor.py`.

---

## 3. API Routers & Authentication

**Files reviewed:** `routers/`, `main.py`, `services/auth/`

### Overview

~50 endpoints across 10 routers. Auth model: HS256 JWT for miniprogram/app, WeChat signature verification for webhook, PBKDF2 access code for patient portal, admin token for UI.

### Strengths

- WeChat HMAC signature verification (`wechat.py:887`) prevents message spoofing
- PBKDF2-SHA256 (600k iterations, 32-byte salt, `hmac.compare_digest`) for patient access codes
- Magic-byte file upload validation (`export.py:74`) prevents MIME spoofing
- Sliding-window rate limiting (`services/auth/rate_limit.py`) with `Retry-After` header
- Cross-doctor data isolation enforced at CRUD level throughout
- Structured `DomainError` exception handler with error code + message

### Weaknesses & Risks

| Priority | Issue | Location | Detail |
|---|---|---|---|
| **P0 CRITICAL** | Plaintext `doctor_id` fallback | `routers/records.py:414` (+ 8 other endpoints) | `RECORDS_ALLOW_BODY_DOCTOR_ID=true` allows full doctor impersonation via JSON body |
| **P0** | Patient portal: name-only fuzzy login | `patient_portal.py:164` | `Patient.name.ilike(f"{patient_name}%")` prefix match; common names enumerate to first match |
| **P1** | Doctor cache timing window | `wechat.py:133` | 5-min `_DOCTOR_CACHE` TTL; newly registered doctors routed to patient pipeline until cache refreshes |
| **P1** | Hardcoded dev JWT secret | `miniprogram_auth.py:36` | Falls back to `"dev-miniprogram-secret"` unless `APP_ENV=prod` |
| **P1** | WeChat AES decrypt failure: silent ACK | `wechat.py:1116` | Encrypted message with missing config is ACK'd; message silently lost |
| **P1** | PHI in logs | `wechat.py:1104` | `xml_str[:200]` logged; may contain patient names/symptoms |
| **P2** | CORS `allow_origins=["*"]` | `main.py:503` | Permissive; should be locked to known origins in production |
| **P2** | No circuit breaker on external services | `agent.py`, `wechat.py` | WeChat API / Ollama failures retry until timeout with no back-off |
| **P2** | File upload filename unsanitised | `voice.py:85` | User-controlled filename passed to OpenAI API metadata |
| **P2** | Rate limit applied after invite lookup | `auth.py:280` | Pre-lookup invite code enumeration window not protected |

### Recommendations

1. **P0** — Set `RECORDS_ALLOW_BODY_DOCTOR_ID=false` in production; consider removing the fallback path entirely and requiring JWT on all endpoints.
2. **P0** — Require access code for patient portal login (remove the `if patient.access_code:` optional guard; make it mandatory).
3. **P1** — Remove the `"dev-miniprogram-secret"` hardcoded default; raise `RuntimeError` if `MINIPROGRAM_TOKEN_SECRET` is missing in any environment.
4. **P1** — Redact PHI from logs: replace `xml_str[:200]` with structured log of `msg_type` + masked `source_id`.
5. **P1** — Implement distributed rate limiting (Redis-backed) before multi-process deployment.

---

## 4. Session & State Management

**Files reviewed:** `services/session.py`, `services/ai/memory.py`, `db/crud/doctor.py` (session upsert), `routers/wechat.py` (lock discipline)

### Overview

Hybrid in-memory + DB persistence:
- `_sessions: dict[str, DoctorSession]` — per-doctor Python object
- Hydrated from DB every 5 min (`_HYDRATION_TTL_SECONDS = 300`)
- Per-doctor `asyncio.Lock` (created lazily; `_registry_lock: threading.RLock` guards creation)
- Conversation turns buffered in `_pending_turns`, flushed async; rolling window of 10 kept in DB
- Compressed LLM summary in `DoctorContext` after 30-min idle

### Pending Record Flow

```
add_record intent → assemble_record() → PendingRecord in DB (TTL 10 min)
  → set_pending_record_id() → doctor sees preview
  → doctor confirms/abandons → save/abandon_pending_record() → clear_pending_record_id()
```

One pending record per doctor at a time; second message overwrites first (orphaned draft expires via TTL).

### Strengths

- Per-doctor locks prevent global contention
- Double-check inside lock prevents thundering herd on first hydration
- TTL-based pending record expiry; handler correctly no-ops if already confirmed/abandoned
- Voice message path acquires lock before state checks (correct TOCTOU ordering)

### Weaknesses & Risks

| Priority | Issue | Location | Detail |
|---|---|---|---|
| **P0 CRITICAL** | Hydration outside lock (TOCTOU) | `wechat.py:950` | `hydrate_session_state()` called before lock acquired; another request can mutate state between hydration and lock acquisition |
| **P0** | Unvalidated `pending_record_id` in handler | `wechat.py:~500` | Handler trusts in-memory `sess.pending_record_id`; expired or deleted records cause silent failures without re-fetch |
| **P1** | Non-atomic session field updates | `db/crud/doctor.py:179` | Concurrent upserts on different fields can interleave; in-memory object diverges from DB |
| **P1** | No automatic pending record cleanup | `main.py` | No scheduled task to call `expire_stale_pending_records()`; relies on manual triggers |
| **P2** | Stale knowledge context (5-min TTL) | `wechat.py:135` | Doctor knowledge edits take up to 300s to reach routing decisions |
| **P2** | No session divergence telemetry | `services/session.py` | No metric emitted when in-memory and DB state differ |
| **P3** | Imprecise type hints | `session.py:63` | `conversation_history: List[dict]` — no structured `ConversationTurn` TypedDict |

### Recommendations

1. **P0** — Move `hydrate_session_state(doctor_id)` to inside the lock scope at `wechat.py:950`:
   ```python
   await asyncio.wait_for(_lock.acquire(), timeout=_LOCK_TIMEOUT)
   _lock_acquired = True
   await hydrate_session_state(doctor_id)  # ← now inside lock
   ```
2. **P0** — In `_handle_pending_record_reply()`, re-fetch and validate `PendingRecord` from DB before processing.
3. **P1** — Add a scheduled background task (every 5 min) to call `expire_stale_pending_records()` and `purge_old_pending_records(days=1)`.
4. **P2** — Log in `hydrate_session_state()` when in-memory `pending_record_id` differs from DB value; emit `session_state_divergence` metric.
5. **P3** — Centralise all TTL constants in `services/config/session_ttls.py`.

---

## 5. Frontend

**Files reviewed:** `frontend/src/`, `frontend/vite.config.js`, `frontend/package.json`, `frontend/capacitor.config.ts`, `miniprogram/`

### Overview

React 19 + MUI 7 SPA. Zustand 5 (persist) for auth state only. Vite 6 with Capacitor 7 for Android WebView. WeChat Mini Program at `miniprogram/` uses webview bridge with URL-param token hand-off.

### Strengths

- Token stripped from URL immediately after extraction (`App.jsx:33`) — no history leak
- Minimal Zustand store prevents over-engineering
- 15s request timeout with AbortController (`api.js:43`)
- Clean separation of doctor/admin/debug request clients
- Magic-byte upload validation on backend; frontend validates file type before send

### Weaknesses & Risks

| Priority | Issue | Location | Detail |
|---|---|---|---|
| **P0** | `DoctorPage.jsx` monolith | `DoctorPage.jsx` (2811 lines) | Chat, patients, tasks, settings, all dialogs inline; unmaintainable, uncodeable as a unit |
| **P0** | No error boundaries | Throughout | Unhandled API errors crash entire page; no fallback UI |
| **P1** | Duplicate data-fetch logic | `usePatientData.js`, `useTaskData.js`, `useLabelData.js` | Identical `useState/useCallback/useEffect` pattern repeated 3× |
| **P1** | localStorage for chat history | `ChatPage.jsx:90` | `JSON.stringify` on every send blocks main thread for large histories |
| **P1** | No request deduplication | `api.js:41` | Double-tab navigation spawns duplicate in-flight requests |
| **P1** | Capacitor Android: hardcoded localhost | `vite.config.js` | Proxy target `127.0.0.1:8000` breaks in APK; needs `VITE_API_BASE_URL` at build time |
| **P2** | Serial initial data loads | `DoctorPage.jsx` | Three hooks each fire independently; should be `Promise.all()` |
| **P2** | No pagination | `PatientPanel.jsx`, `RecordPanel.jsx` | `limit: 100` silently truncates; no infinite scroll |
| **P2** | `.env.android` committed | `frontend/.env.android` | Contains API URLs; should be gitignored (`.env.android.example` already present) |
| **P3** | No ARIA labels on icon-only buttons | `DoctorPage.jsx` | Accessibility gap; MUI `IconButton` without `aria-label` |

### Recommendations

1. **P0** — Split `DoctorPage.jsx` into `src/sections/ChatSection.jsx`, `PatientsSection.jsx`, `TasksSection.jsx`, `SettingsSection.jsx`. Target: ~150 LOC per section file.
2. **P0** — Add `ErrorBoundary` wrappers around each section; show inline fallback rather than full-page crash.
3. **P1** — Extract `useFetchData(apiFn, deps)` factory hook; replace the three duplicate data hooks.
4. **P1** — Migrate chat history to IndexedDB (`idb` package); remove `localStorage.setItem` on every send.
5. **P1** — Add in-flight deduplication in `api.js` (`Map` keyed on `method+url`; return same Promise for concurrent identical requests).
6. **P1** — Gitignore `.env.android`; document required vars in `.env.android.example`.
7. **P2** — Parallelize initial loads: `Promise.all([getPatients(), getTasks(), getLabels()])`.

---

## 6. Cross-Cutting Summary

### Severity Matrix

| # | Area | Issue | Priority | Status |
|---|---|---|---|---|
| 1 | API | Plaintext `doctor_id` fallback — full impersonation | **P0 CRITICAL** | ✅ Fixed 2026-03-10 |
| 2 | Session | Hydration outside lock (TOCTOU race) | **P0 CRITICAL** | ✅ Fixed 2026-03-10 |
| 3 | DB | `get_scores_for_record()` missing `doctor_id` filter | **P0** | ✅ Fixed 2026-03-10 |
| 4 | DB | N+1 labels in `search_patients_nl()` | **P0** | ✅ Fixed 2026-03-10 |
| 5 | API | Patient portal name-only fuzzy login | **P0** | ✅ Fixed 2026-03-10 |
| 6 | Session | `pending_record_id` not re-validated in handler | **P0** | ✅ Fixed 2026-03-10 |
| 7 | Routing | Tier 3 deletion unvalidated; latency regression | **P0** | 🔴 Open |
| 8 | Frontend | `DoctorPage.jsx` 2811-line monolith | **P0** | 🔴 Open |
| 9 | Frontend | No error boundaries | **P0** | ✅ Fixed 2026-03-10 |
| 10 | DB | Race in conversation turn rollover | **P1** | ✅ Fixed 2026-03-10 |
| 11 | DB | CVD promoted column drift | **P1** | 🔴 Open |
| 12 | API | Hardcoded dev JWT secret | **P1** | ✅ Fixed 2026-03-10 |
| 13 | API | PHI in logs | **P1** | ✅ Fixed 2026-03-10 |
| 14 | Session | No automatic pending record cleanup | **P1** | ✅ Already scheduled (main.py:399) |
| 15 | Routing | `confidence` field unused | **P1** | ✅ Fixed 2026-03-10 |
| 16 | Frontend | Duplicate fetch hook pattern | **P1** | 🔴 Open |
| 17 | Frontend | localStorage for chat history | **P1** | 🔴 Open |
| 18 | Frontend | No request deduplication | **P1** | 🔴 Open |

### Resolved

| Date | Issue | Fix |
|---|---|---|
| 2026-03-10 | Web chat `add_record` direct-save (codex P0) | Option A: pending-draft confirm flow. `_handle_add_record()` now creates `PendingRecord`; `POST /pending/{id}/confirm` and `/abandon` added; `PendingConfirmCard` in frontend. |
| 2026-03-10 | #1 Plaintext `doctor_id` fallback | `request_auth.py`: `_allow_insecure_doctor_id_fallback()` now hard-returns `False` when `ENVIRONMENT=production`. |
| 2026-03-10 | #2 TOCTOU — hydration outside lock | `wechat.py`: `hydrate_session_state()` moved inside lock scope (after `_lock_acquired = True`). |
| 2026-03-10 | #3 Missing `doctor_id` filter in score retrieval | `crud/scores.py`: `get_scores_for_record()` now requires and filters by `doctor_id`. |
| 2026-03-10 | #4 N+1 labels in `search_patients_nl()` | `crud/patient.py:340`: `selectinload(Patient.labels)` added. |
| 2026-03-10 | #5 Patient portal name-only fuzzy login | `patient_portal.py`: `ilike` prefix fallback removed; access code is now mandatory for all logins. |
| 2026-03-10 | #6 `pending_record_id` not re-validated | `wechat_flows.py`: `handle_pending_record_reply()` now re-fetches `PendingRecord` from DB at start. |
| 2026-03-10 | #12 Hardcoded dev JWT secret | `miniprogram_auth.py`: secret guard now checks `ENVIRONMENT` (not `APP_ENV`); raises `RuntimeError` in any non-dev environment. |
| 2026-03-10 | #13 PHI in logs | `wechat.py:509`: `decrypted={xml_str[:200]}` replaced with `decrypted ok, length={len(xml_str)}`. |
| 2026-03-10 | #9 No error boundaries | `ErrorBoundary.jsx` created; all 5 sections in `DoctorPage.jsx` wrapped — unhandled errors show inline retry instead of crashing the page. |
| 2026-03-10 | #10 Conversation turn rollover race | `crud/doctor.py`: two-step SELECT+DELETE replaced with single atomic `DELETE … WHERE id NOT IN (scalar subquery)`. |
| 2026-03-10 | #14 No pending record cleanup | Already scheduled — `main.py:399` runs `_expire_stale_pending_records` every 5 min; no code change needed. |
| 2026-03-10 | #15 `confidence` field unused | `router.py`: `FAST_ROUTE_CONFIDENCE_THRESHOLD` env var checked; fast-route results below threshold fall through to LLM. |

### Remaining Open Items

| # | Area | Issue | Priority |
|---|---|---|---|
| 7 | Routing | Tier 3 deletion unvalidated — no benchmark comparing LLM vs keyword accuracy | **P0** |
| 8 | Frontend | `DoctorPage.jsx` still ~2800 lines — split into smaller section files | **P0** |
| 11 | DB | CVD promoted column drift — `upsert_cvd_field()` doesn't re-sync both columns | **P1** |
| 16 | Frontend | Duplicate fetch hook pattern in 3 hooks — extract `useFetchData` factory | **P1** |
| 17 | Frontend | `localStorage` for chat history — `JSON.stringify` on every send blocks main thread | **P1** |
| 18 | Frontend | No in-flight request deduplication — double-tap spawns duplicate requests | **P1** |

### Top 5 Architecture Investments (Medium Term)

1. **Split `DoctorPage.jsx`** into smaller section files (target ~150 LOC each).
2. **Tier 3 benchmark** — measure LLM accuracy vs. keyword classifier on ≥1000-message corpus; restore Tier 3 behind `ENABLE_TIER3=true` flag if ≥95% precision confirmed.
3. **Redis-backed rate limiting + distributed session cache** before multi-process deployment.
4. **`useFetchData` factory hook** + IndexedDB for chat history — eliminates duplicate hook pattern and main-thread blocking.
5. **CVD promoted column sync** — after any `upsert_cvd_field()`, re-sync both promoted columns from deserialized JSON to prevent drift.

---

*Generated by 5 parallel Explore agents on 2026-03-10.*
*Each section cites specific file:line references verified against the v1.0.0 codebase.*
