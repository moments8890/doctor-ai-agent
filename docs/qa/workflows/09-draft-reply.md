# Workflow 09 — Draft reply send

Ship gate for the **审核 · 待回复** path — the AI drafts a reply, the
doctor reviews/edits, and sends it to the patient. This is the other
core doctor workflow (paired with [08](08-review-diagnosis.md)) and the
main end-to-end test of the "AI thinks like me" value proposition.

**Area:** `src/pages/doctor/ReviewQueuePage.jsx` (待回复 tab),
`src/pages/doctor/patients/PatientDetail.jsx` (chat view + draft
editing), `SheetDialog` confirm send. Draft API surface
(`api.js:1010-1034, 944-949`):
- List drafts: `GET /api/manage/drafts?doctor_id=<id>&patient_id=<pid>`
- Draft summary: `GET /api/manage/drafts/summary?doctor_id=<id>`
- Edit draft: `PUT /api/manage/drafts/<draftId>/edit?doctor_id=<id>` body `{edited_text}`
- Send draft: `POST /api/manage/drafts/<draftId>/send?doctor_id=<id>`
- Send confirmation: `POST /api/manage/drafts/<draftId>/send-confirmation?doctor_id=<id>`
- Dismiss: `POST /api/manage/drafts/<draftId>/dismiss?doctor_id=<id>`
- Manual fallback reply: `POST /api/manage/patients/<patientId>/reply` body `{text}`
**Spec:** `frontend/web/tests/e2e/09-draft-reply.spec.ts`
**Estimated runtime:** ~8 min manual / ~60 s automated

---

## Scope

**In scope**

- 待回复 tab queue card: patient avatar, name, message preview in quotes,
  "AI已起草 · 常规咨询/紧急" label.
- Tap card → chat view at `/doctor/patients/<id>?view=chat`.
- Chat thread renders patient messages + AI draft bubble.
- Draft bubble header "AI起草回复 · 待你确认".
- No raw `[KB-N]` in draft text.
- Inline actions: 修改 / 确认发送 ›.
- Edit mode: bottom input switches with "正在编辑AI草稿" label, 取消 button.
- Edit persists across the send flow (confirm sheet shows edited text).
- Send confirm sheet: "确认发送回复" title; shows patient message + reply
  + "AI辅助生成，经医生审核" attribution; 取消 LEFT grey / 发送 RIGHT green.
- Send success: sheet closes; item moves 待回复 → 已完成; chat shows sent
  bubble with attribution.
- Patient portal reflects the delivered reply.

**Out of scope**

- Message authoring from scratch (no AI draft) — partial coverage.
- Voice input in the edit bar.
- Multi-turn patient-doctor chat beyond one reply.

---

## Pre-flight

Seed:

1. Patient + completed interview (for chat context).
2. At least one knowledge item relevant to the test message so the draft
   generator has something to cite.
3. Patient message via `seed.sendPatientMessage` (hits
   `POST /api/patient/message`, not `/messages`).
4. **Async wait.** Draft generation runs out-of-band after the message
   lands. Use `seed.waitForDraft(doctor, patientId)` which polls
   `GET /api/manage/drafts?doctor_id=…&patient_id=…` until at least one
   draft exists. Default 30 s timeout.

---

## Steps

### 1. Queue tab

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to 审核 → tap 待回复 | Tab label "患者消息 · 待回复"; queue populated |
| 1.2 | Card content | Patient avatar, name, message preview in quotes, "AI已起草 · 常规咨询" (or 紧急) label, relative date |
| 1.3 | Empty state | EmptyState when no drafts pending |

### 2. Open draft

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap card | Navigates to `/doctor/patients/<id>?view=chat`; chat view shown with thread history |
| 2.2 | AI draft bubble | Right-aligned (doctor side); primaryLight bg; header "AI起草回复 · 待你确认"; below text: inline actions "修改" and "确认发送 ›" |
| 2.3 | No `[KB-N]` anywhere in draft | Rendered clean; citations extracted server-side |

### 3. Edit draft

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap `修改` | Bottom input bar switches to edit mode; header label "正在编辑AI草稿"; 取消 button visible; input pre-filled with draft text |
| 3.2 | Change text (append/replace) → tap send arrow | Confirmation sheet opens below |
| 3.3 | Confirmation sheet shows edited text, NOT original draft | Verify the diff — the shown reply matches step 3.2 text |
| 3.4 | Tap 取消 in edit mode (before sending) | Edit mode closes; original draft bubble restored; no send |

### 4. Send confirmation sheet

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Sheet title "确认发送回复" | Contains: patient message (quoted), reply text, "AI辅助生成，经医生审核" attribution line |
| 4.2 | Button row | 取消 LEFT grey, 发送 RIGHT green |
| 4.3 | Tap `发送` | Sheet closes; success toast/animation; item moves from 待回复 to 已完成 |
| 4.4 | Tap 取消 in sheet | Sheet closes; nothing sent; draft still present |

### 5. Post-send state

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Chat view after send | New sent bubble on doctor side; `wechatGreen` bg; attribution "AI辅助生成，经医生审核" below bubble |
| 5.2 | Navigate back to 审核 → 待回复 | Item removed from 待回复; count decremented |
| 5.3 | Tap 已完成 tab | Item appears with "已发送" badge and sent timestamp |
| 5.4 | Patient portal (separate session) | Doctor reply visible in patient's chat; text exactly matches what was sent |

---

## Edge cases

- **Draft generation pending** — if AI draft hasn't finished, bubble
  shows skeleton or "AI 正在起草…" placeholder.
- **Draft generation failed** — `patients/PatientDetail.jsx` shows
  "AI未能起草回复（知识库中无匹配规则），请直接回复患者" with a manual
  input prompt "直接回复患者..." — the doctor can type from scratch.
- **Multiple drafts for same patient** — both appear as separate cards
  in 待回复.
- **Patient sends another message while doctor is editing** — the new
  message appears in the chat thread; draft is unchanged.
- **Very long reply (2000+ chars)** — sent successfully; rendered in
  chat without overflow.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues:

- **FINDING-001** — ✅ Fixed. Regression gate: step 2.3 — no raw
  `[KB-N]` in the draft.

---

## Failure modes & debug tips

- **待回复 tab empty despite seeded draft** — the AI draft generation
  is async; may take 5-30 s depending on LLM. In CI, bump the poll
  timeout or wait for the specific patient to appear in the queue.
- **Confirm sheet shows original draft, not edited text** — look at
  PatientDetail.jsx send handler; it may be reading `initialDraft`
  instead of the current editor state.
- **Draft bubble is blank** — backend returned empty `content`. Check
  `GET /api/manage/drafts?doctor_id=<id>&patient_id=<pid>` response
  (`api.js:1010`); verify knowledge rules relevant to the patient message
  exist — without them the LLM has nothing to cite and the draft pipeline
  may emit an empty body.
- **Send fails silently** — check for `sendPatientMessage` mutation
  error handler that swallows the exception.
- **Item stays in 待回复 after send** — cache not invalidated; check
  `QK.reviewQueue(doctorId)` invalidation on success.
