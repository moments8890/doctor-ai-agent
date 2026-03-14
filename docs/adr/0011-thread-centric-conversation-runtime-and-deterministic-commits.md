# ADR 0011: Thread-Centric Conversation Runtime and Deterministic Commits

## Status

Accepted

## Date

2026-03-13

## Implementation Status

Complete

Last reviewed: 2026-03-13

Notes:

- This is the definitive runtime model for doctor-facing clinical conversations.
- Existing artifact tables remain the source of truth for committed clinical
  data.
- Scoped to MVP. Hardening concerns (staged promotion, automatic crash replay,
  unassigned intake lifecycle, park-and-resume for provisional notes) are
  deferred to a future ADR.

## Context

A clinical conversation assistant must balance safety (one patient per record,
draft-before-save, deterministic commits) with natural doctor workflow
(free-form dictation, multi-turn clarification, partial information).

With stronger models and larger context windows, the runtime can be reduced to
a small core that keeps a few hard invariants and lets the conversation model
manage the rest of the provisional state.

This ADR defines that minimal runtime, scoped to what moves the needle on
accuracy and usability for the MVP.

## Decision

Adopt a thread-centric conversation runtime with:

- one mutable context row per doctor
- one conversation-model call per turn with full recent history
- one deterministic commit engine
- draft-first persistence

### 1. Core invariants

- one patient per active context
- one patient per committed artifact
- a free-form turn that is ambiguous across multiple patients must clarify
  before context switch, memory patch, or durable commit
- pending draft before final medical record save
- only deterministic code may commit durable artifacts
- one active context per doctor at a time
- one doctor uses one channel at a time; cross-channel concurrency is out of
  scope for MVP

### 2. Storage model

The runtime adds one new table and reuses existing stores:

- `doctor_context`
  - one mutable row per doctor
  - the only live conversation state loaded and updated per turn
- `chat_archive` (existing)
  - continues to serve as the append-only turn log
  - used by the structuring step for raw turn content
- existing artifact tables remain unchanged:
  - `patients`
  - `pending_drafts`
  - `medical_records`

No new `conversation_turns`, `conversation_threads`, or `turn_receipts` tables
for MVP. The existing `chat_archive` is sufficient.

### 3. Context state model

Each `doctor_context` row has two logical sections: `workflow` and `memory`.

#### Workflow

`workflow` is authoritative and deterministic. Only deterministic product code
may mutate workflow fields.

It contains:

- `patient_id`
- `patient_name` (display cache)
- `pending_draft_id`

`pending_draft_id` doubles as the only blocking signal in MVP. When set, the
deterministic guard intercepts the next turn to check for confirm/abandon
before passing anything to the model. All other disambiguation (patient lookup,
destructive confirms, clarification) is handled by the conversation model as
normal turns, with the commit engine validating the result.

#### Memory

`memory` is provisional and LLM-facing.

It contains:

- `candidate_patient`
- `working_note`
- `summary`

`working_note` accumulates clinical facts during the conversation. It is used
as input to the structuring step alongside raw archived turns when generating
drafts. The structuring step should not rely solely on `working_note` for note
content; raw archived turns remain the primary source.

### 4. Patient switching

- a pending draft (`pending_draft_id` set) blocks patient switch; the doctor
  must confirm, abandon, or explicitly discard the draft first
- if `working_note` has accumulated content but no draft exists, the switch
  proceeds but the reply warns the doctor: e.g., "注意：关于王芳的未保存记录
  已清除"
- on switch, `workflow` resets (`patient_id`, `patient_name`,
  `pending_draft_id` all cleared) and `memory` resets
- the old context is not preserved for resume in MVP; the doctor can re-dictate
  or look up the patient again

This is a known UX trade-off. Doctors who frequently interleave patients will
lose provisional context on switch. This is acceptable for MVP because:

- drafted content is already persisted in `pending_drafts`
- raw turns are already persisted in `chat_archive`
- the alternative (multi-thread lifecycle) adds significant complexity with
  uncertain UX benefit before real usage data exists

### 5. Per-turn runtime

```text
turn
-> normalize input
-> de-dup by message ID (simple check, not atomic gate)
-> load doctor_context
-> deterministic guards
-> if not handled: conversation model
-> {reply, memory_patch, action_request?}
-> validate action_request
-> if create_draft: structuring step -> pending_draft
-> commit engine executes action
-> apply memory_patch to context
-> persist updated doctor_context
-> append turns to chat_archive
-> return reply
```

#### De-duplication

Channel adapters should pass a stable message identifier (e.g., WeChat
`MsgId`). The runtime checks whether that ID was recently processed and skips
duplicate deliveries. A simple in-memory or DB check is sufficient for MVP; no
atomic ingest gate or receipt state machine is required.

#### Concurrency

MVP assumes one doctor uses one channel at a time. No per-doctor mutex,
DB-level row locks, or doctor-scoped resolution locks are required. If
cross-channel concurrency becomes a real need, a future ADR should introduce
appropriate serialization.

### 6. Deterministic guards

Before the conversation model runs, the runtime checks for one condition:

- if `pending_draft_id` is set, the guard checks whether the doctor's input
  is a confirm or abandon; if yes, the commit engine handles it directly and
  the model is not called; if the input is neither, the guard re-prompts

All other conversational decisions — patient disambiguation, clarification,
destructive confirms — are handled by the conversation model as normal turns.
The commit engine validates the model's proposed action before executing.

### 7. Conversation model

The normal conversational path uses one conversation-model call per turn.

Input:

- current `doctor_context` (workflow + memory)
- recent turn history from `chat_archive`

Output:

- `reply` — text response to the doctor
- `memory_patch` — updates to the `memory` section
- optional `action_request` — proposed action for the commit engine

The model proposes actions but cannot commit durable state directly.

### 8. Action contract

Phase 1 action types:

- `none`
- `clarify`
- `select_patient`
- `create_patient`
- `create_draft`
- `create_patient_and_draft`

`create_patient_and_draft` is a bounded composite for the common first-turn
"new patient + note" flow. This does not create a general multi-action
execution engine.

### 9. Memory patch contract

`memory_patch` updates only the `memory` section.

Rules:

- the model cannot patch workflow fields
- the patch is validated against an allowlist of memory fields
  (`candidate_patient`, `working_note`, `summary`)
- invalid keys or types are logged and dropped
- simple replace semantics (not deep merge)
- if the turn is ambiguous across multiple patients, `memory_patch` must be
  dropped

### 10. Deterministic commit engine

The commit engine is the only code that writes durable artifacts.

It is responsible for:

- validating patient binding before any write
- setting the initial patient binding for an unbound context
- creating or selecting patients
- creating pending drafts
- confirming or abandoning drafts
- enforcing one patient per committed artifact

The commit engine must not silently rebind an established context to a
different patient. A patient switch clears the context (see section 4).

### 11. Structuring step

When `action_request.type` is `create_draft` or `create_patient_and_draft`,
the runtime runs one structuring step to generate the pending-draft note
content.

Input:

- recent doctor turns from `chat_archive` for the current patient context
- current workflow state (patient binding)
- `working_note` as an advisory hint for organization

Output:

- formatted note content → written directly to `pending_drafts.content`

The structuring step is the only note-generation path. The conversation model
must not generate saved note prose.

### 12. Recovery

MVP recovery is simple:

- `doctor_context` is persisted after every turn; on process restart, the
  latest persisted state is loaded
- if a turn was partially processed when the process died, the doctor retries
  by sending the message again (or the channel retries delivery)
- the de-dup check prevents double-processing if the retry carries the same
  message ID; if it does not, a duplicate turn is acceptable (the doctor sees
  a repeated response, which is harmless)
- `chat_archive` provides the full turn history for context reconstruction

No staged promotion, turn receipts, or automatic crash replay is required.

## Deferred to future ADR

The following concerns are explicitly out of scope for MVP. They should be
addressed in a hardening ADR when real traffic patterns justify the complexity:

- **Staged thread-state promotion**: atomic snapshot promotion that prevents
  partial state on crash
- **Turn receipt state machine**: ingested/completed lifecycle for automatic
  replay
- **Unassigned intake turns**: durable parking of turns that cannot be assigned
  to a context, with TTL expiry and late-binding
- **Multi-thread lifecycle**: active/closed thread states, deterministic resume
  of closed threads, park-and-resume for provisional notes
- **Formal append-only audit log**: a separate `conversation_turns` table with
  structured audit fields beyond what `chat_archive` provides
- **Source-turn-key derivation**: deterministic `turn_id` derived from stable
  `source_turn_key` for cross-channel idempotency
- **Working_note provenance cross-checking**: requiring `source_turn_id` on
  every working_note entry and cross-checking against archived turns during
  structuring
- **Cross-channel concurrency**: per-doctor mutex or DB-level serialization
  for doctors using multiple channels simultaneously
- **Typed blocking_state**: a general-purpose blocking cursor for patient
  disambiguate, destructive confirms, and other exact continuations beyond
  draft confirm/abandon

## Consequences

- the live runtime becomes much smaller: one context row per doctor, one
  conversation model call, one commit engine
- draft confirmation is the only deterministic guard; all other conversation
  decisions go through the model
- one `action_request` union keeps the action contract simple and bounded
- patient isolation is maintained by the commit engine's binding validation
  and the single-active-context invariant
- note generation stays bounded because only the structuring step can generate
  saved pending-draft prose
- provisional context is lost on patient switch (except drafted content and
  archived turns); this is a known trade-off documented in section 4
- recovery is manual (doctor retries); this is acceptable for MVP with
  single-process deployment
