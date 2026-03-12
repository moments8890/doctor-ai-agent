# ADR 0009: Modality Normalization at Workflow Entry

## Status

Accepted

## Date

2026-03-12

## Implementation Status

Complete (all 5 phases)

Last reviewed: 2026-03-12

Notes:

- Phase 1: `/api/voice/consultation` now transcribes with
  `consultation_mode=True` then enters the same 5-layer workflow as
  `/api/voice/chat`. Direct structuring+save removed. `ConsultationResponse`
  model removed; endpoint returns `VoiceChatResponse`.
- Phase 2: `/from-image` and `/from-audio` now extract text then dispatch to
  `import_history` instead of direct single-record structuring.
- Phase 3: WeChat image/PDF already routed via `[Image:ocr]`/`[PDF:]` prefix
  → `import_history`. All channels now follow the same modality rule.
- Phase 4: All endpoints conform to ADR 0009. `records_media.py` is unmounted
  dead code (not included in main.py).
- Phase 5: `ARCHITECTURE.md` updated to reflect modality normalization.

## Context

The product now has a clearer LLM architecture:

- normal doctor messages use minimal stateful precheck, routing, bind/gate, and
  structuring for write intents
- blocked writes resume from authoritative session state
- draft-first confirmation protects normal record creation

But modality entrypoints are still inconsistent:

- voice chat already transcribes audio and sends the transcript through the
  normal doctor workflow
- voice consultation transcribes and structures directly, bypassing routing and
  draft-first confirmation
- image/PDF upload flows can extract text, but some routes still treat that
  text as a direct single-record note instead of import

That inconsistency makes the system harder to reason about and weakens the
accuracy-first goal. The right question is not whether a modality uses an LLM,
but which workflow the normalized content should enter after extraction.

For the MVP, the product should adopt one modality rule set:

- spoken doctor input behaves like a normal doctor message once transcribed
- image and PDF uploads behave like historical/document import once text is
  extracted

## Decision

Normalize all non-text inputs before workflow selection, then dispatch by
workflow type rather than by raw modality-specific shortcut.

The target shape is:

```text
raw modality
-> extraction / normalization
-> workflow entry selection
-> either:
   - normal doctor message workflow
   - import workflow
```

### 1. Voice becomes a normal doctor message after transcription

Audio uploads that represent doctor input must be transcribed first, then enter
the same doctor-message workflow used by Web and WeChat text:

```text
audio
-> transcription
-> text
-> minimal stateful precheck
-> routing_llm
-> intent + coarse entities
-> bind/gate
-> per-intent executor
-> structuring_llm for write intents
-> pending draft
-> explicit confirm
```

Voice must not keep a separate direct structuring-and-save workflow for normal
doctor use just because the original input was audio.

### 2. Image and PDF become import after extraction

Image and PDF uploads must be OCRed or text-extracted first, then enter the
document import workflow by default:

```text
image / pdf
-> OCR / text extraction
-> import workflow entry
-> import_history
-> chunking / structuring as needed
-> import persistence rules
```

They should not be treated as ordinary single-turn doctor chat messages or as
direct single-record `add_record` content by default.

### 3. Extraction is separate from workflow execution

Utilities such as OCR, PDF extraction, and transcription remain valid as
normalization helpers. They do not themselves define persistence behavior.

Extraction endpoints may still exist for tooling or UI preview, but saving
behavior must be determined by the workflow selected after extraction.

### 4. Modality metadata remains available

The normalized workflow entry may carry metadata such as:

- `source_type=voice|image|pdf`
- filename
- extraction confidence or extraction mode
- consultation/transcription hints when needed

This metadata may influence prompts or import preprocessing, but it must not
create a separate safety-bypassing workflow.

### 5. Legacy direct-create shortcuts should be converged or deprecated

The codebase may keep temporary compatibility endpoints during rollout, but the
target architecture is:

- no direct-save voice consultation path for normal doctor workflow
- no image/PDF path that creates a normal single medical record by directly
  structuring extracted text

## Consequences

- voice becomes easier to reason about because audio and typed doctor input
  share the same routing, gating, and draft-confirmation model
- image/PDF handling becomes more accurate for multi-visit records and bulk
  historical material, because extracted text is treated as import instead of a
  single fresh note by default
- OCR/transcription utilities remain useful without implicitly bypassing safety
  rules
- some existing endpoints become compatibility wrappers or deprecation targets,
  especially direct structuring paths for `/api/voice/consultation`,
  `/api/records/from-image`, and related direct-create media helpers
- implementation must define whether legacy endpoints are rewritten in place or
  kept temporarily with explicit deprecated semantics

## Related ADRs

- [ADR 0002: Draft-First Record Persistence](0002-draft-first-record-persistence.md)
- [ADR 0006: One Patient Scope Per Turn](0006-one-patient-scope-per-turn.md)
- [ADR 0007: Stateful Blocked-Write Continuations](0007-stateful-blocked-write-continuations.md)
- [ADR 0008: Minimal Routing and Structuring-Only Note Generation](0008-minimal-routing-and-structuring-only-note-generation.md)
