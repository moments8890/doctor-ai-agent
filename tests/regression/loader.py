from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pytest

from tests.regression.models import (
    Assertion,
    ExtractionExpectations,
    ExecutionSpec,
    ExpectationsSpec,
    FactRule,
    ForbiddenRule,
    InputSpec,
    PatientInfo,
    ScenarioSpec,
    TurnInput,
)

_CONFIRM_TEXTS = {"确认", "确认保存", "保存"}


def load_scenarios(dirs: List[str]) -> List[pytest.param]:
    """Load all JSON scenario files from *dirs*, auto-detect format, return as pytest.params."""
    specs: List[pytest.param] = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in sorted(p.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                spec = _load_one(data, f)
                if spec:
                    specs.append(pytest.param(spec, id=spec.id))
            except Exception:
                pass  # skip unparseable files
    return specs


def _load_one(data: dict, path: Path) -> Optional[ScenarioSpec]:
    fmt = _detect_format(data)
    if fmt == "d1d8":
        return _normalize_d1d8(data, path)
    elif fmt == "mvp":
        return _normalize_mvp(data, path)
    elif fmt == "v2":
        return _parse_v2(data)
    return None


def _detect_format(data: dict) -> str:
    if data.get("schema_version") == 2:
        return "v2"
    if "turn_plan" in data and ("fact_catalog" in data or "facts" in data):
        return "d1d8"
    if "chatlog" in data and "expectations" in data:
        return "mvp"
    return "unknown"


# ---------------------------------------------------------------------------
# Format 1: D1-D8 doctor sim extraction scenarios
# ---------------------------------------------------------------------------


def _normalize_d1d8(data: dict, path: Path) -> ScenarioSpec:
    pid = data.get("id") or path.stem.upper()
    pinfo = data.get("patient_info", {})

    turns: List[TurnInput] = []
    for tp in data.get("turn_plan", []):
        turns.append(TurnInput(actor="doctor", text=tp["text"]))

    facts_raw = data.get("fact_catalog") or data.get("facts") or []
    facts: List[FactRule] = []
    for fr in facts_raw:
        text = fr.get("text", "")
        # Legacy "field" is a single field; convert to allowed_fields list
        allowed = fr.get("allowed_fields", [])
        if not allowed and fr.get("field"):
            allowed = [fr["field"]]
        aliases = fr.get("aliases", [])
        if text:
            facts.append(FactRule(text=text, allowed_fields=allowed, aliases=aliases))

    forbidden_raw = data.get("forbidden_facts") or data.get("forbidden") or []
    forbidden = [
        ForbiddenRule(text=f.get("text", ""), reason=f.get("reason", ""))
        for f in forbidden_raw
    ]

    thresholds = data.get("thresholds", {"recall": 0.80})

    extraction: Optional[ExtractionExpectations] = None
    if facts:
        extraction = ExtractionExpectations(
            facts=facts,
            forbidden=forbidden,
            thresholds=thresholds,
        )

    return ScenarioSpec(
        id=pid,
        scenario_type="doctor_extraction",
        title=data.get("name", "") or data.get("title", "") or path.stem,
        tags=data.get("tags", ["extraction"]),
        patient=PatientInfo(
            name=pinfo.get("name", ""),
            gender=pinfo.get("gender", ""),
            age=pinfo.get("age", 0),
        ),
        input=InputSpec(mode="doctor_interview", turns=turns),
        execution=ExecutionSpec(entrypoint="records.interview.turn", auto_confirm=True),
        expectations=ExpectationsSpec(extraction=extraction),
    )


# ---------------------------------------------------------------------------
# Format 2: MVP benchmark (chat pipeline) scenarios
# ---------------------------------------------------------------------------


def _normalize_mvp(data: dict, path: Path) -> ScenarioSpec:
    case_id = data.get("case_id", path.stem)
    exp = data.get("expectations", {})
    group = data.get("group", "")

    turns: List[TurnInput] = []
    for turn in data.get("chatlog", []):
        if turn.get("speaker") != "doctor":
            continue
        text = turn.get("text", "")
        if text.strip() in _CONFIRM_TEXTS:
            continue
        turns.append(TurnInput(actor="doctor", text=text))

    assertions: List[Assertion] = []

    if exp.get("expected_patient_name"):
        assertions.append(
            Assertion(
                target="db.patients.name",
                matcher="eq",
                expected=exp["expected_patient_name"],
            )
        )
    if exp.get("expected_patient_count") is not None:
        assertions.append(
            Assertion(
                target="db.patients.count",
                matcher="eq",
                expected=exp["expected_patient_count"],
            )
        )

    for table, min_v in (exp.get("expected_table_min_counts_by_doctor") or {}).items():
        assertions.append(
            Assertion(target=f"db.{table}.count", matcher="min", expected=min_v)
        )
    for table, max_v in (exp.get("expected_table_max_counts_by_doctor") or {}).items():
        assertions.append(
            Assertion(target=f"db.{table}.count", matcher="max", expected=max_v)
        )

    # MVP scenarios use the chat pipeline, not interview pipeline
    return ScenarioSpec(
        id=case_id,
        scenario_type="doctor_chat",
        title=data.get("title", path.stem),
        tags=data.get("tags", [group] if group else []),
        patient=PatientInfo(
            name=exp.get("expected_patient_name", ""),
            gender="",
            age=0,
        ),
        input=InputSpec(mode="doctor_chat", turns=turns),
        execution=ExecutionSpec(entrypoint="records.chat", auto_confirm=False),
        expectations=ExpectationsSpec(assertions=assertions),
    )


# ---------------------------------------------------------------------------
# Format 3: v2 native (schema_version: 2)
# ---------------------------------------------------------------------------


def _parse_v2(data: dict) -> ScenarioSpec:
    """Parse native v2 format directly into ScenarioSpec."""
    patient = data.get("patient", {})
    inp = data.get("input", {})
    exe = data.get("execution", {})
    exp = data.get("expectations", {})

    turns = [
        TurnInput(actor=t.get("actor", "doctor"), text=t["text"])
        for t in inp.get("turns", [])
    ]

    assertions = [
        Assertion(
            target=a["target"],
            matcher=a["matcher"],
            expected=a.get("expected"),
        )
        for a in exp.get("assertions", [])
    ]

    extraction: Optional[ExtractionExpectations] = None
    extraction_data = exp.get("extraction")
    if extraction_data:
        facts = [
            FactRule(
                text=f["text"],
                allowed_fields=f.get("allowed_fields", []),
                aliases=f.get("aliases", []),
            )
            for f in extraction_data.get("facts", [])
        ]
        forbidden = [
            ForbiddenRule(text=f["text"], reason=f.get("reason", ""))
            for f in extraction_data.get("forbidden", [])
        ]
        extraction = ExtractionExpectations(
            facts=facts,
            forbidden=forbidden,
            field_rules=extraction_data.get("field_rules", {}),
            thresholds=extraction_data.get("thresholds", {"recall": 0.80}),
        )

    return ScenarioSpec(
        id=data["id"],
        scenario_type=data.get("scenario_type", "doctor_extraction"),
        title=data.get("title", ""),
        tags=data.get("tags", []),
        patient=PatientInfo(
            name=patient.get("name", ""),
            gender=patient.get("gender", ""),
            age=patient.get("age", 0),
        ),
        input=InputSpec(mode=inp.get("mode", "doctor_interview"), turns=turns),
        execution=ExecutionSpec(
            entrypoint=exe.get("entrypoint", "records.interview.turn"),
            auto_confirm=exe.get("auto_confirm", True),
            timeout_seconds=exe.get("timeout_seconds", 60),
        ),
        expectations=ExpectationsSpec(assertions=assertions, extraction=extraction),
    )
