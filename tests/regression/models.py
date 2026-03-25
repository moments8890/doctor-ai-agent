from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FactRule:
    text: str
    allowed_fields: List[str]
    aliases: List[str] = field(default_factory=list)


@dataclass
class ForbiddenRule:
    text: str
    reason: str = ""


@dataclass
class ExtractionExpectations:
    facts: List[FactRule]
    forbidden: List[ForbiddenRule] = field(default_factory=list)
    field_rules: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=lambda: {"recall": 0.80})


@dataclass
class Assertion:
    target: str
    matcher: str
    expected: Any = None


@dataclass
class TurnInput:
    actor: str
    text: str


@dataclass
class InputSpec:
    mode: str
    turns: List[TurnInput]


@dataclass
class ExecutionSpec:
    entrypoint: str
    auto_confirm: bool = True
    timeout_seconds: int = 60


@dataclass
class ExpectationsSpec:
    assertions: List[Assertion] = field(default_factory=list)
    extraction: Optional[ExtractionExpectations] = None


@dataclass
class PatientInfo:
    name: str
    gender: str
    age: int


@dataclass
class ScenarioSpec:
    id: str
    scenario_type: str
    title: str
    tags: List[str]
    patient: PatientInfo
    input: InputSpec
    execution: ExecutionSpec
    expectations: ExpectationsSpec


@dataclass
class MatchResult:
    passed: bool
    detail: str


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    failures: List[str]
    duration_ms: int
    record_snapshot: Dict[str, str] = field(default_factory=dict)
    fact_matches: Dict[str, MatchResult] = field(default_factory=dict)
