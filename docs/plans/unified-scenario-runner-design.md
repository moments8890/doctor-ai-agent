# Unified Scenario Runner — Design

**Status:** Planned (Codex-reviewed)
**Date:** 2026-03-25
**Depends on:** Doctor sim pipeline (done), patient sim pipeline (done)
**Coverage analysis:** [scenario-coverage-analysis.md](scenario-coverage-analysis.md) — full gap analysis across all pipelines

## Goal

One deterministic test infrastructure for all scripted scenarios — doctor extraction,
MVP accuracy, patient interview benchmarks. No LLM judges in the regression gate.
Usable in CI, pytest-integrated, with clear regression detection.

## Unified Scenario Format (v2)

Both MVP and extraction scenarios use one envelope with a `scenario_type` discriminator:

```json
{
  "schema_version": 2,
  "id": "D1",
  "scenario_type": "doctor_extraction",
  "title": "详细主治医师 — 完整入院记录",
  "tags": ["regression", "extraction", "neurosurgery"],

  "patient": {
    "name": "陈建国",
    "gender": "男",
    "age": 56
  },

  "input": {
    "mode": "doctor_interview",
    "turns": [
      {"actor": "doctor", "text": "陈建国 男 56岁 神经外科..."}
    ]
  },

  "execution": {
    "entrypoint": "records.interview.turn",
    "auto_confirm": true,
    "timeout_seconds": 60
  },

  // NOTE: Patient record is created at CONFIRM time (deferred creation),
  // not during interview turns. All DB assertions run after confirm.

  "expectations": {
    "assertions": [
      {"target": "record.exists", "matcher": "eq", "expected": true},
      {"target": "record.chief_complaint", "matcher": "not_empty"},
      {"target": "db.patients.count", "matcher": "eq", "expected": 1},
      {"target": "db.medical_records.count", "matcher": "min", "expected": 1}
    ],

    "extraction": {
      "facts": [
        {
          "text": "体检发现颅内动脉瘤",
          "allowed_fields": ["chief_complaint", "present_illness"],
          "aliases": ["脑动脉瘤", "颅内动脉瘤"]
        },
        {
          "text": "高血压8年",
          "allowed_fields": ["past_history"],
          "aliases": ["高血压病史8年", "HTN 8y"]
        },
        {
          "text": "否认药物及食物过敏",
          "allowed_fields": ["allergy_history"],
          "aliases": ["无过敏", "无药物过敏"]
        }
      ],

      "forbidden": [
        {"text": "糖尿病", "reason": "patient does not have DM"}
      ],

      "field_rules": {
        "chief_complaint": {"required": true},
        "present_illness": {"required": true},
        "past_history": {"required": true},
        "allergy_history": {"required": true}
      },

      "thresholds": {
        "recall": 0.80,
        "field_accuracy": 0.80,
        "forbidden_hits": 0,
        "max_duplicates": 0
      }
    }
  }
}
```

### Backward Compatibility

The loader auto-detects format by checking keys:
- Has `chatlog` + `expectations.expected_patient_name` → MVP format → normalize to v2
- Has `turn_plan` + `facts` → D1-D8 format → normalize to v2
- Has `schema_version: 2` → already v2

## Deterministic Matchers

### Generic matchers (reuse from tests/scenarios/matchers.py)
```
eq(expected)              — exact match
not_empty()               — field has content
empty()                   — field is empty/absent
contains(text)            — substring match
contains_any([texts])     — any substring matches
not_contains_any([texts]) — none match
regex(pattern)            — regex match
min(n) / max(n)           — numeric comparison
count_eq(n)               — exact count
```

### Clinical matchers (new)
```
fact_present(text, aliases, normalize=True)
  — normalized text search across all record fields
  — applies: NFKC, full→half width, whitespace collapse, lowercase Latin, alias table

fact_in_field(text, allowed_fields, aliases)
  — fact_present + check field location

numeric_preserved(token)
  — "EF 45%" or "hs-cTnI 3.2" appears with original number

negation_present(text)
  — "无" / "否认" / "未见" appears for the expected negation

brand_generic_match(brand, generic)
  — either 波立维 or 氯吡格雷 is acceptable

surface_preserved(tokens)
  — specific abbreviations/values appear unmodified

duplicate_absent(field)
  — no repeated clause segments within a field (>80% similarity)

forbidden_absent(text)
  — text does NOT appear in any field (hallucination guard)
```

### Normalization Pipeline
```python
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)       # full→half width
    text = re.sub(r"\s+", " ", text).strip()          # whitespace collapse
    text = text.lower()                                # lowercase Latin only
    # Chinese punctuation → standard
    text = text.replace("，", ",").replace("。", ".").replace("；", ";")
    return text
```

### Alias Tables
```python
BRAND_GENERIC = {
    "波立维": "氯吡格雷", "拜新同": "硝苯地平",
    "立普妥": "阿托伐他汀", "可定": "瑞舒伐他汀",
    "倍他乐克": "美托洛尔", "格华止": "二甲双胍",
    "拜阿司匹林": "阿司匹林", "泰嘉": "氯吡格雷",
}

ABBREVIATION_FULL = {
    "HTN": "高血压", "DM": "糖尿病", "CHD": "冠心病",
    "BP": "血压", "HR": "心率", "EF": "射血分数",
    "PCI": "经皮冠状动脉介入", "STEMI": "ST段抬高型心肌梗死",
}

TIME_ALIASES = {
    "10y": "10年", "3d": "3天", "90min": "90分钟",
    "qd": "每日一次", "bid": "每日两次", "tid": "每日三次",
}
```

## Pytest Integration

### File structure
```
tests/
  regression/
    __init__.py
    conftest.py           # fixtures: server URL, DB path, scenario loader
    test_scenarios.py     # parametrized test from all scenarios
    matchers.py           # deterministic matcher library
    normalizer.py         # text normalization + alias tables
    loader.py             # auto-detect format, normalize to ScenarioSpec
    runner.py             # execute scenario against server, collect artifacts
    models.py             # ScenarioSpec, FactRule, MatchResult, ScenarioResult
```

### Test parametrization
```python
SCENARIOS_DIRS = [
    "tests/fixtures/doctor_sim/scenarios",
    "tests/fixtures/patient_sim/scenarios",
]

def _collect_scenarios():
    specs = []
    for d in SCENARIOS_DIRS:
        for f in sorted(Path(d).glob("*.json")):
            spec = load_scenario(f)
            specs.append(pytest.param(spec, id=spec.id))
    return specs

@pytest.mark.regression
@pytest.mark.parametrize("scenario", _collect_scenarios())
async def test_scenario(scenario: ScenarioSpec, server_url, db_path):
    result = await run_scenario(scenario, server_url, db_path)
    for failure in result.failures:
        # Collect all failures, don't stop at first
        pass
    assert not result.failures, result.failure_summary()
```

### Markers
```
pytest -m regression          # all regression scenarios
pytest -m extraction          # D1-D8 extraction only
pytest -m mvp                 # MVP accuracy only
pytest -k "stemi"             # specific scenario by name
```

### Artifacts collected per scenario
```python
@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    turn_responses: list          # raw API responses
    record_snapshot: dict         # DB record fields
    fact_matches: dict            # {fact_text: MatchResult}
    assertion_results: list       # generic assertion results
    failures: list[str]           # human-readable failure messages
    duration_ms: int
```

## Regression Baseline & Comparison

### Primary baseline = scenario file itself
- facts defines what must be present
- thresholds define acceptable scores
- forbidden_facts define what must NOT be present
- No separate "baseline snapshot" needed for pass/fail

### Secondary: run artifact comparison
- After each `main` merge, persist `ScenarioResult` JSON
- On PR, compare: newly missed facts, newly wrong-field, score deltas
- Alert on regressions, don't block on improvements

### Matcher profile versioning
```
matcher_profile: cn_medical_v1
```
- Bump when alias tables or normalization rules change
- Triggers baseline refresh

## Execution Modes

| Mode | How | Use case |
|------|-----|----------|
| HTTP (default) | Against server on port 8001 | CI, regression |
| In-process | Import and call directly | Local debugging |

## What This Replaces

| Current | Replaced by |
|---------|-------------|
| `test_e2e_fixtures.py` | `tests/regression/test_scenarios.py` |
| `scripts/doctor_sim/validator.py` (LLM judges) | `tests/regression/matchers.py` (deterministic) |
| `scripts/run_doctor_sim.py` (pass/fail) | `pytest -m regression` |
| LLM-based NHC quality scoring | Exploratory only, not regression gate |

## What Stays

| Component | Status |
|-----------|--------|
| `scripts/run_doctor_sim.py` | Exploratory mode with HTML reports |
| `scripts/run_patient_sim.py` | Exploratory mode with HTML reports |
| LLM judges / NHC quality | Exploratory analysis, not CI gate |
| D9 interactive persona | Exploratory only (non-deterministic) |

## Implementation Phases

### Phase 1: Core infrastructure
- `models.py` — ScenarioSpec, FactRule, MatchResult
- `normalizer.py` — text normalization + alias tables
- `matchers.py` — deterministic matcher library
- `loader.py` — auto-detect and normalize both formats

### Phase 2: Runner + pytest
- `runner.py` — execute scenario against server
- `conftest.py` — server URL, DB fixtures
- `test_scenarios.py` — parametrized test

### Phase 3: Migrate existing scenarios
- Convert D1-D8 to v2 format (add `allowed_fields`, `aliases`, `thresholds`)
- Convert MVP scenarios to v2 format
- Remove `test_e2e_fixtures.py` (replaced)

### Phase 4: CI integration
- GitHub Actions workflow
- Run on port 8001
- Artifact persistence for regression comparison
