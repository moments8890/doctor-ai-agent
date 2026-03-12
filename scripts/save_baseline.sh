#!/usr/bin/env bash
set -euo pipefail
#
# Save the current candidate hero-loop summary as a named baseline.
#
# Usage:
#   bash scripts/save_baseline.sh                     # uses git SHA as name
#   bash scripts/save_baseline.sh my-release-name     # custom name
#
# Reads from: reports/candidate/hero.json
# Writes to:  reports/baseline/<name>-hero.json

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE="$ROOT_DIR/reports/candidate/hero.json"
BASELINE_DIR="$ROOT_DIR/reports/baseline"

if [[ ! -f "$CANDIDATE" ]]; then
  echo "ERROR: No candidate summary found at $CANDIDATE"
  echo "Run the hero-loop first:  bash scripts/test.sh hero-loop"
  exit 1
fi

NAME="${1:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
mkdir -p "$BASELINE_DIR"
cp "$CANDIDATE" "$BASELINE_DIR/${NAME}-hero.json"
echo "Baseline saved: $BASELINE_DIR/${NAME}-hero.json"
