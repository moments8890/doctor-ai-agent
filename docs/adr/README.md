# ADR Log

This folder holds architecture decision records for decisions that should not be
re-litigated in every plan or review.

## When to Add an ADR

Add an ADR when the decision:

- changes how safety-critical state is interpreted
- affects AI routing, persistence, or write approval rules
- narrows future implementation options on purpose
- has already come up repeatedly in reviews or plans

## ADR Format

Use small, direct records with:

- `Title`
- `Status`
- `Date`
- `Implementation Status`
- `Context`
- `Decision`
- `Consequences`

## Current ADRs

- [ADR 0001: Turn Context Authority](0001-turn-context-authority.md)
- [ADR 0002: Draft-First Record Persistence](0002-draft-first-record-persistence.md)
- [ADR 0003: Medical Record Content Is the Source of Truth](0003-record-content-source-of-truth.md)
- [ADR 0004: Prefer Official WeCom Channel Over Automation](0004-prefer-official-wecom-channel-over-automation.md)
- [ADR 0005: Bound Single-Turn Compound Intents](0005-bound-single-turn-compound-intents.md)
- [ADR 0006: One Patient Scope Per Turn](0006-one-patient-scope-per-turn.md)
- [ADR 0007: Stateful Blocked-Write Continuations](0007-stateful-blocked-write-continuations.md)
- [ADR 0008: Minimal Routing and Structuring-Only Note Generation](0008-minimal-routing-and-structuring-only-note-generation.md)
- [ADR 0009: Modality Normalization at Workflow Entry](0009-modality-normalization-at-workflow-entry.md)

## Status Values

- `Accepted`
- `Superseded`
- `Proposed`
- `Deprecated`

If an ADR is replaced, update the old ADR to say which newer ADR superseded it.

## Implementation Status Values

ADR `Status` tracks the decision lifecycle. `Implementation Status` tracks how
far the codebase has actually rolled the decision out.

- `Complete`
- `Partial`
- `Not Started`

Current rollout snapshot:

| ADR | Decision Status | Implementation Status |
| --- | --- | --- |
| [ADR 0001](0001-turn-context-authority.md) | Accepted | Partial |
| [ADR 0002](0002-draft-first-record-persistence.md) | Accepted | Complete |
| [ADR 0003](0003-record-content-source-of-truth.md) | Accepted | Complete |
| [ADR 0004](0004-prefer-official-wecom-channel-over-automation.md) | Accepted | Complete |
| [ADR 0005](0005-bound-single-turn-compound-intents.md) | Accepted | Complete |
| [ADR 0006](0006-one-patient-scope-per-turn.md) | Accepted | Partial |
| [ADR 0007](0007-stateful-blocked-write-continuations.md) | Accepted | Complete |
| [ADR 0008](0008-minimal-routing-and-structuring-only-note-generation.md) | Accepted | Complete |
| [ADR 0009](0009-modality-normalization-at-workflow-entry.md) | Accepted | Not Started |
