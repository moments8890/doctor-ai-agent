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
- `Context`
- `Decision`
- `Consequences`

## Current ADRs

- [ADR 0001: Turn Context Authority](0001-turn-context-authority.md)
- [ADR 0002: Draft-First Record Persistence](0002-draft-first-record-persistence.md)
- [ADR 0003: Medical Record Content Is the Source of Truth](0003-record-content-source-of-truth.md)

## Status Values

- `Accepted`
- `Superseded`
- `Proposed`
- `Deprecated`

If an ADR is replaced, update the old ADR to say which newer ADR superseded it.
