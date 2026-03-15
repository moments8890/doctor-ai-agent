#!/usr/bin/env bash
set -euo pipefail

# Unified test runner with reports.
#
# Usage:
#   bash scripts/test.sh integration
#   bash scripts/test.sh integration-full
#   bash scripts/test.sh chatlog-half
#   bash scripts/test.sh chatlog-full
#   bash scripts/test.sh hero-loop
#   bash scripts/test.sh benchmark-gate
#   bash scripts/test.sh all

MODE="${1:-integration}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

mkdir -p reports/junit reports/coverage reports/coverage/html reports/logs reports/candidate

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

run_chatlog_half() {
  echo "[test] Running chatlog E2E replay with half dataset..."
  "$PYTHON" scripts/run_chatlog_e2e.py --dataset-mode half --response-keywords-only \
    --summary-json reports/candidate/hero.json
}

run_chatlog_full() {
  echo "[test] Running chatlog E2E replay with full dataset..."
  "$PYTHON" scripts/run_chatlog_e2e.py --dataset-mode full --response-keywords-only \
    --summary-json reports/candidate/hero.json
}

run_hero_loop() {
  echo "[test] Running hero-loop (benchmark_gate)..."
  bash "$ROOT_DIR/scripts/benchmark_gate.sh"
}

case "$MODE" in
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
  hero-loop)
    run_hero_loop
    ;;
  benchmark-gate)
    echo "[test] Delegating to benchmark_gate.sh..."
    bash "$ROOT_DIR/scripts/benchmark_gate.sh"
    ;;
  all)
    run_integration
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: bash scripts/test.sh [integration|integration-full|chatlog-half|chatlog-full|hero-loop|benchmark-gate|all]"
    exit 2
    ;;
esac

echo "[test] Done. Reports are in ./reports/"
