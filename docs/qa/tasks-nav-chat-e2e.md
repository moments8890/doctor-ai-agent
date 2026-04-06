# Tasks, Navigation & Chat E2E Regression Checklist

Scripted walkthrough of the task pipeline, navigation/UI polish, and chat/AI
interaction. Run this after changes to task management, page routing, or chat
infrastructure.

**Tool**: gstack `/qa` (headless Chromium via `$B`) or manual browser at http://127.0.0.1:5173/doctor
**Test account**: `doctor_id=test_doctor` (URL param or cookie)
**Backend**: default port **8000** (`./dev.sh`); use **8001** for isolated API-only runs
**Prerequisite**: seed demo data first (see Setup)
**Time to complete**: ~15 min manual, ~8 min automated

---

## Setup

```bash
# Start dev server
./dev.sh

# Seed demo data (creates patients, tasks, messages)
curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/seed-demo" \
  -H "Content-Type: application/json" -d '{"doctor_id":"test_doctor"}'
```

Navigate to: `http://127.0.0.1:5173/doctor?doctor_id=test_doctor`

If the onboarding wizard appears, skip it or set localStorage:
```javascript
localStorage.setItem('onboarding_wizard_done:test_doctor', 'completed')
```

---

## TC-1 · Task List & Filtering

Navigate to 任务 tab (bottom nav, 4th tab).

| # | Action | Pass Criteria |
|---|--------|--------------|
| 1.1 | View 任务 tab | Page loads with summary: 待完成 (N) / 已完成 (N) filter tabs |
| 1.2 | Check 待完成 list | Task cards show: title, due date (relative: 明天, 3天后, etc.), chevron |
| 1.3 | Click 已完成 tab | Completed tasks shown with green checkmarks, different from pending style |
| 1.4 | Click back to 待完成 | Pending tasks reappear, list is consistent |
| 1.5 | Check badge count | Badge on 任务 tab matches number of pending tasks in list |
| 1.6 | 新建任务 button visible | Green "新建任务" row at top of task list with "添加待办提醒或随访任务" subtitle |

**Verify via API:**
```bash
curl -s "http://127.0.0.1:8000/api/tasks?doctor_id=test_doctor" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); items=d if isinstance(d,list) else d.get('items',[]); pending=[i for i in items if i.get('status') in ('pending','notified')]; print(f'total: {len(items)}, pending: {len(pending)}')"
```

---

## TC-2 · Task Detail View

| # | Action | Pass Criteria |
|---|--------|--------------|
| 2.1 | Click a pending task | Task detail page loads at `/doctor/tasks/{id}` |
| 2.2 | Check fields | Shows: title (bold), 患者 (clickable link), 截止 (date + relative), 来源, 类型, 详情 |
| 2.3 | Check buttons | 查看患者 (secondary) and 标记完成 (primary green) buttons present |
| 2.4 | Check 备注 | Text area with placeholder "添加备注..." |
| 2.5 | Check 提醒 | Shows "未设置" or configured reminder |
| 2.6 | Check 删除任务 | Red text link at bottom |
| 2.7 | Click 查看患者 | Navigates to patient detail page |

---

## TC-3 · Task Completion

| # | Action | Pass Criteria |
|---|--------|--------------|
| 3.1 | Click 标记完成 on a task | Task status changes to completed |
| 3.2 | Return to task list | Task moves from 待完成 to 已完成 tab |
| 3.3 | Badge count decrements | 任务 tab badge shows N-1 |
| 3.4 | Check completed task | Shows green checkmark, greyed-out style |

**Verify via API:**
```bash
TASK_ID=<id>
curl -s -X PATCH "http://127.0.0.1:8000/api/tasks/$TASK_ID" \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","doctor_id":"test_doctor"}' \
  | python3 -m json.tool
```

---

## TC-4 · Task Creation

| # | Action | Pass Criteria |
|---|--------|--------------|
| 4.1 | Click 新建任务 | Task creation form/dialog opens |
| 4.2 | Fill title + select patient | Form accepts input |
| 4.3 | Set due date | Date picker works |
| 4.4 | Submit | `POST /api/tasks → 200`; task appears in pending list |

---

## TC-5 · Tab Navigation

Starting from 我的AI tab.

| # | Action | Pass Criteria |
|---|--------|--------------|
| 5.1 | Click 我的AI tab | Navigates to `/doctor`; content loads without console errors |
| 5.2 | Click 患者 tab | Navigates to `/doctor/patients`; patient list loads |
| 5.3 | Click 审核 tab | Navigates to `/doctor/review`; review queue loads with summary counts |
| 5.4 | Click 任务 tab | Navigates to `/doctor/tasks`; task list loads |
| 5.5 | Rapid tab switching | Click all 4 tabs in quick succession; no crash, no console errors |

**Console check after each navigation:**
```javascript
// In browser console — should return 0
document.querySelectorAll('.error').length
```

---

## TC-6 · Subpage Navigation

| # | Action | Pass Criteria |
|---|--------|--------------|
| 6.1 | 患者 tab → click a patient | Navigates to `/doctor/patients/{id}`; patient detail loads |
| 6.2 | Browser back button | Returns to `/doctor/patients`; patient list intact |
| 6.3 | 审核 tab → click a review item | Navigates to `/doctor/review/{id}`; review page loads |
| 6.4 | Browser back button | Returns to `/doctor/review` |
| 6.5 | 任务 tab → click a task | Navigates to `/doctor/tasks/{id}`; task detail loads |
| 6.6 | Browser back button | Returns to `/doctor/tasks` |

---

## TC-7 · Responsive Layout

| # | Action | Pass Criteria |
|---|--------|--------------|
| 7.1 | Viewport 375x812 (iPhone) | Full-width layout, nav tabs visible at bottom, no horizontal overflow |
| 7.2 | Viewport 768x1024 (iPad) | Centered card layout, proper spacing, no text truncation issues |
| 7.3 | Viewport 1280x720 (Desktop) | Centered max-width container (~800px), no stretch to full width |
| 7.4 | Resize from mobile → desktop | Layout adapts smoothly, no layout jumps or broken elements |

**Automated check:**
```bash
$B viewport 375x812 && $B screenshot screenshots/responsive-mobile.png
$B viewport 768x1024 && $B screenshot screenshots/responsive-tablet.png
$B viewport 1280x720 && $B screenshot screenshots/responsive-desktop.png
```

---

## TC-8 · Badge Counts

| # | Action | Pass Criteria |
|---|--------|--------------|
| 8.1 | Check 审核 tab badge | Number matches count of pending review items (待审核 count) |
| 8.2 | Check 任务 tab badge | Number matches count of pending tasks |
| 8.3 | Complete a task → check badge | Badge decrements by 1 |
| 8.4 | Finalize a review → check badge | 审核 badge decrements |

---

## TC-9 · Chat Interface

Navigate to 新建病历 (from 我的AI tab or direct: `/doctor/patients/new`).

| # | Action | Pass Criteria |
|---|--------|--------------|
| 9.1 | Open 新建病历 | Chat interface loads with AI system message: "病历采集模式已开启。请输入患者信息..." |
| 9.2 | Check input bar | Text input, mic button (left), attachment button (+), send button (right arrow) |
| 9.3 | Type and send message | User bubble appears with correct text; "处理中..." spinner shows |
| 9.4 | Wait for AI response | AI responds with structured extraction (name, symptoms parsed); status bar updates |

**LLM timeout behavior:**
| # | Action | Pass Criteria |
|---|--------|--------------|
| 9.5 | If LLM times out | Error message shown: "出错: Request timed out" or "系统暂时繁忙，请重新发送您的回答。" |
| 9.6 | After timeout | App does NOT crash; input field remains available; no console errors |
| 9.7 | Retry after timeout | User can type and send again |

---

## TC-10 · Chat with Existing Patient

| # | Action | Pass Criteria |
|---|--------|--------------|
| 10.1 | Navigate to patient detail → chat tab | `/doctor/patients/{id}?view=chat`; chat history loads |
| 10.2 | Check message display | Messages show correct direction (patient left, doctor right), timestamps |
| 10.3 | Check draft bubble | If AI draft exists, shows with citation badges and 确认发送/修改 buttons |
| 10.4 | Send a message | Message appears in chat; response from AI or "处理中..." spinner |

---

## TC-11 · Voice Mode Toggle

| # | Action | Pass Criteria |
|---|--------|--------------|
| 11.1 | Click mic icon (left of text input) | Voice mode activates: shows "按住说话" + keyboard icon appears on the left |
| 11.2 | Click keyboard icon | Returns to normal text input mode |
| 11.3 | Toggle multiple times | Mode switches correctly each time, no stuck state |

*(BUG-NEW-001 regression from core-e2e-regression.md)*

---

## TC-12 · Console Health (Cross-cutting)

| # | Action | Pass Criteria |
|---|--------|--------------|
| 12.1 | Navigate all 4 tabs | Zero JS errors in console |
| 12.2 | Open and close a subpage | Zero JS errors |
| 12.3 | Send a chat message | Zero JS errors (even if LLM times out) |
| 12.4 | Switch between filter tabs (任务, 审核) | Zero JS errors |

---

## Pass/Fail Criteria Summary

| Area | Must pass to ship |
|------|------------------|
| TC-1–2 Task list | Tasks render with correct data; filter tabs switch correctly |
| TC-3 Completion | Status change works; badge updates |
| TC-5–6 Navigation | All tabs load; back button works; no console errors |
| TC-7 Responsive | Mobile/tablet/desktop all render correctly |
| TC-9 Chat interface | Chat loads; message sends; timeout handled gracefully |
| TC-12 Console | Zero JS errors across all navigation |

TC-3 (task completion), TC-4 (creation), and TC-9.4 (LLM response quality) require
a running LLM backend. If the local model is offline, mark as **INFRA** not **FAIL**.

---

## Running with gstack `/qa`

```
/qa
```

In the `/qa` prompt:
> Run the tasks + navigation + chat E2E checklist: (1) Open 任务 tab, verify 待完成/已完成 filter, click a task detail, check all fields. (2) Navigate all 4 tabs checking for console errors. (3) Test subpage push/pop with browser back button. (4) Check responsive at 375/768/1280. (5) Open 新建病历, send a test message, verify AI responds or timeout is handled gracefully. Report pass/fail per TC.

---

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-04-05 | 19/20 pass | §8 6/6, §20 10/10, §9 3/4. LLM timeout (local Ollama offline, not code bug). Error handling verified working. |
