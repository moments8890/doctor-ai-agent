# Backend Comprehensive Audit — 2026-03-29

> Five-dimension deep dive: feature completeness, best practices, fault tolerance, debugging visibility, and extensibility.

---

## Dashboard

| Dimension | Score | Verdict |
|-----------|-------|---------|
| Feature Completeness | **92 %** | Ship-ready for MVP; 5 endpoints missing, 3 roadmap phases partially blocked |
| Best Practices | **B+** | Solid architecture; type safety & transaction patterns need work |
| Fault Tolerance | **5.5 / 10** | LLM path is resilient; DB + concurrency = critical gaps |
| Debugging Visibility | **7.5 / 10** | Excellent tracing & audit; SQL visibility and metrics are blind spots |
| Extensibility | **6.5 / 10** | Adding intents & LLM providers is easy; channels & per-doctor customization are hard |

---

## 1  Feature Completeness

### What works end-to-end

- Authentication & unified login (doctor + patient)
- Patient management (CRUD, search, grouped list, timeline)
- Doctor interview (multi-turn session, carry-forward, confirm/cancel)
- Patient pre-consultation interview
- Medical record creation (chat, image OCR, PDF extract, voice transcribe)
- Clinical decision support (diagnosis pipeline, suggestion review, finalize)
- Task management (CRUD, scheduling, APScheduler notifications)
- Knowledge base (add/edit/delete, URL import, file upload, citation tracking)
- Draft reply pipeline (AI-generated replies, teaching loop)
- Review queue (3-tab: outpatient / reply / completed)
- Data export (PDF, outpatient report, bulk ZIP)
- Admin tools (invite codes, DB viewer, observability, config)

### Missing endpoints (frontend calls them, backend returns 404)

| Endpoint | Impact |
|----------|--------|
| `POST /api/export/template/upload` | Can't upload custom report templates |
| `GET  /api/export/template/status` | Can't fetch template metadata |
| `DELETE /api/export/template` | Can't revert to default template |
| `POST /api/records/pending/{id}/confirm` | Low — current flow creates records directly |
| `POST /api/records/pending/{id}/abandon` | Low — same as above |

### Product roadmap coverage

| Phase | Coverage | What's blocking the rest |
|-------|----------|--------------------------|
| 1 — Patient Pre-Consultation | **100 %** | — |
| 2 — AI Diagnostics | **83 %** | External AI integration (HuatuoGPT, MedPaLM) has no backend hooks |
| 3 — Doctor-Patient Loop | **70 %** | Prescriptions, labs, allergies are flat NHC text strings — no structured extraction |
| 4 — Lifecycle Management | **33 %** | Outcome tracking schema doesn't exist |

### Missing data models

| Model needed | Unblocks |
|-------------|----------|
| `PrescriptionOrder` | Patient medication list (P3.7) |
| `LabResult` | Structured lab display (D3.6) |
| `PatientOutcome` | Longitudinal treatment tracking (F4.1) |
| `NotificationPreference` | Per-doctor/patient notification routing (D6.6, P4.1) |

---

## 2  Best Practices

### Strengths

- **Clean 3-layer architecture** — channels (API) → domain (business logic) → db (data access). CRUD properly isolated.
- **Async done right** — all I/O is `async`; blocking PDF/image ops use `run_in_executor()`.
- **59+ Pydantic models** for request/response validation.
- **Auth is solid** — unified JWT with role-based access, PBKDF2-SHA256 hashing, configurable rate limiting.
- **Frozen dataclass config** with secret masking in logs. Production guards at startup.
- **Proper indexing** — named indexes on frequently queried columns, foreign keys with CASCADE.

### Critical issues

| Issue | Where | Why it matters |
|-------|-------|----------------|
| Hardcoded dev JWT secret | `infra/auth/unified.py:28` | If deployed to prod, all JWTs are forgeable |
| 44× raw `AsyncSessionLocal()` | Throughout `channels/web/` | Connection leak risk; should use DI |
| No return type hints on handlers | `channels/web/*.py` | Breaks type-checking and IDE support |
| Unsafe `json.loads()` | `patient_portal_tasks.py:13` | Crash on corrupted JSON; no Pydantic validation |
| Mixed timezone patterns | Multiple files | `datetime.utcnow()` (deprecated) vs `datetime.now(timezone.utc)` |
| `__import__("datetime")` | `infra/auth/unified.py:223` | Code smell from incomplete refactor |

### Moderate issues

- **Code duplication** across interview handlers (`doctor_interview_turn.py`, `_confirm.py`, `_shared.py`).
- **Inconsistent error messages** — some snake_case English, some Chinese, no standard error code enum.
- **Only 3 Pydantic validators** across 59+ models — phone, date range, cross-field validation missing.
- **N+1 query risk** in `search_patients_nl()` — relationship loading not specified.
- **Unindexed LIKE searches** on `medical_records.content` — full table scans.

---

## 3  Fault Tolerance

### What's resilient

| Component | Protection |
|-----------|-----------|
| LLM routing/intent calls | Exponential backoff retry (2-3 attempts) + circuit breaker per model |
| Interview LLM | 3-attempt retry with 1s/2s backoff, graceful fallback message |
| WeChat intent processing | Hard 4.5s timeout (`asyncio.wait_for`) |
| Background tasks | `safe_create_task()` logs all unhandled exceptions |
| Health checks | `/healthz` monitors DB, scheduler, background workers |
| Connection pool | `pool_pre_ping=True` detects stale connections |

### Critical unhandled failures

| Failure scenario | What happens | Severity |
|------------------|-------------|----------|
| DB query hangs | Request blocks **indefinitely** — no query timeout set | **Critical** |
| DB pool exhausted (30 connections) | Immediate 500, no queuing or backpressure | High |
| Two concurrent `interview_turn` on same session | Data race — second request silently overwrites first turn | **Critical** |
| WeChat message send fails | Message **silently lost** — no retry, no dead-letter queue | High |
| Alembic migration error in production | App **refuses to start entirely** | **Critical** |
| `session.commit()` throws | No rollback in most call sites — partial data saved | High |
| Audit drain worker crashes | Queue fills, then audit events **dropped** — no auto-restart | Medium |
| Circuit breaker state | In-memory only — lost on restart, re-triggers retries immediately | Medium |
| Jieba initialization hangs | Entire app startup blocks (synchronous, no timeout) | Medium |
| WeChat KF cursor write fails | Next sync re-processes old messages (duplicate notifications) | Medium |

### Missing across the board

- No DB query-level timeouts
- No transaction savepoints (`begin_nested()`) for grouped operations
- No optimistic locking (version column) on any table
- No dead-letter queue for failed notifications
- No auto-restart for dead background workers (health endpoint reports but doesn't act)

---

## 4  Debugging Visibility

### What's traceable today

Given a `trace_id`, you can reconstruct the full request journey:

```
trace_id → HTTP layer (method, path, status, latency)
         → Agent layer (intent routing, fast vs LLM, handler dispatch)
         → LLM layer (full prompt + response in llm_calls.jsonl)
         → Audit layer (doctor_id, action, resource, IP, success/fail)
         → Structured logs (doctor_id + trace_id auto-injected)
```

### Infrastructure

| Capability | Implementation | Status |
|------------|---------------|--------|
| Structured logging | `structlog` with JSON output, context vars | Excellent |
| Request tracing | Custom spans in JSONL, `trace_block()` context manager | Excellent |
| LLM call logging | Dual: per-call `.txt` + append-only JSONL | Excellent |
| Audit trail | Async buffered writes to DB, 7-year retention | Excellent |
| Health endpoints | `/healthz` (liveness) + `/readyz` (startup) | Excellent |
| Log rotation | Size-based (10 MB) with 5 backups | Good |
| Admin debug UI | `/api/debug/logs`, `/api/debug/observability` (trace waterfall) | Good |
| Routing metrics | In-memory counters, fast-router hit rate | Basic |

### Blind spots

| Gap | Impact |
|-----|--------|
| SQL query logging disabled (`echo=False`) | Can't diagnose slow DB queries |
| No error aggregation (Sentry) | Errors only in local logs, not centralized |
| No latency percentiles (p50/p95/p99) | Can't set SLOs or detect degradation |
| No LLM token/cost tracking | Can't budget or detect runaway calls |
| Request body not logged | Can't replay failed requests |
| Turn log defined but not actively written | Decision mining incomplete |

---

## 5  Extensibility

### Effort to add common features

| Extension | Effort | Files to touch | Notes |
|-----------|--------|----------------|-------|
| New LLM provider | **Trivial** | 1-2 | Add to provider registry dict + env var |
| New API endpoint | **Trivial** | 2 | Create router + register in `app_routes.py` |
| New intent | **Moderate** | 5 | types.py + handler + __init__ + prompt_config + prompt .md + routing prompt update |
| New DB table | **Moderate** | 4-6 | Model + CRUD + import + handler + no migration story yet |
| New channel (Telegram) | **Significant** | 10-15 | Session mgmt locked to doctor_id, notifications locked to WeChat |
| Per-doctor customization | **Significant** | 8+ | No per-doctor config table, prompts are static files |
| Multi-specialty support | **Major** | 15+ | Only neurology domain prompt exists, routing LLM unaware of specialty |
| Team/org features | **Major** | 20+ | Everything scoped to individual doctor_id |

### Well-designed extension points

- **Intent handler `@register` decorator** — clean, fail-fast (assert at import)
- **LLM provider registry** — env-driven, zero code changes needed
- **Prompt LayerConfig matrix** — explicit, every intent must have an entry
- **Knowledge categories** — simple enum, knowledge auto-loaded into prompts
- **CRUD layer** — thin SQLAlchemy wrappers, easy to add operations

### Coupling hotspots (pain points)

| Module | Problem |
|--------|---------|
| `channels/wechat/router.py` | 24 imports across all layers — god module |
| `domain/diagnosis_pipeline.py` | 18 imports — tightly coupled to everything |
| Channel → Domain direct calls | Bypasses agent layer in several places |
| Session management | Hardcoded to `doctor_id` — can't support patient or team sessions |
| Notification sender | Hardcoded to WeChat — no abstract interface |
| Static prompts | No per-doctor overrides, no versioning, no hot-reload |

---

## Recommendations

### Before Production (do now)

| # | Action | Why | Effort |
|---|--------|-----|--------|
| 1 | **Fix hardcoded JWT secret** — fail-fast in prod, don't default | All tokens forgeable if this reaches production | 1 hour |
| 2 | **Add DB query timeouts** — wrap `session.execute()` | Requests can hang indefinitely on slow DB | 2 hours |
| 3 | **Add optimistic locking to interview sessions** — version column | Concurrent turns silently overwrite each other | 4 hours |
| 4 | **Add WeChat message retry queue** | Failed sends are permanently lost | 4 hours |
| 5 | **Add transaction rollback** — `try/finally` on all commit paths | Partial data saved on commit failure | 3 hours |

### Next Sprint (high impact)

| # | Action | Why | Effort |
|---|--------|-----|--------|
| 6 | Enable SQL query logging (env-configurable) | Biggest debugging blind spot | 1 hour |
| 7 | Standardize DB session management with DI | 44 raw session creations = leak risk | 1 day |
| 8 | Integrate Sentry | Errors only in local logs today | 2 hours |
| 9 | Implement template management endpoints | Quick win — unblocks frontend feature | 4 hours |
| 10 | Add per-doctor config table (`doctor_settings`) | Foundation for all per-doctor customization | 4 hours |

### Architectural (longer term)

| # | Action | Why | Effort |
|---|--------|-----|--------|
| 11 | Abstract notification interface | Unblocks Telegram, SMS, push | 2 days |
| 12 | Structured clinical data extraction | Unblocks medication list, lab views | 3 days |
| 13 | Prompt versioning (DB-backed) | Per-doctor overrides, A/B testing, rollback | 3 days |
| 14 | Domain event system (pub/sub) | Decouple channels from domain logic | 2 days |
| 15 | Multi-specialty domain prompts | Currently only neurology; others get generic behavior | 1 day per specialty |

---

## Appendix: File References

Key files mentioned in this audit:

| Area | File |
|------|------|
| JWT secret issue | `src/infra/auth/unified.py:28` |
| Session management | `src/db/engine.py` (pool config), all `channels/web/*.py` (44 usages) |
| LLM resilience | `src/infra/llm/resilience.py` (circuit breaker), `src/agent/llm.py` (calls) |
| Interview race condition | `src/domain/patients/interview_turn.py` |
| Observability | `src/infra/observability/` (7 files) |
| Health checks | `src/app_routes.py:159-165` |
| WeChat message send | `src/channels/wechat/router.py:212` |
| Prompt system | `src/agent/prompt_composer.py`, `src/agent/prompt_config.py` |
| Provider registry | `src/infra/llm/client.py` |
| Audit trail | `src/infra/observability/audit.py`, `src/db/models/audit.py` |
