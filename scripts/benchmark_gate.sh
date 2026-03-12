#!/usr/bin/env bash
set -euo pipefail
#
# Benchmark Gate — automated regression check for push workflow.
#
# Runs unit tests (fast sanity), then compares the most recent candidate
# hero-loop summary against the saved baseline.  Exits non-zero on regression.
#
# Usage:
#   bash scripts/benchmark_gate.sh            # unit tests + baseline comparison
#   bash scripts/benchmark_gate.sh --skip-unit # skip unit tests, comparison only
#   bash scripts/benchmark_gate.sh --help
#
# Prerequisites:
#   - reports/candidate/hero.json must exist (run hero-loop benchmark first)
#   - reports/baseline/ should contain at least one *-hero.json baseline
#
# Exit codes:
#   0 — all checks passed, no regression
#   1 — regression detected or missing inputs
#   2 — usage error

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SKIP_UNIT=0

# ── Argument parsing ────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --skip-unit)
      SKIP_UNIT=1
      ;;
    --help|-h)
      echo "Usage: bash scripts/benchmark_gate.sh [--skip-unit] [--help]"
      echo ""
      echo "Runs the benchmark regression gate:"
      echo "  1. Unit tests (quick sanity check, skippable with --skip-unit)"
      echo "  2. Compare reports/candidate/hero.json against latest baseline"
      echo "  3. Print summary table with pass/fail/regression status"
      echo "  4. Exit non-zero on regression"
      echo ""
      echo "Options:"
      echo "  --skip-unit   Skip running unit tests (useful if already run)"
      echo "  --help, -h    Show this help message"
      echo ""
      echo "Prerequisites:"
      echo "  - reports/candidate/hero.json must exist"
      echo "  - reports/baseline/ should contain at least one *-hero.json"
      echo ""
      echo "Examples:"
      echo "  bash scripts/benchmark_gate.sh              # full gate"
      echo "  bash scripts/benchmark_gate.sh --skip-unit  # comparison only"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: bash scripts/benchmark_gate.sh [--skip-unit] [--help]"
      exit 2
      ;;
  esac
done

# ── Determine Python ────────────────────────────────────────────────
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

# ── Colors ──────────────────────────────────────────────────────────
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
BOLD="\033[1m"
RESET="\033[0m"

# ── Step 1: Unit tests ─────────────────────────────────────────────
if [[ "$SKIP_UNIT" -eq 0 ]]; then
  echo ""
  echo -e "${BOLD}[benchmark-gate] Step 1/2: Running unit tests...${RESET}"
  echo ""
  if ! bash "$ROOT_DIR/scripts/test.sh" unit; then
    echo ""
    echo -e "${RED}[benchmark-gate] FAILED — unit tests did not pass.${RESET}"
    exit 1
  fi
  echo ""
  echo -e "${GREEN}[benchmark-gate] Unit tests passed.${RESET}"
else
  echo ""
  echo -e "${YELLOW}[benchmark-gate] Skipping unit tests (--skip-unit).${RESET}"
fi

# ── Step 2: Baseline comparison ─────────────────────────────────────
echo ""
echo -e "${BOLD}[benchmark-gate] Step 2/2: Comparing candidate vs baseline...${RESET}"
echo ""

CANDIDATE="$ROOT_DIR/reports/candidate/hero.json"
if [[ ! -f "$CANDIDATE" ]]; then
  echo -e "${RED}[benchmark-gate] ERROR: No candidate summary found at:${RESET}"
  echo "  $CANDIDATE"
  echo ""
  echo "Run the hero-loop benchmark first to generate this file."
  echo "  e.g.: bash scripts/test.sh chatlog-full"
  exit 1
fi

COMPARE_SCRIPT="$ROOT_DIR/scripts/compare_baseline.py"
if [[ ! -f "$COMPARE_SCRIPT" ]]; then
  echo -e "${RED}[benchmark-gate] ERROR: compare_baseline.py not found.${RESET}"
  exit 1
fi

# Run comparison with --fail-on-regression so non-zero exit means regression.
if "$PYTHON" "$COMPARE_SCRIPT" "$CANDIDATE" --fail-on-regression; then
  echo ""
  echo -e "${GREEN}${BOLD}[benchmark-gate] PASSED — no regression detected.${RESET}"
  exit 0
else
  RC=$?
  echo ""
  echo -e "${RED}${BOLD}[benchmark-gate] FAILED — regression detected (exit code $RC).${RESET}"
  echo ""
  echo "To investigate:"
  echo "  $PYTHON $COMPARE_SCRIPT $CANDIDATE"
  echo ""
  echo "To update the baseline after verifying the change is intentional:"
  echo "  bash scripts/save_baseline.sh"
  exit 1
fi
