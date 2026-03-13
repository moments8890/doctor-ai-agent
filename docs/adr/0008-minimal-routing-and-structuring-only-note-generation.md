# ADR 0008: Minimal Routing and Structuring-Only Note Generation

## Status

Accepted

## Date

2026-03-12

## Implementation Status

Complete

Last reviewed: 2026-03-13

Notes:

- The main doctor write path now matches the ADR:
  - blocked writes resume from authoritative state
  - `add_record` uses structuring as the single note-generation path
  - the `add_medical_record` routing schema is reduced to coarse entities only
- Router-produced `structured_fields` no longer drive final `add_record` note
  generation.
- A narrow correction-oriented compatibility path still exists for
  `update_record`, but it does not reintroduce a second final-note path for
  normal doctor-authored record creation.
- Known gap: `/api/neuro/from-text` uses its own extract → save path outside
  the 5-layer workflow. Tracked for convergence alongside ADR 0002/0009.

## Context

The product is aiming for accuracy-first behavior in the MVP hero loop:

- identify or create the patient
- dictate or append the clinical note
- create a pending draft
- explicitly confirm or abandon the draft

The system already separates authoritative workflow state, draft-first
persistence, and one-patient-scope rules in earlier ADRs.

But the current LLM split is still overloaded in places:

- routing may emit detailed clinical section fields
- router-produced `structured_fields` can act like an alternate note-generation
  path
- blocked write continuation can still depend on ad hoc history interpretation
- deterministic routing risks expanding beyond exact workflow or operational
  transitions

That makes the system harder to reason about and can produce inconsistent note
content for the same doctor input.

For accuracy, the system should use LLMs where they are strongest:

- semantic routing
- clinical note generation

And use deterministic workflow state where it is stronger:

- blocked-write continuation
- patient-binding approval
- draft confirmation and cancellation
- write gating

## Decision

Adopt a minimal-routing, structuring-only note-generation architecture for the
doctor-facing workflow.

The target processing shape is:

```text
message
-> minimal stateful precheck
-> routing_llm
-> intent + coarse entities
-> bind/gate
-> if blocked: store blocked write context and ask for missing input
-> if approved: per-intent executor
-> structuring_llm (note-producing write intents only)
-> pending draft
-> explicit confirm
```

### 1. Routing LLM decides control flow, not final note content

Routing output may include:

- intent
- patient name candidate
- gender
- age
- emergency flag
- narrow intent-specific metadata such as task or appointment parameters

Routing output must not be treated as final medical note content.

### 2. Routing schema stays coarse

The routing layer must not define or rely on full medical note section fields as
part of its normal contract.

Examples of fields that do not belong in the routing contract:

- chief complaint
- present illness
- diagnosis
- treatment plan
- follow-up plan

If temporary compatibility fields exist during migration, they are treated as
hints only and not as an authoritative saved-note path.

### 3. Deterministic prechecks stay minimal and stateful

The deterministic layer before routing may handle only:

- exact workflow-state transitions
- blocked-write continuation
- explicit draft confirmation or cancellation
- exact low-risk command-style operations where deterministic precision is
  clearly better than LLM routing

It must not grow into a broad semantic substitute for the routing LLM.

### 4. Blocked writes are resumed from authoritative state

If required input is missing for a write, the system stores explicit blocked
write context and resumes that workflow deterministically on the next turn when
possible.

This continuation path is authoritative workflow logic, not a fresh routing
guess from chat history.

### 5. Structuring LLM is the single note-generation path

Readable doctor-facing note content is generated through the structuring layer
for note-producing write intents.

This includes at minimum:

- `add_record`

And may include:

- `update_record` when the correction flow requires regenerated note content

The system should not maintain two parallel final-note generation paths where
one comes from routing output and the other comes from structuring.

### 6. Draft-first confirmation remains mandatory

LLM-generated note content still goes through pending-draft creation and
explicit confirmation before final persistence, except for separately defined
deliberate exceptions such as explicit emergency rules.

## Consequences

- routing and structuring responsibilities become easier to reason about
- the same doctor input should no longer persist different note shapes based on
  whether the routing LLM happened to emit section fields
- blocked-write recovery no longer depends on the routing LLM inferring intent
  from minimal follow-up text such as a bare patient name
- deterministic routing should shrink to exact operational or workflow-state
  transitions rather than broad semantic heuristics
- implementation work should remove router-produced `structured_fields` as a
  final-note shortcut and move note generation behind the structuring path
- benchmarks and tests should measure:
  - routing intent accuracy
  - blocked-write continuation accuracy
  - final note fidelity after structuring
  - pending-draft lifecycle correctness

## Related ADRs

- [ADR 0001: Turn Context Authority](0001-turn-context-authority.md)
- [ADR 0002: Draft-First Record Persistence](0002-draft-first-record-persistence.md)
- [ADR 0003: Medical Record Content Is the Source of Truth](0003-record-content-source-of-truth.md)
- [ADR 0006: One Patient Scope Per Turn](0006-one-patient-scope-per-turn.md)
- [ADR 0007: Stateful Blocked-Write Continuations](0007-stateful-blocked-write-continuations.md)
