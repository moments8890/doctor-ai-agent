"""Kind A: JSON-driven parametrized extraction tests."""
from __future__ import annotations

import time
from typing import Any, Optional

import pytest

from tests.regression.loader import load_scenarios
from tests.regression.models import ScenarioSpec
from tests.regression.helpers import (
    chat,
    db_count,
    db_patient,
    db_record_fields,
    interview_confirm,
    interview_turn,
)
from tests.regression.matchers import fact_in_field, forbidden_absent, run_matcher

pytestmark = [pytest.mark.regression, pytest.mark.extraction]

SCENARIO_DIRS = [
    "tests/fixtures/doctor_sim/scenarios",
    # patient_sim scenarios need their own runner (patient auth, different API endpoints)
    # TODO: implement test_patient_interview.py for these
]

_scenarios = load_scenarios(SCENARIO_DIRS)


@pytest.mark.parametrize("scenario", _scenarios)
def test_extraction(scenario: ScenarioSpec, server_url, db_path, cleanup):
    """Run a scripted scenario and verify extraction accuracy."""
    doctor_id = cleanup.make_doctor_id(scenario.id)
    failures = []

    # 1. Send turns
    session_id: Optional[str] = None
    if scenario.execution.entrypoint == "records.chat":
        # MVP scenarios go through chat pipeline
        for turn in scenario.input.turns:
            chat(server_url, turn.text, doctor_id)
    else:
        # Extraction scenarios go through interview pipeline
        for turn in scenario.input.turns:
            resp = interview_turn(
                server_url, turn.text, session_id=session_id, doctor_id=doctor_id
            )
            session_id = resp.get("session_id")

        # 2. Confirm
        if scenario.execution.auto_confirm and session_id:
            status_code, _ = interview_confirm(server_url, session_id, doctor_id)
            if status_code != 200:
                failures.append(f"Confirm failed with status {status_code}")
            time.sleep(0.5)  # WAL flush delay

    # 3. Run generic assertions
    for a in scenario.expectations.assertions:
        # db.patients.name needs special handling: look up by name
        if a.target == "db.patients.name":
            patient = db_patient(db_path, doctor_id, a.expected)
            if patient is None:
                failures.append(
                    f"ASSERT db.patients.name: patient {a.expected!r} not found"
                )
            continue

        actual = _resolve_target(a.target, db_path, doctor_id)
        result = run_matcher(a.matcher, actual, a.expected)
        if not result.passed:
            failures.append(
                f"ASSERT {a.target} {a.matcher} {a.expected!r}: {result.detail}"
            )

    # 4. Run extraction checks
    extraction = scenario.expectations.extraction
    warnings = []  # individual misses — diagnostic, not failures
    if extraction:
        record = db_record_fields(db_path, doctor_id)
        if not record:
            failures.append("No medical record found in DB after confirm")
        else:
            # Fact matching
            matched = 0
            for fact in extraction.facts:
                result = fact_in_field(
                    fact.text, fact.allowed_fields, fact.aliases, record
                )
                if result.passed:
                    matched += 1
                else:
                    warnings.append(f"MISS: {fact.text} — {result.detail}")

            # Forbidden facts — these ARE failures (hallucination guard)
            for f in extraction.forbidden:
                result = forbidden_absent(f.text, record)
                if not result.passed:
                    failures.append(f"FORBIDDEN: {f.text} found — {result.detail}")

            # Recall threshold — the regression gate
            total_facts = len(extraction.facts)
            if total_facts > 0:
                recall = matched / total_facts
                threshold = extraction.thresholds.get("recall", 0.80)
                if recall < threshold:
                    failures.append(
                        f"RECALL: {recall:.0%} ({matched}/{total_facts}) "
                        f"< {threshold:.0%}"
                    )
                    # Include misses as context when recall fails
                    failures.extend(warnings)

    # Print warnings even on pass — diagnostic info visible with -v
    if warnings and not failures:
        print(f"\n  [{scenario.id}] {len(warnings)} info misses (recall above threshold):")
        for w in warnings[:5]:
            print(f"    {w}")
        if len(warnings) > 5:
            print(f"    ... +{len(warnings) - 5} more")

    assert not failures, "\n".join(failures)


def _resolve_target(target: str, db_path: str, doctor_id: str) -> Any:
    """Resolve an assertion target string to an actual value from the DB."""
    # record.exists — boolean
    if target == "record.exists":
        return bool(db_record_fields(db_path, doctor_id))

    # db.<table>.count — row count for doctor_id
    if target.startswith("db.") and target.endswith(".count"):
        table = target[3:-6]  # "db.patients.count" → "patients"
        return db_count(db_path, doctor_id, table)

    # record.<field> — value from latest medical_record
    if target.startswith("record."):
        field_name = target[7:]
        record = db_record_fields(db_path, doctor_id)
        return record.get(field_name)

    return None
