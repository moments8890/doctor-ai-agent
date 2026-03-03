# Architecture Review — 2026-03-03

## Purpose
Critical review of the current Phase 3 architecture. Documents what is working well,
what carries real risk, and what should be addressed before scaling beyond a single doctor
on a single device.

---

## What Is Correct

### Core pipeline
- **Background task pattern** for WeChat's 5-second reply timeout — no viable alternative;
  correctly decouples acknowledgement from processing.
- **Single-LLM dispatch** (routing + structuring + natural reply in one tool call) — eliminates
  sequential LLM latency, simplifies the failure surface, and matches how function-calling APIs
  are designed to work.
- **Local-first stack (Ollama + SQLite)** — strategically essential for clinical data residency;
  avoids mandatory cloud dependency for PHI.
- **Async throughout (FastAPI + SQLAlchemy async)** — correct for an I/O-heavy workload with
  concurrent WeChat requests.
- **LLM-compressed conversation memory** — right abstraction; rolling window prevents unbounded
  context growth while persisting summaries across restarts.
- **`notified_at IS NULL` recovery pattern** — scheduler re-queues unnotified tasks on restart
  without needing a persistent job store; simple and effective for current scale.

### Test strategy
- All LLM and DB calls mocked in unit tests; no real network calls.
- In-memory SQLite for test isolation.
- `asyncio_mode = auto` removes boilerplate from async tests.
- CI diff-coverage gate (>81% on changed lines) catches uncovered new code paths.

---

## Risks and Gaps

### 1. Identity is unverified on REST endpoints
**Current state:** Two different identity paths exist:

- **WeChat path (lower risk):** `doctor_id` is derived server-side from `msg.source` in the
  verified and signature-checked WeChat XML. This is not caller-controlled.
- **REST path (higher risk):** Endpoints like `/api/tasks`, `/api/manage/patients`, and
  `/api/records/chat` accept `doctor_id` as a caller-supplied query parameter with no
  verification. Any caller who knows a valid `doctor_id` value has full access to that
  doctor's data via these endpoints.

**Impact:** High for REST endpoints. The WeChat webhook itself is adequately protected by
WeChat's signature verification; the REST API surface is not.

**Suggested fix:** Add a session token or API key requirement to all REST endpoints that
accept `doctor_id`. Until then, restrict REST endpoint exposure to trusted internal networks.

---

### 2. Tenancy coupled to WeChat openid
**Current state:** `doctor_id` is a WeChat openid used as the primary tenancy key across all
DB tables. Notification delivery is already abstracted (`NOTIFICATION_PROVIDER=log|wechat`),
so delivery is not WeChat-only. However, the identity and tenancy model still assumes a
WeChat openid as the stable identifier for a doctor.

**Impact:** Medium now, high later. Adding a web UI, mobile app, or second messaging channel
means either generating synthetic openid-shaped keys (fragile) or rethinking the identity
model. Every DB row (`patients`, `medical_records`, `doctor_tasks`, `doctor_contexts`) is
keyed on a WeChat-specific string.

**Suggested fix:** Introduce a `doctors` table with a stable internal `id`. Store WeChat openid
as one attribute on that row. Map inbound WeChat messages to the internal id at the router
boundary, keeping the rest of the system channel-agnostic.

---

### 3. No doctor approval gate on AI writes
**Current state:** The agent writes records, creates tasks, and updates risk scores directly
to the database on the basis of LLM output alone. There is no draft state, no confirmation
step, and no way for the doctor to reject a write before it persists.

**Impact:** High for clinical safety. A structuring error silently becomes a permanent record.

**Suggested fix:** Introduce a `draft` status on `medical_records`. The AI writes a draft;
the doctor confirms, edits, or discards via WeChat reply or web UI before the record is
finalised. This is P0 #1 in the feature plan.

---

### 4. APScheduler in-process with no persistent job store
**Current state:** `AsyncIOScheduler` runs inside the FastAPI process. Emergency tasks already
call `send_task_notification()` immediately with a retry policy (`TASK_NOTIFY_RETRY_COUNT`,
`TASK_NOTIFY_RETRY_DELAY_SECONDS`). The `notified_at IS NULL` recovery pattern re-queues
unnotified tasks within 1 minute of restart.

**Remaining gap:** If the process crashes *during* a retry sequence (after the first attempt
but before `mark_task_notified()` completes), the retry state is lost. On restart the task
will be retried again from scratch — a duplicate notification risk, not a missed notification
risk.

**Impact:** Low-medium. Acceptable for MVP. The duplicate risk matters more than the missed
notification risk given the retry policy already in place.

**Suggested fix:** For production, use a persistent scheduler backend (e.g. APScheduler with
SQLAlchemy job store) so in-flight retry state survives restarts. Alternatively, make
`send_task_notification()` idempotent at the transport layer so duplicate sends are harmless.

---

### 5. No uniqueness constraint on patient names
**Current state:** `(doctor_id, name)` has no uniqueness constraint in `patients`. The
auto-create-on-name-match logic in `crud.py` means a typo or alternate romanisation silently
creates a duplicate patient. Medical records then accumulate on different patient rows for
the same person.

**Impact:** High for data integrity. Duplicate patient records in a clinical system can lead
to incomplete history being shown to the doctor.

**Suggested fix:** Add a `UNIQUE(doctor_id, name)` constraint, or implement a fuzzy-match
confirmation step ("Did you mean 张三 (existing patient)?") before auto-creating.

---

### 6. Single-LLM tool schema doing double duty
**Current state:** The routing tool call carries both intent metadata (patient name, age,
gender, is_emergency) and full clinical content (8 structured fields). When the LLM produces
a routing error, clinical content is also lost. When clinical content is complex, routing
reliability drops.

**Evidence:** The fallback to `structure_medical_record()` when no clinical fields are returned
shows this tension already exists.

**Impact:** Low-medium. The single-call design is the right latency trade-off, but the schema
coupling should be monitored as clinical content complexity grows (e.g. neuro cases with NIHSS,
oncology with multi-cycle chemo data).

**Suggested fix:** No immediate change needed. Monitor fallback rate in logs. If it exceeds
~5% of `add_record` intents, re-evaluate splitting routing and structuring back into two calls
for complex cases only.

---

### 7. No audit trail
**Current state:** `created_at` timestamps exist but there is no record of who wrote what,
what the LLM originally produced vs. what was saved, or what edits were made.

**Impact:** Medium. Insufficient for clinical compliance in a multi-doctor setup. Also blocks
the P2 feedback-to-model loop, which depends on capturing doctor edits.

**Suggested fix:** Add `created_by` (doctor_id) and `source` (`agent` | `interview` | `rest`)
to `medical_records`. Log original LLM output separately from the saved record once the
approval gate exists.

---

## Priority Order for Fixes

| Priority | Issue | Effort | Blocks |
|----------|-------|--------|--------|
| P0 | Doctor approval gate (no direct AI writes) | Medium | Clinical safety |
| P0 | Identity verification (server-side doctor_id) | Low | Privacy/security |
| P1 | `doctors` table / decouple from WeChat openid | Medium | Multi-channel, auth |
| P1 | Uniqueness constraint on patient names | Low | Data integrity |
| P1 | Audit trail (`created_by`, `source`) | Low | Compliance, feedback loop |
| P2 | Emergency notification resilience | Low | Reliability |
| P2 | Monitor single-LLM fallback rate | None (observability) | Schema stability |

---

## What Does Not Need Changing Now

- SQLite is appropriate for single-process MVP; migrate to PostgreSQL when multi-worker is needed.
- In-memory session is a known limitation; acceptable until Redis is warranted by load.
- faster-whisper local ASR with `initial_prompt` bias is sufficient until a fine-tuned medical
  ASR model is available.
- The `ROUTING_LLM` / `STRUCTURING_LLM` configuration split is the right abstraction even
  though both currently point to the same model.
