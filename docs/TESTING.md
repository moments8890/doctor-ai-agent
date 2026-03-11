# Testing and Evaluation Guide

This repo uses several test layers. Pick the lightest layer that can prove the change,
then escalate when the change touches AI behavior, runtime state, or real API flows.

## Test Layers

### 1. Unit tests

Use for most changes in `db/`, `services/`, `routers/`, and `utils/`.

Commands:

```bash
./dev.sh test unit
# or
.venv/bin/python -m pytest tests/ -v
```

Rules:

- Unit tests in `tests/` must not make real LLM, DB, or network calls.
- Use `AsyncMock` and `patch` for I/O.
- Every new function or branch should have at least one direct test.
- Coverage gate is enforced through `bash scripts/test.sh unit`.

### 2. Core E2E tests

Use for app-level behavior that does not require a running server or live model backend.

Command:

```bash
.venv/bin/python -m pytest e2e/core/ -v
```

### 3. Integration tests

Use when the change affects prompt behavior, routing, structuring, API pipelines,
or DB side effects through running HTTP endpoints.

Commands:

```bash
./dev.sh test integration
./dev.sh test integration-full
```

Direct pytest:

```bash
.venv/bin/python -m pytest e2e/integration/ -v -m integration
```

Requirements:

- Running app server
- Reachable model backend
- Matching DB path when tests assert DB side effects

### 4. Chatlog replay

Use for human-language regression checks across realistic multi-turn cases.

Commands:

```bash
./dev.sh e2e half
./dev.sh e2e full

# or
./dev.sh test chatlog-half
./dev.sh test chatlog-full
```

Use this when routing, prompt wording, clarification behavior, or multi-turn continuity changes materially.

## Standard Pre-Push Flow

The default local gate for code changes is:

```bash
.venv/bin/python -m pytest tests/ -v
bash scripts/test.sh unit
git fetch --no-tags origin main
.venv/bin/diff-cover reports/coverage/coverage.xml --compare-branch=origin/main --diff-range-notation=.. --fail-under=81
```

If the change touches the LLM pipeline or prompts, also run integration tests.
If the change meaningfully affects natural-language behavior, run chatlog replay as well.

## Change-Type Matrix

### Prompt-only change

Run:

- unit tests that cover the touched prompt path
- integration tests for the affected route
- chatlog replay if wording or routing behavior may shift

### Routing or context-assembly change

Run:

- direct unit tests for the changed functions
- `./dev.sh test unit`
- `./dev.sh test integration-full`
- chatlog replay for meaningful routing changes

### Structuring change

Run:

- direct unit tests for parsing/filtering logic
- `./dev.sh test unit`
- integration tests hitting record creation paths

### Session/state change

Run:

- direct unit tests for hydration, locking, and transition logic
- `./dev.sh test unit`
- core E2E and integration tests if state crosses request boundaries

### Schema change

Run:

- direct model/CRUD tests
- `./dev.sh test unit`
- targeted integration tests for affected write/read paths

## Runtime Notes

- Main application runtime config lives in `config/runtime.json`.
- Prefer the LAN inference server configured there over starting a local Ollama server for the main app.
- If you need a dedicated integration server, repo policy is to use port `8001` and point
  `INTEGRATION_SERVER_URL` at it.
- Some older docs mention `ollama serve`; treat those as historical unless the specific test explicitly requires a local provider.

## Reports and Artifacts

`bash scripts/test.sh unit` writes reports to:

- `reports/junit/unit.xml`
- `reports/coverage/coverage.xml`
- `reports/coverage/html/`

Integration tests write JUnit output to:

- `reports/junit/integration.xml`

## Related Docs

- [`tests/README.md`](doctor-ai-agent/tests/README.md)
- [`e2e/README.md`](doctor-ai-agent/e2e/README.md)
- [`e2e/integration/README.md`](doctor-ai-agent/e2e/integration/README.md)
- [`AGENTS.md`](doctor-ai-agent/AGENTS.md)
