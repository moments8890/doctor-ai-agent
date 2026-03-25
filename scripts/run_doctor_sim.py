#!/usr/bin/env python
"""Doctor simulation CLI — run scripted doctor personas against the interview pipeline.

Usage:
    PYTHONPATH=src python scripts/run_doctor_sim.py --personas all
    PYTHONPATH=src python scripts/run_doctor_sim.py --personas D1,D2
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
    # Config uses nested structure: categories.*.settings.KEY.value
    for _cat in (_cfg.get("categories") or {}).values():
        for k, v in ((_cat.get("settings") if isinstance(_cat, dict) else None) or {}).items():
            val = v.get("value") if isinstance(v, dict) else v
            if isinstance(val, str) and val and k not in os.environ:
                os.environ[k] = val

from doctor_sim.engine import run_persona, cleanup_sim_data  # noqa: E402
from doctor_sim.validator import validate_doctor_extraction, resolve_db_path  # noqa: E402
from doctor_sim.report import generate_reports  # noqa: E402

# Import analyze_results from patient_sim (reused)
from patient_sim.validator import analyze_results  # noqa: E402

# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------

_PERSONAS_DIR = _REPO_ROOT / "tests" / "fixtures" / "doctor_sim" / "personas"

_PERSONA_FILES = {
    "D1": "d1_verbose_attending.json",
    "D2": "d2_telegraphic_surgeon.json",
    "D3": "d3_ocr_paste.json",
    "D4": "d4_multi_turn.json",
    "D5": "d5_bilingual_mix.json",
    "D6": "d6_negation_cluster.json",
    "D7": "d7_copy_paste_conflict.json",
    "D8": "d8_template_fill.json",
}


def _load_personas(ids: list[str]) -> list[dict]:
    """Load persona JSON files by ID."""
    personas = []
    for pid in ids:
        filename = _PERSONA_FILES.get(pid.upper())
        if not filename:
            print(f"Unknown persona ID: {pid}. Valid: {', '.join(_PERSONA_FILES)}")
            sys.exit(1)
        path = _PERSONAS_DIR / filename
        if not path.exists():
            print(f"Persona file not found: {path}")
            sys.exit(1)
        personas.append(json.loads(path.read_text()))
    return personas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run(args: argparse.Namespace) -> None:
    db_path = resolve_db_path()
    server = args.server.rstrip("/")

    # Resolve persona IDs
    if args.personas.lower() == "all":
        persona_ids = list(_PERSONA_FILES.keys())
    else:
        persona_ids = [p.strip().upper() for p in args.personas.split(",")]

    personas = _load_personas(persona_ids)

    print(f"Server: {server}")
    print(f"Personas: {[p['id'] for p in personas]}")
    print(f"DB: {db_path}")
    print()

    results = []

    for persona in personas:
        pid = persona["id"]
        name = persona.get("name", "?")
        style = persona.get("style", "")
        turns = len(persona.get("turn_plan", []))
        label = f"Running {pid} {name} ({style}, {turns} turns)..."
        print(label, end=" ", flush=True)

        try:
            # Run simulation
            sim_result = await run_persona(
                persona=persona,
                server_url=server,
                db_path=str(db_path),
            )

            # Validate extraction accuracy
            record_id = sim_result.get("record_id")
            if record_id:
                validation = await validate_doctor_extraction(
                    persona=persona,
                    db_path=str(db_path),
                    record_id=record_id,
                )
                sim_result["validation"] = validation
                sim_result["pass"] = validation["pass"]
            else:
                sim_result["validation"] = {
                    "pass": False,
                    "combined_score": 0,
                    "dimensions": {},
                }
                sim_result["pass"] = False

            status = "PASS" if sim_result["pass"] else "FAIL"
            combined = sim_result["validation"].get("combined_score", "?")
            print(f"{status} (score={combined})")

        except Exception as exc:
            print(f"ERROR: {exc}")
            sim_result = {
                "persona_id": pid,
                "persona": persona,
                "doctor_id": f"docsim_{pid}_error",
                "turns": 0,
                "session_id": None,
                "record_id": None,
                "soap_snapshot": {},
                "confirm_data": {},
                "turn_responses": [],
                "validation": {
                    "pass": False,
                    "combined_score": 0,
                    "dimensions": {},
                },
                "pass": False,
                "error": str(exc),
            }

        results.append(sim_result)

    # ------------------------------------------------------------------
    # AI Analysis — 2 analysts review full results
    # ------------------------------------------------------------------
    print("\nRunning AI analysis...", end=" ", flush=True)
    try:
        ai_analyses = await analyze_results(results, "scripted")
        print(f"done ({len(ai_analyses)} analysts)")
    except Exception as e:
        print(f"failed: {e}")
        ai_analyses = []

    # ------------------------------------------------------------------
    # Report (before cleanup — needs DB records for display)
    # ------------------------------------------------------------------
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    html_path, json_path = generate_reports(
        results=results,
        server_url=server,
        db_path=str(db_path),
        ai_analyses=ai_analyses,
    )

    # ------------------------------------------------------------------
    # Cleanup (after report generation)
    # ------------------------------------------------------------------
    deleted = cleanup_sim_data(str(db_path))
    if deleted:
        print(f"\nCleaned up {deleted} test rows")

    print()
    print("=" * 50)
    print(f"Results: {passed_count}/{total} passed")
    print(f"Report:  {html_path}")
    print(f"JSON:    {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Doctor simulation testing pipeline")
    parser.add_argument(
        "--personas", default="all",
        help="Comma-separated persona IDs (D1,D2,D3) or 'all'",
    )
    parser.add_argument(
        "--server", default="http://127.0.0.1:8000",
        help="Server URL (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
