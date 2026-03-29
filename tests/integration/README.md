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
.venv/bin/python -m pytest tests/integration/test_plan_and_act_e2e.py -v -m integration
```

Full integration suite:
```bash
bash scripts/test.sh integration-full
```

Direct pytest:
```bash
.venv/bin/python -m pytest tests/integration/ -v -m integration
```

Notes:

- `bash scripts/test.sh integration` is stale in the current repo. It still
  references removed file `tests/integration/test_text_pipeline.py`.
- Some integration/benchmark flows also depend on local fixtures under
  `e2e/fixtures/data/`, which are not guaranteed to exist in a fresh clone.
