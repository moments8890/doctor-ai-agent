# E2E Module

Purpose:
- End-to-end tests that validate behavior from human-language input to DB/output effects.

Layout:
- `integration/`: integration suites that call running API services.
- `fixtures/data/`: E2E datasets (chatlogs/scenario JSON files).
- `core/`: app-level E2E smoke/parity tests (non-WeChat specific).
- `wechat/`: WeChat/WeCom entrypoint E2E-style tests (mock + optional live checks).

Execution:
- Quick replay: `./dev.sh e2e half`
- Full replay: `./dev.sh e2e full`
- Integration suite: `./dev.sh test integration` or `./dev.sh test integration-full`

## Dependency setup (recommended)

1. Bootstrap runtime dependencies:
```bash
./dev.sh bootstrap --with-frontend
```

2. Start local services:
```bash
./dev.sh start
```

3. Verify E2E entrypoints:
```bash
./dev.sh e2e half
./dev.sh test integration
```

## Environment variables used by E2E

- `INTEGRATION_SERVER_URL` (default `http://127.0.0.1:8000`)
- `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`)
- `PATIENTS_DB_PATH` (must match server DB when assertions query DB directly)
- `CHAT_TIMEOUT`, `CHAT_RETRIES` (for long-running model calls)
