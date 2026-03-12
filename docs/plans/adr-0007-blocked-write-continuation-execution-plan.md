# Goal

Implement [ADR 0007](../adr/0007-stateful-blocked-write-continuations.md)
with the smallest safe rollout:

- blocked writes become authoritative workflow state
- next-turn continuation is resolved deterministically
- routing remains responsible for control flow
- note generation is unified behind the structuring path for write intents

# Status

`In Progress` — Phase 1 complete as of 2026-03-12.

This is an active implementation plan for the ADR, not a dated review.

# Why this plan exists

The current code still handles blocked write continuation through a mix of:

- ad hoc `followup_name` plumbing
- recent-history heuristics
- router-time clinical field extraction

That is workable, but not precise enough for the MVP hero loop.

This plan converts that behavior into one explicit workflow model that can be
shared across Web, WeChat, and voice.

# Scope

- blocked `add_record` continuation when patient name is missing
- minimal stateful precheck before normal routing
- deterministic name-only and name-plus-supplement recovery
- single note-generation path for `add_record`
- eventual cross-channel parity for Web, WeChat, and voice

# Out of scope

- multi-patient blocked writes
- arbitrary missing-field recovery beyond MVP needs
- broad prompt redesign
- full removal of all deterministic fast routes in one patch
- specialty-specific workflow redesign

# Success criteria

1. A doctor can send clinical text without a patient name, receive a name
   clarification, then reply with only the patient name and still get the
   correct pending draft.
2. A doctor can reply with `name + supplement` and the system resumes the same
   blocked write instead of treating it as a fresh standalone turn.
3. `add_record` no longer depends on router-produced `structured_fields` as a
   final saved-note shortcut.
4. Web, WeChat, and voice use one shared blocked-write continuation rule.
5. The deterministic precheck stays narrow and does not become a broad semantic
   rule engine.

# Affected files

Core session and workflow:

- `services/session.py` — ✅ Phase 1 done (BlockedWriteContext, session helpers)
- `services/ai/turn_context.py` — Phase 2+
- `services/intent_workflow/workflow.py` — no changes needed (precheck runs before workflow)
- `services/intent_workflow/entities.py` — Phase 3 (remove followup_name)
- `services/intent_workflow/precheck.py` — ✅ Phase 1 done (new file)

Name parsing and record assembly:

- `services/domain/name_utils.py` — ✅ Phase 1 done (name_with_supplement, is_blocked_write_cancel)
- `services/domain/record_ops.py` — Phase 4
- `services/domain/intent_handlers/_add_record.py` — Phase 4

Routing surfaces:

- `routers/records.py` — ✅ Phase 1 done (precheck wiring, gate context storage)
- `routers/wechat.py` — Phase 2
- `routers/voice.py` — Phase 2

LLM routing and tool schema:

- `services/ai/agent.py` — Phase 5
- `services/ai/agent_tools.py` — Phase 5
- `services/ai/fast_router/_router.py` — Phase 5

Persistence:

- `db/models/doctor.py` — Phase 2
- `db/crud/doctor.py` — Phase 2
- optional migration if deployed databases need the new persisted session field

Tests:

- `tests/test_blocked_write_precheck.py` — ✅ Phase 1 done (29 tests)
- `tests/test_records_router.py` — no changes needed
- `tests/test_wechat_routes.py` — Phase 2
- `tests/test_voice_router.py` — Phase 2
- `tests/test_handler_add_record.py` — Phase 4

# Execution phases

## Phase 1. Web-only blocked-write continuation without schema changes

Purpose:

- prove the workflow with minimal blast radius

Implementation steps:

1. [x] Add an in-memory blocked-write context to `DoctorSession` in
   `services/session.py`. — `BlockedWriteContext` dataclass + `blocked_write`
   field on `DoctorSession`.
2. [x] Add session helpers:
   - `get_blocked_write_context()` — with 300s TTL auto-expiry
   - `set_blocked_write_context()` — stores intent, clinical text, history
   - `clear_blocked_write_context()` — explicit clear on success/cancel
   - Expiry handled inline by `get_blocked_write_context()` (no separate helper
     needed).
3. [x] Add a shared precheck module in `services/intent_workflow/precheck.py`.
   — `precheck_blocked_write()` returns `BlockedWriteContinuation` on match,
   `is_blocked_write_cancel_reply()` for cancel detection.
4. [x] Add a deterministic parser in `services/domain/name_utils.py` for:
   - bare patient name — existing `name_only_text()`
   - leading patient name with trailing supplement — new `name_with_supplement()`
   - cancel detection — new `is_blocked_write_cancel()`
5. [x] Wire the precheck into `routers/records.py` before `workflow_run()`. —
   Cancel check returns "好的，已取消。"; continuation skips routing entirely
   and dispatches to `handle_add_record` with stored clinical text.
6. [x] When `add_record` is blocked for missing patient name, store
   blocked-write context before returning the clarification message. — Stored
   in `chat_core` after gate check when `reason == "no_patient_name"` and
   `intent == add_record`.
7. [x] When the resumed write succeeds or is explicitly canceled, clear the
   blocked context. — Cleared in precheck on success, cancel, or unrelated
   message.

Exit criteria:

- [x] Web supports:
  - [x] clinical text -> ask for patient name
  - [x] bare-name reply -> resume blocked write
  - [x] name + supplement -> resume blocked write
  - [x] cancel -> clear blocked state
- [x] no DB migration required for Phase 1
- [x] 29 new tests pass in `tests/test_blocked_write_precheck.py`
- [x] 1897 total tests pass, 0 regressions

## Phase 2. Persist blocked-write context and share it across channels

Purpose:

- make the workflow durable across restart, multi-device use, and all doctor
  surfaces

Implementation steps:

1. Add a nullable `blocked_write_json` field to `DoctorSessionState` in
   `db/models/doctor.py`.
2. Extend `get_doctor_session_state()` and `upsert_doctor_session_state()` in
   `db/crud/doctor.py` to restore and persist blocked-write state.
3. Extend hydration and persistence in `services/session.py`.
4. Wire the same shared precheck into:
   - `routers/wechat.py`
   - `routers/voice.py`
5. Remove router-local continuation handling that becomes redundant.

Exit criteria:

- Web, WeChat, and voice share one continuation rule
- blocked-write context survives restart if session persistence is enabled

## Phase 3. Replace ad hoc follow-up-name plumbing

Purpose:

- remove the current continuation behavior that depends on history heuristics

Implementation steps:

1. Delete Web router follow-up override in `routers/records.py`.
2. Delete voice router follow-up override in `routers/voice.py`.
3. Remove `followup_name` priority handling from
   `services/intent_workflow/entities.py`.
4. Keep only the shared precheck-based continuation path.

Exit criteria:

- no doctor-facing router needs a special `followup_name` override
- continuation behavior is driven by blocked-write state, not ad hoc history

## Phase 4. Unify note generation for `add_record`

Purpose:

- make note content deterministic regardless of the router branch

Implementation steps:

1. Remove the `structured_fields` saved-note shortcut from
   `services/domain/intent_handlers/_add_record.py`.
2. Route `add_record` through `services/domain/record_ops.py` as the single
   note assembly path.
3. Treat router-produced clinical fields, if still present temporarily, as
   hints only, not final note content.
4. Re-check whether `update_record` should stay field-oriented or also be moved
   to the same final structuring path.

Exit criteria:

- `add_record` uses one final note-generation policy
- the same message does not save different note shapes based on router output

## Phase 5. Shrink routing schema and deterministic semantic routing

Purpose:

- align routing with its intended job: control flow, not note generation

Implementation steps:

1. Remove the 8 clinical note fields from the routing tool schema in
   `services/ai/agent_tools.py`.
2. Remove router-time `structured_fields` extraction in `services/ai/agent.py`.
3. Trim `fast_route` in `services/ai/fast_router/_router.py` to exact low-risk
   operational commands and explicit workflow-state transitions only.
4. Keep benchmark-backed deterministic commands where precision is clearly
   higher than the LLM.

Exit criteria:

- routing LLM produces intent and coarse entities only
- note generation belongs to the structuring path
- deterministic routing stays intentionally narrow

# Test plan

Phase 1: **DONE**

- [x] new `tests/test_blocked_write_precheck.py` (29 tests)
- existing `tests/test_records_router.py` — no changes needed (no regressions)

Covered cases:

- [x] blocked `add_record` stores continuation state
- [x] bare-name continuation resumes the write
- [x] `name + supplement` continuation merges correctly
- [x] explicit cancel clears blocked state
- [x] unrelated next turn clears stale context (does not silently persist)
- [x] expired context returns None
- [x] history snapshot preserved through continuation
- [x] cancel without active context is no-op

Phase 2:

- update `tests/test_wechat_routes.py`
- update `tests/test_voice_router.py`

Required cases:

- Web / WeChat / voice all resolve the same blocked-write continuation
- persisted blocked-write state restores correctly after hydration

Phase 3-5:

- update `tests/test_handler_add_record.py`
- update `tests/test_agent.py`
- update `tests/test_intent_workflow_classifier.py`

Required cases:

- `add_record` no longer uses router `structured_fields` as final note content
- routing still classifies core commands correctly after schema reduction
- the hero-loop regression suite stays green

# Risks and open questions

## 1. Persistence rollout

Phase 1 intentionally avoids a schema change. Phase 2 adds persistence only
after the blocked-write workflow is proven on Web.

Answered:

- Phase 1 ships with in-memory blocked state (no DB migration). Phase 2 adds
  persistence. This is acceptable for MVP because blocked writes have a 5-minute
  TTL — restart loss is low-impact.

## 2. `update_record` treatment

`add_record` clearly belongs on the unified structuring path. `update_record`
may remain a field-oriented correction flow if that proves more precise.

Open question:

- should `update_record` reuse the same final structuring path, or remain a
  separate correction-specific write path?

## 3. Fast-route shrink scope

The repo should keep a narrow deterministic layer. The exact retained set
should be benchmark-backed rather than decided by taste.

Open question:

- which explicit query/list/help commands still outperform LLM routing enough
  to remain deterministic?

# Rollout order

1. Phase 1: Web-only in-memory blocked-write continuation
2. Phase 2: persistence + cross-channel parity
3. Phase 3: remove `followup_name` plumbing
4. Phase 4: unify `add_record` note generation
5. Phase 5: shrink routing schema and semantic fast routing

# Definition of done

This plan is complete only when:

1. blocked writes are explicit workflow state, not history inference
2. bare-name continuation works deterministically across the supported channels
3. `add_record` has one final note-generation path
4. routing no longer acts as an alternate final-note generator
5. the targeted regression suites and hero-loop benchmark remain green
