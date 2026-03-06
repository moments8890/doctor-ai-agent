# Multi-Instance Shared Storage Execution Plan

## Goal
Deliver and validate multi-instance-safe runtime behavior with shared storage, then verify through full unit/e2e-style test gates.

## Agent-Style Workstreams
### Workstream A — Data Model + CRUD
- Add runtime tables and scheduler/notify preference primitives.
- Implement CRUD for lease, token, cursor, and conversation turns.

### Workstream B — Runtime Wiring
- Wire shared DB config (`DATABASE_URL`) in engine setup.
- Wire scheduler lease and preference gating in task cycle.
- Wire session turn persistence/hydration and memory clear behavior.
- Wire WeChat token shared cache and WeCom shared cursor.

### Workstream C — Quality and Regression
- Add/extend tests for new CRUD and runtime behavior.
- Fix regressions in legacy test harnesses.
- Run full quality gates (`pytest`, `scripts/test.sh`, `diff-cover`).

## Affected Files
- `db/engine.py`
- `db/models.py`
- `db/crud.py`
- `services/session.py`
- `services/memory.py`
- `services/tasks.py`
- `services/wechat_notify.py`
- `routers/wechat.py`
- `tests/conftest.py`
- `tests/test_engine.py` (new)
- `tests/test_runtime_state.py` (new)
- `tests/test_session_persistence.py`
- `tests/test_wechat_routes.py`
- `tests/test_tasks.py`
- `plans/multi-instance-shared-storage-design.md`
- `plans/multi-instance-shared-storage-execution.md`

## Execution Steps
1. Implement DB runtime primitives.
2. Enable remote DB URL configuration with SQLite fallback.
3. Persist/rehydrate doctor rolling conversation turns in DB.
4. Persist shared WeChat token cache in DB and keep local L1 cache.
5. Persist shared WeCom sync cursor in DB with local fallback.
6. Harden scheduler lease handling for mocked/test environments and transient failures.
7. Add/update tests for engine/runtime/session/wechat paths.
8. Run full tests and quality gates.

## Validation Commands
- `.venv/bin/python -m pytest tests/ -q`
- `bash scripts/test.sh unit`
- `git fetch --no-tags origin main`
- `.venv/bin/diff-cover reports/coverage/coverage.xml --compare-branch=origin/main --diff-range-notation=.. --fail-under=81`

## Final Status
- Unit tests: PASS (`591 passed, 1 skipped`).
- Coverage gate: PASS (`88.77%`).
- Diff coverage gate: PASS (`86%`).
- Multi-instance safety primitives are implemented and validated in test harness.

## Remaining Follow-ups
- Optional: remove local cursor file fallback after production burn-in.
- Optional: replace DB shared token/cursor with Redis plugin for high-scale traffic.
- Optional: suppress/clean runtime warnings in mocked lease tests by refining test doubles.
