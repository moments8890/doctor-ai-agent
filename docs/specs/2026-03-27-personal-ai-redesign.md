# Personal AI Redesign — Product & UI Spec

> Date: 2026-03-27
> Status: Approved (mockups reviewed)
> Mockups: `docs/ux/mockups/tab-*.html`

---

## 1. Product Vision

### What We Are

A **personal AI follow-up copilot** for specialists managing recurring
patients. The doctor's clinical expertise, guidelines, communication style,
and treatment preferences shape every AI output — diagnosis review, follow-up
drafts, patient triage. The AI learns from the doctor's edits and decisions,
getting smarter with use.

Operates within the doctor's existing patient relationships (WeChat, portal,
or clinic channels). Positioned as a copilot for follow-up and review, not
as a standalone diagnostic or prescribing system.

### What We Are Not

- Not a hospital EMR/HIS/PMS
- Not an appointment/billing/prescription system
- Not an autonomous diagnostic or prescribing system
- Not a generic medical chatbot
- Not a replacement for the physician's clinical judgment

### Core Value Proposition

**"This AI thinks like me."** The doctor's own rules, case history, and
communication style shape every AI output. The product gets smarter with
every interaction.

### Competitive Landscape

Doctors can already assemble a comparable stack:

| Need | Current alternatives |
|------|---------------------|
| Documentation | Freed, Heidi, Nabla, Abridge |
| Clinical answers | OpenEvidence, Heidi Evidence |
| Personal knowledge | ChatGPT Projects, Claude Projects |
| Patient comms | Artera, Hippocratic AI |
| "Doctor twin" | GoodDoctorAI |

**Our moat is not any single feature — it is the integrated loop:**
personal knowledge → patient context → personalized reasoning → doctor
feedback → compounding improvement.

### What Makes a Doctor Pay

1. The AI reliably sounds like them, not generic
2. It improves visibly after they teach it
3. It saves real time on daily tasks (replies, diagnosis review)
4. They can see and control what rules it uses
5. It's easier than maintaining their own ChatGPT setup

---

## 2. UI Redesign

### Navigation: 4 Bottom Tabs

```
┌─────────────────────────────────────┐
│   ◆        👤        ☑        ✉    │
│  我的AI    患者      审核      随访   │
└─────────────────────────────────────┘
```

- Settings merged into 我的AI (top-right "设置" action)
- Active tab: green `#07C160`
- Badges: red dot + count on 审核 and 随访

### Design System Compliance

All designs follow `docs/ux/UI-DESIGN.md`:

- WeChat-native flat: no shadows, no gradients
- Green `#07C160` primary, `#ededed` background, white `#fff` cards
- Typography from `theme.js` TYPE tokens only
- Hairline borders (`0.5px solid #e5e5e5`)
- Destructive left, constructive right
- Chinese-first, function over decoration

---

### 2A. 我的AI Tab (Home)

**File:** Replaces `HomePage.jsx` + `HomeSubpage.jsx`
**Mockup:** `docs/ux/mockups/tab-my-ai.html`

**Top bar:** `我的AI` (title) + `设置` (green action, right)

**Layout (top to bottom, fits in ~1.5 screens):**

#### Hero Identity Card

```
┌──────────────────────────────────────┐
│ [AI]  张医生AI              在线     │
│       神经外科 · 已学会 12 条规则     │
├──────────────────────────────────────┤
│    26        │     2      │    3     │
│  7天引用      │   待确认    │  今日处理 │
├──────────────────────────────────────┤
│ 刚刚在李阿姨复诊中用了「术后头痛危险信号」  │
├──────────────────────────────────────┤
│  [ 继续教AI ]      [ 导入病例 ]      │
└──────────────────────────────────────┘
```

- Avatar: green square `#07C160` with "AI" text
- Stats: 3-column row (7天引用 / 待确认 / 今日处理)
- Live status: 1 line showing most recent AI activity with knowledge citation
- CTAs: primary green "继续教AI" → knowledge page, secondary "导入病例" → import flow

#### Quick Actions (list rows)

```
┌──────────────────────────────────────┐
│ [◫]  患者预问诊码                  › │
│      患者扫码自助填写病史              │
├──────────────────────────────────────┤
│ [✓]  待审核                    3  › │
│      AI建议等你确认                   │
├──────────────────────────────────────┤
│ [💬] 处理随访                   5  › │
│      患者消息可快速处理               │
└──────────────────────────────────────┘
```

- Standard `ListCard` rows with colored square icons
- 患者预问诊码: generates QR code for patients to scan and enter interview
- Badges on 待审核 (amber) and 处理随访 (red)

#### 我的方法 (knowledge preview)

Section label: `我的方法 · 最近活跃` + `全部 12 条 ›` link

```
┌──────────────────────────────────────┐
│ ● 术后头痛危险信号                 今天3次│
│   先排除再出血，再评估颅压             │
├──────────────────────────────────────┤
│ ● TIA复查路径                 本周5次│
│   48h内颈动脉超声+MRA                │
├──────────────────────────────────────┤
│ ● 随访安抚话术                  待确认│
│   先共情再给时间节点                  │
└──────────────────────────────────────┘
```

- Green dot = active, amber dot = pending confirmation
- Each row: rule title + summary + usage count or status
- Tap → rule detail; "全部" → full knowledge management page

#### 最近由AI处理

Section label: `最近由AI处理` + `全部 ›`

- 2 patient rows showing AI actions (e.g., "按你的话术起草了随访回复")
- Standard `ListCard` with `PatientAvatar`

---

### 2B. 患者 Tab

**File:** Modifies `PatientsPage.jsx`
**Mockup:** `docs/ux/mockups/tab-patients.html`

**Top bar:** `患者` (title) + `新建` (green action)

**Layout:**

1. **Search bar** — 搜索患者姓名
2. **AI建议关注** — patients flagged by doctor's own rules
   - Each row: patient avatar + name + reason citing the doctor's rule
   - Badges: 紧急 (red outlined) / 待处理 (amber outlined)
   - Example: "术后第7天 · 按你的规则 需复查CT"
3. **Patient list** — `全部 · 12位患者`
   - `+ 新建患者` card at top
   - Each row: avatar + name + gender·age + AI status
   - AI status examples: `AI: 需复查CT` / `AI: 引用2条规则` / `AI: 回复已起草`
   - Older patients without AI activity show plain clinical context
4. **No filter chips** for MVP (<50 patients, search is sufficient)

**Key difference from current:** Each patient row shows what AI knows/did,
not just demographics. The AI建议关注 section surfaces patients needing
action based on the doctor's own rules.

---

### 2C. 审核 Tab

**File:** Replaces current review flow entry point
**Mockup:** `docs/ux/mockups/tab-review.html`

**Top bar:** `审核` (title)

**Layout:**

1. **Summary bar** — 3-column stats
   - 待审核 (amber) / 已确认 / 已修改
2. **待审核 items** — each item contains:
   - Header: patient avatar + name + time + urgency badge
   - Diagnosis preview: gray `#f7f7f7` card with title + detail text
   - Citation line: "引用了你的规则：术后头痛危险信号" (green tag)
   - Or: "未引用个人规则" (gray) — signals generic AI reasoning
   - Actions (right-aligned text): `✗ 排除` (red) `✎ 修改` (blue) `✓ 确认` (green)
3. **最近已审核** — greyed-out history rows
   - ✓ (green) = confirmed, ✎ (amber) = modified
   - Shows what was done: "已确认 · 引用了你的 1 条规则"

**Key design choice:** "未引用个人规则" contrast makes the doctor want to
teach AI more rules. The citation line is the trust primitive.

---

### 2D. 随访 Tab

**File:** Replaces `TasksPage.jsx` concept
**Mockup:** `docs/ux/mockups/tab-followup.html`

**Top bar:** `随访` (title)

**Layout:**

1. **Summary bar** — 3-column stats
   - 待回复 (red) / AI已起草 (amber) / 即将到期
2. **患者消息 · 待回复** — each item contains:
   - Header: patient avatar + name + time + badge (新消息/紧急)
   - Patient message: gray `#f7f7f7` bubble with actual message text
   - AI draft reply: white card with green border
     - Label: "AI按你的话术起草"
     - Draft text in doctor's communication style
     - Citation: "引用：随访安抚话术" (green tag)
   - Actions: `✎ 修改` (blue) + `发送 ›` (green)
3. **即将到期的随访** — upcoming follow-up tasks
   - Clock icon + patient·task description + date
   - Amber date for urgent (今天/明天)
4. **最近已发送** — sent message history
   - ✓ (green) + patient·task + "已发送 · 患者已读/未读"

**Key product moment:** Doctor opens tab, sees AI already drafted replies
in their voice with rule citations, taps 发送. This is the daily habit loop.

---

## 3. Backend Changes

### 3A. Knowledge Usage Tracking

**Purpose:** Track when and where knowledge rules are cited by the AI.

**Changes:**

- New table `knowledge_usage_log`:
  - `id`, `doctor_id`, `knowledge_item_id`, `usage_context` (enum: diagnosis/chat/followup/interview)
  - `patient_id` (nullable), `record_id` (nullable), `created_at`
- When prompt_composer injects KB items and LLM returns `[KB-id]` citations,
  log each citation to this table
- New API endpoints:
  - `GET /api/manage/knowledge/stats` — per-item usage counts, last used time, total 7-day count
  - `GET /api/manage/knowledge/activity` — recent usage events (for 我的AI activity feed)

### 3B. AI Activity Feed

**Purpose:** Aggregate recent AI actions across patients for the 我的AI tab.

**Changes:**

- New API endpoint: `GET /api/manage/ai/activity`
- Returns recent events: knowledge citations, diagnosis generated, draft replies created, tasks auto-generated
- Sources: knowledge_usage_log + ai_suggestions + patient_messages + tasks
- Query layer only — no new tables, aggregates from existing data + 3A's new table

### 3C. AI-Flagged Patients

**Purpose:** Surface patients needing attention based on doctor's own rules.

**Changes:**

- New API endpoint: `GET /api/manage/patients/ai-attention`
- Logic:
  1. Tasks due today/overdue for this doctor's patients
  2. Unread patient messages with triage urgency ≥ medium
  3. Recent AI suggestions not yet reviewed
  4. Rule-based triggers: e.g., "术后第N天" matched against patient records and doctor's rules
- Returns: list of patients with reason text and urgency level
- Initially can be simple (due tasks + unread messages); rule-based triggers added later

### 3D. AI Draft Replies

**Purpose:** Generate follow-up reply drafts using doctor's personal knowledge and communication style.

**Changes:**

- New prompt template: `src/agent/prompts/intent/followup_reply.md`
  - Input: patient message, patient context (records, history), doctor's knowledge (especially communication-style rules)
  - Output: draft reply text + cited knowledge IDs
  - Tone instruction: "Reply as this doctor would. Use their communication style, their terminology, their follow-up patterns."
- New domain function: `src/domain/patient_lifecycle/draft_reply.py`
  - `async def generate_draft_reply(doctor_id, patient_id, message_id) -> DraftReply`
  - Loads doctor knowledge (category: communication/followup)
  - Loads patient context (recent records, active tasks)
  - Calls LLM with followup_reply prompt
  - Returns: `DraftReply(text, cited_knowledge_ids, confidence)`
- New model: `MessageDraft` in `src/db/models/message_draft.py`
  - `id`, `doctor_id`, `patient_id`, `source_message_id` (FK to inbound PatientMessage)
  - `draft_text`, `edited_text` (nullable — populated when doctor edits before sending)
  - `cited_knowledge_ids` (JSON list), `confidence` (float)
  - `status` (enum: generated/edited/sent/dismissed)
  - Separate table — a draft is NOT a message (different lifecycle)
  - Supports multiple draft versions (doctor dismisses, AI regenerates)
- Trigger: auto-generate draft only for **escalated** messages (where `ai_handled=False`).
  Do NOT generate for messages the triage system already auto-replied to.
  Trigger in `handle_escalation()` as a background task with 30-second batching
  delay for rapid-fire messages from the same patient.

### 3E. Draft Approve/Send Flow

**Purpose:** Doctor reviews AI draft, optionally edits, then sends to patient.

**Changes:**

- New API endpoints:
  - `POST /api/manage/messages/{id}/send-draft` — approve and send AI draft as-is
  - `PUT /api/manage/messages/{id}/edit-draft` — edit draft text before sending
  - `POST /api/manage/messages/{id}/dismiss-draft` — dismiss draft, write manual reply
- On send: create a doctor reply message to the patient, update draft status
- If doctor edits the draft before sending, log the original + edited
  version as a teaching signal
- **Send confirmation:** after tapping "发送", show a confirmation sheet:
  - Patient context summary: "王建国 · 脑膜瘤术后第12天 · 上次复查CT正常"
  - Full draft text
  - Which rules were cited: "引用：术后头痛危险信号"
  - `AI生成` disclosure label (will appear in the sent message to patient)
  - "确认发送" button (green) / "返回修改" (gray)
  - One extra tap to prevent accidental sends and verify correct patient context.
- **Medical safety constraints on draft content:**
  - Hard-block: drafts MUST NOT contain new diagnosis, new treatment recommendations,
    dose/medication changes, or prescription advice. These require manual doctor input.
  - Allowed content: plan reiteration, follow-up reminders, education, symptom monitoring
    instructions, escalation instructions ("请尽快来院检查").
  - Red-flag blocker: if patient message contains red-flag symptoms (fever, neuro deficit,
    chest pain, dyspnea, bleeding, postop deterioration), draft must default to
    escalation template ("请立即就医") rather than a conversational reply.
- **AI disclosure:** all patient-facing messages generated or drafted by AI must include
  a visible `AI辅助生成，经医生审核` label in the sent message.
- **Stale draft invalidation:** if a new patient message arrives after a draft was
  generated but before the doctor sends it, the draft is marked stale and regenerated
  with the new message context included.

### 3F. Message Read Status

**Purpose:** Track whether patient has read the doctor's reply.

**Changes:**

- Add `read_at` timestamp column to patient messages (doctor→patient direction)
- Patient portal marks message as read when displayed: `POST /api/patient/messages/{id}/read`
- Doctor-facing API returns read/unread status per message

---

## 4. Knowledge Engine Improvements

All knowledge improvements ship together. No phasing — build the complete system.

### 4A. Fix What's Broken (build first — other features depend on this)

- **Knowledge categories**: stop hardcoding to `custom`, respect doctor's choice.
  Three call sites need fixing: `knowledge_crud.py`, `knowledge_ingest.py`, and
  `save_knowledge_item` domain function. All hardcode `category="custom"`.
  Draft replies need category filtering (communication vs diagnosis rules).
  **This must ship BEFORE draft reply pipeline.**
- **Knowledge title extraction**: `DoctorKnowledgeItem` has no `title` field —
  UI shows rule titles ("术后头痛危险信号") but model only has `content` blob.
  Add `title` and `summary` fields. Extract during ingest via LLM or use
  first line of content as title fallback.
- **Knowledge editing**: persist inline edits (currently UI-only)
- **Profile sync**: align frontend/backend fields (clinic_name, bio, specialty)
- **Structured record editing**: fix frontend→backend field mismatch

### 4B. Citation Parsing (build first — everything depends on this)

The entire product ("引用了你的规则" vs "未引用个人规则") depends on
reliably extracting `[KB-{id}]` markers from LLM free text. This doesn't
exist in the codebase today. Build and validate BEFORE other features.

- Regex parser for `[KB-\d+]` patterns in LLM output — extract from inside
  structured JSON fields (`detail` strings in differentials, workup, treatment),
  not just free text
- Validation: extracted IDs must exist in doctor's actual KB items
- Hallucination handling: ignore IDs that don't match real items, log anomalies
- Missing citation fallback: fuzzy token overlap scoring against injected
  KB items when LLM uses knowledge but doesn't cite it. Note: existing
  `_score_item()` in `knowledge_context.py` runs input-side; output-side
  matching is a different problem — defer fuzzy fallback if spike shows
  explicit citation recall >70%
- Must work across all prompt pipelines: `diagnosis.md` (already has citation
  instructions), `query.md` (needs citation instructions added),
  `followup_reply.md` (new, include from start)
- **Spike first:** measure citation recall on 20+ test cases before committing.
  Pass criteria: >80% recall on explicit `[KB-id]` citations. Build 20 test
  fixtures with realistic KB items + expected citations. If spike fails
  (<50% recall), invest in few-shot examples per prompt pipeline before
  proceeding.

### 4C. Structured Knowledge

- Convert uploaded documents into structured rule cards (not flat text blobs)
- Chunk documents, preserve source spans, classify content type
- Categories: diagnosis rules, communication style, follow-up protocols, medication preferences
- Version history on knowledge items

### 4D. Personal Case Memory

- Enable similar-case matching (currently disabled in diagnosis.py)
- Doctor-confirmed cases become part of the retrieval corpus
- When doctor confirms/edits a diagnosis, store the decision as a personal case
- Semantic retrieval over cases + rules (replace keyword scoring)

### 4E. Teaching Loop (edit-to-preference learning)

**Data model:** New unified `doctor_edits` table:
- `id`, `doctor_id`, `entity_type` (enum: diagnosis/draft_reply/record),
  `entity_id`, `field_name` (nullable)
- `original_text`, `edited_text`, `diff_summary` (LLM-generated one-line)
- `rule_created` (boolean — did doctor tap "记成我的偏好?"), `rule_id` (FK, nullable)
- `created_at`

This table captures edits across ALL entity types in one place, enabling
cross-entity pattern detection.

**Trigger logic:**
- Fires when doctor edits a diagnosis suggestion (already has `edited_text`
  on `AISuggestion`) or edits a draft reply (via `MessageDraft.edited_text`)
- Does NOT fire on minor text corrections (<10 char diff or whitespace-only)
- For record edits: add edit tracking to `record_edit_handlers.py` (currently
  just overwrites fields with no history)
- Prompt appears as a bottom toast after save: "记成我的偏好？ [是] [否]"
  — not a blocking dialog, dismisses after 5 seconds

**Split implementation:**
- 4E-diagnosis: ships with Stream A (uses existing `AISuggestion.edited_text`)
- 4E-drafts: ships after Stream B (needs `MessageDraft` to exist)
- 4E-records: deferred — requires adding edit tracking to record handlers first

**Pattern extraction (v1 approach):**
- Simple frequency heuristic: if doctor makes the same type of edit 3+ times
  (e.g., always adds "48h内复查" to post-craniotomy follow-ups), generate a
  rule suggestion via LLM call over the last 10 similar edits
- NOT a real-time system — runs as a weekly batch job, surfaces suggestions
  on 我的AI tab: "AI发现你经常这样改，要存为规则吗？"

**Alignment indicator:**
- "与你的风格一致度：高/中/低" on draft replies
- Computed as: edit distance ratio between draft and doctor's final sent text,
  averaged over last 10 sends. >90% = 高, 70-90% = 中, <70% = 低
- Only shown after 10+ drafts have been sent (need baseline data)

### 4F. Citation Visual Treatment

Citations must be visually prominent, not 11px metadata:

- **Review tab:** colored left border on cards when personal rules are cited
  (green = cited, gray dashed = not cited)
- **随访 tab:** citation tag inside the draft card, same green treatment
- **"未引用个人规则"** state: include inline action "教AI一条 ›" that links
  to adding a relevant rule. Turn absence of personalization into a
  micro-conversion moment.
- Citations should be the second most prominent element on each card
  (after the clinical content itself)

### 4G. Voice Input & Image Handling (acknowledged gaps)

The product targets specialists (e.g., neurosurgeons) who work with voice
between surgeries and receive CT/MRI images from patients. These are real
workflow gaps:

- **Voice input:** Doctor dictates rules, replies, and case notes by voice.
  The codebase already has `VoiceInput.jsx` component for patient-side.
  Extend to doctor-side: voice → text transcription → feed into draft edit,
  knowledge creation, or chat input. Use existing Whisper/cloud ASR.
- **Image handling in follow-up:** Patients send CT scans, wound photos, MRI
  images via messages. The draft reply pipeline should include image context
  when available (vision model for image description → include in prompt).
  The codebase already has `vision_import.py` for OCR/image processing.
- **Batch operations:** When doctor has 10+ pending drafts, offer a batch
  review mode: show all high-confidence (>0.9) drafts in a scrollable list
  with "全部发送" for the batch and individual "修改" for exceptions.

These integrate into the existing architecture — not new systems, extensions
of what exists.

---

## 5. Language & Identity

### Personal AI Identity

Every surface replaces generic "AI" with the doctor's personal AI name:

| Current | New |
|---------|-----|
| 问 AI 任何问题 | 让张医生AI先看一眼 |
| AI助手 | 张医生AI |
| AI建议 | 引用了你的规则：术后头痛危险信号 |
| 管理知识库 | 继续教AI |
| 新增病历 | 导入病例 |
| 任务 | 随访 |

### Citation Language

- "引用了你的规则：{rule_name}" — in diagnosis review
- "AI按你的话术起草" — in follow-up drafts
- "未引用个人规则" — when AI used generic reasoning (teaches doctor to add more rules)
- "按你的方法处理了 N 位患者" — on home screen

---

## 6. Empty States

### First-time User (0 knowledge, 0 patients)

**我的AI hero card:**
- "你还没开始教AI"
- "上传你的诊疗规则或常用模板后，它才会按你的方法工作"
- CTA: `添加第一条规则` / `上传第一份资料`

**Quick actions:** same 3 rows, but badges show 0

**我的方法:** 3 guide cards instead of rules:
- "上传指南" / "粘贴常用回复" / "导入已确认病例"

**患者:** search + `+ 新建患者` only, no AI建议关注 section

**审核/随访:** empty state with "暂无待审核/待回复" message

### After 1 Week

- Hero switches to "值班态" with real stats
- Activity feed has real events
- 我的方法 shows most-active rules
- AI建议关注 starts surfacing patients

---

## 7. Implementation Priority

All features ship together. Build order by dependency (parallelizable where noted):

```
Stream A: Knowledge Foundation (build FIRST — everything depends on this)
  1. Knowledge category fix (4A)         ← 3 call sites, unblocks draft quality
  2. Knowledge title extraction (4A)     ← add title/summary to KB model
  3. Citation parsing spike (4B)         ← validate >80% recall before proceeding
  4. Knowledge usage tracking (3A)       ← depends on citation parsing
  5. Teaching loop — diagnosis edits (4E-diagnosis) ← uses existing AISuggestion

Stream B: Draft Reply Pipeline (start after steps 1+3 — needs categories AND citations)
  6. AI draft replies (3D)               ← new LLM pipeline, heaviest work
  7. Medical safety constraints (3E)     ← hard-blocks, red-flag blocker, AI disclosure
  8. Draft approve/send + confirmation (3E) ← depends on 3D
  9. Stale draft invalidation            ← regenerate on new patient message
  10. Teaching loop — draft edits (4E-drafts) ← depends on MessageDraft existing
  11. Message read status (3F)           ← lightweight, independent

Stream C: Query & Aggregation (start after step 3)
  12. AI activity feed (3B)              ← depends on 3A
  13. AI-flagged patients (3C)           ← depends on tasks + messages

Stream D: Frontend (start once backend APIs ready; mockups updated first)
  14. Update mockups to match spec       ← citation visuals, send confirmation, teach prompt
  15. Nav restructure + settings merge   ← 4-tab shell
  16. Frontend: 我的AI tab               ← depends on 3A, 3B
  17. Frontend: 患者 tab                 ← depends on 3C
  18. Frontend: 审核 tab                 ← restructure + citation visuals (4F)
  19. Frontend: 随访 tab                 ← depends on 3D, 3E, 3F + send confirmation
  20. Frontend: batch draft review mode  ← high-confidence batch send
```

**Dependency notes:**
- Stream B depends on Stream A steps 1 AND 3 (not just step 1). B team can
  start coding after step 1 but must stub citation extraction until step 3 lands.
- Stream C depends on step 3 (citation parsing) for activity feed data.
- Stream D step 14 (mockup update) should happen BEFORE frontend coding starts.
  Current mockups contradict the spec on citations, send confirmation, and teaching loop.
- For a solo developer: critical path is 1→3→6→7→8→14→15→18→19 (serial).
  The "4 streams" framing only parallelizes with 2+ backend developers.

---

## 8. Files Changed

### New Files

| File | Purpose |
|------|---------|
| `src/db/models/knowledge_usage.py` | Knowledge usage log model |
| `src/domain/knowledge/usage_tracking.py` | Log and query knowledge citations |
| `src/domain/patient_lifecycle/draft_reply.py` | Generate AI draft replies |
| `src/agent/prompts/intent/followup_reply.md` | Draft reply prompt template |
| `src/channels/web/ui/ai_activity_handlers.py` | AI activity feed + stats API |
| `src/channels/web/ui/draft_handlers.py` | Draft approve/send/edit API |
| `frontend/web/src/pages/doctor/MyAIPage.jsx` | 我的AI tab (replaces HomePage) |
| `frontend/web/src/pages/doctor/FollowupPage.jsx` | 随访 tab (replaces TasksPage concept) |

### Modified Files

| File | Change |
|------|--------|
| `src/db/models/message_draft.py` | MessageDraft model (separate table) |
| `src/domain/knowledge/citation_parser.py` | Extract + validate [KB-id] from LLM output |
| `src/db/models/patient_message.py` | Add read_at column |
| `src/channels/web/ui/knowledge_handlers.py` | Fix category hardcoding |
| `src/channels/web/ui/patient_detail_handlers.py` | AI attention endpoint |
| `src/agent/prompt_composer.py` | Log KB citations after LLM response |
| `frontend/web/src/pages/doctor/DoctorPage.jsx` | 4-tab nav, remove settings tab |
| `frontend/web/src/pages/doctor/PatientsPage.jsx` | AI建议关注 section, AI status per row |
| `frontend/web/src/pages/doctor/ReviewPage.jsx` | Restructure as queue with summary bar |
| `frontend/web/src/pages/doctor/SettingsPage.jsx` | Move to subpage of 我的AI |
| `frontend/web/src/pages/doctor/constants.jsx` | Update nav labels/icons |
| `frontend/web/src/api.js` | New API functions |
| `frontend/web/src/components/AskAIBar.jsx` | Personalized text |
| `docs/ux/UI-DESIGN.md` | Update nav spec, add new page layouts |

---

## 9. Review Findings (2026-03-27)

10 independent reviewers (5 Claude, 5 Codex) reviewed this spec.
Average score: **4.9/10**. Changes incorporated above.

### Key Changes Made From Reviews

| Finding | Source | Action Taken |
|---------|--------|--------------|
| Follow-up drafts are the killer feature | All reviewers | Kept as core feature |
| Cold-start: upload-first kills onboarding | Doctor, Growth, Product | Added edit-to-rule teaching loop (4E) |
| Citation parsing doesn't exist in codebase | Tech Architect | Added citation spike as first build step (4B) |
| Knowledge category fix blocks draft quality | Tech Architect | Moved to build step 1 (was step 12) |
| One-tap send is medical liability risk | UX Designer, Medical | Added send confirmation sheet (3E) |
| Draft should be separate table from messages | Tech Architect | Changed to `message_drafts` table |
| Only generate drafts for escalated messages | Tech Architect | Added escalation filter + 30s batching |
| Citations visually buried as metadata | UX Designer, UX Critic | Added citation visual treatment spec (4F) |
| Regulatory: must frame as follow-up copilot | Medical Domain | Reframed positioning language |
| Chinese competitors missing from analysis | Competitive Analyst | Acknowledged — see competitive section |
| Build order was waterfall, should parallelize | Startup Advisor | Restructured into 4 parallel streams |

### Decisions Kept Despite Pushback

| Suggestion | Reviewers | Decision |
|------------|-----------|----------|
| Cut scope to draft-reply wedge only | 8/9 reviewers | **Keep full scope** — build everything |
| Merge 审核+随访 into one 待办 tab | UX Designer, Codex UX | **Keep 4 tabs** — cognitive tasks differ |
| Phase the launch into drops | Product Strategist | **Ship together** — no version thinking |

### Round 2 Changes (from R2 reviews, avg 4.9→6.3)

| Finding | Source | Action |
|---------|--------|--------|
| Mockups contradict spec on citations | UX Designer, Codex UX | Added step 14: update mockups before frontend |
| Voice input + image handling missing | Doctor (7→8 if added) | Added 4G: voice, image, batch operations |
| Teaching loop has no data model | Tech Architect | Added `doctor_edits` table spec, trigger logic, split into 3 phases |
| Draft needs medical safety hard-blocks | Codex Medical, Doctor | Added red-flag blocker, content constraints, `AI生成` label |
| Send confirmation needs patient context | Doctor | Added patient summary + cited rules to confirmation sheet |
| Stream B depends on A step 3, not just step 1 | Tech Architect | Fixed dependency notes in build order |
| 3 call sites for category hardcode, not 1 | Tech Architect | Noted in 4A |
| Stale drafts need invalidation | Tech Architect | Added to Stream B step 9 |
| KB items need title/summary fields | Tech Architect | Added to 4A |
| Citation spike needs pass/fail criteria | Tech Architect | Added >80% recall threshold |

### Unresolved Risks (acknowledged, not addressed)

- LLM citation compliance is inherently unreliable — spike with pass/fail criteria mitigates
- Chinese internet medicine regulation is evolving — copilot positioning + AI disclosure + content constraints reduce risk
- Competitive window is narrow — 京东京医智能体 and 蚂蚁好大夫 could replicate in 1-2 quarters
- Market size (specialists with private patient pools) may be 10K-50K doctors total
- Distribution strategy is not addressed in this spec (how doctors find the product)
- No network effects — per-doctor switching costs only, no cross-doctor value
