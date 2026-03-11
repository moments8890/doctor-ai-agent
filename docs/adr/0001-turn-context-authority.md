# ADR 0001: Turn Context Authority

## Status

Accepted

## Date

2026-03-11

## Context

The system uses multiple context sources during routing:

- live session state
- recent history
- compressed memory
- doctor knowledge
- patient-related hints from prior turns

Reviews repeatedly found that accuracy and safety problems came more from mixed
context authority than from prompt wording. The system needed an explicit rule
for which sources may control routing and write-path decisions.

## Decision

Adopt a two-tier turn context model:

- `WorkflowState` is authoritative.
- `AdvisoryContext` is advisory only.

Authoritative context includes:

- current patient binding
- pending draft / pending record state
- active interview or specialist workflow state
- explicit session cursor state required for continuation

Advisory context includes:

- recent history
- compressed memory
- doctor knowledge snippets
- doctor profile hints

Only authoritative context may control:

- patient binding
- write-path approval
- confirmation flow state
- destructive action gating

Advisory context may inform the LLM, but it may not override authoritative state.

## Consequences

- context assembly should separate authoritative and advisory fields explicitly
- routing tests should verify that advisory context cannot silently rebind patients
- prompt changes must not be used to smuggle advisory context into authoritative decisions
- future refactors should preserve this authority boundary even if builders or data structures change
