# ADR 0005: Bound Single-Turn Compound Intents

## Status

Accepted

## Date

2026-03-11

## Implementation Status

Complete

Last reviewed: 2026-03-12

Notes:

- The shared intent workflow planner implements a bounded allowlist of
  same-turn compound patterns.
- Tests cover the supported combinations and keep the execution model scoped to
  one core patient transaction per turn.
- The repo does not expose a general multi-intent free-text execution engine.

## Context

Doctor messages may mix patient creation, record dictation, correction language,
query requests, and reminder/task language in one turn.

The current workflow model is intentionally narrow:

- one primary classified intent
- one patient binding decision
- a bounded action plan for a small set of compound patterns

Trying to support arbitrary combinations of `query_records`, `create_patient`,
`add_record`, `update_record`, task actions, and destructive operations in one
turn would require a different execution model with clause segmentation,
dependency planning, and partial-failure policy.

That is not needed for the MVP and would increase ambiguity on a medical write
path.

## Decision

Adopt a bounded single-turn transaction model.

For MVP:

- each turn should resolve to one core patient-scoped transaction
- only allowlisted same-turn compound patterns are supported
- same-turn correction language rewrites the unsaved payload; it is not a
  separate `update_record` action
- read/query intents do not combine with write intents in one supported turn
- destructive or admin intents do not combine with other intents in one
  supported turn

Allowed same-turn compounds:

- `create_patient + add_record`
- `create_patient + add_record + create_task`
- `add_record + create_task`
- `create/add_record + same-turn correction`

Unsupported combinations should trigger clarification instead of best-effort
execution.

## Consequences

- planners and handlers should preserve one patient scope and one core record
  transaction per turn
- prompts should not encourage arbitrary multi-action execution plans
- `update_record` remains reserved for changing an already persisted latest
  record, not for correcting text inside the current unsaved turn
- if future work needs general multi-intent execution, it should introduce a new
  turn-plan model explicitly rather than stretching the current single-root
  workflow
