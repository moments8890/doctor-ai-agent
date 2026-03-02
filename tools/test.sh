#!/usr/bin/env bash
set -euo pipefail

# Unified test runner with reports.
#
# Usage:
#   bash tools/test.sh unit
#   bash tools/test.sh integration
#   bash tools/test.sh integration-full
#   bash tools/test.sh all

MODE="${1:-unit}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

mkdir -p reports/junit reports/coverage reports/coverage/html reports/logs

run_unit() {
  echo "[test] Running unit tests with coverage..."
  if "$PYTHON" -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('pytest_cov') else 1)"; then
    "$PYTHON" -m pytest tests/ -v \
      --ignore=tests/integration \
      --junitxml=reports/junit/unit.xml \
      --cov=db --cov=models --cov=routers --cov=services --cov=utils \
      --cov-report=term-missing:skip-covered \
      --cov-report=xml:reports/coverage/coverage.xml \
      --cov-report=html:reports/coverage/html
  else
    echo "[test][warn] pytest-cov is not installed; running unit tests without coverage."
    echo "[test][hint] Install with: $PYTHON -m pip install pytest-cov"
    "$PYTHON" -m pytest tests/ -v \
      --ignore=tests/integration \
      --junitxml=reports/junit/unit.xml
  fi
}

run_integration() {
  echo "[test] Running integration text pipeline tests..."
  "$PYTHON" -m pytest tests/integration/test_text_pipeline.py -v -m integration \
    --junitxml=reports/junit/integration.xml
}

run_integration_full() {
  echo "[test] Running full integration test suite..."
  "$PYTHON" -m pytest tests/integration/ -v -m integration \
    --junitxml=reports/junit/integration.xml
}

case "$MODE" in
  unit)
    run_unit
    ;;
  integration)
    run_integration
    ;;
  integration-full)
    run_integration_full
    ;;
  all)
    run_unit
    run_integration
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: bash tools/test.sh [unit|integration|integration-full|all]"
    exit 2
    ;;
esac

echo "[test] Done. Reports are in ./reports/"
