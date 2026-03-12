# Goal

Turn the 2026-03-12 component-by-component review into an execution plan that
closes the remaining critical gaps before the product is treated as stable at
the architecture level.

# Status

Current state as of 2026-03-12:

- Intent workflow core: mostly good
- Web workbench UI: not yet trustworthy because auth and hydration are weak
- WeChat core doctor flow: mostly good, but media and expired-draft edges are
  regressing
- Voice channel: not aligned with the draft-first safety model
- Adapter layer: improved, but still only partially represents the real runtime
  boundary

Validation from this review pass:

- Targeted critical-path suite: `321 passed, 7 failed`
- All 7 failures are in `tests/test_wechat_record_gates.py`
- Highest-risk auth issue was reproduced directly against the current code

# Why this plan exists

The existing MVP and architecture closure docs describe several gaps as already
closed. The current code and test state do not fully support that claim. This
plan is the current-state correction for the critical components that still need
work.

# Scope

- Web auth and session authority
- Web workbench state correctness
- WeChat media and pending-draft reliability
- Voice-path safety alignment
- Channel-boundary convergence
- Component-level regression coverage for the above

# Out of scope

- New product features
- Mini-program expansion
- Patient portal expansion
- Non-critical UI polish
- New transport channels

# Component assessment

## 1. Intent workflow core

Status: `Healthy`

What is good:

- Shared 5-layer workflow remains the right backbone
- Targeted workflow tests for classifier, binder, entities, planner, and gate
  passed in this review pass

What is still weak:

- Context assembly is not yet uniform; classifier still reads raw session state
  instead of consuming one authoritative turn-context object

Primary files:

- `services/intent_workflow/workflow.py`
- `services/intent_workflow/classifier.py`
- `services/ai/turn_context.py`

## 2. Web workbench auth and state

Status: `Critical`

What is wrong:

- Workbench endpoints ignore the resolved auth principal and continue using the
  raw query `doctor_id`
- Workbench context and pending-draft APIs read in-memory session state without
  hydration

Primary files:

- `routers/ui/__init__.py`
- `routers/ui/_utils.py`
- `services/session.py`
- `tests/test_auth_boundary.py`
- `tests/test_ui_router.py`
- `tests/test_working_context.py`

## 3. Web doctor flow convergence

Status: `Needs closure`

What is wrong:

- The web router still dispatches through legacy router-local handlers instead
  of the shared domain handler layer in several paths
- Architecture docs and progress framing overstate how complete the unification
  is

Primary files:

- `routers/records.py`
- `routers/records_intent_handlers.py`
- `services/domain/intent_handlers/`

## 4. WeChat doctor flow

Status: `Mixed`

What is good:

- Core doctor-message workflow is mostly serviceable
- Adapter-level unit coverage for formatting/history is in place

What is wrong:

- Media wrapper paths are currently the main regression cluster
- Expired pending-draft fallback can collapse into live LLM/provider-config
  failures instead of deterministic recovery behavior

Primary files:

- `routers/wechat.py`
- `routers/wechat_flows.py`
- `services/wechat/wechat_media_pipeline.py`
- `tests/test_wechat_record_gates.py`
- `tests/test_wechat_routes.py`

## 5. Voice channel

Status: `Critical`

What is wrong:

- Voice still uses direct routing and immediate record save behavior
- That bypasses the draft-first confirmation model used by the main doctor
  channels

Primary files:

- `routers/voice.py`
- `services/intent_workflow/`
- `services/domain/intent_handlers/`
- `tests/test_voice_router.py`

## 6. Adapter layer

Status: `Partial`

What is good:

- Adapters now exist and some unit behavior is covered

What is wrong:

- The adapter layer is still not the single runtime boundary
- Some runtime paths still bypass it directly

Primary files:

- `services/domain/message.py`
- `services/domain/adapters/web_adapter.py`
- `services/domain/adapters/wechat_adapter.py`
- `routers/records.py`
- `routers/wechat.py`

# Workstreams

## Workstream 1. Fix workbench doctor-scope authority

Priority: `P0`

Problem:

- `_resolve_ui_doctor_id()` is called, but the resolved value is not used
  consistently when reading or mutating workbench state

Implementation steps:

1. Audit all workbench endpoints that call `_resolve_ui_doctor_id()`.
2. Replace every downstream use of raw query `doctor_id` with the resolved
   principal.
3. Cover working-context, pending-record read, confirm, and abandon.
4. Add explicit route-level tests for mismatched token/query doctor IDs.

Exit criteria:

- Doctor A cannot read or mutate Doctor B workbench state by passing a spoofed
  `doctor_id`
- Regressions fail in route-level tests

## Workstream 2. Make workbench context authoritative

Priority: `P0`

Problem:

- Workbench state depends on in-memory session state and is not reliable on cold
  load, restart, or second-device access

Implementation steps:

1. Hydrate session state before workbench context and pending-draft reads.
2. Reuse persisted session recovery already available in the session service.
3. Add cold-session coverage for current patient and pending draft recovery.
4. Add expired-draft cleanup coverage.

Exit criteria:

- First page load matches persisted workflow state
- Restart or second-device load does not silently drop visible workbench context

## Workstream 3. Stabilize WeChat media and expired-draft recovery

Priority: `P0`

Problem:

- The current regression cluster is concentrated in media wrappers and
  expired-draft fallback behavior

Implementation steps:

1. Align `wechat_flows` media wrappers with the intended dependency injection
   contract so they remain testable and do not fall through to live config.
2. Make expired pending-draft recovery deterministic and safe when provider
   config is missing.
3. Re-run the full WeChat gate/router suite after the fix.

Exit criteria:

- `tests/test_wechat_record_gates.py` is green
- Expired pending-draft replies fail gracefully without provider-dependent
  behavior

## Workstream 4. Align voice with draft-first semantics

Priority: `P0`

Problem:

- Voice still defines a weaker write path than Web and WeChat

Implementation steps:

1. Route voice note handling through the shared workflow and shared handlers.
2. Make normal add-record voice flows create pending drafts.
3. Preserve direct-save behavior only for explicitly accepted emergency cases.
4. Rewrite voice tests to encode the intended safety model, not the legacy one.

Exit criteria:

- Voice no longer writes normal records directly
- Voice tests validate pending-draft behavior and emergency exceptions

## Workstream 5. Close the web handler convergence gap

Priority: `P1`

Problem:

- Web routing still relies on legacy router-local handlers in important paths

Implementation steps:

1. Audit current web dispatch branches against the shared handler layer.
2. Move remaining supported intents onto `services/domain/intent_handlers/`.
3. Remove or clearly isolate duplicated legacy logic.

Exit criteria:

- Web doctor flow uses one handler model for supported intents
- The architecture docs no longer overstate convergence

## Workstream 6. Finish the component-level regression net

Priority: `P1`

Problem:

- Coverage exists, but the new workbench endpoints and some channel-edge cases
  are still under-tested

Implementation steps:

1. Add route-level auth-boundary tests for workbench endpoints.
2. Add workbench cold-session and hydration tests.
3. Add voice-path safety tests for draft creation and emergency bypass.
4. Keep WeChat gate/media tests as release-gating coverage.

Exit criteria:

- Every P0 workstream is protected by a focused regression test
- Critical-channel edge cases are no longer relying on manual spot checks

# Execution order

1. Workstream 1: workbench doctor-scope authority
2. Workstream 2: workbench context authority
3. Workstream 3: WeChat media and expired-draft stabilization
4. Workstream 4: voice draft-first alignment
5. Workstream 5: web handler convergence
6. Workstream 6: regression-net completion

# Test plan

Target suites for closure:

- `tests/test_auth_boundary.py`
- `tests/test_ui_router.py`
- `tests/test_working_context.py`
- `tests/test_wechat_record_gates.py`
- `tests/test_wechat_routes.py`
- `tests/test_voice_router.py`
- `tests/test_channel_adapters.py`
- focused workflow suites under `tests/test_intent_workflow_*.py`

Recommended validation command:

```bash
.venv/bin/pytest -q \
  tests/test_auth_boundary.py \
  tests/test_working_context.py \
  tests/test_ui_router.py \
  tests/test_voice_router.py \
  tests/test_intent_workflow_classifier.py \
  tests/test_intent_workflow_binder.py \
  tests/test_intent_workflow_entities.py \
  tests/test_intent_workflow_planner.py \
  tests/test_intent_workflow_gate.py \
  tests/test_records_router.py \
  tests/test_records_chat.py \
  tests/test_wechat_intent.py \
  tests/test_wechat_record_gates.py \
  tests/test_wechat_routes.py \
  tests/test_channel_adapters.py
```

# Peer-review lenses

Architecture review:

- The backbone is correct, but convergence claims still exceed implementation
  reality

Security review:

- Workbench doctor-scope enforcement is the highest-severity issue

Reliability review:

- WeChat media/error paths and expired-draft recovery are the current runtime
  regression cluster

Product review:

- Incorrect or stale workbench context will damage trust faster than missing UX
  polish

# Definition of done

This plan is complete only when all of the following are true:

1. Workbench endpoints are principal-scoped and hydration-backed.
2. WeChat gate/media tests pass without live config dependencies.
3. Voice follows the same draft-first model as the main doctor channels.
4. Remaining web handler divergence is either closed or explicitly documented.
5. The targeted critical-path suite is green.
