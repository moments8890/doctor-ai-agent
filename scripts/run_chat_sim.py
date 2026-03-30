#!/usr/bin/env python
"""Chat simulation CLI — test intent routing + handlers via /api/records/chat.

Usage:
    PYTHONPATH=src:scripts python scripts/run_chat_sim.py --scenarios all --server http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse, asyncio, json, os, sys
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

from chat_sim.engine import run_scenario, cleanup_sim_data
from chat_sim.validator import validate_all
from chat_sim.report import generate_reports

_SCENARIOS_DIR = _REPO_ROOT / "tests" / "fixtures" / "chat_sim" / "scenarios"
_SCENARIO_FILES = {
    "CX1": "cx1_query_record.json",
    "CX2": "cx2_query_patient_list.json",
    "CX3": "cx3_query_task.json",
    "CX4": "cx4_create_task.json",
    "CX5": "cx5_general_greeting.json",
    "CX6": "cx6_daily_summary.json",
    "CX7": "cx7_routing_ambiguous.json",
    "CX8": "cx8_create_record_chat.json",
}


def _resolve_db_path():
    env = os.environ.get("PATIENTS_DB_PATH")
    if env: return str(Path(env).expanduser())
    rj = _REPO_ROOT / "config" / "runtime.json"
    if rj.exists():
        try:
            cfg = json.loads(rj.read_text(encoding="utf-8"))
            val = cfg.get("PATIENTS_DB_PATH")
            if isinstance(cfg.get("database"), dict):
                val = val or cfg["database"].get("PATIENTS_DB_PATH")
            if val: return str(Path(val).expanduser())
        except Exception: pass
    return str(_REPO_ROOT / "data" / "patients.db")


def _load_scenarios(ids):
    scenarios = []
    for sid in ids:
        fn = _SCENARIO_FILES.get(sid.upper())
        if not fn:
            print(f"Unknown: {sid}. Valid: {', '.join(_SCENARIO_FILES)}")
            sys.exit(1)
        path = _SCENARIOS_DIR / fn
        if not path.exists():
            print(f"Not found: {path}")
            sys.exit(1)
        scenarios.append(json.loads(path.read_text()))
    return scenarios


async def _run(args):
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
    for sc in scenarios:
        sid = sc["id"]
        print(f"Running {sid} {sc.get('title', sid)}...", end=" ", flush=True)
        try:
            r = await run_scenario(scenario=sc, server_url=server, db_path=db_path)
            v = validate_all(r, sc)
            r["validation"] = v
            r["pass"] = v["pass"]
            status = "PASS" if r["pass"] else "FAIL"
            print(f"{status} (intent={r.get('intent','?')}, {r.get('response_time_s',0)}s)")
        except Exception as exc:
            import traceback; traceback.print_exc()
            print(f"ERROR: {exc}")
            r = {"scenario_id": sid, "message": sc.get("message",""), "reply": "",
                 "intent": "", "error": str(exc), "response_time_s": 0,
                 "validation": {"pass": False, "checks": {}}, "pass": False}
        results.append(r)

    html_path, json_path = generate_reports(results, scenarios, server, db_path)
    deleted = cleanup_sim_data(db_path)
    if deleted: print(f"\nCleaned up {deleted} rows")

    passed = sum(1 for r in results if r.get("pass"))
    print()
    print("=" * 50)
    print(f"Results: {passed}/{len(results)} passed")
    print(f"Report:  {html_path}")
    print(f"JSON:    {json_path}")


def main():
    p = argparse.ArgumentParser(description="Chat simulation testing")
    p.add_argument("--scenarios", default="all")
    p.add_argument("--server", default="http://127.0.0.1:8001")
    asyncio.run(_run(p.parse_args()))

if __name__ == "__main__":
    main()
