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

- [ADR 0011: Thread-Centric Conversation Runtime and Deterministic Commits](0011-thread-centric-conversation-runtime-and-deterministic-commits.md)
  — companion: [Architecture and Workflows](0011-architecture-and-workflows.md)
  ([中文](0011-architecture-and-workflows.zh-CN.md))
- [ADR 0012: Understand / Execute / Compose Pipeline for Operational Actions](0012-understand-execute-compose-pipeline.md)
  — companion: [Architecture Diagram](0012-architecture-diagram.md)
- [ADR 0013: Action Type Simplification](0013-action-type-simplification.md)
  — companion: [Architecture Diagram](0013-architecture-diagram.md)
- [ADR 0014: Medical Record Import/Export](0014-medical-record-import-export.md)
- [ADR 0015: Clinical Text Collection Boundary](0015-clinical-text-collection-boundary.md)
- [ADR 0016: Patient Pre-Consultation Interview Pipeline](0016-patient-pre-consultation-interview.md)
  — companion: [Architecture Diagram](0016-architecture-diagram.md)

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
| [ADR 0011](0011-thread-centric-conversation-runtime-and-deterministic-commits.md) | Accepted | Complete |
| [ADR 0012](0012-understand-execute-compose-pipeline.md) | Accepted | Complete |
| [ADR 0013](0013-action-type-simplification.md) | Accepted | Complete |
| [ADR 0014](0014-medical-record-import-export.md) | Proposed | Not Started |
| [ADR 0015](0015-clinical-text-collection-boundary.md) | Accepted | Complete |
| [ADR 0016](0016-patient-pre-consultation-interview.md) | Accepted | Complete |
