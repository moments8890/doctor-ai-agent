# Workflow 10 — Tasks browse + complete

Ship gate for the **任务** tab — doctor follow-up tasks, scheduled outreach,
and the "待完成 / 已完成" queue. Covers the TaskPage merged inbox (pending
messages + upcoming followups + doctor-created tasks) and the
`TaskDetailSubpage` for per-task actions.

**Area:** `src/pages/doctor/TaskPage.jsx` (2-tab filter bar),
`src/pages/doctor/subpages/TaskDetailSubpage.jsx`,
`useCompletedTasks` / `usePendingTasks` / `useDrafts` / `useDraftSummary`
hooks in `src/lib/doctorQueries.js`. Task API surface (`api.js:516-570`):
- List: `GET /api/tasks?doctor_id=<id>&status=<pending|completed>`
- Create: `POST /api/tasks?doctor_id=<id>` body
  `{task_type, title, patient_id?, content?, due_at?}`
- Complete/reopen: `PATCH /api/tasks/<taskId>?doctor_id=<id>` body `{status}`
- Detail: `GET /api/tasks/<taskId>?doctor_id=<id>`
- Notes: `PATCH /api/tasks/<taskId>/notes?doctor_id=<id>` body `{notes}`

**Spec:** `frontend/web/tests/e2e/10-tasks.spec.ts`
**Estimated runtime:** ~5 min manual / ~40 s automated

---

## Scope

**In scope**

- `FilterBar` with exactly **2 tabs**: `待完成` (followups, default) and
  `已完成` (completed). Counts per tab match seeded data.
- Default tab = `followups`. URL param `?tab=followups | ?tab=completed`
  round-trips on refresh.
- Merged "待完成" list contains:
  - Upcoming scheduled follow-ups (`summaryData.upcoming_followups`)
  - Doctor-created tasks (`usePendingTasks`)
  - Urgent items (`item.soon === true`) rendered at the top in `dangerLight`
- Task row structure: tappable checkbox circle (left), title + subtitle +
  due label (body, taps through to detail), `NewItemCard` "新建任务" above
  the list.
- Tap circle → `handleCompleteTask` → task moves from pending to completed
  optimistically, then API `PATCH /api/tasks/<id>` body `{status:"completed"}`.
- Tap row body → navigate to `/doctor/tasks/<id>` → `TaskDetailSubpage`.
- `TaskDetailSubpage` shows title, content, patient link, source, status,
  notes editor, and action buttons.
- Uncomplete from 已完成 → row moves back to 待完成.
- Empty states per tab — EmptyState component, not raw "暂无…" text.
- Origin-banner behaviors: `?origin=patient_submit` and
  `?origin=review_finalize` show the corresponding card at the top.

**Out of scope**

- Draft-reply flow from the pending messages section — covered by
  [09-draft-reply](09-draft-reply.md). The draft summary hook shares this
  page but clicking a message row navigates into the chat view tested there.
- Task creation via NewItemCard dialog UX — out of scope for this ship gate;
  covered by a dedicated follow-up spec once the sheet form is stable.
- Reminders / due-date picker — dial in when the scheduling flow lands.

---

## Pre-flight

Uses `doctorAuth` + `patient` fixtures and the `seed.createPatientTask`
helper (seed.ts). Test flow:

1. Register a doctor and one patient (fixtures).
2. Call `createPatientTask(request, doctor, patient.patientId, {title, content})`
   at least once per test case that needs a task to exist — this hits the
   real `POST /api/tasks?doctor_id=` route with body
   `{task_type:"follow_up", title, content, patient_id:Number, target:"patient"}`.
3. Navigate to `/doctor/tasks`.

For tests that assert completion round-trips, seed 2 tasks so the count
change is visible.

---

## Steps

### 1. List shell + default tab

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/tasks` | `PageSkeleton` header "任务"; `FilterBar` with exactly 2 tabs — `待完成` and `已完成`; `待完成` active by default |
| 1.2 | Filter-bar counts | `followups` count = N seeded pending tasks + scheduled followups + urgent items; `completed` count = recently sent + completed tasks |
| 1.3 | Check URL after tap on `已完成` | URL updates to `?tab=completed` via `window.history.replaceState` |
| 1.4 | Refresh with `?tab=completed` | App honors the URL param, `已完成` tab active |
| 1.5 | `NewItemCard` row | Title "新建任务", subtitle "添加待办提醒或随访任务", tappable (opens create sheet — not exercised in this spec) |

### 2. Task row rendering

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Seed 1 pending task via `createPatientTask` | Row visible under 待完成: circle checkbox (left), title text, optional subtitle, due label |
| 2.2 | Seed 1 urgent task (force `soon: true` via a short due_at) | Row rendered with `COLOR.dangerLight` background, sorted above non-urgent |
| 2.3 | Tap row body (not the circle) | Navigates to `/doctor/tasks/<taskId>` → `TaskDetailSubpage` slides in |

### 3. Complete task from the list

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Seed 1 pending task | Row visible, `followups` count = 1 |
| 3.2 | Tap the circle checkbox on that row | Optimistic update: row disappears from 待完成, `followups` count decrements to 0 |
| 3.3 | Switch to `已完成` tab | The completed row is visible with "已完成" label or similar sent-style rendering |
| 3.4 | Reload the page | State persists: the task stays in `已完成` (API mutation was committed) |

### 4. Complete task from the detail page

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Seed 1 pending task → navigate directly to `/doctor/tasks/<taskId>` | Detail page shows task title, content, patient name |
| 4.2 | Tap the primary action (`完成` / `标记完成`) | Optimistic update; back navigation lands on 任务 tab with the item in `已完成` |

### 5. Empty states

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Fresh doctor (no tasks) → `/doctor/tasks` | `待完成` tab shows `EmptyState` component (not plain text); `NewItemCard` still rendered |
| 5.2 | Fresh doctor, switch to `已完成` | `EmptyState` component shown |

### 6. Origin banners

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Navigate `/doctor/tasks?origin=patient_submit` | Top banner "已创建审核任务" visible with subtitle |
| 6.2 | Navigate `/doctor/tasks?origin=review_finalize` | Top banner "已生成随访任务" visible |

---

## Edge cases

- **Task for deleted patient** — row shows task but patient link may 404;
  tap should degrade to a readable error, not crash.
- **Task with no due_at** — `relativeFuture(null)` returns empty string;
  due label area stays blank, no "NaN" or "Invalid Date".
- **Simultaneous complete via checkbox + detail-page button** — both mutate
  the same task; the second patch is a no-op (idempotent `status: completed`).
- **Long task content (200+ chars)** — truncated with ellipsis in the list
  row, full text only in detail.
- **URL `?tab=sent` (legacy deep link)** — `VALID_TABS` accepts it but the
  FilterBar only shows 2; the spec should not assert a third tab exists.

---

## Known issues

None specific to this workflow as of 2026-04-11. Bulk regression bugs from
`hero-path-qa-plan.md` §Known Issues do not land on TaskPage.

---

## Failure modes & debug tips

- **`待完成` count doesn't match seeded tasks** — the count combines
  `upcoming_followups.length + pending_tasks.length + urgent.length`. If the
  count is wrong, inspect `effectiveData` in `TaskPage.jsx:293`.
- **Tapping the checkbox opens the detail page** — event propagation bug.
  The circle must `stopPropagation()`; check `TaskPage.jsx:539`.
- **Complete mutation silently fails** — `handleCompleteTask` wraps the API
  call in `try { … } catch { /* silent */ }`. To debug, log the error or
  open the Network panel. The optimistic update succeeds visually but the
  server state drifts — a reload would reveal the divergence.
- **FilterBar shows 0 tabs** — `filter` state may have an unrecognized URL
  tab value. `VALID_TABS` filters down to `{followups, completed, sent}`;
  anything else resets to `followups` on mount.
