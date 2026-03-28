# /test-gate — Pre-Push Test Validation

Run the full test suite as a push gate. Use before `git push` to catch regressions.
This skill is independent of TDD mode — any agent can use it.

## Usage

- `/test-gate` — run core unit tests (fast, no server needed)
- `/test-gate full` — run core + integration (needs server on 8001)
- `/test-gate --scope domain` — run only tests matching domain modules

## Step 1: Determine Scope

| Input | What runs | Needs server? | Time |
|-------|----------|---------------|------|
| `/test-gate` | `tests/core/` + root-level `tests/test_*.py` | No | ~10s |
| `/test-gate full` | Above + `tests/integration/` + `tests/regression/` | Yes (8001) | ~2min |
| `/test-gate prompts` | `tests/prompts/run.sh` (promptfoo) | Groq API | ~3min |
| `/test-gate --scope X` | `pytest -k X` against `tests/core/` | No | ~10s |

## Step 2: Pre-flight Checks

```bash
# Check for uncommitted changes
git status --porcelain | head -5
```

If dirty working tree, warn:
"You have uncommitted changes. Tests will run against the working tree, not the last commit."

For `full` mode, check server:
```bash
curl -sf http://127.0.0.1:8001/health > /dev/null 2>&1 && echo "SERVER_UP" || echo "SERVER_DOWN"
```

If `SERVER_DOWN` and full mode requested:
"Test server not running on port 8001. Either:
- Start it: `./cli.py start --port 8001 --no-frontend`
- Or run `/test-gate` (core only, no server needed)"

## Step 3: Run Tests

### Core tests (always)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src ROUTING_LLM=deepseek .venv/bin/python -m pytest \
  tests/core/ tests/test_*.py \
  -x -v --tb=short \
  --ignore=tests/core/test_multi_gateway_e2e.py \
  --ignore=tests/core/test_p3_d2_parity_e2e.py \
  2>&1
```

Use `timeout: 60000` (1 minute).

### Integration tests (full mode only)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/integration/ -v -m integration --tb=short \
  2>&1
```

Use `timeout: 180000` (3 minutes).

### Regression tests (full mode only)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
RUN_REGRESSION=1 PYTHONPATH=src .venv/bin/python -m pytest \
  tests/regression/ -v --tb=short \
  2>&1
```

Use `timeout: 180000` (3 minutes).

### Prompt eval (prompts mode)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
bash tests/prompts/run.sh 2>&1
```

Use `timeout: 300000` (5 minutes).

## Step 4: Report Results

```
TEST GATE RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scope: [core / full / prompts]
Branch: main
Commit: [short SHA]

| Suite | Tests | Pass | Fail | Skip | Time |
|-------|-------|------|------|------|------|
| Core  |    N  |   N  |   N  |   N  | Xs   |
| Integration | N | N  |   N  |   N  | Xs   |
| Regression  | N | N  |   N  |   N  | Xs   |

VERDICT: PASS / FAIL (N failures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If FAIL, show each failure:
```
FAILURES:
  1. tests/core/test_xxx.py::test_name
     AssertionError: expected X, got Y
  2. ...
```

## Step 5: Gate Decision

- **PASS** — "All tests green. Safe to push."
- **FAIL** — "Tests failed. Fix before pushing." List each failure with file:line.
- **SKIP** (server down for full mode) — "Core tests passed. Integration/regression skipped (no server). Run `/test-gate full` with server for complete validation."

## Rules

- **Never modify test files** — this skill is read-only validation
- **Never auto-fix failures** — report them, let the user decide
- **Port 8001 only** — never hit port 8000
- **No blocking** — if a test suite hangs, timeout and report partial results
- **Works without TDD** — any agent can use this regardless of TDD mode
