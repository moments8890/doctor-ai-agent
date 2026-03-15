# Services Module

Purpose:
- Core business logic organized as sub-packages. Each sub-package owns one domain.

Key areas:
- `runtime/` — ADR 0012 UEC pipeline: understand → resolve → read/commit engine → compose. Entry point: `process_turn()`.
- `ai/` — LLM integration: `llm_client.py`, `structuring.py`, `vision.py`, `transcription.py`, `llm_resilience.py`.
- `domain/` — Domain logic: `intent_handlers/_confirm_pending.py` (draft save + background CVD extraction).
- `patient/` — Risk scoring, NL search, timeline, encounter detection.
- `knowledge/` — PDF/Word extraction, doctor knowledge base, specialty skill loader.
- `notify/` — Task scheduling (APScheduler), notification delivery.
- `export/` — PDF generation, outpatient reports.
- `auth/` — JWT, rate limiting, access codes, WeChat ID hashing.
- `observability/` — Audit trail, routing metrics, trace context.

Notes:
- Keep side effects and external calls centralized here (not in routers/channels).
- New code should not use the legacy `session.py` — it is scheduled for removal.
