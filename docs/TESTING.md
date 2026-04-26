# Testing and Evaluation Guide

## Testing Policy

**Default mode**: agents do NOT run tests automatically. The `AGENTS.md` "DO NOT RUN TESTS"
rule stays in effect for normal development sessions.

**Opt-in TDD**: invoke `/tdd` to activate test-driven development for a session.
This overrides the default and enables red-green-refactor cycles.

**Pre-push gate**: `/test-gate` is the policy name, not a checked-in repo command.
In this repo, run the commands in **Standard Validation Path** directly.

## Test Classification

Tests are classified by **determinism**, not folder name.

| Classification | What to test | How to test | Example |
|---------------|-------------|------------|---------|
| **Deterministic** | Pure domain logic, CRUD, parsers, validators, formatters | **Unit tests** (TDD via `/tdd`) | `structuring.py`, `triage.py`, `pdf_helpers.py`, `knowledge_crud.py` |
| **Seam/Contract** | Orchestration around LLM calls — assert side effects, not LLM output | **Mock LLM**, assert DB writes, tool calls, routing | `handle_turn.py`, `session.py` |
| **Scenario** | Multi-turn workflows, intent routing, field extraction | **YAML fixtures** with tolerant matchers | `tests/scenarios/fixtures/*.yaml` |
| **Eval/Regression** | Prompt quality, extraction accuracy, agent behavior | **promptfoo** + **patient/doctor simulation** | `tests/prompts/`, `/sim` |
| **Frontend** | Zustand stores, form logic, critical flows | **Vitest** + `@testing-library/react` | `doctorStore.test.js` |
| **Visual/UX** | Layout, styling, responsive, clinical warnings | **Browser QA** via `/qa` | Screenshots + walkthrough |

## Test Directories

| Directory | Classification | Needs server? |
|-----------|---------------|---------------|
| `tests/core/` | Deterministic + Seam | No |
| `tests/integration/` | Scenario + Seam | Yes (port 8001) |
| `tests/regression/` | Eval/Regression | Yes (port 8001) |
| `tests/scenarios/` | Scenario (YAML fixtures) | Data only |
| `tests/prompts/` | Eval (promptfoo) | Groq API |
| `tests/wechat/` | Integration | Yes |
| `tests/fixtures/` | Shared test data | Data only |
| `frontend/web/src/**/*.test.js` | Frontend (Vitest) | No |

## Test Modes (`scripts/test.sh`)

```bash
bash scripts/test.sh <mode>
```

| Mode | What it runs | When to use |
|------|-------------|-------------|
| `unit` | `tests/core/` (mocked, no server) | After modifying domain logic or CRUD |
| `integration` | Legacy wrapper for removed `tests/integration/test_text_pipeline.py` | Stale, do not use in fresh clones |
| `integration-full` | All of `tests/integration/` | Current backend integration gate |
| `chatlog-half` | Chatlog E2E replay (half dataset) | Requires local dataset fixture under `e2e/fixtures/data/` |
| `chatlog-full` | Chatlog E2E replay (full dataset) | Requires local dataset fixture under `e2e/fixtures/data/` |
| `hero-loop` | Benchmark gate | Requires local dataset fixture + saved baseline |
| `all` | Integration tests | Quick full check |

### Frontend Tests

```bash
cd frontend/web && npm test          # run once
cd frontend/web && npm run test:watch # watch mode
```

## Patient Simulation

Simulates realistic patient intakes against the running server.

```bash
# Start test server first
./cli.py start --port 8001 --no-frontend &

# Run simulation (or use /sim skill)
python scripts/run_patient_sim.py --server http://127.0.0.1:8001
```

Reports written to `reports/patient_sim/` and `reports/doctor_sim/`.

## Standard Validation Path

For normal code changes (no TDD):

```bash
cd frontend/web && npm run build
bash scripts/test.sh integration-full
```

For TDD sessions (after `/tdd`):

```bash
# Unit tests run during TDD cycle automatically
# Then validate integration before push:
bash scripts/test.sh integration-full
```

If local benchmark fixtures are installed under `e2e/fixtures/data/`, add:

```bash
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh hero-loop
```

Escalate to `chatlog-full` only when the dataset fixture is present and the
change affects LLM routing, structuring, or multi-turn workflow behavior.

## Current Repo Caveats

- `bash scripts/test.sh integration` is stale. It still points to removed file
  `tests/integration/test_text_pipeline.py`.
- `bash scripts/test.sh chatlog-half`, `chatlog-full`, and `hero-loop` need
  local benchmark fixtures under `e2e/fixtures/data/` plus any saved baseline
  expected by `scripts/benchmark_gate.sh`.
- For a clean clone without benchmark assets, the reliable checked-in gate is:
  frontend build + `bash scripts/test.sh integration-full`.

## Change-Type Matrix

| Change type | Run |
|------------|-----|
| Domain logic (structuring, triage, PDF, knowledge) | `/tdd` + unit tests |
| Prompt-only | `integration-full`, add benchmark/chatlog only if dataset is installed |
| Routing / context-assembly | `integration-full`, add benchmark/chatlog only if dataset is installed |
| Structuring | integration tests hitting record creation paths |
| Session / state | core + integration if state crosses request boundaries |
| Schema | targeted integration for affected write/read paths |
| Frontend components | `npm run build` and Vitest (`npm test` in `frontend/web/`) |
| Pre-push (any change) | `/test-gate` |

## Medical Safety Testing

For code touching clinical data, these assertion patterns apply:

**Clinical Invariants** — must always hold:
- Allergies never dropped during record updates
- Negations preserved ("no history of diabetes" stays negative)
- Patient identity never crosses records
- Red flags always surface in diagnosis output

**Must-Not Assertions** — safety guardrails:
- No fabricated vitals or lab values
- No invented diagnosis certainty
- No medication dose mutation without evidence
- No unsafe reassurance for signal-flag symptoms

**Metamorphic Tests** — same input, different form:
- Reordered facts produce same clinical classification
- OCR artifacts / abbreviations don't change extraction results
- Bilingual input (mixed Chinese/English) extracts correctly

## Custom Skills

| Skill | Purpose | When to use |
|-------|---------|-------------|
| `/tdd` | Activate TDD mode for session | Before implementing deterministic code |
| `/test-gate` | Policy alias for the direct commands above | Before `git push` |
| `/sim` | Patient/doctor simulation | After agent behavior changes |
| `/prompt-surgeon` | Prompt edit with eval | After modifying prompt files |

## Rules

- All tests MUST run against port **8001**, never 8000 (dev server with real data)
- Unit tests must not make real LLM, DB, or network calls — use `AsyncMock` / `patch`
- Default LLM provider for tests: `groq`
- Safety-critical modules (diagnosis pipeline, CDS) require integration test coverage
- TDD is opt-in via `/tdd` — default agents skip tests unless explicitly invoked

## Runtime Notes

- Config: `config/runtime.json` (gitignored; see `config/runtime.json.sample`)
- Test server: `ENVIRONMENT=test PATIENTS_DB_PATH="$PWD/.pytest-data/patients.test.db" PYTHONPATH=src uvicorn main:app --port 8001`
  - `ENVIRONMENT=test` activates the engine tripwire that refuses to bind to the dev `patients.db`
  - `PATIENTS_DB_PATH` must match what pytest uses (`tests/conftest.py` defaults to `.pytest-data/patients.test.db`); override both with `PYTEST_DATABASE_URL` for CI
- Patient sim: always use `--server http://127.0.0.1:8001`

## Reports

| Path | Content |
|------|---------|
| `reports/junit/unit.xml` | Unit test JUnit output |
| `reports/junit/integration.xml` | Integration test JUnit output |
| `reports/candidate/hero.json` | Chatlog replay summary |
| `reports/patient_sim/` | Patient simulation results |
| `reports/doctor_sim/` | Doctor simulation results |
