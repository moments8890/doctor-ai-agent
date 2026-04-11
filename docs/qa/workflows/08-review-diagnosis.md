# Workflow 08 — Review diagnosis suggestions

Ship gate for the **审核 · 待审核** queue and the review detail page
where doctors accept, edit, reject, and augment AI diagnosis suggestions.
This is the core doctor workflow of the app — if suggestions don't
render or can't be acted on, the product is unusable.

**Area:** `src/pages/doctor/ReviewQueuePage.jsx` (待审核 tab),
`src/pages/doctor/ReviewPage.jsx`, suggestion API
`/api/doctor/records/<id>/suggestions`
**Spec:** `frontend/web/tests/e2e/08-review-diagnosis.spec.ts`
**Estimated runtime:** ~8 min manual / ~60 s automated

---

## Scope

**In scope**

- 审核 tab shell: three sub-tabs 待审核 / 待回复 / 已完成, pending count
  badge, filter bar.
- Queue card content: patient avatar, name, triage badge (紧急 red /
  待处理 amber), chief complaint, "预问诊 · AI：X" preview, date.
- Tap card → review detail page with `诊断审核` header.
- Three suggestion sections: 鉴别诊断 / 检查建议 / 治疗方向.
- Suggestion card states: collapsed, expanded, confirmed (✓),
  rejected/removed, edited.
- "+ 添加" inline form for custom suggestions.
- Record summary collapse/expand with MUI `Collapse` transition.
- No raw `[KB-N]` text visible anywhere (citations extracted server-side).
- Action button order: 确认 / 修改 / 移除 per suggestion; cancel LEFT,
  save RIGHT in edit forms (BUG-05 gate).
- Badge count updates after confirming suggestions.
- Back to queue reflects updated state.

**Out of scope**

- 待回复 tab — [09](09-draft-reply.md).
- Citation correctness (does the suggestion actually cite the right KB?) —
  `ai-thinks-like-me-qa-plan.md`.
- Adding new records / creating interviews — [07](07-patient-detail.md).

---

## Pre-flight

Seed a pending review by running a patient through an interview via
`seed.completePatientInterview`. This creates a record with status
`pending_review`, which the backend picks up and generates suggestions
for (async — may need a short poll).

For deterministic tests, call `/api/doctor/records/<id>/generate-suggestions`
directly if such a dev endpoint exists, OR seed 2-3 knowledge items
relevant to the interview symptoms so the LLM has something to cite.

---

## Steps

### 1. Queue tab

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Tap 审核 bottom-nav tab | Header "审核"; sub-tab bar 待审核 / 待回复 / 已完成 |
| 1.2 | 待审核 tab active by default (or after tap) | Pending count badge correct (matches number of pending records) |
| 1.3 | Queue card content | Avatar, patient name, triage badge if urgent, "主诉：<chief>" line, "预问诊 · AI：<preview>" line, relative date |
| 1.4 | Urgent suggestions sorted to top | 紧急 red badge items appear above 待处理 amber |

### 2. Open review detail

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap a queue card | Navigates to `/doctor/review/<record_id>`; header "诊断审核"; `‹` back arrow; bottom nav hidden |
| 2.2 | Record summary at top | Shows patient name, chief complaint, history; collapse header "收起 ▴" |
| 2.3 | Three sections rendered | 鉴别诊断 / 检查建议 / 治疗方向 — each has label + suggestions + "+ 添加" button |
| 2.4 | No `[KB-N]` anywhere in any suggestion text | Citations rendered as badges or extracted to citation popover, not inline literals |

### 3. Expand / confirm / reject

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap a collapsed suggestion row | Expands (▾ arrow rotates); full AI explanation visible; action row "确认 / 修改 / 移除" appears |
| 3.2 | Tap `确认` | Row turns green with ✓ icon; 修改 and 移除 remain active; section header count (if shown) increments |
| 3.3 | Tap `移除` on a confirmed suggestion | Row returns to unconfirmed/dimmed state; item is NOT deleted from list (still present for re-confirm) |
| 3.4 | Tap `移除` on an unconfirmed suggestion | Row dims; state persists on reload |

### 4. Edit suggestion

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Expand a suggestion → tap `修改` | Inline edit form opens with current text pre-filled; button row: 取消 LEFT grey / 保存 RIGHT green (BUG-05 gate) |
| 4.2 | Modify text, tap 保存 | Text updates in place; persists on reload |
| 4.3 | Tap 取消 instead | No change, form closes |

### 5. Add custom suggestion

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Tap `+ 添加` in any section | Inline form with two fields: 建议内容 (required) + 详细说明（可选） |
| 5.2 | Leave 建议内容 empty | `添加` button disabled |
| 5.3 | Type content + optional detail → `添加` | New item appended to that section with a distinguishing badge ("自定义" or similar); section count updates |

### 6. Record summary collapse

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Tap the record summary header "收起 ▴" | Collapses via MUI `Collapse` transition (not instant); single-line preview with chief complaint visible; header changes to "展开 ▾" |
| 6.2 | Tap "展开 ▾" | Expands again smoothly |

### 7. Back to queue

| # | Action | Verify |
|---|--------|--------|
| 7.1 | Press back arrow | Returns to 审核 list; transitions back (Slide 300ms) |
| 7.2 | Queue badge updated | If all suggestions confirmed, item may move to 已完成 (depending on finalize logic); otherwise badge count decrements or stays |

### 8. Empty state

| # | Action | Verify |
|---|--------|--------|
| 8.1 | Fresh doctor with no pending reviews | 待审核 tab shows EmptyState "暂无待审核病历" (not blank, not plain 暂无…) |

---

## Edge cases

- **Record with no suggestions** (LLM failed) — review page shows "暂无
  AI建议" + manual add still works.
- **All three sections empty** — still render section headers with "+
  添加" buttons.
- **Double-tap 确认** — no duplicate confirm; optimistic update idempotent.
- **Simultaneous edit + confirm** — edit dialog wins; confirm disabled
  while editing.
- **Very long suggestion text (1000+ chars)** — expands cleanly, no
  horizontal scroll.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues:

- **BUG-05** — ✅ Fixed `795729ff`. Regression gate: step 4.1 — edit
  form has 取消 LEFT / 保存 RIGHT.
- **FINDING-001** — ✅ Fixed `4c5e829b`. Phantom KB IDs filtered and
  dedup guard prevents suggestion accumulation. Regression gate: step
  2.4 — no `[KB-N]` literals.

---

## Failure modes & debug tips

- **Queue card doesn't render** — `useReviewQueue(doctorId)` must
  return `pending` array. Check network panel for `/api/doctor/review/queue`.
- **Suggestions don't appear on detail page** — either the backend
  hasn't generated them yet (async — poll), or the record has no
  `ai_suggestions` row. Check `SELECT * FROM ai_suggestions WHERE
  record_id = ?`.
- **Confirm button does nothing** — optimistic update path; check the
  mutation handler for a silent catch.
- **Edit form buttons in wrong order** — `DialogFooter` order matters.
  Cancel must be first child (LEFT), confirm second child (RIGHT).
- **Section header shows stale count** — `invalidate` may only touch
  query cache, not the local section count state. Refresh triggered by
  mutation handler.
