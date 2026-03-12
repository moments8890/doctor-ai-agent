# ADR 0006: One Patient Scope Per Turn

## Status

Accepted

## Date

2026-03-11

## Implementation Status

Partial

Last reviewed: 2026-03-12

Notes:

- The workflow and handlers preserve a single patient-scoped transaction model,
  and same-name ambiguity already clarifies instead of guessing.
- Explicit free-text multi-patient detection is still not fully implemented;
  earlier implementation notes already defer that detection work.
- This ADR should be marked complete only after multi-patient free-text turns
  reliably clarify rather than depending on incidental routing behavior.

## Context

Doctor messages sometimes mention more than one patient in a single sentence,
for example:

- `查张三和李四`
- `给王芳建档，再给赵强补一条`
- `删除张三并查询李四`

The product is deliberately centered on one visible working context, one
patient-scoped transaction, and explicit draft / persistence safety rules.

Supporting arbitrary multi-patient free-text turns would introduce ambiguity in:

- patient binding
- execution order
- partial failure handling
- final response shape
- benchmark interpretation

This cost is not justified for the MVP hero loop.

## Decision

Adopt a one-patient-scope-per-turn rule for free-text doctor workflow.

For MVP:

- one doctor turn should resolve to at most one patient-scoped transaction
- free-text turns that mention multiple patients should not execute best-effort
- those turns should trigger clarification asking which patient to handle first
- read-only aggregate/list commands may still operate across multiple patients if
  they are explicit product features rather than free-text multi-patient
  workflow mixing

Examples:

- `患者列表`
- `今天要复诊的患者`
- `最近待随访患者`

These are aggregate read surfaces, not exceptions to the one-patient workflow
rule.

## Consequences

- routing, planning, and gate logic should reject or clarify multi-patient
  free-text turns
- prompts should not encourage multi-patient best-effort execution
- benchmarks should include explicit multi-patient clarification cases
- future support for multi-patient write flows would require a new execution
  model rather than an incremental prompt tweak
