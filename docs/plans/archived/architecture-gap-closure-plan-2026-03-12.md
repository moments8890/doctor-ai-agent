# Goal

Turn the 2026-03-12 architecture re-review into one closure plan that fixes the
remaining high-risk gaps before the MVP is treated as fully closed.

# Status

- **All five workstreams complete** as of 2026-03-12.
- This plan was a follow-up to the shipped MVP hero-loop work.
- It does not replace the original MVP execution plan; it closed the gaps that
  remained after implementation and the March 12 re-review.

## Workstream completion summary

| WS | Title | Status | Notes |
|---|---|---|---|
| 1 | Doctor-scope authority | **Done** | 4 workbench endpoints use resolved_id; auth-boundary tests added |
| 2 | Workbench context hydration | **Done** | `hydrate_session_state` called before `get_session` in context endpoints |
| 3 | Voice safety alignment | **Done** | `voice.py /chat` wired through shared 5-layer workflow (draft-first model) |
| 4 | Adapter convergence | **Done** | `parse_inbound` and `format_reply` wired in production; `send_reply`/`send_notification` documented as deferred stubs |
| 5 | Benchmark + docs re-close | **Done** | Architecture docs, routing pipeline doc, and progress tracker updated to match shipped state |

### Deferred from WS4

- `send_reply` (Web): no async push channel yet; replies are in the HTTP response cycle.
- `send_reply` (WeChat): send-path calls go through `services/wechat/wechat_notify.py` directly, not through the adapter.
- `send_notification` (Web): client-side polling; no server-push mechanism yet.
- `send_notification` (WeChat): stub delegates to `_send_customer_service_msg` but is not called from router code.

# Why this plan exists

The current product direction is still correct:

- Web doctor workbench is the primary MVP surface
- shared 5-layer workflow is the core doctor path
- draft-first + explicit confirm is still the right safety model

But the re-review found four closure gaps that are still material:

1. New workbench endpoints still trust query `doctor_id` after auth resolution
2. Workbench context reads in-memory session state without hydration
3. Voice still bypasses the draft-first confirmation model
4. Channel-adapter convergence is incomplete and partly still stubbed

# Scope

- doctor-scoped auth and session authority for Web workbench endpoints
- authoritative workbench context behavior across restart / multi-device cases
- convergence of voice onto the same hero-loop semantics
- closure of adapter-layer drift where the repo currently claims more unification
  than the code actually delivers
- benchmark and docs follow-up needed to prove the fixes

# Out of scope

- new specialty features
- patient portal expansion
- mini-program UX expansion
- broad admin/dashboard work
- new transport channels beyond the current Web / WeChat surfaces

# Success criteria

This closure cycle is successful only if all of the following are true:

1. Authenticated doctors cannot read or mutate another doctor's workbench state
   by passing a different `doctor_id`.
2. Web workbench context matches persisted workflow state on cold start, restart,
   or second-device entry.
3. Voice note entry follows the same draft-first safety semantics as the main
   Web and WeChat doctor flow, except for explicit emergency cases.
4. Any claimed channel abstraction is either wired end to end or explicitly
   documented as deferred.
5. Benchmark and docs reflect the real architecture after these fixes land.

# Workstreams

## Workstream 1. Doctor-scope authority on Web workbench endpoints

Priority: `P0`

Problem:

- Several new UI endpoints resolve auth, but then keep using the raw query
  `doctor_id` when reading session or pending-draft state.

Implementation steps:

1. Audit all workbench endpoints that currently call `_resolve_ui_doctor_id()`.
2. Replace raw query `doctor_id` with the resolved principal everywhere session
   or DB state is read or written.
3. Apply the same rule to:
   - working-context endpoint
   - pending-record get / confirm / abandon endpoints
   - any new profile-adjacent workbench endpoints added in the same surface
4. Add route-level auth-boundary tests for mismatched token/query doctor IDs.

Primary files:

- `routers/ui/__init__.py`
- `routers/ui/_utils.py`
- `services/auth/request_auth.py`
- `tests/test_auth_boundary.py`
- `tests/test_ui_router.py`

Exit criteria:

- valid auth for doctor A can never observe or mutate doctor B state through the
  workbench APIs
- the tests fail if a raw query `doctor_id` is accidentally used again

## Workstream 2. Make workbench context authoritative

Priority: `P0`

Problem:

- The workbench header and pending-draft endpoints currently read from
  `get_session()` directly, which is not authoritative on cold start or
  multi-device entry until hydration happens elsewhere.

Implementation steps:

1. Hydrate session state before serving workbench context and pending-draft APIs.
2. Reuse the same persisted workflow state assumptions already used by the main
   doctor workflow.
3. Verify behavior for:
   - cold session with persisted current patient
   - cold session with persisted pending draft
   - expired pending draft cleanup
   - second-device page load
4. Decide whether the workbench should assemble a smaller authoritative context
   helper or call existing session hydration directly.

Primary files:

- `routers/ui/__init__.py`
- `services/session.py`
- `services/ai/turn_context.py`
- `tests/test_working_context.py`
- new focused UI/session authority tests if needed

Exit criteria:

- first page load shows the same active patient and pending draft the doctor
  would see in the chat workflow
- restart does not silently clear visible workbench context

## Workstream 3. Align voice with hero-loop safety semantics

Priority: `P0`

Problem:

- Voice currently performs direct routing and immediate save behavior that sits
  outside the shared draft-first workflow.

Implementation steps:

1. Route voice note chat through the shared intent workflow and shared handlers.
2. Make normal add-record voice flows create pending drafts instead of saving
   directly.
3. Keep explicit emergency cases allowed to save immediately if that remains the
   accepted rule.
4. Remove or isolate any remaining direct-save logic that duplicates Web/WeChat
   business semantics.
5. Add voice-specific tests for add-record, create-patient, clarification, and
   emergency behavior.

Primary files:

- `routers/voice.py`
- `services/intent_workflow/`
- `services/domain/intent_handlers/`
- `tests/` new voice-router coverage

Exit criteria:

- voice no longer defines a weaker write path than the Web / WeChat hero loop
- patient binding, draft creation, and confirm semantics are consistent across
  all doctor-facing channels

## Workstream 4. Finish or de-scope adapter-layer convergence

Priority: `P0`

Problem:

- The repo now contains `ChannelAdapter`, `WebAdapter`, and `WeChatAdapter`, but
  the WeChat adapter is still not the real channel boundary and part of it is
  stubbed or incorrect.

Implementation steps:

1. Decide the closure rule:
   - either wire adapters into the real router boundaries now
   - or explicitly mark the adapter layer as deferred and keep only the parts
     already used in production paths
2. If keeping the adapter track active now:
   - wire WeChat router code through `WeChatAdapter`
   - fix history retrieval to use the real session field
   - replace send-path stubs or keep them clearly outside the active interface
3. Remove or document legacy overlap to avoid three parallel abstractions
   existing at once.
4. Add regression tests for the actual adapter contract.

Primary files:

- `services/domain/message.py`
- `services/domain/adapters/web_adapter.py`
- `services/domain/adapters/wechat_adapter.py`
- `routers/records.py`
- `routers/wechat.py`
- `routers/wechat_flows.py`
- `tests/test_channel_adapters.py`

Exit criteria:

- adapter code either reflects real runtime boundaries or is no longer presented
  as if it does
- WeChat history and formatting behavior are verified by tests

## Workstream 5. Re-close benchmark and docs against the real architecture

Priority: `P1`

Problem:

- Benchmark tooling exists, but the release claim is stronger than the current
  proof, and architecture docs still describe parts of the old layout or more
  convergence than the code currently has.

Implementation steps:

1. Run the hero-loop benchmark after the P0 fixes on the dedicated `:8001`
   target.
2. Save candidate artifacts and compare against the last accepted baseline.
3. Update architecture docs to reflect:
   - `frontend/web` and `frontend/miniprogram` split
   - current `DoctorTurnContext` usage
   - voice exception if it still exists
   - real adapter status
4. Update progress docs so shipped work and remaining gaps are not in conflict.

Primary files:

- `scripts/compare_baseline.py`
- `scripts/save_baseline.sh`
- `e2e/README.md`
- `docs/review/architecture-overview.md`
- `docs/product/message-routing-pipeline.md`
- `docs/plans/archived/mvp-hero-loop-progress.md`

Exit criteria:

- benchmark result is recorded after the closure work
- docs no longer overstate what is unified or shipped

# Test plan

## Required unit / route coverage

- auth-boundary tests for workbench endpoints
- cold-session / hydration tests for working context
- voice workflow tests for pending-draft behavior
- adapter regression tests for WeChat history and formatting

## Required benchmark validation

Run after all `P0` items land:

1. `bash scripts/test.sh hero-loop`
2. compare candidate with baseline using `scripts/compare_baseline.py`
3. treat hero-loop regression as blocking until explicitly reviewed

# Suggested execution order

1. Workstream 1 — doctor-scope authority
2. Workstream 2 — authoritative workbench context
3. Workstream 3 — voice safety alignment
4. Workstream 4 — adapter convergence closure
5. Workstream 5 — benchmark + docs re-close

# Definition of done

This plan is complete only when:

- all `P0` workstreams are finished
- the new tests are in place
- the benchmark has been rerun and compared
- architecture/progress docs match the shipped state
