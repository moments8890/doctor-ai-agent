# Pre-Presentation Readiness (2026-03-04)

## What was fixed in this pass

1. AppConfig deterministic defaults
- Fixed `AppConfig.from_env({})` to stop falling back to process env.
- File: `utils/app_config.py`

2. Agent robustness for Ollama tool-call variance
- Added parser for embedded tool-call payloads returned in `message.content`.
- Added conservative fallback behavior for no-tool-call responses.
- File: `services/agent.py`

3. Integration environment alignment
- Integration tests now load shared env first (same behavior as runtime).
- File: `tests/integration/conftest.py`

4. WeChat unknown-intent safety
- Guarded unknown-intent path so it never returns `None` even if lookup result is empty.
- File: `routers/wechat.py`

5. Deterministic clinical-note routing in `/api/records/chat`
- Added deterministic extraction of leading patient name for clinical dictation.
- Added routing rescue: if note is clearly clinical and has leading name, force `add_record`.
- File: `routers/records.py`

## Validation results

- Unit tests: `507 passed`, coverage `87.86%` (gate >= 81% passed)
- Integration tests (`tests/integration/test_text_pipeline.py`): `7 passed`

## Remaining known risks before user demo

1. Diff coverage gate currently fails in working tree
- `diff-cover` reported `69%` vs required `81%`.
- Cause: many unrelated modified files already present in workspace and not part of this pass.

2. Deprecation warnings
- `datetime.utcnow()` warnings are widespread; not blocking, but should be cleaned for production hardening.

3. Roadmap expectation management
- Knowledge augmentation modules exist, but full online orchestration into main user flow is still partial.
- Present as "in progress" rather than "fully shipped".

## Demo flow (recommended)

1. New clinical note with explicit name (text)
2. Missing-name two-turn follow-up
3. Emergency note (STEMI-like)
4. Query patient history by name
5. List patients
6. Manage view: risk/timeline/task visibility

## Suggested presentation language

- "Phase 1 and core Phase 2 workflows are production-like and verified by unit + integration suites."
- "Phase 3 knowledge enhancement is implemented at module level and entering workflow integration."
