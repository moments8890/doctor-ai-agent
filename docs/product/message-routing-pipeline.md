# Message Routing Pipeline

> Last updated: 2026-03-12

Current routing flow for doctor messages across all three channels: web chat,
WeChat, and voice.

This document replaces the older Tier-3 clinical-keyword description. The live
system now uses a shared 5-layer intent workflow, with `fast_route` limited to
deterministic Tier 0-2 rules and the LLM used as a classification fallback
when rules do not match.

---

## Scope

This is the canonical pipeline for:

- Web doctor chat: `POST /api/records/chat`
- Main WeChat doctor message handling in `routers/wechat.py`
- Voice doctor chat: `POST /api/voice/chat` (transcription + shared workflow)

All three channels use the same `services.intent_workflow.run()` entry point
and dispatch to the same set of shared handlers in `services/domain/intent_handlers/`.

Notes:

- `routers/voice.py` `/api/voice/consultation` endpoint is a separate explicit
  structured-recording flow that does not use the shared workflow
- `services/ai/router.py` remains as a legacy helper for some WeChat flow
  helpers, but it is not the main pipeline documented here

---

## End-to-End Flow

```text
Doctor sends message
        │
        ▼
Channel entrypoint
  Web:    routers/records.py::_chat_for_doctor()
  WeChat: routers/wechat.py::_handle_intent()
  Voice:  routers/voice.py::_voice_chat_for_doctor() (after transcription)
        │
        ▼
Channel prechecks / deterministic fast paths
  - rate limit / greeting / menu shortcut / notify control
  - knowledge-base command interception
  - task completion and a few channel-specific direct handlers
        │
        ▼
Load doctor knowledge context (best effort)
  services/knowledge/knowledge_cache.py — per-doctor TTL cache (5 min)
        │
        ▼
services.intent_workflow.run()
  1. classify  -> menu shortcut OR fast_route OR LLM dispatch
  2. extract   -> resolve patient/gender/age with provenance
  3. bind      -> decide bound / has_name / no_name / not_applicable
  4. plan      -> annotate compound actions
  5. gate      -> block unsafe writes / require clarification
        │
        ▼
WorkflowResult -> IntentResult
        │
        ▼
Intent handler dispatch (shared handlers)
  create_patient / add_record / query_records / list_tasks / ...
        │
        ├─ add_record / update_record
        │    -> assemble record from structured fields or structuring LLM
        │    -> emergency record saves immediately
        │    -> non-emergency record becomes pending draft for confirmation
        │
        └─ read / task / export / patient-management intents
             -> execute directly
```

---

## Channel Entry And Prechecks

### Web (`routers/records.py`)

Before the workflow runs, web chat may intercept:

- rate limiting
- notify-control commands
- greetings
- menu-number shortcuts after an unclear-intent menu
- bare-name follow-up replies
- task completion fast path
- additional direct fast paths inside `chat_core()`:
  - patient count
  - delete patient by numeric ID
  - save doctor context
  - knowledge-base commands

If none of those returns a response, web loads doctor knowledge context and
calls `services.intent_workflow.run()`.

### WeChat (`routers/wechat.py`)

Before the workflow runs, WeChat may intercept:

- task completion fast path
- notify-control commands
- knowledge-base commands

If no interception matches, WeChat loads doctor knowledge context and calls
the same workflow.

If the workflow itself fails, WeChat still has a structuring fallback for
resilience: try `structure_medical_record(text)`, on failure return a generic
retry message.

### Voice (`routers/voice.py`)

Voice entry:

1. Transcribe uploaded audio via `transcribe_audio()`
2. Check for followup-name pattern (if the last turn asked for a patient name)
3. Run the shared 5-layer workflow with `channel="voice"`
4. Dispatch to the same shared handlers used by Web and WeChat

Voice follows the same draft-first safety model: non-emergency records create
a pending draft for explicit confirmation rather than saving directly.

---

## Layer 1: Classification

Classification happens in `services/intent_workflow/classifier.py`.

Resolution order:

1. `effective_intent` / menu shortcut if the channel already resolved one
2. `fast_route(text, session=...)`
3. `agent_dispatch(...)` if `fast_route` returns `None`

### What `fast_route` does now

`fast_route` is conservative and deterministic. It no longer performs Tier-3
clinical keyword routing.

Current coverage:

- Tier 0
  - `help`
  - `import_history` for `[PDF:]`, `[Word:]`, `[Image:]`, or long multi-date
    history text
- Tier 1
  - `list_patients`
  - `list_tasks`
- Tier 2
  - task actions: `complete_task`, `cancel_task`, `postpone_task`
  - follow-up scheduling: `schedule_follow_up`
  - appointment scheduling: `schedule_appointment`
  - export actions: `export_records`, `export_outpatient_report`
  - record queries: `query_records`
  - patient CRUD: `create_patient`, `delete_patient`, `update_patient`
  - explicit supplement patterns: `add_record`
  - mixed-message tail-command override such as clinical text followed by a
    command suffix
  - pending-draft continuation when a session already has `pending_record_id`

Session-aware behavior:

- when a matched intent has no `patient_name`, `fast_route` can backfill the
  current patient from session state
- LLM dispatch also receives session context such as `specialty`,
  `doctor_name`, `current_patient_context`, candidate patient context, and
  not-found patient context

---

## Layer 2: Entity Extraction

Entity extraction happens in `services/intent_workflow/entities.py`.

It does more than trust the raw classifier output. Patient name resolution
follows a fallback cascade:

1. follow-up bare-name reply from the previous turn
2. `IntentResult.patient_name` from fast route or LLM
3. leading-name pattern in the current text for `add_record`
4. recent history
5. current patient in session
6. weak session candidates:
   - `candidate_patient_name`
   - `patient_not_found_name`

Each entity keeps provenance, for example:

- `fast_route`
- `llm`
- `followup`
- `text_leading_name`
- `history`
- `session`
- `candidate`
- `not_found`

This provenance is used downstream by binding, gating, logging, and
draft-confirmation behavior.

---

## Layer 3: Patient Binding

Patient binding happens in `services/intent_workflow/binder.py`.

It does not write to the database. It only decides how strong the current
patient context is:

- `bound`
  - patient already resolved by ID from session
- `has_name`
  - a patient name exists, but the handler still needs to resolve or create
    the patient
- `no_name`
  - no usable patient context is available
- `not_applicable`
  - the intent does not need a patient

Weak sources such as `candidate` and `not_found` are marked
`needs_review=True`.

---

## Layer 4: Action Planning

Planning happens in `services/intent_workflow/planner.py`.

This layer annotates compound intent patterns so downstream handlers and logs
have structure, for example:

- `create_patient` + clinical content -> create patient, then add record
- `create_patient` + reminder text -> create patient, then create task

The planner is metadata-oriented. Actual execution still happens in the
existing intent handlers.

---

## Layer 5: Safety Gate

Safety checks happen in `services/intent_workflow/gate.py`.

Current gate rules:

- read-only intents are allowed through
- write intents with no patient context are blocked with a clarification
  question
- `not_found` attribution without explicit location context (`ICU`, `PACU`,
  bed number, ward, etc.) is blocked
- weak attribution may be allowed, but flagged for confirmation

Typical blocked replies:

- `Please specify the patient name`
- `Patient [X] not found, please create or specify`

Typical allowed-but-review-required behavior:

- create a pending draft instead of silently saving
- return a warning such as "draft generated for candidate patient, please
  verify before confirming"

Channel note:

- Web respects the gate directly and returns the clarification message
- WeChat has one intentional exception: when the gate reason is
  `no_patient_name`, it still lets the downstream handler attempt its own
  patient-resolution logic before giving up

---

## Handler Execution

After gating, `WorkflowResult` is converted back into a backward-compatible
`IntentResult` and dispatched to shared handlers in
`services/domain/intent_handlers/`.

Common handlers:

- `create_patient`
- `add_record`
- `query_records`
- `list_patients`
- `delete_patient`
- `list_tasks`
- `complete_task`
- `schedule_appointment`
- `update_patient`
- `update_record`
- `help`

### `add_record`

This is the most important post-routing path:

1. resolve or create the patient
2. pin the resolved patient into session state
3. build the record
   - reuse `structured_fields` from the routing LLM when available, or
   - call `assemble_record()` which filters history down to clinical-only
     turns and may call the structuring LLM
4. save immediately only for emergency records
5. otherwise create a pending draft and require confirmation

The shared record-assembly path also adds:

- clinical-only history filtering
- encounter-type detection
- prior-visit summary injection for follow-up encounters

### Query / list / export / task intents

These typically execute directly after routing and may also update session
context, for example:

- querying a patient record pins that patient as the current session patient
- some list-task mixed messages capture a candidate patient into session for
  the next turn

---

## Session State Matters

The workflow is intentionally session-aware. Routing quality depends on state
captured from prior turns, including:

- current patient ID and name
- pending draft ID
- candidate patient name, gender, age
- last not-found patient name
- doctor specialty and doctor name

This is why short follow-up messages can often resolve without a new patient
name.

---

## Operational Notes

- The active fast router lives in the package `services/ai/fast_router/`, not
  the old monolithic `services/ai/fast_router.py`
- Tier-3 clinical keyword routing is not part of the live path anymore
- Keywords are compiled into `services/ai/fast_router/_keywords.py`; the admin
  reload endpoint is now informational and does not hot-reload runtime behavior
- `data/mined_rules.json` loader still exists, but mined rules are not part of
  the current canonical routing path

---

## Historical: Tier-3 Classifier Benchmark (2026-03-08)

The TF-IDF + logistic regression binary classifier (`services/ai/tier3_classifier.pkl`)
was deployed as a final gate inside `_is_clinical_tier3()`. This path is now
inactive -- the live system routes ambiguous clinical messages through LLM
dispatch instead. The classifier remains available for future use.

5-fold CV F1: **0.978 +/- 0.002**. See git history for full benchmark tables.
