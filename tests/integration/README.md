# Integration E2E Tests

These tests hit running HTTP endpoints and assert DB side effects.

## Dependencies

1. App server running:
```bash
./cli.py start
```

2. Ollama running and reachable via `OLLAMA_BASE_URL`.

3. DB path alignment:
- Test process and server must point to same `PATIENTS_DB_PATH`.

## Run

Fast integration subset:
```bash
bash scripts/test.sh integration
```

Full integration suite:
```bash
bash scripts/test.sh integration-full
```

Direct pytest:
```bash
.venv/bin/python -m pytest tests/integration/ -v -m integration
```
