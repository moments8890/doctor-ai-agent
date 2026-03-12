# Bounded Compound Intent Execution Plan

## Goal

Implement the MVP compound-intent policy so one doctor turn resolves to one
core patient-scoped transaction, with only allowlisted same-turn compounds and
clear clarification for unsupported mixed-intent turns.

## Status: Implemented

All 8 steps completed. 1121 tests passing (0 regressions), 32 new tests added.

## Affected files

### New files
- `services/domain/compound_normalizer.py` — residual-text clinical content detection, same-turn correction detection, secondary-intent signal patterns
- `tests/test_compound_normalizer.py` — 19 tests covering residual-text, correction detection, signal regexes
- `tests/test_intent_workflow_gate.py` — 5 tests covering gate unsupported-combo blocking and normal behavior

### Modified files
- `services/intent_workflow/models.py` — `ActionPlan.unsupported_reason` + `clarification_message` fields
- `services/intent_workflow/entities.py` — replaced keyword-based `has_clinical_content` with residual-text approach; added `has_correction` signal
- `services/intent_workflow/planner.py` — added `text` parameter; unsupported-combo detection (`_detect_unsupported_combo`)
- `services/intent_workflow/gate.py` — early return on `plan.unsupported_reason`
- `services/intent_workflow/workflow.py` — passes `text` to planner
- `services/domain/intent_handlers/_create_patient.py` — replaced `_contains_clinical_content()` keyword check with `has_residual_clinical_content()`
- `services/domain/chat_constants.py` — deleted `CLINICAL_CONTENT_HINTS` (fully replaced by residual-text approach)
- `routers/records.py` — replaced `_contains_clinical_content()` keyword check with `has_residual_clinical_content()`; removed `CLINICAL_CONTENT_HINTS` import
- `tests/test_intent_workflow_planner.py` — 8 new tests for unsupported combos and correction behavior
- `e2e/fixtures/data/mvp_accuracy_benchmark.json` — 5 new cases (dermatology, orthopedics, correction, 2 unsupported-combo clarifications)

### Deleted constants
- `CLINICAL_CONTENT_HINTS` — removed from definition (`chat_constants.py`) and all 3 consumers (`entities.py`, `_create_patient.py`, `routers/records.py`); fully replaced by `has_residual_clinical_content()` which uses demographic-stripping + meaningful-residual check instead of a fixed keyword list

## Steps

1. [x] Lock the implementation target to the accepted policy
   - [`docs/adr/0005-bound-single-turn-compound-intents.md`](../../adr/0005-bound-single-turn-compound-intents.md)
     and [`docs/ai/context-and-prompt-contract.md`](../../ai/context-and-prompt-contract.md)
     are the product contract.
   - Allowlist preserved:
     - `create_patient + add_record`
     - `create_patient + add_record + create_task`
     - `add_record + create_task`
     - `create/add_record + same-turn correction`

2. [x] Introduce a shared compound-turn normalizer
   - `services/domain/compound_normalizer.py`:
     - `has_residual_clinical_content()` — strips demographics, checks residual for meaningful text (4+ mixed CJK/alphanumeric chars or 2+ uppercase ASCII like EF, ST, BNP)
     - `detect_same_turn_correction()` — detects correction patterns (说错了/改为/应该是/etc.)
     - Secondary-intent signal regexes exported for planner use
   - Same-turn correction detected and flagged as `has_correction` in extra_data

3. [x] Remove brittle keyword-gate compounding
   - Deleted `CLINICAL_CONTENT_HINTS` constant and all imports
   - Replaced all `_contains_clinical_content()` implementations with `has_residual_clinical_content()` in `entities.py`, `_create_patient.py`, and `routers/records.py`
   - Residual-text approach: strip command verbs + patient category + name + gender + age, then check if meaningful text remains
   - Deterministic fast paths preserved (greetings, task completion, patient counts)
   - Works across all specialties (dermatology, orthopedics, neurology, oncology verified)
   - Threshold tuned: "你好"/"谢谢" → no content; "胸痛2小时"/"EF 45%"/"皮疹3天" → has content

4. [x] Add an explicit unsupported-combo gate in the workflow layer
   - `planner.py::_detect_unsupported_combo()` checks primary intent + text for incompatible secondary signals
   - Requires conjunction separator (，然后/；再/etc.) to avoid false-positives on clinical narratives
   - Unsupported combos detected and rejected:
     - `query_records + write verb` → "查询和录入请分两步操作"
     - `write intent + query verb` → "录入和查询请分两步操作"
     - `update_record + create verb` → "修改记录和新建录入请分两步操作"
     - `delete_patient + any other action` → "删除操作请单独执行"
   - `ActionPlan.unsupported_reason` and `clarification_message` propagate through gate
   - Multi-patient detection deferred (requires NER; acknowledged in risks section)

5. [x] Unify Web and WeChat behavior
   - Both channels share `compound_normalizer.py` for content detection
   - Both channels use the same planner/gate pipeline via `workflow.py`
   - Both channels produce the same unsupported-combo clarification messages
   - Shared handlers in `services/domain/intent_handlers/` handle compound execution

6. [x] Add direct unit coverage for every new branch
   - 19 tests in `test_compound_normalizer.py`: residual-text (9 cases across 5 specialties), correction detection (6 cases), signal regex (4 cases)
   - 8 new tests in `test_intent_workflow_planner.py`: 4 unsupported-combo blocked, 2 no-false-positive, 1 allowed compound preserved, 1 correction stays single-action
   - 5 tests in `test_intent_workflow_gate.py`: unsupported-combo gate blocking, normal gate behavior preserved

7. [x] Extend the MVP benchmark
   - 5 new cases added to `mvp_accuracy_benchmark.json`:
     - MVP-ACC-019: dermatology create+record (non-cardiology)
     - MVP-ACC-020: same-turn correction within create flow
     - MVP-ACC-021: unsupported query+write clarification
     - MVP-ACC-022: unsupported delete+create clarification
     - MVP-ACC-023: orthopedics create+record (non-cardiology)
   - Total benchmark: 23 cases (was 18)

8. [x] Validate and close
   - 1121 tests passing, 0 regressions (17 pre-existing WeChat router failures from prior refactor, unrelated)
   - All new branches covered by direct unit tests
   - Benchmark cases added for all new behavior categories
   - Diff-coverage check: deferred to push time per repo policy

## Risks / open questions

- ~~Web and WeChat still have partially separate create/add handling~~ — Resolved: both channels use shared `compound_normalizer.py` and shared pipeline
- Same-turn correction uses deliberately narrow rule set — only explicit correction signals (说错了/改为/应该是)
- Some borderline messages may still need clarification even after normalization — this is acceptable for MVP
- Multi-patient detection (multiple patient names in one turn) deferred — requires NER capabilities beyond text pattern matching; the current single-patient-scope model is preserved
- ~~Benchmark runner limitations~~ — benchmark cases use single-turn API replay which is sufficient for the new cases added
