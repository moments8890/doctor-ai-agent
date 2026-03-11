# Goal
Define a doctor-facing UX contract that keeps the product lightweight, safe, and fast to adopt, instead of drifting into a HIS-style management system.

# Summary

## Product position
- The product is a lightweight clinical assistant, not a miniature HIS.
- Its job is to help a doctor capture, query, and follow through with minimal navigation and data entry.
- The primary success metric is not feature breadth; it is repeat use after the first session.

## Core principle
- Let the doctor start in natural language.
- Keep one visible working context.
- Hide system complexity unless it is needed for a safe next step.

## What "simple" means
- One obvious place to act.
- Minimal concepts exposed to the doctor.
- Clear current state.
- Explicit handling of high-risk decisions.
- Recovery in one step.

# UX contract

## 1. One entrypoint, not one menu
- Both Web and WeChat should have one primary entrypoint: a unified input/composer surface.
- The doctor should not choose a module before doing useful work.
- That single entrypoint must support three common intents:
  - capture or update a clinical note
  - ask about a patient
  - check or act on pending tasks
- These are different outcomes, not different first screens.

## 2. One working context per turn
- The doctor-facing product should always operate around one visible working context.
- That context should translate internal workflow state into plain language:
  - current patient
  - pending draft status
  - what the system is waiting for next
- If there is no active patient, the interface should say so clearly instead of implying one.
- If there is ambiguity, the interface should surface the ambiguity instead of silently resolving it.

## 3. Let the doctor speak first
- Free text or voice should be the default input method for doctor workflow.
- The system should infer intent from the message instead of forcing the doctor through forms first.
- Structured forms may exist as secondary tools, but they must not define the default experience.

## 4. State must be visible, compact, and human-readable
- The doctor should be able to understand the current state in a quick glance.
- Visible state should be compact, not verbose or architectural.
- Doctor-facing state should never expose backend terms such as:
  - pending record IDs
  - router modes
  - tool calls
  - session internals
- Replace system jargon with next-step language such as:
  - "Current patient: Zhang San"
  - "Draft pending confirmation"
  - "Need patient name"

## 5. No silent high-risk automation
- The system must not silently:
  - switch patient binding
  - save a draft as a formal record
  - treat free text as confirmation for a high-risk action
- Convenience assumptions are allowed only when they are surfaced clearly and easy to undo.
- Confirmation friction should be proportional to risk:
  - low-risk read/query actions should stay lightweight
  - record persistence, patient switching, and destructive actions must be explicit

## 6. Recovery must be shorter than explanation
- When the system cannot proceed, it should ask for the single missing piece of information.
- Avoid long help menus and generic fallback dumps in conversational channels.
- Error recovery should usually fit into one reply and one next action.

## 7. Action first, management second
- The first layer of the product is for doctor work:
  - record
  - query
  - task follow-through
- The second layer is for operations and management:
  - labels
  - prompt editing
  - admin tables
  - debugging
  - exports
- Management pages can exist, but they must not define the product identity or home screen.

# Interface implications

## Shared doctor-facing layout contract
- Every doctor-facing surface should present the same mental model:
  - working context header
  - unified input/composer
  - recent useful outputs
- The working context header should show:
  - current patient or "no active patient"
  - pending draft state if any
  - next required action if blocked
- The unified composer should remain the dominant control on the screen.

## Web UI
- The Web product should feel like a workbench, not a dashboard of modules.
- The default page should center on:
  - current working context
  - one main input area
  - recent notes, tasks, or results tied to that context
- CRUD-heavy management pages should stay reachable but secondary.
- Avoid making the first screen a grid of admin destinations.

## WeChat
- WeChat should be the fastest capture and lightweight follow-up channel.
- Optimize for:
  - one-message clinical capture
  - one-message patient lookup
  - quick task handling
- Replies should be short, direct, and action-oriented.
- Draft confirmation in chat must behave like a real confirmation gate, not an implicit auto-save.

# Decision rules

## Patient binding
- Patient binding is part of the visible working context.
- If the system is using an active patient, that should be visible.
- If more than one patient is plausible, the system should ask, not guess.
- Silent rebinding is not acceptable.

## Draft handling
- Drafts are temporary working state, not saved records.
- A pending draft must remain visibly pending until explicit confirmation.
- Confirmation language should be predictable and channel-consistent.

## Task handling
- Task checks and lightweight task actions belong in the primary flow.
- Task administration and bulk operations belong in secondary management surfaces.

# Anti-patterns to avoid
- Turning the doctor home screen into a module picker.
- Making the user think in terms of records, tasks, labels, prompts, pending states, and exports before they can start.
- Exposing architecture instead of next-step guidance.
- Silent patient rebinding.
- Silent draft auto-save.
- Long generic fallback messages in chat.
- Overusing multi-step confirmations for low-risk operations.
- Mixing doctor workflow UI with admin/debug UI.

# Execution implications

## Done

3. ~~Tighten confirmation behavior for patient switching, record persistence, and destructive actions.~~
   - `set_current_patient()` now returns the previous patient name when a switch occurs (different patient_id).
   - All key callers in Web (`records_intent_handlers.py`: create_patient, add_record, query_records) and WeChat (`wechat_domain.py`: create_patient, add_record, query_records, name_lookup; `wechat_flows.py`: single-patient auto-bind) prepend a `🔄 已从【旧患者】切换到【新患者】` notification when the context switches.
   - Draft confirmation gate was already implemented (emergency bypass is intentional for clinical urgency).

## Done — concise fallback (Principle 6)

- Replaced verbose WeChat `_FALLBACK_TEXT` (6-item menu dump) with one-line message consistent with Web's `UNCLEAR_INTENT_REPLY`: "没太理解您的意思，能说得更具体一些吗？发送「帮助」可查看完整功能列表。"

## Done — draft auto-save removed (Principle 5)

- WeChat `handle_pending_record_reply` previously auto-saved unconfirmed drafts when the doctor sent a new message (silent high-risk automation). Changed to **abandon** the draft and notify: `⚠️ 【患者】的病历草稿已放弃。`
- Drafts now require explicit confirmation (`确认`/`保存`/`ok`) or explicit cancellation (`撤销`/`取消`) on both Web and WeChat. Any other message abandons the pending draft with a visible notice.
- Web path was already correct (explicit confirm/abandon endpoints, no auto-save).

## Satisfied by existing implementation
- Error messages: most error replies already follow the "one missing thing" pattern (e.g. "请问这位患者叫什么名字？", "⚠️ 未找到患者【X】").
- Free text / voice as default input: both Web and WeChat accept natural language as the primary input method. Intent is inferred, not form-driven.

## Deferred — frontend / follow-up

1. Build the doctor-facing experience around a single composer and a shared working-context header.
   - Requires frontend changes (new default route, working-context header component).
2. Align Web and WeChat around the same visible state model.
   - Patient switch notifications are now aligned. Pending-draft and waiting-for-next-step state are partially aligned but a shared header component is needed for full consistency.
4. Keep admin and management capabilities available but out of the default doctor workflow.
   - Current Web UI API routes are management-oriented. A dedicated doctor workbench entry route is needed.
5. Review new doctor-facing features against one question: does this reduce time-to-first-use, or does it make the product look more like a HIS?
   - Process guideline; no code change needed.

# Acceptance criteria

- [x] ~~The product never silently switches patient context or silently persists a draft.~~ — Patient switch notification implemented across all key call sites.
- [x] ~~Error replies in WeChat and Web usually ask for one missing thing, not a full menu of options.~~ — WeChat fallback shortened; most error messages already concise.
- [ ] A first-time doctor can start from one obvious input surface without choosing a module. — Deferred (frontend).
- [ ] At any moment, the doctor can tell who the current patient is and whether a draft is pending. — Partially: switch notifications added; visible header deferred (frontend).
- [ ] Admin/debug capabilities exist without dominating the doctor-facing default experience. — Deferred (frontend).

# Affected files
- services/session.py — `set_current_patient()` returns `Optional[str]` (previous patient name on switch)
- routers/records_intent_handlers.py — switch notifications in create_patient, add_record, query_records
- services/wechat/wechat_domain.py — switch notifications in create_patient, add_record (via `_resolve_add_record_patient`), query_records, name_lookup
- routers/wechat_flows.py — shortened `_FALLBACK_TEXT`; switch notification in single-patient auto-bind; **replaced draft auto-save with abandon + notify**
- tests/test_wechat_routes.py — updated fallback text assertions

# Risks / open questions
- Some current web routes are management-oriented; a true doctor workbench may need a new default entry route instead of incremental cleanup.
- Simplicity and safety can conflict; confirmation design must stay explicit without becoming heavy.
- If Web and WeChat diverge in wording for patient state or draft state, doctors will have to learn two mental models.
- The `handle_pending_create` and `handle_interview_step` call sites in `wechat_domain.py` do not yet include switch notifications; these flows have explicit doctor interaction (demographics entry, interview completion) that makes the context change expected, but could be tightened in a follow-up.
