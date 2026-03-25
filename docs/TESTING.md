# Testing and Evaluation Guide

Current MVP policy: skip unit tests during normal development. Prefer
integration tests and E2E replay for behavior validation.

## Test Directories

| Directory | What it tests | Needs server? |
|-----------|--------------|---------------|
| `tests/core/` | Unit tests (mocked I/O, no server) | No |
| `tests/integration/` | API pipelines, prompts, DB side effects | Yes (port 8001) |
| `tests/regression/` | Scenario-based regression tests | Yes (port 8001) |
| `tests/scenarios/` | Individual patient scenario fixtures | Data only |
| `tests/prompts/` | Prompt evaluation tests (promptfoo) | Varies |
| `tests/wechat/` | WeChat channel-specific tests | Yes |
| `tests/fixtures/` | Shared test fixtures | Data only |

## Test Modes (`scripts/test.sh`)

```bash
bash scripts/test.sh <mode>
```

| Mode | What it runs | When to use |
|------|-------------|-------------|
| `unit` | `tests/core/` (mocked, no server) | Explicit test work only |
| `integration` | `tests/integration/test_text_pipeline.py` | Default gate for code changes |
| `integration-full` | All of `tests/integration/` | Prompt, routing, or pipeline changes |
| `chatlog-half` | Chatlog E2E replay (half dataset) | Routing or wording changes |
| `chatlog-full` | Chatlog E2E replay (full dataset) | Major workflow changes |
| `hero-loop` | Benchmark gate (via `scripts/benchmark_gate.sh`) | Pre-release validation |
| `benchmark-gate` | Same as hero-loop | Alias |
| `all` | Integration tests | Quick full check |

## Patient Simulation

Simulates realistic patient interviews against the running server.

```bash
# Start test server first
./cli.py start --port 8001 --no-frontend &

# Run simulation
python scripts/run_patient_sim.py --server http://127.0.0.1:8001
```

Reports written to `reports/patient_sim/` and `reports/doctor_sim/`.

## Standard Validation Path

For normal code changes:

```bash
bash scripts/test.sh integration
bash scripts/test.sh chatlog-half
```

Escalate to `integration-full` or `chatlog-full` when changes affect
LLM routing, structuring, or multi-turn workflow behavior.

## Change-Type Matrix

| Change type | Run |
|------------|-----|
| Prompt-only | integration + chatlog if wording/routing may shift |
| Routing / context-assembly | `integration-full` + chatlog |
| Structuring | integration tests hitting record creation paths |
| Session / state | core + integration if state crosses request boundaries |
| Schema | targeted integration for affected write/read paths |

## Rules

- All tests MUST run against port **8001**, never 8000 (dev server with real data)
- Unit tests must not make real LLM, DB, or network calls — use `AsyncMock` / `patch`
- Do not add new unit tests for normal product work during MVP phase
- Default LLM provider for tests: `groq`

## Runtime Notes

- Config: `config/runtime.json` (gitignored; see `config/runtime.json.sample`)
- Test server: `PYTHONPATH=src ENVIRONMENT=development uvicorn main:app --port 8001`
- Patient sim: always use `--server http://127.0.0.1:8001`

## Reports

| Path | Content |
|------|---------|
| `reports/junit/unit.xml` | Unit test JUnit output |
| `reports/junit/integration.xml` | Integration test JUnit output |
| `reports/candidate/hero.json` | Chatlog replay summary |
| `reports/patient_sim/` | Patient simulation results |
| `reports/doctor_sim/` | Doctor simulation results |
