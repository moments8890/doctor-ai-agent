#!/usr/bin/env bash
set -euo pipefail
#
# Benchmark Gate — automated regression check for push workflow.
#
# Generates a fresh candidate hero.json via chatlog replay, then compares it
# against the saved baseline.  Exits non-zero on regression.
#
# Usage:
#   bash scripts/benchmark_gate.sh                # generate + compare
#   bash scripts/benchmark_gate.sh --skip-generate # assume candidate exists, compare only
#   bash scripts/benchmark_gate.sh --help
#
# Prerequisites:
#   - A running server (for chatlog replay to generate the candidate)
#   - reports/baseline/ should contain at least one *-hero.json baseline
#
# Exit codes:
#   0 — all checks passed, no regression
#   1 — regression detected or missing inputs
#   2 — usage error

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SKIP_GENERATE=0

# ── Argument parsing ────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --skip-generate|--skip-unit)
      SKIP_GENERATE=1
      ;;
    --help|-h)
      echo "Usage: bash scripts/benchmark_gate.sh [--skip-generate] [--help]"
      echo ""
      echo "Runs the benchmark regression gate:"
      echo "  1. Generate reports/candidate/hero.json via chatlog replay"
      echo "  2. Compare candidate against latest baseline"
      echo "  3. Print summary table with pass/fail/regression status"
      echo "  4. Exit non-zero on regression"
      echo ""
      echo "Options:"
      echo "  --skip-generate   Skip generating the candidate (assume it exists)"
      echo "  --help, -h        Show this help message"
      echo ""
      echo "Examples:"
      echo "  bash scripts/benchmark_gate.sh                # full gate"
      echo "  bash scripts/benchmark_gate.sh --skip-generate # comparison only"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: bash scripts/benchmark_gate.sh [--skip-generate] [--help]"
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

CANDIDATE="$ROOT_DIR/reports/candidate/hero.json"

# ── Step 1: Generate candidate ────────────────────────────────────
if [[ "$SKIP_GENERATE" -eq 0 ]]; then
  echo ""
  echo -e "${BOLD}[benchmark-gate] Step 1/2: Generating candidate hero.json via chatlog replay...${RESET}"
  echo ""
  mkdir -p "$ROOT_DIR/reports/candidate"
  "$PYTHON" scripts/run_chatlog_e2e.py \
    --dataset-mode full \
    --response-keywords-only \
    --summary-json "$CANDIDATE"
  echo ""
  echo -e "${GREEN}[benchmark-gate] Candidate generated.${RESET}"
else
  echo ""
  echo -e "${YELLOW}[benchmark-gate] Skipping candidate generation (--skip-generate).${RESET}"
fi

# ── Step 2: Baseline comparison ─────────────────────────────────────
echo ""
echo -e "${BOLD}[benchmark-gate] Step 2/2: Comparing candidate vs baseline...${RESET}"
echo ""

if [[ ! -f "$CANDIDATE" ]]; then
  echo -e "${RED}[benchmark-gate] ERROR: No candidate summary found at:${RESET}"
  echo "  $CANDIDATE"
  echo ""
  echo "Run with --skip-generate removed, or generate manually:"
  echo "  $PYTHON scripts/run_chatlog_e2e.py --dataset-mode full --response-keywords-only --summary-json $CANDIDATE"
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
