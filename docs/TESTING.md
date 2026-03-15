# Testing and Evaluation Guide

This repo uses several test layers, but the current MVP iteration has a
temporary policy change:

- do not add or update unit tests during normal development
- do not run unit tests as a default local gate
- prefer integration tests and chatlog / E2E replay for behavior validation

The unit-test suite remains in the repo for reference and for explicit
test-focused work, but it is not the default development gate right now.

## Test Layers

### 1. Unit tests

Current policy: frozen during normal feature development.

Use only when:

- the user explicitly asks for tests
- the task is a test-only or test-fix task
- you are debugging existing test infrastructure

Commands:

```bash
./dev.sh test unit
# or
.venv/bin/python -m pytest tests/ -v
```

Rules:

- Unit tests in `tests/` must not make real LLM, DB, or network calls.
- Use `AsyncMock` and `patch` for I/O.
- Do not add new unit tests for normal product work during this temporary phase.
- The old coverage gate is currently not the default development gate.

### 2. Core E2E tests

Use for app-level behavior that does not require a running server or live model backend.

Command:

```bash
.venv/bin/python -m pytest tests/core/ -v
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
.venv/bin/python -m pytest tests/integration/ -v -m integration
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

## Standard Development Validation

The default validation path for code changes is now:

```bash
./dev.sh test integration
./dev.sh e2e half
```

Escalate to `./dev.sh test integration-full` or `./dev.sh e2e full` when the
change materially affects LLM routing, structuring, or multi-turn workflow
behavior.

Run unit tests only if the task explicitly calls for them.

## Change-Type Matrix

### Prompt-only change

Run:

- integration tests for the affected route
- chatlog replay if wording or routing behavior may shift

### Routing or context-assembly change

Run:

- `./dev.sh test integration-full`
- chatlog replay for meaningful routing changes

### Structuring change

Run:

- integration tests hitting record creation paths

### Session/state change

Run:

- core E2E and integration tests if state crosses request boundaries

### Schema change

Run:

- targeted integration tests for affected write/read paths

## Runtime Notes

- Main application runtime config lives in `config/runtime.json`.
- Prefer the LAN inference server configured there over starting a local Ollama server for the main app.
- If you need a dedicated integration server, repo policy is to use port `8001` and point
  `INTEGRATION_SERVER_URL` at it.
- Some older docs mention `ollama serve`; treat those as historical unless the specific test explicitly requires a local provider.

## Reports and Artifacts

Legacy unit-test reports, when run explicitly, write to:

- `reports/junit/unit.xml`
- `reports/coverage/coverage.xml`
- `reports/coverage/html/`

Integration tests write JUnit output to:

- `reports/junit/integration.xml`

## Related Docs

- [`tests/README.md`](doctor-ai-agent/tests/README.md)
- [`tests/README.md`](doctor-ai-agent/tests/README.md)
- [`tests/integration/README.md`](doctor-ai-agent/tests/integration/README.md)
- [`AGENTS.md`](doctor-ai-agent/AGENTS.md)
