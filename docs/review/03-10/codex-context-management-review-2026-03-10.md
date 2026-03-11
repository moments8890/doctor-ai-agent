# Context Management Review

Date: 2026-03-10

Scope: Doctor-agent context management across session state, conversation history, compressed memory, doctor knowledge context, and prior-visit clinical context.

## Executive Summary

The current doctor-agent context system is functionally strong but architecturally fragmented.

It already contains the right categories of context for a medical workflow:

- live workflow/session state
- recent conversation history
- persisted session state
- compressed long-term conversation summary
- doctor-specific knowledge context
- prior-visit clinical summary

The main issue is not missing capability. The issue is that these context sources are assembled and consumed in different places with different semantics, and there is no single explicit turn-level context model describing:

- which source is authoritative
- which source is advisory
- which source can influence routing
- which source can influence patient binding

If accuracy is the primary concern, the biggest architectural risk is context divergence rather than lack of context.

## Current Context Sources

### 1. Live Session Context

Owned by `services/session.py`.

Contains:

- `current_patient_id`
- `current_patient_name`
- `pending_create_name`
- `pending_record_id`
- `interview`
- `pending_cvd_scale`
- `specialty`
- `doctor_name`
- `conversation_history`

Strengths:

- Correctly models doctor workflow state.
- Supports stateful multi-turn medical workflows.
- Persists important workflow fields to DB.

Risks:

- It is a mutable shared object with several asynchronous persistence paths.
- Authority is implicit rather than formally defined.

### 2. Persisted Session State

Also managed by `services/session.py` through DB hydration and persistence.

Strengths:

- Enables restart recovery and multi-device continuity.
- Prevents total loss of pending workflow state.

Risks:

- Freshness depends on hydration policy and turn timing.
- In-memory state and DB state can drift temporarily.

### 3. Recent Conversation History

Maintained in `DoctorSession.conversation_history`, flushed to DB via `push_turn()` / `flush_turns()`.

Strengths:

- Supports short-horizon conversational continuity.
- Preserves recent doctor/assistant interactions.

Risks:

- Live history, persisted turns, and compressed memory are separate representations.
- No single abstraction defines which one should be preferred in each stage.

### 4. Compressed Long-Term Memory

Owned by `services/ai/memory.py`.

Strengths:

- Gives cross-session continuity.
- Prevents unbounded history growth.
- Uses a structured summary format rather than arbitrary free text.

Risks:

- Summary is advisory but that is not explicitly modeled in the wider architecture.
- Compression output is a different representation of the same underlying conversation state.

### 5. Doctor Knowledge Context

Owned by `services/knowledge/doctor_knowledge.py`.

Strengths:

- Distinguishes doctor preference/protocol knowledge from live workflow state.
- Useful for routing and response shaping.

Risks:

- Cached independently from session state.
- Not part of a unified turn context model.

### 6. Prior-Visit Clinical Context

Injected in `services/domain/record_ops.py` for structuring.

Strengths:

- Improves follow-up record quality.
- Correctly treated as clinical context rather than workflow state.

Risks:

- Structuring sees richer patient-specific clinical context than routing does.
- The two LLM stages do not reason over the same context slice.

## Architectural Assessment

## What Is Good

The current design reflects a real medical workflow rather than a generic chatbot.

That is a strength.

The system correctly distinguishes several context types:

- workflow state
- conversational context
- persistent memory
- physician preference/protocol knowledge
- prior clinical context

Those distinctions are appropriate.

## What Is Missing

There is no explicit per-turn context assembly layer.

Today, context is pulled ad hoc by:

- routing
- WeChat flow control
- add-record execution
- structuring
- memory compression

Each subsystem sees a valid subset of context, but not through one explicit contract.

This makes the architecture harder to reason about, especially for:

- patient binding
- context freshness
- debugging wrong outcomes
- future refactoring

## Main Risk

The main risk is context divergence.

Examples:

- routing uses session patient context
- structuring uses prior-visit summary
- memory stores compressed historical context
- knowledge context is injected separately

All of these may be individually correct, but the system has no single answer to:

“What was the full doctor-agent context used for this turn?”

That makes accuracy investigation harder than it should be.

## Recommended Architecture

Introduce a logical per-turn context model:

### `DoctorTurnContext`

Suggested fields:

- `doctor_id`
- `doctor_profile`
  - `doctor_name`
  - `specialty`
- `workflow_state`
  - `current_patient_id`
  - `current_patient_name`
  - `pending_create_name`
  - `pending_record_id`
  - `interview_state`
  - `pending_cvd_scale`
- `recent_history`
  - `recent_turns`
  - `routing_history`
  - `structuring_history`
- `long_term_memory`
  - `compressed_summary`
  - `summary_freshness`
- `knowledge_context`
  - `rendered_knowledge_snippet`
  - `knowledge_freshness`
- `clinical_context`
  - `encounter_type`
  - `prior_visit_summary`
- `provenance`
  - `current_patient_source`
  - `memory_used`
  - `knowledge_used`
  - `prior_visit_used`

This does not require a new DB table. It is first an architectural assembly object.

## Authority Rules

Not all context should be equal.

Recommended rules:

- `workflow_state.current_patient_*`
  - authoritative for turn-local execution unless explicitly overridden by current message

- `pending_*`, `interview_state`
  - authoritative workflow state

- `recent_history`
  - primary short-horizon conversational context

- `compressed_summary`
  - advisory only

- `knowledge_context`
  - advisory only

- `prior_visit_summary`
  - advisory clinical context for record interpretation and structuring

Doctor knowledge should never influence patient binding.

Compressed memory should never be treated as authoritative workflow state.

## Locking and DB Contention Guidance

This architecture should not be implemented as one large DB-heavy locked context load.

That would increase contention.

Recommended pattern:

1. Acquire per-doctor lock
2. Read or validate minimal authoritative workflow state
3. Snapshot what is needed
4. Release lock
5. Load advisory context outside lock
6. Route / assemble / prepare result
7. Re-acquire lock only if applying mutations

This keeps lock scope narrow while still allowing a unified logical turn context.

## Local Memory Cache Strategy

Local in-process memory cache can be valuable for context management, but only for the right class of context.

### Good Cache Candidates

These are advisory or read-heavy context sources and can safely benefit from local memory caching:

- doctor profile
  - `doctor_name`
  - `specialty`
- rendered doctor knowledge context
- compressed long-term conversation summary
- recent prior-visit summary
- recent read-only conversation slices prepared for routing

These items are useful, relatively stable, and not by themselves sufficient to cause a dangerous write if stale.

### Poor Cache Candidates

These should not become cache-authoritative:

- `current_patient_id`
- `current_patient_name`
- `pending_record_id`
- `pending_create_name`
- `interview_state`
- `pending_cvd_scale`

These are workflow-critical state and directly affect persistence safety.

### Recommended Rule

Use a two-tier context model:

- authoritative context
  - workflow state
  - patient binding
  - pending write state

- advisory cached context
  - doctor profile
  - compressed memory
  - doctor knowledge snippet
  - prior-visit summary

### Cache Design Guidance

If local memory cache is used, it should have:

- bounded TTLs
- explicit invalidation on writes
- provenance logging when cached context is consumed
- no authority over patient binding or write-path state

The goal is to reduce latency and DB read pressure, not to replace authoritative state handling.

### Architectural Verdict on Local Cache

Yes, local memory cache should be leveraged for context management.

But it should be applied only to advisory context.

Using local cache for workflow-critical state would increase the risk of stale patient binding and unsafe writes, which is the opposite of an accuracy-first design.

## Observability Recommendations

The system should log context provenance per turn.

At minimum:

- `current_patient_source`
  - `explicit_message`
  - `session_current_patient`
  - `history_recovery`
  - `single_patient_rebind`
  - `created_this_turn`
  - `unknown`

- `knowledge_used`
- `memory_used`
- `prior_visit_used`

That would make context-driven accuracy issues much easier to debug.

## Final Verdict

The current context management is good enough to support a useful and stateful doctor agent.

It is not yet architecturally clean.

The next architectural improvement should not be “more memory” or “more session state.”

It should be:

- one explicit turn-level context assembly layer
- clear authority rules
- narrow lock boundaries
- provenance-aware observability

In short:

The system has the right context ingredients.
What it lacks is one coherent context architecture.
