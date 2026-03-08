#!/usr/bin/env python3
"""
Validate mined routing rules against the turn log.

Reports precision, recall, and coverage for each rule, which is useful for
monitoring rule drift over time as new turns are logged.

Usage:
    python scripts/validate_routing_rules.py \\
      --rules data/mined_rules.json \\
      --log logs/turn_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_turn_log(path: Path) -> List[Dict[str, Any]]:
    """Read all entries from a turn log JSONL file."""
    if not path.exists():
        print(f"[warn] turn log not found: {path}", file=sys.stderr)
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def load_rules(path: Path) -> List[Dict[str, Any]]:
    """Load rules from JSON file and compile patterns."""
    if not path.exists():
        print(f"[error] rules file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        raw: List[Dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[error] failed to parse rules file: {e}", file=sys.stderr)
        sys.exit(1)

    compiled = []
    for rule in raw:
        if not isinstance(rule, dict):
            continue
        try:
            patterns = [re.compile(p) for p in rule.get("patterns", [])]
        except re.error as e:
            print(f"[warn] skipping rule {rule.get('intent')!r}: bad regex: {e}", file=sys.stderr)
            continue
        compiled.append({
            "intent": rule.get("intent", ""),
            "patterns": patterns,
            "keywords_any": list(rule.get("keywords_any") or []),
            "min_length": int(rule.get("min_length", 0)),
            "enabled": bool(rule.get("enabled", True)),
            # Keep original patterns for display
            "_pattern_strs": list(rule.get("patterns", [])),
        })
    return compiled


def _apply_rule(rule: Dict[str, Any], text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < rule.get("min_length", 0):
        return False
    if any(p.search(stripped) for p in rule["patterns"]):
        return True
    if any(k in stripped for k in rule.get("keywords_any", [])):
        return True
    return False


def validate_all(
    rules: List[Dict[str, Any]],
    turns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute per-rule precision/recall/coverage statistics.

    Returns a list of dicts with keys:
        intent, enabled, n_target, n_matched, n_correct,
        precision, recall, coverage
    """
    results = []
    for rule in rules:
        intent = rule["intent"]
        enabled = rule["enabled"]
        target_turns = [t for t in turns if t.get("intent") == intent]
        n_target = len(target_turns)

        matched_total = 0
        matched_correct = 0
        matched_target = 0

        for turn in turns:
            if _apply_rule(rule, turn.get("text", "")):
                matched_total += 1
                if turn.get("intent") == intent:
                    matched_correct += 1

        for turn in target_turns:
            if _apply_rule(rule, turn.get("text", "")):
                matched_target += 1

        precision = matched_correct / matched_total if matched_total > 0 else 0.0
        recall = matched_target / n_target if n_target > 0 else 0.0

        results.append({
            "intent": intent,
            "enabled": enabled,
            "n_target": n_target,
            "n_matched": matched_total,
            "n_correct": matched_correct,
            "precision": precision,
            "recall": recall,
            "patterns": rule["_pattern_strs"],
            "keywords_any": rule.get("keywords_any", []),
        })
    return results


def print_report(results: List[Dict[str, Any]]) -> None:
    header = (
        f"{'Intent':<22} {'Enabled':>7} {'Target':>7} {'Matched':>7} "
        f"{'Correct':>7} {'Precision':>9} {'Recall':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        enabled_str = "yes" if r["enabled"] else "no"
        print(
            f"{r['intent']:<22} {enabled_str:>7} {r['n_target']:>7} {r['n_matched']:>7} "
            f"{r['n_correct']:>7} {r['precision']:>9.3f} {r['recall']:>7.3f}"
        )
        if r["patterns"]:
            for pat in r["patterns"]:
                print(f"    pattern: {pat}")
        if r["keywords_any"]:
            print(f"    keywords_any: {r['keywords_any']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mined routing rules against turn log.")
    parser.add_argument("--rules", default="data/mined_rules.json", help="Rules JSON file")
    parser.add_argument("--log", default="logs/turn_log.jsonl", help="Turn log JSONL file")
    args = parser.parse_args()

    rules_path = Path(args.rules)
    log_path = Path(args.log)

    rules = load_rules(rules_path)
    turns = load_turn_log(log_path)

    print(f"Loaded {len(rules)} rule(s) from {rules_path}")
    print(f"Loaded {len(turns)} turn(s) from {log_path}\n")

    if not rules:
        print("No rules to validate.")
        return
    if not turns:
        print("No turns to validate against.")
        return

    results = validate_all(rules, turns)
    print_report(results)

    # Summary
    n_enabled = sum(1 for r in results if r["enabled"])
    n_high_prec = sum(1 for r in results if r["precision"] >= 0.95 and r["enabled"])
    print(f"Summary: {n_enabled} enabled rule(s), {n_high_prec} with precision >= 0.95")


if __name__ == "__main__":
    main()
