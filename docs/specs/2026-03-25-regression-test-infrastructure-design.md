# Regression Test Infrastructure — Design

**Status:** Approved (brainstorm-reviewed)
**Date:** 2026-03-25
**Related:**
- [Unified Scenario Runner Design](../../plans/unified-scenario-runner-design.md) — format spec, matchers, normalization
- [Scenario Coverage Analysis](../../plans/scenario-coverage-analysis.md) — gap analysis across all pipelines

## Goal

One deterministic test infrastructure for all scripted regression scenarios.
No LLM judges in the regression gate. Pytest-integrated, CI-ready.

Two test styles sharing one infrastructure:
- **Kind A** (extraction): JSON-driven parametrized tests — 60+ scenarios, same execution pattern
- **Kind B** (workflow): pytest functions for session lifecycle, error handling, edge cases — ~16 tests

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deterministic vs behavioral | Deterministic only | Non-deterministic (triage, diagnosis, LLM reply quality) deferred to separate LLM-judge layer |
| One runner vs two | Shared infra, two test styles | Kind A benefits from data-driven parametrization; Kind B benefits from pytest expressiveness |
| Directory structure | Flat `tests/regression/` | Simple, split files by pipeline when they grow |
| Scenario format | v2 JSON (from unified-scenario-runner-design.md) | Auto-detect legacy formats, normalize to v2 |

## Scope

### In scope (deterministic)

**Kind A — Extraction (JSON-parametrized):**
- All 60+ existing doctor_sim and patient_sim scenarios
- Fact presence/absence, field routing, recall thresholds
- Forbidden fact checks (hallucination guard)
- Generic assertions (DB row counts, record existence)

**Kind B — Workflow (pytest functions):**

| Test | What It Asserts |
|------|-----------------|
| `test_cancel` | session status=abandoned, records=0 |
| `test_resume` | collected fields preserved after GET session |
| `test_confirm_empty_rejected` | HTTP 400 when no collected data |
| `test_confirm_double_rejected` | HTTP 400 on second confirm |
| `test_deferred_patient_creation` | patient row created at confirm time |
| `test_confirm_minimal_pending` | status=pending_review with only CC+PI |
| `test_confirm_complete` | status=completed with all 13 clinical fields |
| `test_duplicate_message` | same text twice → no double extraction |
| `test_5_turn_incremental` | 5 turns each adding fields → all merged |
| `test_carry_forward_confirm` | history field injected into collected |
| `test_carry_forward_dismiss` | history field NOT injected |
| `test_auto_task_generation` | orders_followup → doctor_tasks row created |
| `test_empty_input` | HTTP 400 or non-crash response |
| `test_query_task_empty` | non-empty reply when no tasks |
| `test_patient_self_contradict` | later answer overwrites earlier in DB |
| `test_patient_checkup_only` | valid record with minimal fields |

### Out of scope (non-deterministic — deferred)

- Patient triage classification (LLM-dependent)
- Diagnosis generation (LLM-dependent)
- Vision OCR image tests (output varies)
- Natural language completion signals ("我说完了", "就这些了")
- Off-topic handling, mixed intent routing
- LLM reply quality (keyword checks on free-text responses)
- Non-Chinese input routing

## File Structure

```
tests/regression/
  __init__.py
  conftest.py           # fixtures: server_url, db_path, cleanup
  matchers.py           # deterministic matcher library
  normalizer.py         # text normalization + alias tables
  loader.py             # auto-detect format, normalize to ScenarioSpec
  models.py             # ScenarioSpec, FactRule, MatchResult, ScenarioResult
  helpers.py            # API call wrappers + DB helpers
  test_extraction.py    # Kind A: parametrized from JSON scenarios
  test_doctor_interview.py  # Kind B: session lifecycle, confirm states
```

When Kind B grows beyond ~30 tests in one file, split by pipeline:
```
  test_doctor_interview.py   → session lifecycle, confirm, cancel, resume
  test_doctor_chat.py        → routing edge cases (empty input, etc.)
  test_carry_forward.py      → carry-forward specific
  test_patient_interview.py  → patient workflow tests
```

## Shared Layer (6 files)

### conftest.py

```python
import os, pytest

SERVER = os.environ.get("INTEGRATION_SERVER_URL", "http://127.0.0.1:8001")
DB_PATH = ...  # resolve from project root

skip_guard = pytest.mark.skipif(
    os.environ.get("RUN_REGRESSION") != "1",
    reason="Set RUN_REGRESSION=1 to run regression tests",
)

@pytest.fixture(scope="session", autouse=True)
def _check_server():
    """Fail fast if server is not running."""
    import httpx
    try:
        httpx.get(f"{SERVER}/docs", timeout=5)
    except httpx.ConnectError:
        pytest.skip(f"Server not reachable at {SERVER}")

@pytest.fixture
def server_url():
    return SERVER

@pytest.fixture
def db_path():
    return DB_PATH

@pytest.fixture
def cleanup(db_path):
    """Track doctor_ids, delete all related rows on teardown."""
    c = Cleanup(db_path)
    yield c
    c.teardown()

class Cleanup:
    TABLES = [
        "patient_auth", "interview_sessions", "medical_records",
        "doctor_tasks", "doctor_chat_log", "doctor_knowledge_items",
        "patients", "doctors",
    ]

    def __init__(self, db_path):
        self.db_path = db_path
        self.doctor_ids = []

    def make_doctor_id(self, label: str) -> str:
        did = f"reg_{label}_{uuid4().hex[:6]}"
        self.doctor_ids.append(did)
        return did

    def track(self, doctor_id: str):
        self.doctor_ids.append(doctor_id)

    def teardown(self):
        # delete all rows for tracked doctor_ids
        ...
```

### matchers.py

Two categories:

**Generic matchers** — reusable for any assertion:
```python
def eq(actual, expected) -> MatchResult
def not_empty(actual) -> MatchResult
def empty(actual) -> MatchResult
def contains(actual, text) -> MatchResult
def contains_any(actual, texts) -> MatchResult
def not_contains_any(actual, texts) -> MatchResult
def regex(actual, pattern) -> MatchResult
def min_val(actual, n) -> MatchResult
def max_val(actual, n) -> MatchResult
def count_eq(actual, n) -> MatchResult
```

**Clinical matchers** — extraction-specific:
```python
def fact_present(text, aliases, record_fields) -> MatchResult
    # normalize text + aliases, search across all field values

def fact_in_field(text, allowed_fields, aliases, record_fields) -> MatchResult
    # fact_present + verify it's in the right field

def forbidden_absent(text, record_fields) -> MatchResult
    # text does NOT appear in any field

def numeric_preserved(token, record_fields) -> MatchResult
    # specific number/unit appears unmodified

def duplicate_absent(field_text) -> MatchResult
    # no repeated clause segments (>80% similarity)

def negation_present(text, record_fields) -> MatchResult
    # "无"/"否认"/"未见" appears for expected negation

def brand_generic_match(brand, generic, record_fields) -> MatchResult
    # either brand name or generic name is acceptable
```

All matchers return `MatchResult(passed: bool, detail: str)` — never raise.

### normalizer.py

```python
def normalize(text: str) -> str:
    """NFKC → whitespace collapse → lowercase Latin → Chinese punctuation."""

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

def expand_aliases(text: str, aliases: list[str]) -> list[str]:
    """Return all normalized forms: original + aliases + brand/generic + abbreviation."""
```

### helpers.py

API wrappers — all synchronous `httpx.post()`, matching existing test patterns.

**Content-type note:** The interview endpoints (`/turn`, `/confirm`, `/cancel`) use
`Form(...)` parameters — helpers must POST with `data=` (form-encoded), not `json=`.
The carry-forward endpoint uses a JSON body (`CarryForwardConfirmRequest`).
The chat endpoint also uses JSON body (`ChatInput`).

```python
# Form-encoded endpoints (data=)
def interview_turn(server_url, text, session_id=None, doctor_id=None) -> dict
def interview_confirm(server_url, session_id, doctor_id) -> tuple[int, dict]
def interview_cancel(server_url, session_id, doctor_id) -> dict

# JSON body endpoints (json=)
def carry_forward_confirm(server_url, session_id, doctor_id, field, action) -> dict
def chat(server_url, text, doctor_id) -> dict

# GET endpoint
def get_session(server_url, session_id, doctor_id) -> dict
```

`interview_confirm` returns `tuple[int, dict]` (status_code + body) because Kind B
tests need to assert HTTP 400 on error cases. Other helpers raise on non-2xx since
their callers don't need the status code.

DB helpers (synchronous sqlite3, matching existing patterns):
```python
def db_count(db_path, doctor_id, table) -> int
def db_patient(db_path, doctor_id, name) -> Optional[dict]
def db_record_fields(db_path, doctor_id) -> dict   # latest record, 13 clinical columns (see below)
def db_session_status(db_path, session_id) -> Optional[str]
def db_task_count(db_path, doctor_id) -> int
```

**13 clinical columns on MedicalRecordDB:**
chief_complaint, present_illness, past_history, allergy_history, personal_history,
marital_reproductive, family_history, physical_exam, specialist_exam, auxiliary_exam,
diagnosis, treatment_plan, orders_followup.
(`department` is a DB column but the interview confirm endpoint does not save it;
`content` is a text summary field, not a clinical extraction field.)

### models.py

```python
@dataclass
class FactRule:
    text: str
    allowed_fields: list[str]
    aliases: list[str] = field(default_factory=list)

@dataclass
class ForbiddenRule:
    text: str
    reason: str = ""

@dataclass
class ExtractionExpectations:
    facts: list[FactRule]
    forbidden: list[ForbiddenRule] = field(default_factory=list)
    field_rules: dict = field(default_factory=dict)  # field → {required: bool}
    thresholds: dict = field(default_factory=lambda: {"recall": 0.80})

@dataclass
class Assertion:
    target: str       # e.g. "record.exists", "db.patients.count"
    matcher: str       # e.g. "eq", "not_empty", "min"
    expected: Any = None

@dataclass
class TurnInput:
    actor: str           # "doctor" | "patient"
    text: str

@dataclass
class InputSpec:
    mode: str            # "doctor_interview" | "patient_interview"
    turns: list[TurnInput]

@dataclass
class ExecutionSpec:
    entrypoint: str      # "records.interview.turn" | "patient.interview.chat"
    auto_confirm: bool = True
    timeout_seconds: int = 60

@dataclass
class ExpectationsSpec:
    assertions: list[Assertion] = field(default_factory=list)
    extraction: Optional[ExtractionExpectations] = None

@dataclass
class PatientInfo:
    name: str
    gender: str
    age: int

@dataclass
class ScenarioSpec:
    id: str
    scenario_type: str   # "doctor_extraction" | "patient_extraction"
    title: str
    tags: list[str]
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
    failures: list[str]
    duration_ms: int
    record_snapshot: dict = field(default_factory=dict)
    fact_matches: dict = field(default_factory=dict)
```

### loader.py

```python
def load_scenarios(dirs: list[str]) -> list[ScenarioSpec]:
    """Load all JSON scenario files, auto-detect format, normalize to v2."""

def _detect_format(data: dict) -> str:
    """
    - Has 'chatlog' + 'expectations.expected_patient_name' → MVP format
    - Has 'turn_plan' + 'fact_catalog'/'facts' → D1-D8 format
    - Has 'schema_version: 2' → already v2
    """

def _normalize_mvp(data: dict) -> ScenarioSpec: ...
def _normalize_d1d8(data: dict) -> ScenarioSpec: ...
def _parse_v2(data: dict) -> ScenarioSpec: ...
```

## Kind A: test_extraction.py

Single parametrized function, ~40 lines of code. Handles all extraction scenarios:

1. Send turns via `interview_turn()`
2. Confirm via `interview_confirm()` (if `auto_confirm`)
3. Snapshot record fields from DB
4. Run generic assertions (record.exists, db counts)
5. Run fact matching (presence, field routing, forbidden)
6. Check recall threshold
7. Collect all failures, assert at end

Adding a scenario = adding a JSON file. Zero code changes.

**Note:** The separate `runner.py` from the earlier unified-scenario-runner-design is
absorbed into `test_extraction.py`. No standalone runner module is needed — the
parametrized test function IS the runner.

## Kind B: test_doctor_interview.py

Pytest functions grouped by concern:

```
TestSessionLifecycle
  test_cancel
  test_resume
  test_confirm_empty_rejected
  test_confirm_double_rejected
  test_deferred_patient_creation

TestConfirmStatus
  test_minimal_pending_review
  test_confirm_complete

TestEdgeCases
  test_duplicate_message
  test_5_turn_incremental
  test_empty_input

TestCarryForward
  test_carry_forward_confirm
  test_carry_forward_dismiss

TestAutoTasks
  test_auto_task_generation

TestPatientWorkflows
  test_patient_self_contradict
  test_patient_checkup_only

TestDoctorChat  (→ split to test_doctor_chat.py when file grows)
  test_query_task_empty
```

Each function is 5-15 lines using shared helpers. No JSON DSL.

## Execution Model

**Sync tests, sync helpers.** All test functions and helpers are synchronous:
- API calls use `httpx.Client` (blocking), not `httpx.AsyncClient`
- DB reads use `sqlite3` directly (not async SQLAlchemy)

This is safe because tests run in a separate process from the server. The server
uses async SQLAlchemy + SQLite WAL mode; the test process reads via synchronous
sqlite3. WAL mode allows concurrent readers, so no locking issues.

DB reads should include a small retry/delay after confirm calls, since the server's
async commit may not be flushed to disk by the time the test reads. A 0.5s sleep
after confirm is sufficient; no polling loop needed.

## Pytest Markers

Each test file sets its own `pytestmark` (conftest.py `pytestmark` does not propagate):

```python
# test_extraction.py
pytestmark = [pytest.mark.regression, pytest.mark.extraction]

# test_doctor_interview.py
pytestmark = [pytest.mark.regression, pytest.mark.workflow]
```

```bash
pytest -m regression                    # all regression (Kind A + Kind B)
pytest -m extraction                    # Kind A only
pytest -m workflow                      # Kind B only
pytest tests/regression/test_extraction.py -k "D1"   # specific scenario
pytest tests/regression/test_doctor_interview.py -k "cancel"  # specific workflow
```

## What This Replaces

| Current | Replaced by |
|---------|-------------|
| `test_e2e_fixtures.py` | `test_extraction.py` + `test_doctor_interview.py` |
| `scripts/doctor_sim/validator.py` (LLM judges) | `matchers.py` (deterministic) |
| `scripts/run_doctor_sim.py` (pass/fail) | `pytest -m regression` |

## What Stays

| Component | Status |
|-----------|--------|
| `scripts/run_doctor_sim.py` | Exploratory mode with HTML reports |
| `scripts/run_patient_sim.py` | Exploratory mode with HTML reports |
| LLM judges / NHC quality | Exploratory analysis, not CI gate |
| D9 interactive persona | Exploratory only (non-deterministic) |

## Implementation Phases

### Phase 1: Shared layer
`models.py`, `normalizer.py`, `matchers.py`, `helpers.py`, `conftest.py`

### Phase 2: Kind A extraction runner
`loader.py`, `test_extraction.py`
Verify against existing D1-D8 + MVP scenarios

### Phase 3: Kind B workflow tests
`test_doctor_interview.py` — 16 workflow tests

### Phase 4: Migrate scenario format
Convert D1-D8 to v2 format (add `allowed_fields`, `aliases`, `thresholds`)
Convert MVP scenarios to v2 format

### Phase 5: CI integration
GitHub Actions workflow, artifact persistence

## Non-Deterministic Backlog (deferred)

These scenarios need an LLM-judge evaluation layer, to be designed separately:
- Patient triage classification
- Diagnosis generation
- Vision OCR
- Natural completion signals
- Off-topic handling
- Mixed intent routing
- LLM reply quality
- Non-Chinese input
