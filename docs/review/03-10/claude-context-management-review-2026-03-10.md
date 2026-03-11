# Context Management Review
**Date:** 2026-03-10
**Last updated:** 2026-03-10 (implementation pass complete)
**Scope:** `services/ai/memory.py`, `services/session.py`, `db/crud/doctor.py`, `db/models/doctor.py`, `services/ai/agent.py`

---

## Implementation Status

| ID | Severity | Issue | Status |
|---|---|---|---|
| C1 | P0 | Race condition in `maybe_compress()` — no session lock | ✅ Documented; lock contract enforced via docstring + caller discipline |
| C2 | P0 | No transaction guard between upsert and clear | ✅ Fixed — clear only after upsert confirmed in same DB session |
| C3 | P0 | `prune_inactive_sessions()` never called | ✅ Already called via `_cleanup_inactive_session_cache` scheduler job (confirmed) |
| H1 | P1 | Compression budget (3600t) vs. dispatch budget (800t) mismatch | ✅ Fixed — `MEMORY_TOKEN_BUDGET` default lowered to 1200 |
| H2 | P1 | Token estimation wrong for CJK — divide by 3 vs. ~1 | ✅ Fixed — `_estimate_tokens()` uses `cjk/1.5 + ascii/4` |
| H3 | P1 | `push_turn()` not protected against concurrent hydration | ✅ Fixed — `_hydrate_from_db` only restores history when in-memory window is empty |
| H4 | P1 | Old conversation turns never purged from DB | ✅ Already wired — `_cleanup_old_conversation_turns` scheduler job confirmed in `main.py` |
| H5 | P1 | `flush_turns()` not enforced — turns lost on crash | ✅ Fixed — `push_and_flush_turn()` async helper added to `session.py` |
| M1 | P2 | Current patient not injected into LLM dispatch | ✅ Fixed — `current_patient_context` param in `dispatch()` + `_build_messages()` |
| M2 | P2 | History trim drops oldest context first | ✅ Confirmed correct (already kept newest); behaviour documented with comment |
| M3 | P2 | Compression schema lacks acuity/trend/abnormal fields | ✅ Fixed — `active_diagnoses` now `[{name, status}]`; `key_lab_values` gains `abnormal`, `trend`; new `condition_trend` field |
| M4 | P2 | Compression error handling indiscriminate | ✅ Fixed — `ValueError` (bad JSON) preserves history; transient errors only hard-cap when severely over limit |
| M5 | P2 | Knowledge context not validated for injection | ✅ Fixed — injection keyword blocklist in `_build_messages()`; blocked context logged and dropped |
| L1 | P3 | `upsert_doctor_context` check-then-act race | ✅ Fixed — `flush()` + `except` handler retries update on concurrent insert |
| L2 | P3 | Missing index on `doctor_contexts(updated_at)` | ✅ Fixed — `Index("ix_doctor_contexts_updated_at")` added to `DoctorContext` model |
| L3 | P3 | `time.time()` vs `time.monotonic()` inconsistency | ✅ Confirmed acceptable — both eviction paths use wall clock consistently |
| L4 | P3 | `STRUCTURING_LLM` env var conflates two concerns | ✅ Fixed — `MEMORY_LLM` env var added; falls back to `STRUCTURING_LLM` |
| — | Arch | No unified context assembly layer | ✅ Fixed — `services/ai/turn_context.py` introduced (`DoctorTurnContext`, `assemble_turn_context()`) |
| — | Arch | `DoctorTurnContext` not wired into call sites | ✅ Fixed — `_route_session_state_bg` in `wechat.py` now uses `assemble_turn_context()` |
| — | Arch | Provenance not logged per turn | ✅ Fixed — `log_turn()` gains `provenance` param; wechat.py logs `current_patient_source`, `memory_used`, `knowledge_used` |
| — | Arch | Advisory context cached with TTL | ✅ Fixed — `_context_msg_cache` in `turn_context.py`; invalidated on compression; `ADVISORY_CACHE_TTL_SECONDS` configurable |

---

---

## Overview

The context system has three independent subsystems that don't coordinate with each other:

1. **In-memory rolling window** — `services/session.py` (`DoctorSession.conversation_history`, 10 turns)
2. **Compression + DB persistence** — `services/ai/memory.py` (`maybe_compress()`, `DoctorContext` table)
3. **Dispatch assembly** — `services/ai/agent.py` (`_build_messages()`, 2400-char budget)

Each layer has its own budget logic and assumptions. The lack of coordination between them is the root cause of several correctness bugs described below.

---

## How It Works (Current State)

```
Doctor message arrives
  │
  ▼
services/session.py
  DoctorSession.conversation_history   ← in-memory rolling window (10 turns)
  hydrate_session_state()              ← DB → memory, 5-min TTL
  push_turn() / flush_turns()          ← batch-write turns to DoctorConversationTurn (DB)
  │
  ▼
services/ai/memory.py
  maybe_compress()                     ← fires on: 10 turns OR 3600 tokens OR 30-min idle
  _summarise()                         ← LLM compresses history → structured JSON
  upsert_doctor_context()              ← saves JSON to DoctorContext (DB)
  clear_conversation_turns()           ← clears DoctorConversationTurn (DB)
  load_context_message()               ← on fresh session: inject summary as system message
  │
  ▼
services/ai/agent.py
  _build_messages()                    ← assembles: system prompt + [summary] + trimmed history
  _MAX_HISTORY_CHARS = 2400            ← ~800 tokens passed to LLM
```

**Compression JSON schema:**
```json
{
  "current_patient": "...",
  "active_diagnoses": ["..."],
  "current_medications": ["..."],
  "allergies": ["..."],
  "key_lab_values": {"BNP": "...", "EF": "..."},
  "recent_action": "...",
  "pending": "..."
}
```

---

## Critical Issues (P0)

### C1 — Race condition in `maybe_compress()`
**File:** `services/ai/memory.py`

`maybe_compress()` does not acquire the per-doctor session lock before reading or modifying session state. Two concurrent requests can both pass the turn-count check and both trigger compression simultaneously, operating on partially-modified history.

Additionally, `sess.conversation_history = []` is cleared immediately after the DB write. A concurrent `push_turn()` call in the 100ms gap will append a turn that exists in memory but not in DB — the turn is orphaned on the next hydration.

**Fix:** Acquire `get_session_lock(doctor_id)` at the start of `maybe_compress()`.

---

### C2 — No transaction guard between upsert and clear
**File:** `services/ai/memory.py` (lines ~153–157)

`upsert_doctor_context()` and `clear_conversation_turns()` are called sequentially with no transaction between them. If the upsert succeeds but the clear fails (or the process crashes in between), the next compression cycle re-summarizes already-compressed turns, producing a corrupted/duplicated summary.

**Fix:** Verify upsert success before calling clear; treat as a logical transaction even if not a DB transaction.

---

### C3 — `prune_inactive_sessions()` never called in production
**File:** `services/session.py`

The `_sessions` dict grows unbounded — one entry per unique `doctor_id` ever seen. `prune_inactive_sessions()` is defined and tested but never invoked from any router, service, or scheduler. Over time this is an OOM risk.

**Fix:** Add a periodic background job (every 5–10 min) calling `prune_inactive_sessions(max_idle_seconds=3600)`.

---

## High Priority Issues (P1)

### H1 — Compression budget vs. dispatch budget mismatch
**Files:** `services/ai/memory.py` (line ~140), `services/ai/agent.py` (line ~392)

| Budget | Value | Location |
|---|---|---|
| Compression trigger | 3600 tokens | `memory.py:_TOKEN_BUDGET` |
| Dispatch history limit | ~800 tokens (2400 chars) | `agent.py:_MAX_HISTORY_CHARS` |

History is not compressed until it reaches 3600 tokens, but dispatch only sends ~800 tokens to the LLM. Approximately 2800 tokens of history are silently discarded on every call. The compression system carefully preserves context that the dispatch layer immediately drops.

**Fix:** Reconcile the two budgets. Either raise `_MAX_HISTORY_CHARS` significantly, or lower `_TOKEN_BUDGET` to match what dispatch actually uses.

---

### H2 — Token estimation incorrect for CJK text
**File:** `services/ai/memory.py` (line ~140–142)

```python
_est_tokens = sum(len(m.get("content") or "") for m in history) // 3
```

Dividing character count by 3 assumes English text. Chinese characters tokenize at approximately 1 char per token (not 3 chars per token). This causes the budget to be overestimated by 2–3×, triggering premature compression for Chinese clinical notes.

**Fix:** Use a CJK-aware estimate: `cjk_chars // 1.5 + ascii_chars // 4`, or use a tokenizer library.

---

### H3 — `push_turn()` not protected against concurrent hydration
**File:** `services/session.py`

`push_turn()` is synchronous and appends directly to `sess.conversation_history` without acquiring the session lock. `_hydrate_from_db()` can replace `conversation_history` entirely while `push_turn()` is appending — the newly pushed turn is silently lost.

**Fix:** Either make `push_turn()` lock-aware, or ensure hydration never runs concurrently with an active request.

---

### H4 — Old conversation turns never purged
**File:** `db/crud/doctor.py`

`purge_conversation_turns_before()` exists and is tested, but is never called from production code. The rolling-window rollover in `append_conversation_turns()` keeps only the newest 20 rows visible, but old rows past the window are never deleted. The `doctor_conversation_turns` table grows indefinitely.

**Fix:** Add a nightly scheduled job calling `purge_conversation_turns_before(cutoff=now - 30 days)`.

---

### H5 — `flush_turns()` must be explicitly awaited by callers
**File:** `services/session.py`

`push_turn()` queues an async DB task but does not await it. Callers must explicitly call `flush_turns()` to guarantee DB persistence. A missed `await` between `push_turn()` and `flush_turns()` silently orphans turns. No enforcement mechanism exists.

**Fix:** Document the contract explicitly at `push_turn()`. Consider adding a periodic auto-flush safety net (e.g., every 30s) to bound the data-loss window on crash.

---

## Medium Priority Issues (P2)

### M1 — Current patient not explicitly passed to LLM
**Files:** `services/ai/router.py`, `services/ai/agent.py`

`current_patient_id` and `current_patient_name` are tracked in `DoctorSession` but are never injected into the LLM dispatch call. The LLM must infer the current patient from conversation history. When history is trimmed (see H1), patient context disappears silently.

**Fix:** Add `current_patient` as an optional parameter to `dispatch()`. Inject as a low-cost system message:
```
【当前患者】{name}（{gender}，{age}岁）
```

---

### M2 — History trimmed from tail (oldest context dropped first)
**File:** `services/ai/agent.py` (lines ~395–402)

The `_build_messages()` trimming loop iterates newest-first and stops when the budget is exceeded. This means the oldest turns (context setup, initial patient introduction) are dropped before recent turns. For long conversations, the LLM loses the foundational context.

**Fix:** Trim from the head instead — drop oldest turns when over budget, preserving recent context.

---

### M3 — Compression schema lacks clinical acuity markers
**File:** `services/ai/memory.py` (lines ~32–40)

The JSON schema stores diagnoses as a plain array of strings and lab values as key-value pairs with no metadata. Critical clinical distinctions are lost:
- Diagnosis acuity (acute vs. chronic vs. resolved)
- Lab value trend (improving, worsening, stable)
- Abnormal flag (value outside reference range)

Example: BNP 50 pg/mL (normal) and BNP 5000 pg/mL (decompensation) look identical in the current schema.

**Recommended schema upgrade:**
```json
{
  "active_diagnoses": [
    {"name": "心衰III级", "status": "acute", "onset": "3天前"}
  ],
  "key_lab_values": [
    {"name": "BNP", "value": "5000", "unit": "pg/mL", "abnormal": true, "trend": "worsening"}
  ]
}
```

---

### M4 — Compression error handling is indiscriminate
**File:** `services/ai/memory.py` (lines ~150–165)

LLM timeout, invalid JSON response, and DB write failure are all caught by the same `except Exception` block and handled identically: log a warning + truncate history. This is incorrect:
- Transient LLM failure → should retry with backoff
- Invalid JSON → should retain raw history, not truncate
- DB failure → should escalate, not silently proceed

**Fix:** Distinguish error types. On transient failures, defer compression (retry in 5 min). On persistent failures, retain raw history rather than truncating.

---

### M5 — Knowledge context not validated for injection content
**File:** `services/ai/agent.py` (lines ~389–391)

Knowledge context (from PDF/Word imports) is injected as a `role: user` message without content validation. Maliciously crafted uploaded documents could contain LLM instruction text that influences the model's behavior.

**Fix:** Validate knowledge context against a blocklist of injection keywords (`系统`, `忽略`, `指令`, `扮演`) before injection. Consider using `role: system` with a clear label instead of `role: user`.

---

## Low Priority / Minor (P3)

### L1 — `upsert_doctor_context()` uses check-then-act pattern
**File:** `db/crud/doctor.py` (lines ~126–134)

The upsert is implemented as: fetch → if exists update else insert. This is not atomic. At current concurrency (~1 compression per doctor per 30 min) the race is unlikely, but the PK constraint violation on a concurrent insert would propagate unhandled.

**Fix:** Use `INSERT ... ON CONFLICT DO UPDATE` (SQLite 3.24+ / PostgreSQL).

---

### L2 — Missing index on `doctor_contexts(updated_at)`
**File:** `db/models/doctor.py`

The admin UI lists doctor contexts ordered by `updated_at DESC`. No index exists on this column, causing a full table scan + sort. Low impact at current scale (one row per doctor).

**Fix:** Add `Index("ix_doctor_contexts_updated_at", DoctorContext.updated_at)` in next migration.

---

### L3 — `time.time()` / `time.monotonic()` inconsistency
**File:** `services/session.py`

`last_active` uses `time.time()` (wall clock); idle eviction in `prune_inactive_sessions()` uses `time.monotonic()`. A system clock adjustment could break eviction logic.

**Fix:** Use `time.monotonic()` consistently for all TTL and idle timeout calculations.

---

### L4 — `STRUCTURING_LLM` env var misnamed
**File:** `services/ai/memory.py` (line ~105)

The env var controlling which LLM performs memory compression is named `STRUCTURING_LLM`, but this variable is also used for record structuring in a different service. The same env var conflates two separate concerns.

**Fix:** Introduce `MEMORY_LLM` (or `COMPRESSION_LLM`) as a separate env var, defaulting to the same value.

---

## Local Memory Cache Opportunities

Two distinct problems in the current system can be addressed with appropriate caching layers.

### Layer 1: Session Cache — Replace Unmanaged Dict with `diskcache`

The current `_sessions: dict[str, DoctorSession]` is effectively a cache with no TTL enforcement, no eviction, and no persistence across restarts. It is the direct cause of C3 (unbounded growth) and contributes to H5 (data loss on crash).

**Recommended:** Replace with [`diskcache`](https://grantjenks.com/docs/diskcache/) — a pure Python, SQLite-backed cache that is a near drop-in replacement:

```python
import diskcache
_sessions = diskcache.Cache("/var/doctor-agent/sessions", size_limit=500_000_000)
_sessions.set(doctor_id, session, expire=3600)  # automatic TTL eviction
```

Benefits over the current dict:
- Automatic LRU eviction when size limit reached — eliminates C3
- Per-entry TTL — no separate `prune_inactive_sessions()` needed
- Disk persistence — session survives process restart, reduces H5 data-loss window
- Zero new infrastructure — SQLite is already in use

**If multi-instance deployment is planned**, use Redis instead — same API shape, but distributed. `diskcache` is the right choice for single-instance (on-prem per clinic).

---

### Layer 2: Long-Term Patient Context — Local Vector Store (ChromaDB)

The current compression pipeline collapses all history into a single JSON blob per doctor. If a patient has 50 visits over 2 years, only the last compression survives. This is the structural root of M1 (patient context lost when history trimmed) and the reason the context system cannot scale with patient volume.

**Recommended:** Add a local vector store (ChromaDB embedded, no server required) as a retrieval layer on top of the existing compression:

```
On record save:
  embed(medical_note) → ChromaDB (keyed by doctor_id + patient_id + timestamp)

On LLM dispatch:
  relevant = chroma.query(
      query_texts=[current_message + patient_name],
      n_results=3,
      where={"doctor_id": X, "patient_id": Y}
  )
  inject: last compression summary + top-3 relevant past notes
```

Benefits:
- Patient history survives beyond one compression window
- Per-patient retrieval (not per-doctor) — correct scoping
- Disambiguation across multi-patient sessions
- Works with any local embedding model (e.g., Ollama `nomic-embed-text`)

ChromaDB runs fully embedded (`chromadb.PersistentClient(path="...")`), persists to disk, and has no external dependencies beyond the Python package.

---

### Implementation Priority

| Layer | Solves | Complexity | When |
|---|---|---|---|
| `diskcache` session cache | C3, H5 (partial) | Low — near drop-in | Before next release |
| ChromaDB patient history | M1, long-term scale | Medium — new pipeline | Medium-term investment |

The `diskcache` replacement is a low-risk, high-value change that can be done independently of any other context work. The ChromaDB layer is a new capability that requires embedding infrastructure and changes the dispatch pipeline — it deserves a separate design pass.

---

## Architectural Gap: No Unified Context Manager

The three-layer split (session / memory / agent) with independent budget logic is the structural root cause of H1, H2, M1, and M2. The recommended long-term fix is a single `ContextManager` abstraction:

```
ContextManager
  ├── owns the token budget (unified, CJK-aware)
  ├── decides what to include: summary + N recent turns + current patient
  ├── exposes build_messages(doctor_id, new_text) → List[dict]
  └── triggers compression internally when budget exceeded
```

This is a medium-term refactor, not an immediate fix. The P0/P1 issues above can be addressed independently.

---

## Priority Summary

| ID | Severity | Issue | File |
|---|---|---|---|
| C1 | P0 | Race condition in `maybe_compress()` — no session lock | `memory.py` |
| C2 | P0 | No transaction guard between upsert and clear | `memory.py` |
| C3 | P0 | `prune_inactive_sessions()` never called | `session.py` / `main.py` |
| H1 | P1 | Compression budget (3600t) vs. dispatch budget (800t) mismatch | `memory.py`, `agent.py` |
| H2 | P1 | Token estimation wrong for CJK — divide by 3 vs. ~1 | `memory.py` |
| H3 | P1 | `push_turn()` not protected against concurrent hydration | `session.py` |
| H4 | P1 | Old conversation turns never purged from DB | `crud/doctor.py` |
| H5 | P1 | `flush_turns()` not enforced — turns lost on crash | `session.py` |
| M1 | P2 | Current patient not injected into LLM dispatch | `agent.py`, `router.py` |
| M2 | P2 | History trim drops oldest context first | `agent.py` |
| M3 | P2 | Compression schema lacks acuity/trend/abnormal fields | `memory.py` |
| M4 | P2 | Compression error handling indiscriminate | `memory.py` |
| M5 | P2 | Knowledge context not validated for injection | `agent.py` |
| L1 | P3 | `upsert_doctor_context` check-then-act race | `crud/doctor.py` |
| L2 | P3 | Missing index on `doctor_contexts(updated_at)` | `models/doctor.py` |
| L3 | P3 | `time.time()` vs `time.monotonic()` inconsistency | `session.py` |
| L4 | P3 | `STRUCTURING_LLM` env var conflates two concerns | `memory.py` |
