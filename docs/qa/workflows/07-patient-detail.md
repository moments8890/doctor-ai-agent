# Workflow 07 — Patient detail + records

Ship gate for the patient detail view — bio header, record timeline,
message shortcut, and "needs your action" banner. Covers the surface
a doctor opens once per visit to read the patient's history.

**Area:** `src/pages/doctor/patients/PatientDetail.jsx`,
`/api/doctor/patients/<id>`, `/api/doctor/patients/<id>/records`,
`/api/doctor/patients/<id>/messages`
**Spec:** `frontend/web/tests/e2e/07-patient-detail.spec.ts`
**Estimated runtime:** ~4 min manual / ~30 s automated

---

## Scope

**In scope**

- Navigate into patient detail from list.
- Patient bio header: name, gender·age line, `门诊N 检验N 影像N` counts,
  last activity, birth year, 建档 date.
- Records section with sub-tabs (全部 / 病历 / 检验 / 影像 / 问诊).
- Record row: source badge, status (待审核 / 已审核), date, chief complaint.
- Tapping a record navigates to review page.
- "需要你处理" yellow banner when pending items exist.
- Messages shortcut: "患者消息(N) 查看聊天记录 ›" → chat view.
- New record button (新建门诊).
- Delete patient action (overflow menu).
- Back navigation returns to patient list.

**Out of scope**

- Creating a new record / recording voice input.
- Review page itself — [08](08-review-diagnosis.md).
- Chat message send flow — [09](09-draft-reply.md).
- Export / QR code dialogs in the overflow.

---

## Pre-flight

Seed a patient plus at least one completed intake record via
`seed.completePatientIntake` so the records timeline has content
and the review status is `待审核`.

---

## Steps

### 1. Entry

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/patients/<id>` | URL matches; bottom nav hidden; header back arrow `‹` visible; page slides in (300ms) |
| 1.2 | Observe bio header | Patient name; `男/女 · N岁` line; `门诊N 检验N 影像N`; "最近 <relative>"; "出生 YYYY"; "建档 YYYY-MM-DD" |

### 2. Records timeline

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Sub-tabs rendered | 全部 / 病历 / 检验/影像 / 问诊 — all present; 全部 selected by default |
| 2.2 | Record row structure | Source badge (预问诊 / 门诊 / 口述 / 导入); status (待审核 warning / 已审核 text4); date; chief complaint |
| 2.3 | Tap a record row | Navigates to `/doctor/review/<record_id>` |
| 2.4 | Empty state (new patient, 0 records) | EmptyState "暂无病历" subtitle "点击右上角「门诊」新建病历" |

### 3. "需要你处理" banner

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Patient with ≥1 pending review | Yellow banner "⚡ 需要你处理" shows count = pending review count; tap routes to first pending review |
| 3.2 | Patient with 0 pending | Banner hidden |

### 4. Messages shortcut

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Scroll to messages section | Header "患者消息"; row "查看聊天记录 ›" with message count |
| 4.2 | Tap the row | Navigates to `/doctor/patients/<id>?view=chat`; chat thread renders |
| 4.3 | With 0 messages | Shows "暂无患者消息" placeholder |

### 5. Top actions

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Tap `新建门诊` button in header | Opens new-record flow (dictation or manual) |
| 5.2 | Tap overflow menu (three-dot or icon) | Sheet with rows: 门诊报告 / 患者二维码 / 删除患者 (red) |
| 5.3 | Tap `删除患者` → Confirm dialog | Title "删除患者"; message "确定删除…所有病历和任务将一并删除，无法恢复。" |
| 5.4 | Tap cancel in delete dialog | Closes without deleting |

### 6. Back navigation

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Tap back arrow | Slides back to patient list (300ms); previously selected tab preserved; scroll restored |

---

## Edge cases

- **Patient with 20+ messages** — chat scrolls smoothly, auto-scroll to
  bottom on enter.
- **Patient with 100+ records** — list virtualized or paginated; no
  freeze.
- **Deleted patient ID in URL** — 404 page or empty state, not crash.
- **Records with no chief complaint** — falls back to source label only.
- **Record created in timezone A viewed in timezone B** — dates in local
  time; no off-by-one.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues.

---

## Failure modes & debug tips

- **Pending count in banner doesn't match records tab** — two different
  queries; banner uses `useReviewQueue(patientId)`, records uses
  `useRecords(patientId)`. Ensure the pending count filter matches.
- **Messages shortcut count is wrong** — unread vs total divergence;
  check which count the row shows (usually total).
- **Delete dialog missing red tone** — ConfirmDialog needs
  `confirmTone="danger"`.
- **Tapping back goes to list but top tab is "审核"** — router state
  lost; check `useAppNavigate`'s history behavior.
