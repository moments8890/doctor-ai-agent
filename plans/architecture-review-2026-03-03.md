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

### 1. Identity is unverified
**Current state:** `doctor_id` is a WeChat openid passed as a request parameter. It is never
authenticated — any caller who knows a valid openid has full read/write access to that doctor's
patients and records.

**Impact:** High. This is a data integrity and privacy risk even in single-doctor use if the
WeChat webhook is publicly reachable.

**Suggested fix:** Derive `doctor_id` server-side from the verified WeChat XML signature, not
from caller-supplied input. For REST endpoints, require a session token.

---

### 2. Platform coupling — identity tied to WeChat
**Current state:** `doctor_id` is a WeChat openid. The entire tenancy model, notification
delivery, and session management assumes WeChat as the only channel.

**Impact:** Medium now, high later. Adding a web UI, mobile app, or second messaging platform
requires rethinking identity from scratch. Every DB row is keyed on a WeChat-specific identifier.

**Suggested fix:** Introduce a `doctors` table with a stable internal `id`. Store WeChat openid
as an attribute, not the primary key. Map inbound WeChat messages to the internal id at the
router boundary.

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
**Current state:** `AsyncIOScheduler` runs inside the FastAPI process. If the process crashes
between a task becoming due and `mark_task_notified()` completing, the notification may be
lost or duplicated on restart.

**Impact:** Medium. The `notified_at IS NULL` recovery catches most cases, but the 1-minute
polling interval creates a window where an emergency notification is delayed after a crash.

**Suggested fix:** For follow-up reminders, the current approach is acceptable. For emergency
tasks (`is_emergency=True`), consider an immediate retry loop rather than relying on the
scheduler interval.

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
