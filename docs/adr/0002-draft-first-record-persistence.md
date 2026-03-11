# ADR 0002: Draft-First Record Persistence

## Status

Accepted

## Date

2026-03-11

## Context

Doctor messages often mix partial dictation, clarification, and task language.
The LLM can produce a plausible record draft before the system has enough certainty
to treat it as a final medical record.

Earlier reviews identified silent persistence and free-text confirmation as
high-risk behaviors for doctor-facing workflows.

## Decision

Normal doctor-authored record creation follows a draft-first model:

- create a pending draft first
- show the draft clearly as pending
- require explicit confirmation before final persistence

Exceptions may exist for explicitly defined low-risk or emergency flows, but they
must be deliberate product rules, not accidental behavior from LLM output.

LLM output does not by itself authorize immediate persistence.

## Consequences

- the UI and WeChat flow must surface pending-draft state clearly
- confirmation language must be explicit and predictable
- silent auto-save of normal record drafts is not acceptable
- routing and structuring changes must preserve the pending-draft gate unless a future ADR changes the product model
