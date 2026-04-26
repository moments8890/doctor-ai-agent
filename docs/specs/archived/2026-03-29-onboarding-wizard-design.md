# Onboarding Wizard — Design Spec

**Date:** 2026-03-29
**Status:** Review (post Codex + Claude review)
**Target user:** Dr. 陆华 (neurosurgery dept head, 4-day trial)
**Prior art:** `docs/specs/2026-03-28-mockups/deterministic-onboarding-demo.html`

## Problem

The current onboarding (开始体验 on 我的AI) navigates to real production pages
(ReviewPage, ReviewQueuePage) and adds onboarding context with conditional
banners and CTAs. This creates three problems:

1. Production pages show duplicate/conflicting information (13 identical
   diagnosis items instead of 1 clean proof).
2. Page layouts need onboarding-specific conditionals that don't belong in
   production code.
3. Completion is triggered by navigation, not by real actions — the doctor gets
   credit for visiting a page, not for doing work.

## Solution

A dedicated step-by-step onboarding wizard at `/doctor/onboarding`. Purpose-built
screens using real app components. Real data, real actions, focused presentation.
After completion, the doctor lands in the real app. A replay link lets them
return anytime.

## Architecture

### Route

`/doctor/onboarding?step=1` through `?step=6`, plus `?step=done`.

### Entry Logic

- On login, check `localStorage` for `onboarding_wizard_done:{doctorId}`.
- If not set → redirect to `/doctor/onboarding`.
- Every step shows a "跳过引导" text link at the bottom.
- Skip sets `onboarding_wizard_done:{doctorId}` = `"skipped"` and navigates to
  `/doctor`.
- The old `doctor_onboarding_state:v1:{doctorId}` localStorage key is replaced
  by the wizard flag. On migration, if the old key exists with all steps done,
  set the wizard flag to `"completed"` and remove the old key. This avoids two
  parallel state machines.

### Exit Logic

- Step 6 completed → advance to `?step=done`.
- Completion screen (2 seconds or tap) → navigate to `/doctor`.
- Sets `onboarding_wizard_done:{doctorId}` = `"completed"`.
- 我的AI page: onboarding checklist hidden when flag is set. Shows a subtle
  "重新体验引导" text link instead.

### Replay

- "重新体验引导" link (in 我的AI or settings) → navigates to
  `/doctor/onboarding?step=1`.
- Clears wizard step state and calls `ensureOnboardingExamples` to reset proof
  data.

## Wizard Shell Component

**`OnboardingWizard`** — single component registered at `/doctor/onboarding`.

### Layout (every step)

- `SubpageHeader` at top with step title.
- Thin green progress bar below header: step N of 6.
- Scrollable step content area.
- Footer: "下一步" primary button (disabled until `canAdvance`) + "跳过引导"
  grey text link.
- Bottom nav tabs hidden during wizard.
- Back chevron in header navigates to previous step (step 1 has no back).

### Step State

- Current step tracked via `?step=N` query param.
- Each step defines a `canAdvance` condition tied to a real action.
- Completed step numbers and `ensureOnboardingExamples` response are persisted
  to `localStorage` under `onboarding_wizard_progress:{doctorId}`. This way
  browser refresh resumes at the current step, not step 1.
- Proof data IDs (diagnosis_record_id, reply_draft_id, etc.) are part of the
  persisted progress so Steps 2-6 can reload after refresh.
- If doctor navigates away mid-wizard (e.g., closes tab), next login still
  redirects to `/doctor/onboarding` since the done flag isn't set yet. The
  wizard reads persisted progress and resumes.

### Reused Components

All rendering uses existing app components:

- `SubpageHeader`, `AppButton`, `DialogFooter`
- `ListCard`, `IconBadge`, `NameAvatar`, `StatusBadge`
- `FieldReviewCard` or `DiagnosisCard` (Step 2)
- `ReplyCard` (Step 3)
- `ActionRow` (Steps 4, 6)
- QR generation components (Step 5)

No new design system components. The wizard looks like the real app.

## The 6 Steps

### Step 1: 教 AI 三种来源的知识

**Goal:** Doctor adds knowledge from 3 different input methods.

**Screen content:**

- Intro card: "让 AI 学会你的诊疗方法 — 从三种来源各添加一条"
- 3 source rows with check/unchecked state:
  - 文件上传 (PDF, Word, image)
  - 网址导入
  - 手动输入
- Each row is tappable. Navigates to real `AddKnowledgeSubpage` with
  `?onboarding=1&source=file|url|text`.

**Action:** Doctor taps each source, adds knowledge, returns to this screen.

**Completion:** All 3 sources checked off.

**Return mechanism:** `AddKnowledgeSubpage` detects `?onboarding=1`. After save,
navigates back to `/doctor/onboarding?step=1&saved=file|url|text` instead of
showing the current bottom sheet. The wizard updates the check state from the
query param.

**Post-completion:** After 3/3 saved, wizard calls `ensureOnboardingExamples`
with the saved rule IDs. This creates all proof data for Steps 2-6. Then
auto-advances to Step 2.

**Sample content:** The onboarding-mode AddKnowledge page pre-fills a sample
neurosurgery guideline URL and sample rule text. For file upload, a bundled
sample PDF is offered via a "使用示例文件" link. Doctor can replace with their
own content for any source. This ensures the demo works without requiring Dr. Lu
to prepare materials in advance.

### Step 2: 看 AI 如何用于诊断审核

**Goal:** Doctor sees that their saved rule shapes diagnosis suggestions.

**Screen content:**

- Context card: "你刚保存的规则会在诊断审核中被引用" + rule title shown as
  green tag.
- Patient case summary: "陈伟强 · 男 · 42岁" + 1-2 lines of chief complaint.
- ONE `FieldReviewCard` showing:
  - Suggestion: "术后迟发性血肿"
  - Severity badge: 高
  - Cited rule text highlighted in green
  - "确认" / "修改" action buttons on the card

**Action:** Doctor taps "确认" or edits the suggestion.

**Completion:** One suggestion confirmed or edited.

**Data source:** First differential suggestion from `ensureOnboardingExamples`
response (`diagnosis_record_id` → fetch suggestions → take first one).

**Side effect:** When doctor confirms the visible suggestion, the wizard
auto-confirms the remaining 2 suggestions (workup + treatment) and calls
`finalizeReview` on the record. This matches the real backend contract and
triggers follow-up task generation. These tasks are shown in Step 6.

### Step 3: 看 AI 如何起草患者回复

**Goal:** Doctor sees that the same rule shapes patient communication.

**Screen content:**

- Context card: "同一条规则也影响患者沟通草稿"
- Patient message bubble: 陈伟强 asking about worsening headache (from proof
  data).
- AI draft reply card (reuse `ReplyCard`):
  - Draft text with clinical advice
  - Cited rule in green text at bottom
  - "发送" / "修改后发送" buttons

**Action:** Doctor sends or edits+sends the reply.

**Completion:** Draft sent (calls real `sendDraft` API).

**Data source:** `reply_draft_id` from `ensureOnboardingExamples`.

### Step 4: 看 AI 如何自动处理患者消息

**Goal:** Doctor sees the AI acting autonomously — auto-replying to routine
messages and escalating urgent ones.

**Screen content:**

- Context card: "患者发来消息后，AI 会自动判断并处理"
- 3 message cards, each showing patient message + AI action:
  1. Routine: "药还需要继续吃吗？" → AI auto-replied. Green "已自动回复" tag.
  2. Info-logging: "复查报告出来了，一切正常" → AI auto-replied. Green
     "已自动回复" tag.
  3. Urgent/escalated: "头痛又加重了，还吐了一次" → Orange "需医生确认" tag.
     Shows AI draft with cited rule. "确认发送" / "修改" buttons.

**Action:** Doctor confirms or edits the escalated message.

**Completion:** Escalated message confirmed.

**Data source:** `auto_handled_messages` from `ensureOnboardingExamples`
(new field — 3 pre-seeded messages with pre-computed AI responses). The backend
creates 2 `PatientMessage` records with `ai_handled=True` + corresponding
outbound reply records, plus 1 pending escalation with a `MessageDraft`. No new
API endpoint needed — the wizard renders directly from the
`ensureOnboardingExamples` response stored in wizard state. The escalation
confirm calls the existing `sendDraft` API.

### Step 5: 体验患者预问诊

**Goal:** Doctor generates a patient pre-intake entry and optionally previews
the patient experience.

**Screen content:**

- Context card: "为患者生成预问诊入口，预览患者体验"
- Patient name input field (placeholder: "请输入患者姓名，例如：李阿姨")
- "生成入口" button
- After generation: QR code + "预览患者端" button + "复制链接" button

**Action:** Doctor enters a name, generates the QR code, then taps "预览" to
run through the patient intake preview. The preview must reach submission
for the review task to be created (shown in Step 6).

**Completion:** QR code generated AND patient intake preview submitted.
Preview is mandatory because Step 6 depends on the review task created by
patient submission.

**Data source:** Real `createOnboardingPatientEntry` API call. Review task
created by the patient intake submission flow.

### Step 6: 查看生成的审核与随访任务

**Goal:** Doctor sees the two task moments — review task from patient submit,
follow-up tasks from diagnosis confirmation.

**Screen content:**

- Context card: "系统会在两个时刻自动创建任务"
- Section 1 — "审核任务" (from patient submit in Step 5):
  - `ActionRow`: "审阅患者【XX】预问诊记录" with blue "审核任务" tag
- Section 2 — "随访任务" (from diagnosis confirm in Step 2):
  - `ActionRow`: Follow-up tasks with green "来自诊断审核" tags
  - E.g., "48小时内回访头痛/呕吐变化", "发送复诊提醒与危险信号说明"

**Action:** View only.

**Completion:** Tap "完成引导" button.

**Data source:** Tasks created by Steps 2 and 5 actions, fetched from tasks API.

### Completion Screen (`?step=done`)

- Centered card: "设置完成，开始使用"
- Subtitle: "你的 AI 已学会 3 条规则，可以开始处理患者消息了"
- Auto-navigates to `/doctor` after 2 seconds, or tap "进入工作台"

## Data Flow

### Backend: Extended `ensureOnboardingExamples`

Called once after Step 1 completes. Current response:

```json
{
  "knowledge_item_id": 7,
  "diagnosis_record_id": 102,
  "reply_draft_id": 101,
  "reply_message_id": 201
}
```

Extended response:

```json
{
  "knowledge_item_id": 7,
  "diagnosis_record_id": 102,
  "reply_draft_id": 101,
  "reply_message_id": 201,
  "auto_handled_messages": [
    {
      "id": 301,
      "patient_name": "陈伟强",
      "content": "药还需要继续吃吗？",
      "ai_reply": "请继续按原方案服药，下次复诊时再评估。",
      "triage": "routine",
      "status": "sent"
    },
    {
      "id": 302,
      "patient_name": "李阿姨",
      "content": "复查报告出来了，一切正常",
      "ai_reply": "好的，结果已记录。如有不适随时联系。",
      "triage": "info",
      "status": "sent"
    },
    {
      "id": 303,
      "patient_name": "陈伟强",
      "content": "头痛又加重了，还吐了一次",
      "ai_reply": "您术后头痛加重伴呕吐需要高度重视...",
      "triage": "urgent",
      "status": "pending_doctor",
      "draft_id": 150
    }
  ]
}
```

### Backend fix: Diagnosis dedup

Already implemented in this session. `_ensure_diagnosis_example` now deletes all
existing suggestions and creates exactly 3 clean ones (1 differential, 1 workup,
1 treatment).

### Frontend data flow

1. Step 1 saves 3 knowledge items → collects rule IDs.
2. Step 1 completion → `ensureOnboardingExamples({ knowledgeItemId })` → response
   stored in wizard component state.
3. Steps 2-6 read from this stored response. No additional API calls needed for
   proof data (only real action calls like `confirmSuggestion`, `sendDraft`,
   `createOnboardingPatientEntry`, `getTasks`).

## What Changes in Existing Code

### New files

- `frontend/web/src/pages/doctor/OnboardingWizard.jsx` — the wizard component
- Route registration in `App.jsx`

### Modified files

- `App.jsx` — add `/doctor/onboarding` route
- `DoctorPage.jsx` — redirect to wizard on first login (localStorage check),
  hide onboarding checklist when wizard is completed, add "重新体验引导" link
- `AddKnowledgeSubpage.jsx` — when `?onboarding=1`, after save navigate back to
  wizard instead of showing bottom sheet
- `doctor_profile_handlers.py` — extend `ensureOnboardingExamples` to create
  auto-handled messages (Step 4 data)

### Removed from existing pages

- `ReviewPage.jsx` — remove `source === "knowledge_proof"` onboarding branch
- `ReviewQueuePage.jsx` — remove `source === "reply_proof"` onboarding branch
- `MyAIPage.jsx` — simplify `OnboardingChecklist` (no longer drives proof
  navigation, just shows replay link)
- `onboardingProofs.js` — can be deleted or reduced (proof resolution logic
  moves into wizard)

## Environment Assumptions

- Demo runs in **dev mode** (not production). `ensureOnboardingExamples` returns
  404 in production (`is_production()` guard). The Dr. Lu trial uses the dev
  server.
- `mockApi.js` must be updated to return the extended
  `ensureOnboardingExamples` response including `auto_handled_messages`, so the
  wizard works in both mock and real-backend modes.

## What We Are NOT Building

- No changes to production page layouts (ReviewPage, ReviewQueuePage, etc.)
- No new design system components
- No patient-side changes
- No server-side onboarding state tracking (all localStorage)
- No onboarding analytics or event tracking (can add later)
- No chat-based patient creation flow (Step 6 in the mockup — deferred)
