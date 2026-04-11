# Workflow 10 — Tasks browse + complete

Ship gate for the **任务** tab — doctor follow-up tasks and scheduled
outreach. Covers the task list (pending / scheduled / sent / completed
rows) and the task detail subpage where a doctor can complete,
reschedule, or cancel a task.

**Area:** `src/pages/doctor/TaskPage.jsx`, `TaskDetailSubpage.jsx`,
`/api/doctor/tasks`, task mutations
**Spec:** `frontend/web/tests/e2e/10-tasks.spec.ts`
**Estimated runtime:** ~5 min manual / ~40 s automated

---

## Scope

**In scope**

- Task list shell + FilterBar tabs (待处理 / 已安排 / 已发送 / 已完成).
- Per-row actions via `ActionRow` checkbox pattern (done/pending).
- Badge count per status.
- Task detail subpage: read-only info + action buttons.
- Mark-complete flow with optimistic update.
- Reschedule to a new time.
- Cancel task (remove from queue).
- Empty states per tab.
- Back nav to previous tab.

**Out of scope**

- Task creation from AI suggestions — that's part of [08](08-review-diagnosis.md)
  (confirming a diagnosis suggestion may create an auto-task).
- Batch operations on multiple tasks.
- Recurring tasks / complex scheduling rules.

---

## Pre-flight

Seed tasks via the doctor API. If there is no direct `POST
/api/doctor/tasks` endpoint exposed, create tasks indirectly by
confirming review suggestions that auto-create tasks, or use a
test-only seeder route.

For a minimum viable test, register a doctor, confirm one diagnosis
suggestion, and verify a task appears.

---

## Steps

### 1. Task list shell

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Tap 任务 bottom-nav tab | Header "任务"; filter bar with tabs 待处理 / 已安排 / 已发送 / 已完成; 待处理 active by default |
| 1.2 | Pending count badge | Matches number of pending tasks (visible on the nav tab icon) |
| 1.3 | Task row | ActionRow with checkbox (unchecked circle for pending), title, subtitle (patient name + action), due date, chevron |

### 2. Tab switching

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap 已安排 | List filters to scheduled tasks; badge count for 待处理 unchanged |
| 2.2 | Tap 已发送 | Shows sent tasks |
| 2.3 | Tap 已完成 | Shows completed tasks with ✓ checked state |
| 2.4 | Empty tab | EmptyState per tab (not blank) |

### 3. Task detail

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap any pending task row | Navigates to `/doctor/tasks/<id>`; TaskDetailSubpage slides in |
| 3.2 | Detail content | Task title, description, patient link, due date, source (AI-generated vs manual), status |
| 3.3 | Action buttons | 完成 / 重新安排 / 取消任务 (or similar) |

### 4. Complete task

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Tap `完成` | Optimistic: row updates to ✓ (checked); task moves from 待处理 to 已完成 tab |
| 4.2 | Navigate back | 待处理 badge decremented by 1 |
| 4.3 | Reload | Persisted state matches post-complete |

### 5. Reschedule task

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Open a task → tap `重新安排` | Date picker or input opens |
| 5.2 | Pick a future date → confirm | Due date updates; task stays in its tab (待处理 or 已安排) |

### 6. Cancel task

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Open a task → tap `取消任务` | Confirm dialog "确认取消任务？" |
| 6.2 | Confirm | Task removed from queue entirely (not moved to 已完成) |

### 7. Row checkbox shortcut

| # | Action | Verify |
|---|--------|--------|
| 7.1 | Tap the unchecked circle on a pending row (without opening detail) | Task marked complete inline; row moves/updates |

---

## Edge cases

- **Task with overdue due date** — rendered with warning color, possibly
  top of 待处理.
- **Task for deleted patient** — row shows task but patient link
  broken; tap should either show error or route to a placeholder.
- **Completing a task with no action target** — no follow-up navigation
  required; just status flip.
- **Simultaneous complete via checkbox + detail page** — no race;
  second mutation is a no-op.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues. Task-specific: none
open as of 2026-04-11.

Tasks are currently scoped out of the primary hero path since
[nav redesign] merged tasks into 审核 and 我的AI surfaces. If the 任务
tab is deprecated in a future release, retire this workflow plan.

---

## Failure modes & debug tips

- **Task badge count mismatch** — badge uses `useTaskBadge(doctorId)`
  while the list uses `useTasks(...)`; both hit `/api/doctor/tasks` but
  count filter may differ. Verify the pending filter matches.
- **Complete doesn't persist** — check task mutation returns updated
  task object + invalidates `QK.tasks(doctorId)`.
- **Checkbox tap opens detail page instead of completing** — event
  bubbling issue; the checkbox click handler needs `e.stopPropagation()`.
- **Reschedule picker locale wrong** — MUI date picker locale not set;
  add `dateAdapter` with Chinese locale if needed.
