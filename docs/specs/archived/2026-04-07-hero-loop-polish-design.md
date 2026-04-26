# Hero Loop Polish — Design Spec (v2)

**Date:** 2026-04-07
**Goal:** Polish the follow-up reply hero loop to A+ quality for a solo neurosurgeon pilot (~5-10 patient messages/day via WeChat mini program).
**Hero loop:** Patient sends message → triage classifies → AI draft generates → doctor reviews in web dashboard → edits/approves → sends.

---

## Context

- Solo trial — no hand-holding, doctor decides in 10 minutes
- Low volume — ~5-10 messages/day, each interaction must feel excellent
- WeChat mini program — full triage→draft pipeline fires automatically
- Neurosurgery specialty
- Notification infrastructure already built (just needs env config)

## Changes

### 1. Remove Citation Gate — All Messages Get Drafts

**Problem:** `draft_reply.py:117` silently drops drafts when no KB citation is found. For a new doctor with sparse/empty KB, most messages get NO draft. The hero loop never fires.

**Change:** Remove the `return None` gate at `draft_reply.py:117-119`. All inbound patient messages now get an AI draft regardless of KB citation status.

- No new `draft_source` column — the frontend can compute grounded vs ungrounded from the existing `cited_knowledge_ids` field (non-empty = grounded, empty = reference)
- No changes to `confidence` field
- The existing "no draft / manual reply" UI state in `MessageTimeline.jsx` remains for genuine LLM failures (empty response, exception, persistence error)

**Files:**
- `src/domain/patient_lifecycle/draft_reply.py` — remove lines 117-119 (the citation gate)

**What stays unchanged:**
- `SIGNAL_FLAG_KEYWORDS` and `detect_signal_flags()` — still adds the warning prompt hint for dangerous messages. Low cost, no harm.
- `cited_knowledge_ids` — still extracted and stored. Empty list = no KB grounding.
- Draft persistence — unchanged, all drafts now saved.

### 2. Silent Edit Logging in `send_doctor_reply()`

**Problem:** To build the persona later, we need edit pairs (original draft text vs final sent text). Currently `log_doctor_edit()` is only called from the `edit_draft` endpoint, missing:
- Sends without editing (positive signal: doctor approved as-is)
- Direct replies from `patient_detail_handlers.py:285` (no draft involved)

**Change:** Add edit logging to `send_doctor_reply()` in `reply.py` — the single funnel for all doctor replies.

When `draft_id` is provided:
- Load the draft's `draft_text` as `original_text`
- Use the final `text` param (pre-disclosure) as `edited_text`
- Call `log_doctor_edit(entity_type="draft_reply", ...)`
- Log even if unchanged (original == edited) — this is a positive signal

When `draft_id` is None (manual reply, no draft):
- Log with `original_text=""`, `edited_text=text`, `entity_type="manual_reply"`
- Still useful for persona: shows the doctor's natural voice

**Files:**
- `src/domain/patient_lifecycle/reply.py` — add `log_doctor_edit()` call after saving the outbound message

### 3. Persona — Doctor-Confirmed Living Document

**Problem:** The doctor's communication style should shape AI drafts. But auto-applying LLM-extracted patterns risks hallucination silently corrupting future drafts.

**Change:** One persona KB item per doctor. Background extraction produces a **draft** that the doctor must confirm before it's injected into prompts.

#### Lifecycle

| Step | Trigger | What happens | Doctor sees |
|---|---|---|---|
| **Create** | Lazy — first draft send or first knowledge page visit | Empty persona item created with template headers | Pinned card: `我的AI人设 · 待学习` |
| **Collect** | Every doctor reply | Edit pairs logged in `send_doctor_reply()` (Change 2) | Nothing |
| **Extract** | 15+ new `draft_reply` edits since last extraction | Background task: LLM analyzes edit pairs, generates persona text, saves as draft | Notification: `AI已分析你的回复风格 · 查看并确认` |
| **Review** | Doctor taps notification or visits knowledge page | Doctor reads extracted persona, edits freely, taps confirm | Persona card shows full text, editable |
| **Activate** | Doctor confirms | `persona_status` set to `active`. Persona injected into prompts. | Card: `我的AI人设 · 已启用 · 基于 N 条回复` |
| **Re-extract** | 15+ new edits since last extraction | New draft generated. If persona is already active, shows as "suggested update" for doctor to merge/replace/ignore | Card shows diff or update prompt |

#### Key safety rule

**Persona is NOT injected into prompts until `persona_status == "active"`.** Draft persona has zero effect on AI output.

#### Data model

On `DoctorKnowledgeItem`:
- `category = "persona"` (new enum value)
- `source = "system"`
- New field: `persona_status` — `"draft"` or `"active"` (only applies to persona category)

Uniqueness: `get_or_create_persona(doctor_id)` helper — queries by `category="persona" AND doctor_id`, creates if missing. No unique DB constraint needed; the helper is the single creation path.

#### Lazy creation (not onboarding-dependent)

The persona item is created by `get_or_create_persona()` on first use, not in onboarding. This covers:
- Existing doctors who already completed onboarding
- Doctors created via auth paths other than onboarding wizard
- No backfill needed

#### Extraction trigger

Not a periodic scheduler job. Instead, triggered inline (fire-and-forget background task) from `send_doctor_reply()` when:
1. `draft_id` is provided (this was a draft-based reply)
2. Count of `DoctorEdit` records with `entity_type="draft_reply"` since last extraction >= 15

This avoids APScheduler complexity. At 5-10 msgs/day, extraction runs at most once every 2-3 days.

#### Prompt injection

Only when `persona_status == "active"`:

```python
# In knowledge_context.py — load persona SEPARATELY from scored KB items
persona = get_or_create_persona(doctor_id)
if persona and persona.persona_status == "active":
    persona_text = persona.content
else:
    persona_text = ""
```

Persona is injected as a dedicated block BEFORE the top-5 scored KB items:

```xml
<doctor_persona>
回复风格：正式但温和
常用结尾语：有不适随时联系
</doctor_persona>

<doctor_knowledge>
[KB-1] 术后复查建议...
</doctor_knowledge>
```

This bypasses the existing score/top-5 logic entirely. Persona never competes with regular KB items.

#### Template (empty persona)

```
## 回复风格
（AI会根据你的回复逐渐学习，你也可以直接编辑）

## 常用结尾语

## 回复结构

## 回避内容

## 常见修改
```

#### Doctor-facing UI

Knowledge page → pinned card at top (filtered out of regular list to avoid duplicate):
- **Draft state:** Title `我的AI人设`, subtitle `待学习 · 已收集 N 条回复`, muted styling
- **Draft ready:** Title `我的AI人设`, subtitle `AI已分析你的风格 · 点击查看`, highlighted with accent color
- **Active:** Title `我的AI人设`, subtitle `已启用 · 基于 N 条回复 · 上次更新 MM-DD`
- Tap → full text editor (same as any KB item) + confirm/deactivate button

**Files:**
- `src/db/models/doctor.py` — add `persona` to `KnowledgeCategory` enum, add `persona_status` field to `DoctorKnowledgeItem`
- `src/domain/knowledge/teaching.py` — new `get_or_create_persona()`, new `extract_persona()` (produces draft, does not auto-activate)
- `src/domain/knowledge/knowledge_context.py` — load persona separately, inject before scored items, only when active
- `src/domain/patient_lifecycle/reply.py` — trigger extraction check after logging edit
- `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx` — pin persona card at top, filter from regular list
- `src/channels/web/doctor_dashboard/knowledge_handlers.py` — API endpoint to confirm/activate persona

### 4. Batch Delay Reduction

**Problem:** `triage_handlers.py:159` has `_DRAFT_BATCH_DELAY = 30`. At 5-10 msgs/day, 30s makes the app feel broken with no batching benefit.

**Change:** `_DRAFT_BATCH_DELAY = 5`

**Known limitation:** The batch mechanism is per-process and `_delayed_generate()` passes only the latest message text, not all unresponded messages (despite the docstring). This is acceptable for the pilot (single worker, low volume). Document as tech debt.

**Files:**
- `src/domain/patient_lifecycle/triage_handlers.py` — one constant change

---

## Deferred to Post-Pilot

| Item | Why defer |
|---|---|
| UI green/amber draft distinction | Doctor reads every draft at low volume. Compute from `cited_knowledge_ids` later if needed. |
| patient_id type mismatch fix | Works on SQLite at pilot scale. Fix before MySQL production. |
| Batch mechanism rewrite (multi-message collection) | Single worker, low volume. Fix when scaling. |
| Neuro-specific signal flag keywords | Triage LLM handles urgency. Existing generic keywords are adequate. |
| Review queue restructuring | Premature before real usage data. |

## What We Cut (from v1 spec)

- ~~`draft_source` DB column~~ — redundant with `cited_knowledge_ids`. Compute in API if needed.
- ~~Auto-applied persona~~ — replaced with doctor-confirmed draft flow.
- ~~Periodic APScheduler job~~ — replaced with inline trigger from `send_doctor_reply()`.
- ~~Onboarding-dependent persona creation~~ — replaced with lazy `get_or_create_persona()`.
- ~~Per-reply teaching toast~~ — replaced by silent collection + background extraction.
- ~~Confidence score changes~~ — not needed.

## Success Criteria

- [ ] Doctor with empty KB sees AI drafts for every patient message (no silent drops)
- [ ] Every doctor reply (draft-based or manual) is logged as an edit pair
- [ ] Persona item exists on knowledge page (lazy-created on first use)
- [ ] After 15+ draft-based replies, persona draft is generated and doctor is notified
- [ ] Persona is NOT injected into prompts until doctor explicitly confirms
- [ ] Draft appears within ~10s of patient message (not 30s)

## Review History

- **Codex review (2026-04-07):** 12 issues found. Key: persona provenance missing, edit logging in wrong place, onboarding not the only doctor creation path, prompt priority doesn't match code, 3 UI states needed not 2.
- **Claude agent review (2026-04-07):** 12 issues found. Key: persona extraction can hallucinate and silently corrupt drafts (trust-destroying), direct-reply path untracked, `draft_source` column redundant with `cited_knowledge_ids`, `knowledge_context.py` hard-caps at 5 items with no category priority.
- **v2 resolution:** Persona changed from auto-apply to doctor-confirmed draft. `draft_source` column removed. Edit logging moved to `send_doctor_reply()`. Lazy persona creation replaces onboarding-dependent. Persona loads separately from scored KB items. patient_id fix deferred.
- **ChatGPT architectural review (2026-04-07):** Some valid points on feature breadth, but several critiques based on outdated repo understanding (routing LLM already removed, knowledge system already categorized).
