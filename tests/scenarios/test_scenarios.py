"""Scenario-driven E2E tests — in-process, YAML fixtures.

Run: ENVIRONMENT=development pytest tests/scenarios/ -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ROUTING_LLM", "groq")

from tests.scenarios.runner import ScenarioWorld, load_fixture
from tests.scenarios.matchers import (
    assert_equals, assert_exists, assert_contains_any, assert_not_contains_any, assert_min_count,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_all_scenarios() -> List[Dict[str, Any]]:
    scenarios = []
    for f in sorted(FIXTURES_DIR.glob("*.yaml")):
        scenario = yaml.safe_load(f.read_text(encoding="utf-8"))
        scenario["_file"] = f.name
        scenarios.append(scenario)
    return scenarios


ALL_SCENARIOS = _load_all_scenarios()


async def _check_hard_expectations(step_result: Dict, expects: Dict[str, Any], world: ScenarioWorld, step_id: str) -> None:
    """Check hard assertions on a step result."""
    for key, expected in expects.items():
        # Parse assertion: "field.subfield.op" or "field.subfield"
        parts = key.rsplit(".", 1)

        if len(parts) == 2 and parts[1] in ("exists", "contains_any", "not_contains_any", "min_count"):
            field_path, op = parts
        else:
            field_path = key
            op = "equals"

        # Special DB assertions
        if field_path.startswith("db."):
            db_parts = field_path.split(".")
            # db.medical_records.count, db.doctor_tasks.min_count, etc.
            table = db_parts[1]
            count = await world.db_count(table)
            if op == "min_count":
                assert_min_count(count, int(expected), f"{step_id}.{key}")
            else:
                assert_equals(count, expected, f"{step_id}.{key}")
            continue

        # Navigate the result
        actual = world.get_nested(step_result, field_path)

        if op == "exists":
            assert_exists(actual, f"{step_id}.{field_path}")
        elif op == "equals":
            assert_equals(actual, expected, f"{step_id}.{field_path}")
        elif op == "contains_any":
            assert_contains_any(str(actual), expected, f"{step_id}.{field_path}")
        elif op == "not_contains_any":
            assert_not_contains_any(str(actual), expected, f"{step_id}.{field_path}")
        elif op == "min_count":
            assert_min_count(int(actual or 0), int(expected), f"{step_id}.{field_path}")


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.get("id", s.get("_file", "unknown")))
async def test_scenario(scenario: Dict[str, Any]):
    """Execute a single scenario fixture."""
    world = ScenarioWorld(scenario)

    try:
        await world.setup()

        for step in scenario.get("steps", []):
            step_id = step["id"]
            result = await world.execute_step(step)

            # Check hard expectations
            hard = step.get("expect", {}).get("hard", {})
            if hard:
                await _check_hard_expectations(result, hard, world, step_id)

    finally:
        await world.teardown()
