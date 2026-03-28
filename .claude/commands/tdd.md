# /tdd — Test-Driven Development Mode

Activate TDD for the current task. This **overrides** the default "DO NOT RUN TESTS"
policy in AGENTS.md for this session only. Other agents without /tdd are unaffected.

## Usage

- `/tdd` — activate TDD mode, then proceed with the user's next task
- `/tdd src/domain/records/structuring.py` — activate TDD focused on a specific module

## Step 1: Classify the Target Code

Read the files being modified and classify each as:

| Classification | Examples | Test approach |
|---------------|----------|---------------|
| **Deterministic** | `domain/records/`, `domain/patients/triage.py`, `domain/knowledge/`, `db/crud/`, parsers, validators, PDF export | **Full TDD** (red-green-refactor) |
| **LLM-dependent** | `agent/handle_turn.py`, `agent/session.py`, `agent/tools/`, prompt files | **Seam test** (mock LLM, assert side effects) or **scenario fixture** |
| **Frontend logic** | Zustand stores, form validation, conditional rendering | **Vitest TDD** (if vitest configured) |
| **Frontend presentational** | Pure MUI wrappers, layout components | **Skip** (use /qa instead) |

Tell the user:
```
TDD MODE ACTIVE
Target: [file/module]
Classification: [deterministic / LLM-dependent / frontend]
Test approach: [full TDD / seam test / scenario fixture]
Test file: [tests/core/test_xxx.py or tests/scenarios/fixtures/xxx.yaml]
```

## Step 2: Red-Green-Refactor Cycle

### For Deterministic Code (Full TDD)

**RED — Write Failing Test**

```bash
# Create or open the test file
# Write ONE minimal test for ONE behavior
```

Rules:
- One behavior per test
- Clear name describing the behavior
- Real code, no mocks unless I/O is unavoidable
- Use existing fixtures from `tests/core/conftest.py` (session_factory, db_session)

Run the test to verify it fails:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_xxx.py::test_name -x -v
```

Confirm:
- Test FAILS (not errors)
- Failure is because the feature is missing (not a typo or import error)

**GREEN — Minimal Implementation**

Write the simplest code that makes the test pass. Nothing more.

Run again:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_xxx.py::test_name -x -v
```

Confirm: test PASSES, no other tests broken.

**REFACTOR — Clean Up**

Only after green. Remove duplication, improve names, extract helpers.
Run tests again to confirm still green.

**Repeat** for next behavior.

### For LLM-Dependent Code (Seam Tests)

Don't test LLM output directly. Instead:

1. **Mock the LLM call** with `AsyncMock` / `patch`
2. **Assert side effects**: DB writes, tool calls, routing decisions, state changes
3. **Assert contracts**: correct prompt assembly, correct model called, correct response parsing

Example pattern:
```python
@patch("agent.session.structured_call")
async def test_create_record_writes_to_db(mock_llm, db_session):
    mock_llm.return_value = FakeExtractResult(chief_complaint="headache")
    result = await handle_turn("patient has headache", ...)
    # Assert the DB write happened, not the LLM output
    records = await list_records(db_session, doctor_id=1)
    assert len(records) == 1
    assert records[0].chief_complaint == "headache"
```

### For LLM Behavior Changes (Scenario Fixtures)

When changing prompts or routing, don't write unit tests. Instead:

1. Add a YAML fixture to `tests/scenarios/fixtures/`:
```yaml
name: "new_routing_case"
turns:
  - role: doctor
    text: "the triggering message"
    expect:
      intent: expected_intent
      # or: record_created, task_created, fields_present, etc.
```

2. Run scenario tests:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src .venv/bin/python -m pytest tests/scenarios/ -x -v
```

Or use `/sim` for full simulation coverage.

## Step 3: Medical Safety Assertions

For any code touching clinical data, add these assertion types:

**Clinical Invariants** (must always hold):
- Allergies are never dropped during record updates
- Negations are preserved ("no history of diabetes" stays negative)
- Patient identity never crosses (record A's data doesn't leak to record B)
- Red flags always surface in diagnosis output

**Must-Not Assertions** (safety guardrails):
- No fabricated vitals or lab values
- No invented diagnosis certainty
- No medication dose mutation without evidence in transcript
- No unsafe reassurance for red-flag symptoms

**Metamorphic Tests** (same input, different form):
- Reordered facts should produce same clinical classification
- OCR artifacts / abbreviations should not change extraction results
- Bilingual input (mixed Chinese/English) should extract correctly

## Step 4: Verify and Report

After completing the TDD cycle:

```
TDD SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━
Module: [target]
Tests written: N
Tests passing: N/N
Coverage: [files touched]

New test files:
  - tests/core/test_xxx.py (N tests)

Red-Green cycles completed: N
━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Rules

- **This skill overrides "DO NOT RUN TESTS"** — you MUST run tests during TDD
- **One behavior per test** — if a test name has "and", split it
- **Watch every test fail first** — never skip the RED step
- **Minimal code only** — don't over-engineer in the GREEN step
- **Use existing fixtures** — `session_factory`, `db_session` from conftest.py
- **No mocks for deterministic code** — only mock LLM/network/external I/O
- **Port 8001 only** — if tests need a running server, it must be 8001
- **Default LLM provider: groq** — for any test that does call an LLM
- **Chinese medical terms** — preserve abbreviations (STEMI, BNP, etc.) in test data
- **Commit after each green cycle** — small, focused commits
