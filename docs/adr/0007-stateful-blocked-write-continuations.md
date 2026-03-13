# ADR 0007: Stateful Blocked-Write Continuations

## Status

Accepted

## Date

2026-03-12

## Implementation Status

Complete

Last reviewed: 2026-03-12

Notes:

- Blocked-write session state, deterministic precheck logic, and DB-backed
  persistence are now wired across web, WeChat, and voice chat.
- The old `followup_name` continuation plumbing has been removed from the live
  doctor-facing paths.
- Blocked-write continuation is now authoritative workflow state rather than a
  router/history heuristic.

## Context

The MVP hero loop is intentionally narrow:

- identify or create the patient
- dictate or append the clinical note
- create a pending draft
- explicitly confirm or abandon the draft

The repo already treats draft-first persistence, one-patient scope, and
authoritative workflow state as core safety rules.

But the current follow-up behavior for blocked writes is still too implicit:

- a doctor may dictate clinical content without naming the patient first
- the system may ask for the patient name on the next turn
- the current code then relies on ad hoc `followup_name` plumbing and recent
  chat history to reinterpret the next message as an `add_record` continuation

That creates three problems:

1. continuation behavior depends too much on the router or history heuristics
2. a bare-name follow-up can be misread as a new standalone command
3. routing and structuring responsibilities are blurred when router-produced
   clinical fields are allowed to act like final note content

For a precision-first MVP, a blocked write should behave like an explicit
workflow state transition, not an LLM guess.

## Decision

Adopt a stateful blocked-write continuation model for doctor-facing write flows.

### 1. Blocked writes become authoritative session state

When a write intent is blocked because required input is missing, the system
stores an explicit blocked-write context in session state.

For MVP, this primarily applies to:

- `add_record` blocked on missing patient name

The blocked-write context should carry at least:

- blocked intent
- original clinical text
- missing field / question being asked
- optional channel metadata
- creation timestamp / TTL

This context is authoritative workflow state, not advisory history.

### 2. The next-turn continuation is resolved deterministically

If a blocked-write context exists and the next doctor message matches an allowed
continuation pattern, the system resumes the blocked write without asking the
routing LLM to reinterpret the turn from scratch.

For MVP, allowed continuations include:

- bare patient name
- patient name plus additional clinical supplement
- explicit cancel / abandon of the blocked write

The continuation resolver is a minimal stateful precheck layer.

### 3. Routing and structuring remain separate responsibilities

Routing LLM:

- decides intent
- extracts coarse routing entities
- does not define final record content

Structuring LLM:

- runs only for note-producing intents such as `add_record` and `update_record`
- produces the readable clinical note content used for draft creation

Router-produced `structured_fields` must not act as a separate final-note
shortcut that bypasses the normal structuring path for saved doctor notes.

### 4. Deterministic prechecks stay minimal

The stateful precheck layer may handle:

- blocked-write continuation
- explicit draft confirmation / cancellation
- similar exact workflow-state transitions

It must not grow into a broad semantic rule engine for general intent routing.

## Consequences

- blocked write recovery becomes more reliable for two-turn doctor interactions
- bare-name follow-up resolution no longer depends on the router inferring
  intent from minimal text like `张三`
- routing remains responsible for control flow, not final note generation
- structuring becomes the single note-generation path for write intents
- future refactors should replace ad hoc `followup_name` wiring with one shared
  continuation precheck across Web, WeChat, and voice
- if blocked-write continuation later needs cross-device or restart durability,
  the session persistence model should explicitly persist that state rather than
  falling back to history-based recovery

## Related ADRs

- [ADR 0001: Turn Context Authority](0001-turn-context-authority.md)
- [ADR 0002: Draft-First Record Persistence](0002-draft-first-record-persistence.md)
- [ADR 0006: One Patient Scope Per Turn](0006-one-patient-scope-per-turn.md)
