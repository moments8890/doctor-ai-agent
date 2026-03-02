# E2E Test Expansion Plan

## Objective

Increase confidence in critical end-to-end behaviors with deterministic integration tests that are stable in CI and meaningful for regression prevention.

## Scope

Add integration coverage for:

1. Task API lifecycle (`list`, `filter`, `complete`)
2. Manage patients grouped view correctness
3. Manage records raw-field payload correctness

## Test Design Principles

- Prefer deterministic DB-seeded setup over LLM-dependent setup for non-LLM flows.
- Use unique `doctor_id` per test (`inttest_*`) to isolate data.
- Assert response structure and key field semantics, not just status codes.
- Keep tests small and independent.

## Planned Cases

### Case 1: Task API roundtrip

- Seed two pending `doctor_tasks` rows for one doctor.
- Call `GET /api/tasks?doctor_id=...` and assert both are returned.
- Complete one task via `PATCH /api/tasks/{id}`.
- Call `GET /api/tasks?doctor_id=...&status=pending` and assert only remaining pending task is returned.

### Case 2: Manage patients grouped categories

- Seed patients for one doctor across:
  - `high_risk`
  - `new`
  - `NULL` category (should map to `uncategorized`)
- Call `GET /api/manage/patients/grouped`.
- Assert group counts and expected fixed bucket behavior.

### Case 3: Manage records raw field payload

- Seed one patient and one medical record with all core fields.
- Call `GET /api/manage/records?doctor_id=...`.
- Assert raw fields exist and values match DB seed:
  - `history_of_present_illness`
  - `past_medical_history`
  - `physical_examination`
  - `auxiliary_examinations`
  - `follow_up_plan`

## Implementation Tasks

1. Add new integration test module:
- `tests/integration/test_manage_tasks_pipeline.py`

2. Add small local DB helper utilities in that test file:
- direct `sqlite3` inserts for deterministic fixtures
- per-test explicit cleanup by `doctor_id` for `doctor_tasks/patients/medical_records`

3. Improve integration cleanup fixture:
- extend `tests/integration/conftest.py` cleanup to include `doctor_tasks` rows for `inttest_%`

## Validation

- Run:
  - `bash tools/test.sh integration`
  - optionally `bash tools/test.sh integration-full`
- Ensure new tests are marked `@pytest.mark.integration` and skipped cleanly when server/Ollama unavailable.

## Exit Criteria

- New integration module merged and green in CI.
- No flakiness observed in at least two consecutive CI runs.
- Tests remain deterministic without depending on LLM output for these API contracts.
