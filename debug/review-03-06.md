# Doctor AI Agent — High-Level Code Review

_Date: 2026-03-06_

---

## Status Update (as of 2026-03-06)

This review captured the initial snapshot. The following items have since been mitigated and pushed:

- `DONE` API rate limiting (per doctor, default `100 req/min`) across multiple routers (`ff8b465`)
- `DONE` CI deploy SSH private key handling switched to ssh-agent (`4ec5bae`)
- `DONE` Admin route protection via `X-Admin-Token` / `UI_ADMIN_TOKEN` (`f8e89ac`)
- `DONE` Additional auth audit logging for insecure fallback paths (`6e355a5`)
- `DONE` Silent prompt-load fallback paths now log explicit errors (`d3709c0`)
- `DONE` UI manage endpoints now enforce token-bound doctor scope (`c865d64`)
- `DONE` Ollama startup warmup now uses explicit timeout + exponential backoff retries (1s/2s/4s)
- `DONE` Records/voice/neuro router 5xx responses now avoid leaking raw internal exception text
- `DONE` WeChat media/voice user-facing failure messages now avoid exposing internal exception details
- `DONE` Token auth failure responses are now standardized to generic 401 messages (no raw parser/verify errors)
- `DONE` UI label bind/unbind 404 paths now use generic not-found responses (no raw ValueError details)
- `DONE` Admin tunnel-log read errors now return sanitized detail (no raw exception text)
- `DONE` Label assignment/removal now uses domain exceptions (`PatientNotFoundError`/`LabelNotFoundError`) instead of raw `ValueError`
- `PARTIAL` LLM resilience (timeouts/retry/backoff/circuit breaker) is implemented in core LLM paths, but should continue to be audited for full endpoint parity
- `PARTIAL` Session handling remains in-memory first; test lifecycle hardening was completed, but full Redis/DB-backed redesign is still open
- `PARTIAL` Error handling consistency improved in targeted hotspots, but full exception taxonomy + consistent structured logging across all modules remains open
- `PARTIAL` Data-layer modularization and migrations have started (repositories + Alembic present), but full CRUD split/refactor is still open

---

## Overview

A WeChat-native AI assistant for specialist doctors (primarily cardiology & oncology) that:
- Accepts voice/text medical notes from doctors via WeChat or mobile app
- Structures raw clinical input into standardized medical records using LLM
- Persists patient data locally (SQLite/MySQL) with no mandatory cloud dependency
- Manages conversation history with rolling-window compression for continuity
- Provides task scheduling (follow-ups, appointments, emergencies)
- Includes local speech-to-text (faster-whisper) and vision capabilities
- Supports multiple LLM backends (Ollama, DeepSeek, Groq, Gemini, Tencent LKEAP, OpenAI)

**Phase Status:** Phase 3 in progress. Phases 1-2 (core structuring + patient DB + WeChat bot) are complete.

**Technology Stack:**
- Backend: FastAPI + SQLAlchemy (async) + SQLAdmin
- Database: SQLite (dev) / MySQL (production)
- Frontend: React (web) + WeChat Mini Program
- LLM: Multi-provider (local Ollama default, cloud APIs fallback)
- Speech: faster-whisper (local) + OpenAI Whisper API (fallback)
- Scheduling: APScheduler for task notifications

---

## Critical Issues

### 1. LLM calls have no timeouts, retries, or circuit breakers

No retry logic, no rate-limit handling, no circuit breaker. Ollama warmup only at startup; no re-warmup if model unloads. Agent dispatch has no timeout — a slow/failing LLM can hang the entire request chain indefinitely.

```python
# main.py — 3 attempts with 1s sleep, but no exponential backoff
await client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "ping"}],
    max_tokens=1,
)
```

**Fix:** Add timeout to all LLM calls (30s structuring, 60s agent dispatch). Exponential backoff retry (1s/2s/4s). Fallback to simpler model on timeout.

---

### 2. Session state is fragile global dicts

`services/session.py` uses 4 global dicts (`_sessions`, `_locks`, `_loaded_from_db`, `_persist_tasks`) plus a `_pending_turns` list. Tests directly mutate these private dicts in conftest.py (anti-pattern). Race conditions possible if concurrent requests arrive while session is loading from DB.

```python
_sessions: Dict[str, DoctorSession] = {}
_locks: Dict[str, asyncio.Lock] = {}
_persist_tasks: Dict[str, asyncio.Task] = {}
```

**Fix:** Migrate to DB-backed session or proper cache (Redis/cachetools). Implement explicit session lifecycle. Add RW locks.

---

### 3. Error handling is inconsistent — silent failures everywhere

48+ raw `HTTPException` raises. Many `except Exception:` blocks that swallow errors silently. No custom exception hierarchy (only 1 custom exception exists).

```python
except Exception:
    knowledge_context = ""  # routers/records.py — error swallowed
except Exception:
    return []               # routers/ui.py — error swallowed
```

**Fix:** Create domain exceptions (PatientNotFoundError, InvalidMedicalRecordError). Log all exceptions with context (doctor_id, patient_id, operation). Never return generic 500 without structured detail.

---

### 4. No access control on doctor_id

`doctor_id` comes from the request body, not the JWT. Any authenticated user can read any doctor's data.

```python
@router.post("/chat")
async def chat(req: ChatRequest):
    doctor_id = req.doctor_id  # not validated against auth token
```

**Fix:** Extract `doctor_id` from JWT token. Add audit log for all mutations. Unit test that unauthorized doctors cannot access others' data.

---

### 5. No input validation at service layer

Only heuristic-based patient name filtering (regex). No length limits on medical record fields (all `Text` columns). No rate limiting on API endpoints.

```python
_BAD_NAME_FRAGMENTS = ["叫什么名字", "这位患者", "请问", "患者姓名"]
_LEADING_NAME = re.compile(r"^\s*([\u4e00-\u9fff]{2,4})(?:[，,\s]|$)")
```

**Fix:** Add Pydantic validators at service layer. Enforce column constraints. Add API rate limiting (100 req/min per doctor).

---

## Major Architectural Issues

### 6. Data layer is too thin — no repository pattern

`db/crud.py` is 800+ lines of raw SQLAlchemy queries. Business logic directly writes SQL. Hard to mock/test without real DB. No protection against N+1 queries.

**Fix:** Create repository classes (PatientRepository, RecordRepository). Unit test services with mock repositories.

---

### 7. No database migrations (Alembic)

`db/init_db.py` calls `create_tables()` which creates all tables at once. Schema changes require manual DB cleanup. No rollback strategy.

**Fix:** Adopt Alembic. Create migration per schema change. Test migrations locally before production.

---

### 8. Conversation turns accumulate indefinitely

No TTL or cleanup job. Compression fails are silently ignored, leaving orphaned turns.

```python
except Exception as e:
    log(f"[Memory:{doctor_id}] clear persisted turns FAILED: {e}")
    # exception swallowed, orphaned turns remain
```

**Fix:** Add `created_at` to turns; expire rows > 7 days old. Implement startup cleanup job. Wrap compress + clear in atomic transaction.

---

### 9. Large files that need splitting

- `services/` — 39 files, should be split into sub-packages (`services/llm/`, `services/persistence/`, `services/health/`)
- `routers/ui.py` — 1049 lines, should be split by entity
- `routers/wechat.py` — 851 lines, should extract state machine to separate service
- `db/crud.py` — 800+ lines, should be split by entity (patients.py, records.py, tasks.py)

---

### 10. No API versioning or formal contract

Frontend hardcodes endpoint paths. Mini program has duplicated API adapter logic. No versioning.

**Fix:** Version all endpoints (`/api/v1/...`). Generate API clients from OpenAPI schema.

---

## Medium Priority Issues

### Logging is inconsistent

Some modules use custom `log()`, others use `logging.getLogger(__name__)`. No structured/JSON logging for production observability. Context variables (doctor_id, trace_id) often missing from log lines.

**Fix:** Standardize on `logging.getLogger`. Use structlog for JSON output. Add context vars to all logs.

---

### Health check is a stub

```python
@app.get("/healthz")
def healthz():
    return {"status": "ok"}
```

**Fix:** Check DB connectivity, LLM availability, and scheduled task status. Add `/readyz` that returns 503 until warmup completes.

---

### SSH key written to disk in CI

`deploy-prod.yml` echoes the private key to `~/.ssh/id_rsa` — could appear in logs.

**Fix:** Use GitHub environments for secrets scoping. Replace with temporary credentials.

---

### Integration tests require live services

E2E tests need real Ollama/DeepSeek running. No fixtures for synthetic data. Tests can't run in isolated CI without Docker Compose.

**Fix:** Mark integration tests with `@pytest.mark.integration`, skip by default. Create data fixtures for common scenarios.

---

## What's Working Well

- Core medical structuring logic (intent dispatch, specialist-aware prompts for cardiology/oncology)
- Multi-LLM abstraction (Ollama, DeepSeek, Groq, Gemini, Tencent) — clean and flexible
- CI/CD pipeline with 80%+ coverage gate and diff-cover validation
- Async/await used correctly throughout most of the codebase
- Conversation memory with rolling-window compression is well-designed
- Admin UI (SQLAdmin) is polished and useful
- WeChat integration is comprehensive (messaging, media, auth)
- Local-first deployment philosophy (Ollama default, cloud fallback)

---

## Priority Summary

| Priority | Fix | Status |
|---|---|---|
| Critical | LLM timeout + exponential backoff retry | `PARTIAL` |
| Critical | Validate `doctor_id` from JWT, not request body | `PARTIAL` |
| Critical | Custom exception hierarchy + log all errors with context | `PARTIAL` |
| Critical | Fix session state (DB-backed or proper cache) | `PARTIAL` |
| High | Repository pattern for `db/crud.py` | `PARTIAL` |
| High | Alembic migrations | `PARTIAL` |
| High | Conversation turn TTL + cleanup job | `PARTIAL` |
| Medium | Structured logging (structlog) | `OPEN` |
| Medium | Split large files (`services/`, `routers/ui.py`, `db/crud.py`) | `OPEN` |
| Medium | Expand `/healthz`; add `/readyz` | `PARTIAL` |
| Medium | Fix SSH key in CI deploy | `DONE` |
| Low | API versioning + OpenAPI client generation | `OPEN` |
| Low | Load testing + performance regression gates | `OPEN` |
