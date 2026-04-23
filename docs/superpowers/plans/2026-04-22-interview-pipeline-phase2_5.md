# Interview Pipeline Extensibility — Phase 2.5 (Turn Loop Integration)

**Goal:** Inline the turn loop from `interview_turn.py::_interview_turn_inner` into `engine.next_turn`. Stop forwarding. Medical-specific logic moves into `GeneralMedicalExtractor`; engine owns state-machine + retry. Route `/turn` endpoints through the engine. Convert `interview_turn.py` to a deprecation shim.

**Decomposition principle (from codex consult):** engine owns workflow orchestration + invariants + retry/observability; extractor owns prompt shape, medical semantics, and reply-style UX policy.

**Extractor protocol extensions:**
- `prompt_partial(session_state, completeness_state, phase, mode) -> list[dict]` — takes structured state (not opaque kwargs), builds messages list including medical patient_context + conversation window policy.
- `extract_metadata(extracted) -> dict[str, str]` — pulls template-specific metadata (e.g. patient_name/gender/age).
- `post_process_reply(reply, collected, mode) -> str` — template-specific reply polishing (e.g. soften blocking language when can_complete).

**Engine responsibilities:**
- Session lock (per-session asyncio.Lock, CAP=500).
- Load session, guard on status, append user message, turn count increment.
- Safety cap (MAX_TURNS from template.config).
- Call extractor.prompt_partial with structured state.
- LLM call with 3-attempt exponential backoff retry (engine owns retry policy).
- Call extractor.merge, extractor.extract_metadata, extractor.post_process_reply in order.
- Status transition (reviewing when can_complete AND requires_doctor_review).
- Save session, return TurnResult.

**Preconditions:** Phase 3 ended at `cb1e3a7c`, 505/505 tests pass.

## Tasks

### Task 1: Extend FieldExtractor protocol + update contract

Add `extract_metadata` and `post_process_reply` to the Protocol. Change `prompt_partial` signature. Update all existing implementers.

### Task 2: Implement new methods on GeneralMedicalExtractor

- `prompt_partial(session_state, completeness_state, phase, mode)`: absorbs the ~90 lines of patient_context building from `_call_interview_llm` — flat-text format with missing-field hints from `FIELD_META` (now derived from `MEDICAL_FIELDS`), conversation window (last 6 turns + early summary), patient_info fetch.
- `extract_metadata(extracted)`: returns `{"patient_name": ..., "patient_gender": ..., "patient_age": ...}` popping those keys from the extracted dict. Non-medical extractors return `{}`.
- `post_process_reply(reply, collected, mode)`: applies the softening rewrite when `can_complete`.

### Task 3: Update FormSatisfactionExtractor with the new methods

- `extract_metadata` → always `{}`.
- `post_process_reply` → returns reply unchanged.
- `prompt_partial` → upgrade to new signature (already builds its own messages).

### Task 4: Inline the turn loop into InterviewEngine.next_turn

Replace the forwarder with a real orchestrator. Uses the extractor's new methods. Engine owns retry.

### Task 5: Route `/turn` endpoints through engine.next_turn

Convert `TurnResult` back to the legacy `InterviewResponse` shape at the endpoint.

### Task 6: Convert interview_turn.py to deprecation shim

`interview_turn()` becomes a wrapper calling `engine.next_turn()`. `_call_interview_llm` and `_interview_turn_inner` are deleted.

### Task 7: Regression sweep

Full suite. Aim for 505+ passed, zero new failures.
