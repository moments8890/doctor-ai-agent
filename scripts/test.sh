#!/usr/bin/env bash
set -euo pipefail

# Unified test runner with reports.
#
# Usage:
#   bash scripts/test.sh unit
#   bash scripts/test.sh integration
#   bash scripts/test.sh integration-full
#   bash scripts/test.sh chatlog-half
#   bash scripts/test.sh chatlog-full
#   bash scripts/test.sh benchmark-gate
#   bash scripts/test.sh all

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
  echo "[test] Unit test suite under tests/ has been removed; skipping."
}

run_integration() {
  echo "[test] Running integration text pipeline tests..."
  "$PYTHON" -m pytest e2e/integration/test_text_pipeline.py -v -m integration \
    --junitxml=reports/junit/integration.xml
}

run_integration_full() {
  echo "[test] Running full integration test suite..."
  "$PYTHON" -m pytest e2e/integration/ -v -m integration \
    --junitxml=reports/junit/integration.xml
}

run_chatlog_half() {
  echo "[test] Running chatlog E2E replay with half dataset..."
  "$PYTHON" scripts/run_chatlog_e2e.py --dataset-mode half --response-keywords-only
}

run_chatlog_full() {
  echo "[test] Running chatlog E2E replay with full dataset..."
  "$PYTHON" scripts/run_chatlog_e2e.py --dataset-mode full --response-keywords-only
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
  chatlog-half)
    run_chatlog_half
    ;;
  chatlog-full)
    run_chatlog_full
    ;;
  benchmark-gate)
    echo "[test] Delegating to benchmark_gate.sh..."
    bash "$ROOT_DIR/scripts/benchmark_gate.sh"
    ;;
  all)
    run_unit
    run_integration
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: bash scripts/test.sh [unit|integration|integration-full|chatlog-half|chatlog-full|benchmark-gate|all]"
    exit 2
    ;;
esac

echo "[test] Done. Reports are in ./reports/"
