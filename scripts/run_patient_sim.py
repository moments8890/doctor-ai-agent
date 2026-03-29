#!/usr/bin/env python
"""Patient simulation CLI — run LLM-simulated patients against the interview pipeline.

Usage:
    PYTHONPATH=src python scripts/run_patient_sim.py --patients all --patient-llm groq --no-quality-score
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

from patient_sim.engine import run_persona, cleanup_sim_data  # noqa: E402
from patient_sim.validator import validate_tier1, validate_tier2, validate_tier3, validate_tier4, resolve_db_path  # noqa: E402
from patient_sim.report import generate_reports  # noqa: E402

# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------

_PERSONAS_DIR = _REPO_ROOT / "tests" / "fixtures" / "patient_sim" / "personas"

_PERSONA_FILES = {
    "P1": "p1_aneurysm.json",
    "P2": "p2_stroke_followup.json",
    "P3": "p3_carotid_stenosis.json",
    "P4": "p4_avm_anxious.json",
    "P5": "p5_ich_recovery.json",
    "P6": "p6_headache_differential.json",
    "P7": "p7_post_coiling_meds.json",
    "P8": "p8_flow_diverter_nonadherent.json",
    "P9": "p9_amaurosis_fugax.json",
    "P10": "p10_davf_tinnitus.json",
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
    if args.patients.lower() == "all":
        persona_ids = list(_PERSONA_FILES.keys())
    else:
        persona_ids = [p.strip().upper() for p in args.patients.split(",")]

    personas = _load_personas(persona_ids)

    print(f"Patient LLM: {args.patient_llm} | Server: {server}")
    print(f"Personas: {[p['id'] for p in personas]}")
    print(f"DB: {db_path}")
    print()

    results = []

    for persona in personas:
        pid = persona["id"]
        name = persona["name"]
        label = f"Running {pid} {name}..."
        print(label, end=" ", flush=True)

        try:
            # Run simulation
            sim_result = await run_persona(
                persona=persona,
                server_url=server,
                patient_llm_provider=args.patient_llm,
                db_path=str(db_path),
            )

            # Validate Tier 1: DB checks
            t1 = validate_tier1(
                record_id=sim_result["record_id"],
                session_id=sim_result["session_id"],
                review_id=sim_result["review_id"],
                persona=persona,
                db_path=str(db_path),
            )
            sim_result["tier1"] = t1

            # Validate Tier 2: 3-axis scorecard (elicitation + extraction + NHC)
            t2 = await validate_tier2(
                persona=persona,
                db_path=str(db_path),
                record_id=sim_result["record_id"],
                conversation=sim_result["conversation"],
            )
            sim_result["tier2"] = t2

            # Validate Tier 3: Quality
            t3 = await validate_tier3(
                conversation=sim_result["conversation"],
                persona=persona,
                provider=args.patient_llm,
            )
            sim_result["tier3"] = t3

            # Validate Tier 4: Anomaly review
            t4 = await validate_tier4(
                conversation=sim_result["conversation"],
                persona=persona,
                db_path=str(db_path),
                record_id=sim_result["record_id"],
            )
            sim_result["tier4"] = t4

            # Overall pass/fail
            passed = t1["pass"] and t2["pass"]
            sim_result["pass"] = passed

            status = "PASS" if passed else "FAIL"
            turns = sim_result["turns"]
            print(f"{status} ({turns} turns)")

        except Exception as exc:
            print(f"ERROR: {exc}")
            sim_result = {
                "persona_id": pid,
                "doctor_id": f"intsim_{pid}_error",
                "turns": 0,
                "session_id": None,
                "record_id": None,
                "review_id": None,
                "conversation": [],
                "collected": {},
                "structured": {},
                "tier1": {"pass": False, "checks": {"error": {"pass": False, "detail": str(exc)}}},
                "tier2": {"pass": False, "extraction": {}, "checklist_coverage": 0, "checklist_pass": False},
                "tier3": {"score": -1, "explanation": "error"},
                "pass": False,
                "error": str(exc),
            }

        results.append(sim_result)

    # ------------------------------------------------------------------
    # AI Analysis — skipped (analyze_results removed)
    # ------------------------------------------------------------------
    ai_analyses = []

    # ------------------------------------------------------------------
    # Report (before cleanup — needs DB records for medical record display)
    # ------------------------------------------------------------------
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    html_path, json_path = generate_reports(
        results=results,
        patient_llm=args.patient_llm,
        server_url=server,
        db_path=str(db_path),
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
    parser = argparse.ArgumentParser(description="Patient simulation testing pipeline")
    parser.add_argument(
        "--patients", default="all",
        help="Comma-separated persona IDs (P1,P4,P7) or 'all'",
    )
    parser.add_argument(
        "--patient-llm", default="groq",
        choices=["groq", "deepseek", "claude"],
        help="LLM provider for patient simulation",
    )
    parser.add_argument(
        "--server", default="http://127.0.0.1:8001",
        help="Server URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--no-quality-score", action="store_true",
        help="(deprecated — quality scoring is always on)",
    )
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
