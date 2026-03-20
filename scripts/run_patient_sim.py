#!/usr/bin/env python3
"""Patient simulation CLI — run LLM-simulated patients against the interview API.

Usage:
    python scripts/run_patient_sim.py --patients all
    python scripts/run_patient_sim.py --patients P1,P4 --patient-llm groq
    python scripts/run_patient_sim.py --patients all --no-quality-score
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure src/ is importable (for DB_PATH resolution)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts.patient_sim.engine import run_persona
from scripts.patient_sim.patient_llm import create_patient_llm, _PROVIDERS
from scripts.patient_sim.validator import validate
from scripts.patient_sim.report import generate_markdown, generate_json

PERSONAS_DIR = ROOT / "tests" / "fixtures" / "patient_sim" / "personas"
REPORTS_DIR = ROOT / "reports" / "patient_sim"


def _resolve_db_path() -> str:
    """Resolve DB path using same logic as integration test conftest."""
    from utils.runtime_config import load_runtime_json
    cfg = load_runtime_json()
    return str(Path(
        os.environ.get(
            "PATIENTS_DB_PATH",
            str(cfg.get("PATIENTS_DB_PATH") or (ROOT / "data" / "patients.db")),
        )
    ).expanduser())


def _load_personas(selection: str) -> List[Dict]:
    """Load persona JSON files. 'all' loads all, otherwise comma-separated IDs."""
    personas = []
    for f in sorted(PERSONAS_DIR.glob("*.json")):
        with open(f) as fh:
            personas.append(json.load(fh))

    if selection == "all":
        return personas

    ids = {s.strip().upper() for s in selection.split(",")}
    filtered = [p for p in personas if p["id"].upper() in ids]
    if not filtered:
        print(f"No personas matched: {selection}. Available: {[p['id'] for p in personas]}")
        sys.exit(1)
    return filtered


def _cleanup_sim_data(db_path: str, doctor_ids: List[str]) -> None:
    """Remove simulation test data from DB."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        for table in [
            "medical_records",
            "patients",
            "interview_sessions",
            "review_queue",
            "doctor_tasks",
            "doctors",
        ]:
            try:
                conn.execute(f"DELETE FROM {table} WHERE doctor_id LIKE 'intsim_%'")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-simulated patient interviews")
    parser.add_argument(
        "--patients", default="all",
        help="Comma-separated persona IDs or 'all'",
    )
    parser.add_argument(
        "--patient-llm", default="deepseek", choices=list(_PROVIDERS),
        help="Patient LLM provider",
    )
    parser.add_argument(
        "--server", default="http://127.0.0.1:8001",
        help="Server URL",
    )
    parser.add_argument(
        "--no-quality-score", action="store_true",
        help="Skip Tier 3 LLM quality scoring",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path()
    personas = _load_personas(args.patients)
    patient_llm = create_patient_llm(args.patient_llm)

    # Judge LLM (reuse patient LLM provider unless skipped)
    judge_client = None  # type: Optional[object]
    judge_model = ""
    if not args.no_quality_score:
        from openai import OpenAI
        cfg = _PROVIDERS[args.patient_llm]
        api_key = os.environ.get(cfg["api_key_env"], "")
        if api_key:
            judge_client = OpenAI(base_url=cfg["base_url"], api_key=api_key)
            judge_model = cfg["model"]

    print(f"Patient LLM: {args.patient_llm} | Server: {args.server}")
    print(f"Personas: {[p['id'] for p in personas]}")
    print(f"DB: {db_path}")
    print()

    all_results = []  # type: List[Dict]
    doctor_ids = []  # type: List[str]

    for persona in personas:
        print(f"Running {persona['id']} {persona['name']}...", end=" ", flush=True)

        sim = run_persona(persona, patient_llm, args.server, db_path)
        doctor_ids.append(sim.doctor_id)

        vr = validate(db_path, sim, persona, judge_client, judge_model)

        result = {
            "persona_id": persona["id"],
            "persona_name": persona["name"],
            "doctor_id": sim.doctor_id,
            "turns": sim.turns,
            "error": sim.error,
            "db_pass": vr.db_pass,
            "db_errors": vr.db_errors,
            "extraction_results": {
                k: {**v, "matches": {mk: mv for mk, mv in v["matches"].items()}}
                for k, v in vr.extraction_results.items()
            },
            "extraction_pass": vr.extraction_pass,
            "checklist_coverage": vr.checklist_coverage,
            "quality_score": vr.quality_score,
            "quality_detail": vr.quality_detail,
            "passed": vr.passed,
            "conversation": sim.conversation,
        }
        all_results.append(result)

        status = "PASS" if vr.passed else "FAIL"
        print(f"{status} ({sim.turns} turns)")

    # Generate reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

    system_llm = os.environ.get("ROUTING_LLM", "unknown")
    md = generate_markdown(all_results, args.patient_llm, system_llm, args.server)
    json_str = generate_json(all_results, args.patient_llm, system_llm, args.server)

    md_path = REPORTS_DIR / f"sim-{ts}.md"
    json_path = REPORTS_DIR / f"sim-{ts}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json_str, encoding="utf-8")

    # Summary
    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed")
    print(f"Report:  {md_path}")
    print(f"JSON:    {json_path}")

    # Cleanup
    _cleanup_sim_data(db_path, doctor_ids)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
