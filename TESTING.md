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
bash tools/test.sh unit
```

Outputs:
- `reports/junit/unit.xml`
- `reports/coverage/coverage.xml`
- `reports/coverage/html/index.html`

### Integration tests (requires running app dependencies)

```bash
bash tools/test.sh integration
```

Output:
- `reports/junit/integration.xml`

### Train-data template integration tests (manual)

```bash
bash tools/test_train_data_integration.sh
```

Options:
- `--suite all|deepseek|gemini`
- `--server http://127.0.0.1:18000`
- `--followup true|false`

Output:
- `reports/junit/integration-train-data.xml`

Note:
- `integration` runs text pipeline integration tests only (fast and stable default).
- For the full integration suite (including image pipeline):

```bash
bash tools/test.sh integration-full
```

### Full suite

```bash
bash tools/test.sh all
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
