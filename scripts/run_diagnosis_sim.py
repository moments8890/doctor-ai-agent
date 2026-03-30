#!/usr/bin/env python
"""Diagnosis simulation CLI — test the diagnosis pipeline with predefined scenarios.

Usage:
    PYTHONPATH=src python scripts/run_diagnosis_sim.py --scenarios all --server http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure config is loaded so API keys are available in env
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _REPO_ROOT / "config" / "runtime.json"
if _CONFIG_PATH.exists():
    _cfg = json.loads(_CONFIG_PATH.read_text())
    for _cat in (_cfg.get("categories") or {}).values():
        for k, v in ((_cat.get("settings") if isinstance(_cat, dict) else None) or {}).items():
            val = v.get("value") if isinstance(v, dict) else v
            if isinstance(val, str) and val and k not in os.environ:
                os.environ[k] = val

from diagnosis_sim.engine import run_scenario, cleanup_sim_data  # noqa: E402
from diagnosis_sim.validator import validate_all  # noqa: E402
from diagnosis_sim.report import generate_reports  # noqa: E402

# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = _REPO_ROOT / "tests" / "fixtures" / "diagnosis_sim" / "scenarios"

_SCENARIO_FILES = {
    "DX1": "dx1_meningioma_full.json",
    "DX2": "dx2_headache_minimal.json",
    "DX3": "dx3_aneurysm_with_kb.json",
    "DX4": "dx4_ich_emergency.json",
    "DX5": "dx5_carotid_with_cases.json",
    "DX6": "dx6_multisystem_complex.json",
    "DX7": "dx7_epilepsy_kb_meds.json",
    "DX8": "dx8_aneurysm_minimal.json",
    "DX9": "dx9_stroke_followup_cases.json",
    "DX10": "dx10_avm_rare_kb.json",
    "DX11": "dx11_vertigo_differential.json",
    "DX12": "dx12_meningioma_allergy_kb.json",
}


def _resolve_db_path() -> str:
    """Resolve DB path: env var > config/runtime.json > fallback."""
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
    """Load scenario JSON files by ID."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run(args: argparse.Namespace) -> None:
    db_path = _resolve_db_path()
    server = args.server.rstrip("/")

    # Resolve scenario IDs
    if args.scenarios.lower() == "all":
        scenario_ids = list(_SCENARIO_FILES.keys())
    else:
        scenario_ids = [s.strip().upper() for s in args.scenarios.split(",")]

    scenarios = _load_scenarios(scenario_ids)

    print(f"Server: {server}")
    print(f"Scenarios: {[s['id'] for s in scenarios]}")
    print(f"DB: {db_path}")
    print()

    results = []

    for scenario in scenarios:
        sid = scenario["id"]
        title = scenario.get("title", sid)
        label = f"Running {sid} {title}..."
        print(label, end=" ", flush=True)

        try:
            # Run scenario
            sim_result = await run_scenario(
                scenario=scenario,
                server_url=server,
                db_path=db_path,
            )

            # Validate
            suggestions = sim_result.get("suggestions", [])
            validation = validate_all(
                suggestions, scenario,
                kb_relevant_ids=sim_result.get("kb_relevant_ids", []),
                kb_irrelevant_ids=sim_result.get("kb_irrelevant_ids", []),
                kb_items_meta=sim_result.get("kb_items_meta", []),
                baseline_suggestions=sim_result.get("baseline_suggestions", []),
            )
            sim_result["validation"] = validation
            sim_result["pass"] = validation["pass"]
            sim_result["combined_score"] = validation.get("combined_score", 0)

            status = "PASS" if sim_result["pass"] else "FAIL"
            score = sim_result["combined_score"]
            n_suggestions = len(suggestions)
            time_s = sim_result.get("diagnosis_time_s", 0)
            print(f"{status} (score={score}, {n_suggestions} suggestions, {time_s}s)")

        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"ERROR: {exc}")
            sim_result = {
                "scenario_id": sid,
                "doctor_id": f"dxsim_{sid}_error",
                "record_id": None,
                "kb_ids": [],
                "case_record_ids": [],
                "record_fields": scenario.get("record", {}),
                "suggestions": [],
                "error": str(exc),
                "diagnosis_time_s": 0,
                "validation": {
                    "tier1": {"pass": False, "checks": {"error": {"pass": False, "detail": str(exc)}}},
                    "tier2": {"pass": False, "combined_score": 0, "checks": {}},
                    "tier3": {"pass": True, "checks": {}},
                },
                "pass": False,
                "combined_score": 0,
            }

        results.append(sim_result)

    # ------------------------------------------------------------------
    # Report (before cleanup — needs DB records)
    # ------------------------------------------------------------------
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    html_path, json_path = generate_reports(
        results=results,
        scenarios=scenarios,
        server_url=server,
        db_path=db_path,
    )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    deleted = cleanup_sim_data(db_path)
    if deleted:
        print(f"\nCleaned up {deleted} test rows")

    print()
    print("=" * 50)
    print(f"Results: {passed_count}/{total} passed")
    print(f"Report:  {html_path}")
    print(f"JSON:    {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnosis simulation testing pipeline")
    parser.add_argument(
        "--scenarios", default="all",
        help="Comma-separated scenario IDs (DX1,DX4,DX7) or 'all'",
    )
    parser.add_argument(
        "--server", default="http://127.0.0.1:8001",
        help="Server URL (default: http://127.0.0.1:8001)",
    )
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
