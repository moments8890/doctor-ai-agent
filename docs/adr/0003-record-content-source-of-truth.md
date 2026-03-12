# ADR 0003: Medical Record Content Is the Source of Truth

## Status

Accepted

## Date

2026-03-11

## Implementation Status

Complete

Last reviewed: 2026-03-12

Notes:

- `medical_records.content` remains the primary persisted readable note body.
- Derived metadata remains supporting data rather than an authoritative record
  source.
- No shipped migration has promoted structured payloads over readable content.

## Context

The codebase already persists a readable medical record body in
`medical_records.content`. Reviews and schema planning raised the question of
whether future structured payloads should become the authoritative record instead.

Changing the source of truth would affect exports, correction history, tests,
and future schema design.

## Decision

`medical_records.content` remains the primary persisted source of truth for the
doctor-facing medical record.

Derived fields such as:

- tags
- specialty scores
- encounter type
- future optional structured payloads

are supporting data unless a future ADR explicitly promotes them to authoritative status.

If there is disagreement between readable content and derived data, readable content
wins by default.

## Consequences

- schema-hardening work should not block on adding a structured payload column
- future `structured_json` work should be treated as additive evaluation/support data first
- export and correction-history flows should continue to anchor on readable content
- any future move toward structured payload authority requires a separate ADR and migration plan
