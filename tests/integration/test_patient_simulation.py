# tests/integration/test_patient_simulation.py
"""Pytest wrapper for patient simulation (gated behind RUN_PATIENT_SIM=1).

Runs the full LLM-simulated patient pipeline and asserts pass/fail per persona.
Requires: running server + patient LLM API key + system LLM.

Usage:
    RUN_PATIENT_SIM=1 PYTHONPATH=src pytest tests/integration/test_patient_simulation.py -v -s
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_PATIENT_SIM") != "1",
        reason="Set RUN_PATIENT_SIM=1 to run patient simulation tests.",
    ),
]

PERSONAS_DIR = ROOT / "tests" / "fixtures" / "patient_sim" / "personas"


def _load_all_personas() -> List[Dict[str, Any]]:
    """Load all persona JSON files from the fixtures directory."""
    personas = []  # type: List[Dict[str, Any]]
    for f in sorted(PERSONAS_DIR.glob("*.json")):
        with open(f) as fh:
            personas.append(json.load(fh))
    return personas


def _get_persona_ids() -> List[str]:
    """Return persona IDs for pytest parametrize (evaluated at collection time)."""
    return [p["id"] for p in _load_all_personas()]


@pytest.fixture(scope="module")
def sim_components() -> Dict[str, Any]:
    """Set up patient LLM, server URL, and DB path once per module."""
    from scripts.patient_sim.patient_llm import create_patient_llm
    from scripts.patient_sim.engine import run_persona
    from scripts.patient_sim.validator import validate

    provider = os.environ.get("PATIENT_SIM_LLM", "deepseek")
    server = os.environ.get("INTEGRATION_SERVER_URL", "http://127.0.0.1:8001")

    from utils.runtime_config import load_runtime_json
    cfg = load_runtime_json()
    db_path = str(Path(
        os.environ.get(
            "PATIENTS_DB_PATH",
            str(cfg.get("PATIENTS_DB_PATH") or (ROOT / "data" / "patients.db")),
        )
    ).expanduser())

    patient_llm = create_patient_llm(provider)

    return {
        "patient_llm": patient_llm,
        "server": server,
        "db_path": db_path,
        "run_persona": run_persona,
        "validate": validate,
    }


@pytest.mark.parametrize("persona_id", _get_persona_ids())
def test_patient_simulation(persona_id: str, sim_components: Dict[str, Any]) -> None:
    """Run one persona through the interview pipeline and validate.

    No Tier 3 quality scoring in pytest -- too slow and too flaky for CI.
    """
    personas = _load_all_personas()
    persona = next(p for p in personas if p["id"] == persona_id)

    sim = sim_components["run_persona"](
        persona,
        sim_components["patient_llm"],
        sim_components["server"],
        sim_components["db_path"],
    )

    assert sim.error is None, f"Simulation error: {sim.error}"

    vr = sim_components["validate"](
        sim_components["db_path"], sim, persona,
    )

    assert vr.db_pass, f"DB validation failed: {vr.db_errors}"
    assert vr.extraction_pass, (
        f"Extraction validation failed (coverage={vr.checklist_coverage:.0%}): "
        f"{json.dumps({k: v for k, v in vr.extraction_results.items() if not v['pass']}, ensure_ascii=False)}"
    )
