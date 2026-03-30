#!/usr/bin/env python
"""Reply simulation CLI — test triage + reply pipeline with predefined scenarios.

Usage:
    PYTHONPATH=src:scripts python scripts/run_reply_sim.py --scenarios all --server http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _REPO_ROOT / "config" / "runtime.json"
if _CONFIG_PATH.exists():
    _cfg = json.loads(_CONFIG_PATH.read_text())
    for _cat in (_cfg.get("categories") or {}).values():
        for k, v in ((_cat.get("settings") if isinstance(_cat, dict) else None) or {}).items():
            val = v.get("value") if isinstance(v, dict) else v
            if isinstance(val, str) and val and k not in os.environ:
                os.environ[k] = val

from reply_sim.engine import run_scenario, cleanup_sim_data  # noqa: E402
from reply_sim.validator import validate_all  # noqa: E402
from reply_sim.report import generate_reports  # noqa: E402

_SCENARIOS_DIR = _REPO_ROOT / "tests" / "fixtures" / "reply_sim" / "scenarios"

_SCENARIO_FILES = {
    "RX1": "rx1_med_timing_info.json",
    "RX2": "rx2_new_symptom_escalate.json",
    "RX3": "rx3_urgent_headache.json",
    "RX4": "rx4_side_effect_escalate.json",
    "RX5": "rx5_followup_timing_info.json",
    "RX6": "rx6_recovery_question_escalate.json",
    "RX7": "rx7_kb_driven_reply.json",
    "RX8": "rx8_ambiguous_general.json",
    "RX9": "rx9_mixed_info_symptom.json",
    "RX10": "rx10_kb_med_management.json",
    "RX11": "rx11_kb_anticoag_reply.json",
    "RX12": "rx12_kb_diet_guidance.json",
    "RX13": "rx13_kb_exercise_reply.json",
    "RX14": "rx14_kb_multi_select.json",
}


def _resolve_db_path() -> str:
    env = os.environ.get("PATIENTS_DB_PATH")
    if env:
        return str(Path(env).expanduser())
    runtime_json = _REPO_ROOT / "config" / "runtime.json"
    if runtime_json.exists():
        try:
            cfg = json.loads(runtime_json.read_text(encoding="utf-8"))
            val = cfg.get("PATIENTS_DB_PATH")
            if isinstance(cfg.get("database"), dict):
                val = val or cfg["database"].get("PATIENTS_DB_PATH")
            if val:
                return str(Path(val).expanduser())
        except Exception:
            pass
    return str(_REPO_ROOT / "data" / "patients.db")


def _load_scenarios(ids: list[str]) -> list[dict]:
    scenarios = []
    for sid in ids:
        filename = _SCENARIO_FILES.get(sid.upper())
        if not filename:
            print(f"Unknown scenario ID: {sid}. Valid: {', '.join(_SCENARIO_FILES)}")
            sys.exit(1)
        path = _SCENARIOS_DIR / filename
        if not path.exists():
            print(f"Scenario file not found: {path}")
            sys.exit(1)
        scenarios.append(json.loads(path.read_text()))
    return scenarios


async def _run(args: argparse.Namespace) -> None:
    db_path = _resolve_db_path()
    server = args.server.rstrip("/")

    if args.scenarios.lower() == "all":
        scenario_ids = list(_SCENARIO_FILES.keys())
    else:
        scenario_ids = [s.strip().upper() for s in args.scenarios.split(",")]

    scenarios = _load_scenarios(scenario_ids)

    print(f"Server: {server}")
    print(f"Scenarios: {[s['id'] for s in scenarios]}")
    print()

    results = []
    for scenario in scenarios:
        sid = scenario["id"]
        title = scenario.get("title", sid)
        print(f"Running {sid} {title}...", end=" ", flush=True)

        try:
            sim_result = await run_scenario(scenario=scenario, server_url=server, db_path=db_path)
            validation = validate_all(sim_result, scenario)
            sim_result["validation"] = validation
            sim_result["pass"] = validation["pass"]

            status = "PASS" if sim_result["pass"] else "FAIL"
            cat = sim_result.get("triage_category", "?")
            handled = "AI" if sim_result.get("ai_handled") else "医生"
            print(f"{status} (category={cat}, handler={handled}, {sim_result.get('response_time_s', 0)}s)")

        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"ERROR: {exc}")
            sim_result = {
                "scenario_id": sid, "message": scenario.get("message", ""),
                "reply": "", "triage_category": "", "ai_handled": None,
                "error": str(exc), "response_time_s": 0,
                "validation": {"tier1_triage": {"pass": False, "checks": {}},
                               "tier2_reply": {"pass": False, "checks": {}},
                               "tier3_kb": {"pass": True, "checks": {}}},
                "pass": False,
            }

        results.append(sim_result)

    html_path, json_path = generate_reports(
        results=results, scenarios=scenarios, server_url=server, db_path=db_path)

    deleted = cleanup_sim_data(db_path)
    if deleted:
        print(f"\nCleaned up {deleted} test rows")

    passed_count = sum(1 for r in results if r.get("pass"))
    print()
    print("=" * 50)
    print(f"Results: {passed_count}/{len(results)} passed")
    print(f"Report:  {html_path}")
    print(f"JSON:    {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reply simulation testing pipeline")
    parser.add_argument("--scenarios", default="all", help="Comma-separated IDs or 'all'")
    parser.add_argument("--server", default="http://127.0.0.1:8001", help="Server URL")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
