# Workflow 12 — Doctor-side new-record creation

Ship gate for **病历采集** — the doctor-initiated record creation flow at
`/doctor/patients/new`. Covers text entry, AI field extraction, progress
tracking, carry-forward from imports, the confirmation dialog, and
post-submit diagnosis trigger. This is a core doctor action — both
Claude and Codex flagged its absence as a P0 coverage gap.

**Area:** `src/pages/doctor/InterviewPage.jsx` (doctor-side interview),
`src/pages/doctor/PatientsPage.jsx` (entry orchestration: URL-driven
`/new` route + `?action=new` patient-picker), `components/doctor/FieldReviewCard.jsx`,
`components/doctor/InterviewCompleteDialog.jsx`, `components/ImportChoiceDialog.jsx`,
API: `doctorInterviewTurn`, `doctorInterviewConfirm`, `triggerDiagnosis`
**Spec:** `frontend/web/tests/e2e/12-new-record.spec.ts`
**Estimated runtime:** ~6 min manual / ~50 s automated

---

## Scope

**In scope**

- Entry via MyAIPage "新建病历" quick-action → `/doctor/patients/new`.
- Entry via patient detail "新建门诊" button.
- Welcome message varies by context (named patient vs. fresh start).
- Chat UI: user bubbles right-aligned green, AI bubbles left-aligned white.
- Text input: type symptoms → send → AI responds with follow-ups.
- Progress indicator tracking filled/total NHC fields.
- AI-extracted fields displayed in `FieldReviewCard` components.
- `InterviewCompleteDialog` at end: shows all collected fields; confirm
  button creates the record.
- Post-confirm: record appears in patient detail with status `pending_review`,
  and a diagnosis trigger fires.
- Cancel: exits interview without saving, returns to patient list.
- Suggestion chips for quick input shortcuts.

**Out of scope**

- Voice input (VoiceInput component — device-dependent, flaky in headless).
- Camera/photo OCR import via ActionPanel.
- ImportChoiceDialog carry-forward from existing records.
- Desktop layout variant (InterviewPage renders in the detail pane on
  desktop; covered by a future desktop Playwright project).

---

## Pre-flight

Uses `doctorAuth` + `patient` fixtures. No extra seeding — the spec
creates the record through the UI itself (this IS the workflow).

For faster iteration during spec development, add a knowledge item first
so the AI field extraction has contextual rules:

```bash
seed.addKnowledgeText(request, doctor, "高血压头痛鉴别要点");
```

---

## Steps

### 1. Entry from 我的AI tab

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/my-ai` → tap "新建病历" | Navigates to `/doctor/patients/new`; InterviewPage renders with welcome message: "病历采集模式已开启..." |
| 1.2 | SubpageHeader visible | Back arrow `‹`, title area shows interview/record context |
| 1.3 | Progress bar at top | Shows `0/7` (or similar ratio) initially |
| 1.4 | Input bar at bottom | TextField + send icon; mic icon (if voice supported); `+` action panel toggle |

### 2. Chat flow — text input

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Type "张三，男，65岁，头痛三天" → tap send | User bubble appears right-aligned in green; loading indicator briefly; AI reply appears left-aligned in white within 15 s |
| 2.2 | AI asks a follow-up question | Message is a coherent medical question (not a system error); progress bar advances |
| 2.3 | Reply to follow-up "血压160/100，以前吃过降压药" → send | Another turn completes; progress advances further |
| 2.4 | Multiple turns until status becomes `reviewing` or fields are collected | Progress bar reaches or nears 100%; AI signals completion or `InterviewCompleteDialog` opens |

### 3. Field review + confirm

| # | Action | Verify |
|---|--------|--------|
| 3.1 | `InterviewCompleteDialog` opens (or FieldReviewCards appear inline) | All collected NHC fields displayed: 主诉, 现病史, 既往史, etc. |
| 3.2 | Fields are editable (tap to edit inline) | Tapping a field opens edit mode; changed text persists on save |
| 3.3 | Tap `确认提交` / `提交` | Confirm dialog: 取消 LEFT, 确认 RIGHT; on confirm: record created |
| 3.4 | Post-confirm state | InterviewPage exits; navigates back to patient list or patient detail; patient's record list now shows a new record with status `待审核` and source `门诊` or `口述` |

### 4. Entry from patient detail

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Navigate to `/doctor/patients/<id>` → tap "新建门诊" (or "门诊" button) | Navigates to `/doctor/patients/new`; welcome message includes patient name: "正在为 X 建立门诊记录。" |
| 4.2 | Complete the chat flow (same as §2) | Fields auto-tagged with patient context |

### 5. Cancel flow

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Mid-interview, tap back arrow `‹` | Confirm dialog "放弃当前采集？" (or similar) with 取消 / 确认 |
| 5.2 | Confirm abandon | Interview exits; no record created; returns to patient list |
| 5.3 | Cancel the abandon dialog | Stays in interview; no data lost |

### 6. Suggestion chips

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Observe suggestion chips below the input bar (if present) | 1-3 short-cut texts like "高血压" / "糖尿病" / "常规体检" |
| 6.2 | Tap a chip | Text auto-fills into the input bar; send button becomes active |

---

## Edge cases

- **Empty send** — send button disabled when input is blank.
- **Very long message (500+ chars)** — accepted, no truncation; AI handles it.
- **Session resume** — if `resumeSessionId` is passed (from chat interview),
  the page resumes mid-session. Progress reflects the prior state.
- **Network error during a turn** — error message shown in chat; input bar
  re-enables; retry by sending again.
- **Post-confirm diagnosis takes long** — `triggerDiagnosis` fires async;
  the user sees the record in `待审核` state; suggestions arrive later.

---

## Known issues

None specific to this workflow as of 2026-04-11. This page has been stable
since the original launch, but was never gated by a per-workflow Playwright
spec — it relied on the hero-path-qa-plan.md §7 patient-portal interview
which covers the patient side, not the doctor side.

---

## Failure modes & debug tips

- **Welcome message is blank** — `patientContext` may be undefined;
  InterviewPage.jsx:48 falls back to generic greeting. If the generic
  doesn't render, check the useEffect on line 72.
- **AI never replies** — `doctorInterviewTurn` API call failed silently.
  Check the backend interview session table and `NO_PROXY=*` env var.
- **Progress stays at 0/7** — the progress object is set by the API
  response's `progress` field. Check the backend field-extraction pipeline.
- **FieldReviewCard doesn't appear** — fields not populated in `session.collected`.
  Verify the backend returns `collected` with the correct shape.
- **Confirm button does nothing** — `doctorInterviewConfirm` may fail silently;
  check the API response and the error handler in InterviewPage.
