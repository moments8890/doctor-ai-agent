#!/usr/bin/env python3
"""
Compare a hero-loop candidate summary against the latest baseline.

Usage:
  .venv/bin/python scripts/compare_baseline.py reports/candidate/hero.json
  .venv/bin/python scripts/compare_baseline.py reports/candidate/hero.json --baseline reports/baseline/abc1234-hero.json
  .venv/bin/python scripts/compare_baseline.py reports/candidate/hero.json --fail-on-regression
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

BASELINE_DIR = Path(__file__).resolve().parent.parent / "reports" / "baseline"


def _find_latest_baseline() -> Optional[Path]:
    """Find the most recently modified baseline JSON in reports/baseline/."""
    if not BASELINE_DIR.is_dir():
        return None
    baselines = sorted(BASELINE_DIR.glob("*-hero.json"), key=lambda p: p.stat().st_mtime)
    return baselines[-1] if baselines else None


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compare(baseline: dict, candidate: dict, fail_on_regression: bool) -> int:
    """Print comparison table and return exit code (0=ok, 1=regression)."""
    b_total = baseline["total"]
    c_total = candidate["total"]

    print(f"\n{BOLD}Hero-Loop Baseline Comparison{RESET}")
    print(f"{'':2s}{'':20s} {'Baseline':>10s} {'Candidate':>10s} {'Delta':>10s}")
    print(f"{'':2s}{'-' * 52}")

    exit_code = 0

    # Overall accuracy
    b_acc = baseline["accuracy_pct"]
    c_acc = candidate["accuracy_pct"]
    delta = c_acc - b_acc
    color = GREEN if delta >= 0 else RED
    print(f"{'':2s}{'Accuracy':20s} {b_acc:>9.1f}% {c_acc:>9.1f}% {color}{delta:>+9.1f}%{RESET}")
    if delta < 0:
        exit_code = 1

    print(f"{'':2s}{'Cases':20s} {b_total:>10d} {c_total:>10d} {c_total - b_total:>+10d}")

    # Layer breakdown
    b_layers = baseline.get("layers", {})
    c_layers = candidate.get("layers", {})
    for layer in ("routing_ok", "patient_resolution_ok", "structuring_ok", "save_ok"):
        b_val = b_layers.get(layer, 0)
        c_val = c_layers.get(layer, 0)
        d = c_val - b_val
        color = GREEN if d >= 0 else RED
        label = layer.replace("_ok", "").replace("_", " ").title()
        print(f"{'':2s}{label:20s} {b_val:>10d} {c_val:>10d} {color}{d:>+10d}{RESET}")
        if d < 0:
            exit_code = 1

    # Organic accuracy (excludes rescue-succeeded cases)
    b_organic = baseline.get("accuracy_organic_pct")
    c_organic = candidate.get("accuracy_organic_pct")
    if b_organic is not None or c_organic is not None:
        b_o = b_organic if b_organic is not None else b_acc
        c_o = c_organic if c_organic is not None else c_acc
        d = c_o - b_o
        color = GREEN if d >= 0 else RED
        print(f"{'':2s}{'Accuracy (organic)':20s} {b_o:>9.1f}% {c_o:>9.1f}% {color}{d:>+9.1f}%{RESET}")
        if d < 0:
            exit_code = 1

    # Fallback
    b_fb = baseline.get("fallback_count", 0)
    c_fb = candidate.get("fallback_count", 0)
    if b_fb or c_fb:
        d = c_fb - b_fb
        color = GREEN if d <= 0 else YELLOW
        print(f"{'':2s}{'Fallback retries':20s} {b_fb:>10d} {c_fb:>10d} {color}{d:>+10d}{RESET}")

    # Fatal errors (timeouts, connection errors, unhandled exceptions)
    b_fatal = baseline.get("fatal_error_count", 0)
    c_fatal = candidate.get("fatal_error_count", 0)
    if b_fatal or c_fatal:
        d = c_fatal - b_fatal
        color = GREEN if d <= 0 else RED
        print(f"{'':2s}{'Fatal errors':20s} {b_fatal:>10d} {c_fatal:>10d} {color}{d:>+10d}{RESET}")
        if d > 0:
            exit_code = 1

    # Failure diff
    b_fails: Set[str] = set(baseline.get("failures", []))
    c_fails: Set[str] = set(candidate.get("failures", []))
    new_fails = c_fails - b_fails
    fixed = b_fails - c_fails
    still_failing = b_fails & c_fails

    if fixed:
        print(f"\n{GREEN}Fixed ({len(fixed)}):{RESET}")
        for cid in sorted(fixed):
            print(f"  + {cid}")

    if new_fails:
        print(f"\n{RED}New failures ({len(new_fails)}):{RESET}")
        c_details = candidate.get("failure_details", {})
        for cid in sorted(new_fails):
            detail = c_details.get(cid, "")
            print(f"  - {cid}: {detail[:80]}")
        exit_code = 1

    if still_failing:
        print(f"\n{YELLOW}Still failing ({len(still_failing)}):{RESET}")
        for cid in sorted(still_failing):
            print(f"  ~ {cid}")

    if not new_fails and not still_failing:
        print(f"\n{GREEN}All cases passing.{RESET}")

    # Metadata
    print(f"\n{GRAY}Baseline: {baseline.get('git_sha', '?')} ({baseline.get('timestamp', '?')})")
    print(f"Candidate: {candidate.get('git_sha', '?')} ({candidate.get('timestamp', '?')}){RESET}")

    if exit_code and fail_on_regression:
        print(f"\n{RED}REGRESSION DETECTED — blocking release.{RESET}")
        return 1
    if exit_code:
        print(f"\n{YELLOW}Regression detected (not blocking — pass --fail-on-regression to enforce).{RESET}")
        return 0
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Compare hero-loop candidate vs baseline")
    p.add_argument("candidate", help="Path to candidate summary JSON")
    p.add_argument("--baseline", default="", help="Path to baseline JSON (default: latest in reports/baseline/)")
    p.add_argument("--fail-on-regression", action="store_true",
                   help="Exit non-zero if candidate regresses from baseline")
    args = p.parse_args()

    candidate_path = Path(args.candidate)
    if not candidate_path.exists():
        print(f"{RED}Candidate not found: {candidate_path}{RESET}")
        sys.exit(1)

    baseline_path = Path(args.baseline) if args.baseline else _find_latest_baseline()
    if not baseline_path or not baseline_path.exists():
        print(f"{YELLOW}No baseline found. Treating candidate as first baseline.{RESET}")
        candidate = _load(candidate_path)
        print(f"  Accuracy: {candidate['accuracy_pct']}% ({candidate['passed']}/{candidate['total']})")
        print(f"  Failures: {len(candidate.get('failures', []))}")
        fatal = candidate.get("fatal_error_count", 0)
        if fatal:
            print(f"  Fatal errors: {fatal}")
        print(f"\n{GRAY}Save as baseline with: scripts/save_baseline.sh{RESET}")
        sys.exit(0)

    baseline = _load(baseline_path)
    candidate = _load(candidate_path)
    print(f"{GRAY}Baseline file: {baseline_path}{RESET}")
    rc = _compare(baseline, candidate, args.fail_on_regression)
    sys.exit(rc)


if __name__ == "__main__":
    main()
