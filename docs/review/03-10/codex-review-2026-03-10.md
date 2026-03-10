## Architecture Review — 5-Agent Report

Date: 2026-03-10

Scope: Current doctor-facing agent architecture, focused on routing, accuracy, latency, modularity, and observability. This review reflects the current codebase state rather than older workflow documents.

### Executive Summary

The architecture is in a materially better state than the earlier duplicated-router design. Two important extractions now exist:

- `services/ai/router.py` centralizes the shared `fast_route -> agent_dispatch` chain.
- `services/domain/record_ops.py` centralizes shared record assembly logic.

That said, the system is still mid-transition rather than fully simplified. The highest-risk architectural inconsistency is that `add_record` uses different persistence safety models by channel:

- WeChat creates a pending draft and requires confirmation before final save.
- Web chat still persists records directly.

If accuracy is the primary goal, that inconsistency matters more than almost any remaining routing duplication.

### Review Method

Five parallel review lenses were applied:

1. Routing and dispatch architecture
2. Accuracy and patient-safety controls
3. Latency and resilience
4. Modularity and duplication
5. Observability and testability

### Current Architecture

High-level flow:

```text
Channel ingress
  - WeChat: routers/wechat.py
  - Web chat: routers/records.py

Pre-routing channel shortcuts
  - notify / menu / knowledge / greeting / some direct commands

Shared routing
  - services/ai/router.py::route_message()
  - fast_route() first
  - agent_dispatch() on miss

Intent execution
  - per-channel branching still lives in routers
  - some handlers delegated to services/wechat/wechat_domain.py

Record assembly
  - services/domain/record_ops.py::assemble_record()
  - structured_fields fast path, else dedicated structuring LLM

Persistence
  - WeChat add_record: pending draft first
  - Web chat add_record: direct save
```

### Agent 1: Routing / Dispatch

Findings:

- The shared routing entry point is a clear architectural improvement. `route_message()` in `services/ai/router.py` removes the old duplication of `fast_route -> agent_dispatch -> turn logging`.
- The extraction is still partial. Caller responsibilities explicitly remain in the routers: pre-routing shortcuts, knowledge loading, error mapping, and deterministic post-routing fallbacks.
- The LLM routing layer is still a monolith. `services/ai/agent.py` combines provider selection, prompt composition, retries, tool parsing, and local fallback policy.

Assessment:

- Direction: correct
- Completion: partial
- Architectural debt remaining: moderate

### Agent 2: Accuracy / Patient Safety

Findings:

- The strongest accuracy control in the system is the WeChat pending-draft confirmation flow.
- `services/wechat/wechat_domain.py` creates pending drafts for normal `add_record` flows, then `routers/wechat.py` confirms or abandons them.
- Web chat still direct-saves `add_record` to the database in `routers/records.py`.
- Patient-binding still relies on multiple inference paths: explicit extraction, session context, history recovery, and single-patient rebound.

Assessment:

- WeChat path is structurally aligned with accuracy-first persistence.
- Web chat path is not.
- The biggest architectural risk is not routing recall; it is inconsistent write safety.

### Agent 3: Latency / Resilience

Findings:

- Shared routing extraction does not materially simplify the expensive path.
- On a fast-router miss, add-record still pays for:
  - routing LLM
  - record structuring LLM
  - retry/backoff policy in `services/ai/llm_resilience.py`
- The architecture remains accurate-capable but latency-heavy when LLM routing is involved.
- Failure and retry policy is still concentrated in the LLM layer, not at the orchestration boundary.

Assessment:

- Good for quality on hard cases
- Still expensive on the miss path
- Not yet optimized for consistent interactive latency

### Agent 4: Modularity / Duplication

Findings:

- `services/domain/record_ops.py` is a strong modularity improvement because encounter detection and prior-summary injection are now shared across channels.
- Remaining duplication is concentrated in:
  - router pre-checks
  - rescue logic after routing
  - final intent branching
  - channel-specific persistence policy
- This is no longer a fundamentally duplicated architecture. It is a partially consolidated one.

Assessment:

- Better than the older design by a meaningful margin
- Still not fully centralized
- The codebase is in an understandable but transitional state

### Agent 5: Observability / Testability

Findings:

- Routing turn logging is in place and useful for debugging.
- Test coverage around fast routing, add-record handling, pending-record confirmation, and structured-fields paths is substantial.
- Architecture documentation is stale in places and does not fully match the codebase.
- Current observability still does not give a clear system-level view of:
  - wrong-patient binding provenance
  - direct-save vs pending-confirm rates
  - per-channel add-record safety profile

Assessment:

- Debuggability: decent
- Architecture-level observability: still weak
- Documentation drift: high enough to mislead design discussion

### Consensus Findings

#### What Is Working

- Shared routing extraction via `services/ai/router.py`
- Shared record assembly via `services/domain/record_ops.py`
- WeChat pending-draft confirmation as the main write-safety mechanism
- Separation between routing and structuring LLM responsibilities

#### What Is Still Incomplete

- Intent execution is still split across routers
- `services/ai/agent.py` is still too broad in responsibility
- Knowledge loading and post-routing rescue logic remain caller-owned
- Architecture docs still describe older behavior

#### Highest-Risk Inconsistency

The same `add_record` intent has two different persistence safety models:

- WeChat: draft-first, then confirm
- Web chat: direct save

For an accuracy-first medical workflow, this is the most important remaining architectural inconsistency.

### Recommendations

#### Keep As-Is

- Shared `route_message()` boundary
- Shared `assemble_record()` boundary
- WeChat stateful pre-routing flow in `routers/wechat.py`
- Dedicated structuring LLM instead of merging routing and structuring into one prompt

#### Needs Cleanup

- Stale docs in `docs/`
- Remaining duplicated post-routing rescue logic
- Oversized `services/ai/agent.py`
- Limited architecture-level telemetry for binding provenance and write safety

#### ~~High-Risk Inconsistency~~ ✅ RESOLVED (2026-03-10)

- ~~Direct-save web `add_record` versus confirm-first WeChat `add_record`~~
- **Fixed:** Web chat `add_record` now uses pending-draft confirmation flow (Option A).
  - `routers/records.py` `_handle_add_record()` — replaced direct `save_record()` with `create_pending_record()` + `set_pending_record_id()`. Emergency bypass preserved.
  - `POST /api/records/pending/{id}/confirm` — calls `save_pending_record()` from `wechat_domain.py`
  - `POST /api/records/pending/{id}/abandon` — calls `abandon_pending_record()` CRUD
  - `frontend/src/api.js` — `confirmPendingRecordById()`, `abandonPendingRecordById()`
  - `frontend/src/pages/doctor/ChatSection.jsx` — `PendingConfirmCard` component; confirm/abandon wired in-chat

### Final Verdict

The architecture is no longer best described as over-duplicated. It is better described as a partially completed consolidation with one major safety inconsistency — **now resolved**.

Both channels use the same draft-first, confirm-before-persist write safety model. The system now satisfies the accuracy-first requirement for a first release.

### Appendix: Files Reviewed

- `services/ai/router.py`
- `services/ai/agent.py`
- `services/domain/record_ops.py`
- `services/ai/llm_resilience.py`
- `services/ai/structuring.py`
- `routers/records.py`
- `routers/wechat.py`
- `services/wechat/wechat_domain.py`
- `docs/agent_workflow_review.md`
- `docs/product/message-routing-pipeline.md`
