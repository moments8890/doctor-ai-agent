# Testing Guide

## Prerequisites

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Run Tests

### Unit tests + coverage + JUnit report

```bash
bash scripts/test.sh unit
```

Outputs:
- `reports/junit/unit.xml`
- `reports/coverage/coverage.xml`
- `reports/coverage/html/index.html`

### Integration tests (requires running app dependencies)

```bash
bash scripts/test.sh integration
```

Output:
- `reports/junit/integration.xml`

### Human-language chatlog E2E replay

```bash
bash scripts/test.sh chatlog-half
bash scripts/test.sh chatlog-full
```

This replays `e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v1.json`
against `/api/records/chat` and verifies API + DB behavior.

Run the v2 complex corpus (100 cases):

```bash
.venv/bin/python scripts/run_chatlog_e2e.py e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v2.json --max-cases 100 --response-keywords-only
```

Latency benchmark notes:
- See `docs/root/LATENCY_BENCHMARK_2026-03-05.md` for A/B methodology, per-chat latency metrics, and recommended runtime defaults.

Note:
- `integration` runs text pipeline integration tests only (fast and stable default).
- For the full integration suite (including image pipeline):

```bash
bash scripts/test.sh integration-full
```

### Full suite

```bash
bash scripts/test.sh all
```

## CI Artifacts

GitHub Actions uploads:
- `unit-test-reports` (JUnit + coverage XML + coverage HTML)
- `integration-test-reports` (integration JUnit)
- `app-log` on integration failure

## Common Issue

If you see `unrecognized arguments: --cov...`, your virtualenv is missing `pytest-cov`.

```bash
.venv/bin/python -m pip install -r requirements.txt
# or:
.venv/bin/python -m pip install pytest-cov
```
