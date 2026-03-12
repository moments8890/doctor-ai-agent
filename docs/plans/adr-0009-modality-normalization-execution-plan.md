# Goal

Implement [ADR 0009](../adr/0009-modality-normalization-at-workflow-entry.md)
with the smallest rollout that aligns all doctor-facing modalities with one
clear rule:

- voice enters the normal doctor-message workflow after transcription
- image and PDF enter import after extraction

# Status

`Complete`

# Why this plan exists

The current codebase already has the pieces needed for this direction:

- shared doctor-message workflow for text and `voice_chat`
- OCR/PDF extraction helpers
- an existing `import_history` workflow

But it still exposes conflicting modality shortcuts:

- `routers/voice.py:/consultation` transcribes, structures, and can save
  directly
- `routers/records.py:/from-image` and related media helpers directly structure
  a single `MedicalRecord` from extracted content
- image/PDF imports already exist on the WeChat side, but the same rule is not
  yet enforced consistently across channels

This plan removes those ambiguous entry semantics and makes modality handling
predictable.

# Scope

- doctor-facing audio input
- doctor-facing image upload
- doctor-facing PDF upload
- shared normalization helpers
- Web, WeChat, and voice entry surfaces where applicable

# Out of scope

- redesigning the internal chunking or parsing strategy of `import_history`
- non-doctor patient upload flows
- Word/document import changes beyond the same import-entry pattern
- prompt-level tuning unrelated to modality routing
- UI redesign beyond what is needed to call the correct backend path

# Success criteria

1. Audio sent by a doctor is transcribed and then processed by the same normal
   message workflow as typed text.
2. `/api/voice/consultation` no longer bypasses routing and draft-first safety
   for ordinary doctor workflow.
3. Image/PDF upload flows default to `import_history` after extraction instead
   of direct single-record structuring.
4. OCR/PDF extraction endpoints remain utility helpers and do not imply
   persistence semantics by themselves.
5. Architecture docs no longer describe modality-specific save shortcuts as
   part of the target design.

# Affected files

Voice:

- `routers/voice.py`

Web media and extraction:

- `routers/records.py`
- `routers/records_media.py`

WeChat media pipeline:

- `routers/wechat.py`
- `routers/wechat_flows.py`
- `services/wechat/wecom_kf_sync.py`
- `services/wechat/wechat_import.py`

Shared workflow / helpers:

- `services/intent_workflow`
- optional shared modality-entry helper if introduced

Docs:

- `ARCHITECTURE.md`
- `docs/adr/0009-modality-normalization-at-workflow-entry.md`
- `docs/review/architecture-overview.md`

# Execution phases

## Phase 1. Converge voice consultation into the normal message workflow

Purpose:

- remove the main remaining audio-only workflow exception

Implementation steps:

1. Refactor `routers/voice.py:/consultation` so it:
   - transcribes audio
   - reuses the same doctor workflow entry as `voice_chat`
   - preserves any needed transcription hint such as `consultation_mode`
     as metadata only
2. Remove direct structuring-and-save behavior from the consultation path.
3. Keep `save=true` only if it means confirming or finalizing through the same
   pending-draft contract; otherwise remove it.
4. Keep `/transcribe`-style utility behavior separate from workflow behavior.

Exit criteria:

- [x] audio input no longer has a direct-save consultation bypass
- [x] voice workflow safety matches typed doctor-message safety
- Done: commit c2104d5+

## Phase 2. Make image/PDF uploads enter import by default

Purpose:

- stop treating extracted document text as a normal single fresh note

Implementation steps:

1. Define one shared rule for extracted image/PDF content:
   - extracted text + source metadata
   - dispatch to `import_history`
2. Update Web upload entrypoints that currently create a `MedicalRecord`
   directly from image/PDF-derived text.
3. Preserve extraction-only helpers such as OCR or extract-file endpoints for
   UI preview and tooling.
4. Ensure `Intent.import_history` receives the correct `source` metadata
   (`image`, `pdf`, or equivalent).

Exit criteria:

- [x] image/PDF doctor uploads do not default to direct single-record structuring
- [x] import behavior is the default post-extraction path
- Done: `/from-image` and `/from-audio` now OCR/transcribe then call import_history

## Phase 3. Align cross-channel modality behavior

Purpose:

- keep Web, WeChat, and voice consistent

Implementation steps:

1. Verify WeChat image/PDF paths already land in import and clean up any
   remaining divergent handling.
2. Make voice, Web, and WeChat all follow the same top-level modality rule:
   - audio -> normal message
   - image/PDF -> import
3. If a shared modality-entry helper reduces duplication, introduce it instead
   of keeping router-local branching.

Exit criteria:

- [x] channel does not change the modality rule
- [x] modality routing is understandable from one shared architecture description
- Done: WeChat image/PDF already routed via `[Image:ocr]`/`[PDF:]` → import_history.
  Web and voice now match after Phase 1+2. All channels follow same rule.

## Phase 4. Deprecate or repurpose legacy direct-create endpoints

Purpose:

- avoid leaving old APIs that contradict the architecture

Implementation steps:

1. Decide which endpoints remain as compatibility wrappers and which are
   deprecated:
   - `/api/voice/consultation`
   - `/api/records/from-image`
   - `/api/records/from-audio`
   - any mirrored media router endpoints
2. If kept, make their behavior conform to ADR 0009 rather than preserving old
   semantics.
3. Update API docs and comments so the deprecation or new behavior is explicit.

Exit criteria:

- [x] no public-facing endpoint silently contradicts the modality rule
- Done: All three endpoints (`/consultation`, `/from-image`, `/from-audio`) now
  conform to ADR 0009. `records_media.py` is unmounted dead code (only tested
  in isolation). `ConsultationResponse` model removed.

## Phase 5. Update architecture docs and operator guidance

Purpose:

- keep product and engineering docs aligned with the shipped behavior

Implementation steps:

1. Update `ARCHITECTURE.md` workflow sections.
2. Update `docs/review/architecture-overview.md`.
3. Add any needed operator notes for frontends or integrations that call media
   endpoints directly.

Exit criteria:

- [x] the documented modality model matches production behavior
- Done: ARCHITECTURE.md updated with ADR 0009 modality normalization model

# Risks and watchpoints

- `import_history` is intentionally bulk/history-oriented and may need guardrails
  when the uploaded image is actually a single current visit note
- changing `/api/voice/consultation` semantics may affect any client that
  expects a direct `MedicalRecord` payload today
- compatibility wrappers must be explicit; silent behavior changes will confuse
  UI and integration code

# Recommended order

1. Phase 1: voice consultation convergence
2. Phase 2: image/PDF import-by-default
3. Phase 3: cross-channel cleanup
4. Phase 4: endpoint deprecation or wrapper cleanup
5. Phase 5: architecture/doc sync
