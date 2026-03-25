# Doctor QA Simulation Plan

Reusable plan for simulating a doctor user interacting with the web UI via
Playwright (headless Edge). Run this plan whenever the UI changes significantly
to catch regressions, broken flows, and UX issues.

**Tool**: Playwright MCP (`--browser msedge`)
**Target**: `http://localhost:5173` (local Vite dev) or production URL
**Persona**: Dr. Chen, neurologist, new to the platform

---

## 0. Prerequisites

| Step | Command / Action | Done? |
|------|------------------|-------|
| Start backend + frontend | `./cli.py start --provider deepseek` | |
| Create invite code | See [Invite Code Script](#invite-code-script) below | |
| Seed test patients (optional) | `PYTHONPATH=src ENVIRONMENT=development .venv/bin/python scripts/seed_ui_data.py` | |

### Invite Code Script

```bash
PYTHONPATH=src ENVIRONMENT=development .venv/bin/python -c "
import asyncio
from db.engine import AsyncSessionLocal
from db.models import InviteCode
from datetime import datetime, timedelta, timezone

async def create_invite():
    async with AsyncSessionLocal() as db:
        code = InviteCode(
            code='TESTDOC2026',
            doctor_name='测试医生',
            active=True,
            max_uses=10,
            used_count=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(code)
        await db.commit()
        print(f'Created invite code: {code.code}')

asyncio.run(create_invite())
"
```

---

## 1. Registration & Login

**Goal**: Register as a new doctor, verify token persistence, verify redirect.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 1.1 | Navigate to `/login` | Login page renders with Doctor/Patient tabs | P0 |
| 1.2 | Select "Doctor" tab, click "注册" (register) | Registration form shows: name, phone, year of birth, invite code, specialty | P0 |
| 1.3 | Fill form: name=陈医生, phone=13800001111, yob=1985, code=TESTDOC2026 | Form accepts input | P0 |
| 1.4 | Submit registration | Redirect to `/doctor`, working context header visible | P0 |
| 1.5 | Refresh page | Session persists, still on `/doctor` | P1 |
| 1.6 | Navigate to `/login` while logged in | Should redirect to `/doctor` or show logged-in state | P2 |

---

## 2. Home / Briefing

**Goal**: Verify the daily dashboard loads with correct stats.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 2.1 | View home (default after login) | 4 stat cards render (pending, patients, tasks, completed) | P1 |
| 2.2 | Check stats values | Values are 0 or match DB counts (new doctor) | P2 |
| 2.3 | Click a stat card (e.g., "today_patients") | Navigates to correct section (`/doctor/patients`) | P2 |
| 2.4 | Check AskAI bar | Input bar visible at bottom (mobile) or sidebar (desktop) | P2 |

---

## 3. Patient Management

**Goal**: Create patients, verify list, detail view, search.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 3.1 | Navigate to `/doctor/patients` | Patient list renders (empty for new doctor) | P0 |
| 3.2 | Click "+" or "新增患者" | New patient form/dialog opens | P0 |
| 3.3 | Create patient: name=王小明, gender=男, yob=1960, phone=13900001111 | Patient created, appears in list | P0 |
| 3.4 | Create 2nd patient: name=李小红, gender=女, yob=1975 | Patient created | P1 |
| 3.5 | Search "王" in search bar | Filters to 王小明 | P1 |
| 3.6 | Click 王小明 | Patient detail page renders with info header | P0 |
| 3.7 | Check tabs: All, Medical, Lab/Imaging | Tabs render, all empty initially | P1 |
| 3.8 | Check label management | Can add/remove labels | P2 |
| 3.9 | Test delete patient (on 2nd patient) | Confirmation dialog, patient removed | P2 |

---

## 4. Medical Records

**Goal**: Create records via chat and direct entry, verify 病历字段 render.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 4.1 | Navigate to chat, send: "给王小明创建一条病历，主诉头痛两周伴恶心" | AI creates a draft record, working context shows pending | P0 |
| 4.2 | Check working context header | Shows pending draft for 王小明 | P1 |
| 4.3 | Navigate to tasks → review queue | Draft appears as pending review item | P0 |
| 4.4 | Click review item | ReviewDetail page opens with 病历字段 pre-filled | P0 |
| 4.5 | Verify 病历字段: chief_complaint, present_illness, etc. | Fields populated from AI structuring | P1 |
| 4.6 | Edit a field (e.g., add to diagnosis) | Edit mode works, saves on blur | P1 |
| 4.7 | Click "确认" to confirm the record | Record saved, appears under patient records | P0 |
| 4.8 | Navigate to 王小明 → records tab | Record visible with correct type and date | P0 |

---

## 5. AI Chat

**Goal**: Test all chat features — text, quick commands, file upload.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 5.1 | Navigate to `/doctor/chat` | Chat interface loads, quick command chips visible | P0 |
| 5.2 | Tap "今日摘要" chip | AI responds with daily summary | P1 |
| 5.3 | Send: "查询王小明的病历" | AI returns patient info + records | P1 |
| 5.4 | Send: "给王小明安排一周后复查" | AI creates a follow-up task | P1 |
| 5.5 | Test clear context button | Chat cleared, working context reset | P2 |
| 5.6 | Send a long message (>500 chars) | Message sent, no truncation | P2 |
| 5.7 | Send empty message | Button disabled or no-op | P2 |

---

## 6. Tasks

**Goal**: Test task CRUD, filters, status transitions.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 6.1 | Navigate to `/doctor/tasks` | Task list renders | P0 |
| 6.2 | Check filter chips: All, Review, Task, Done | Filters work, counts update | P1 |
| 6.3 | Click "+" to create task | Dialog opens with title, type, due date | P0 |
| 6.4 | Create task: title=复查血压, type=follow_up, due=tomorrow | Task created, appears under "明天" group | P0 |
| 6.5 | Mark task as completed | Status changes, moves to "Done" filter | P1 |
| 6.6 | Postpone a task | Due date updates, task moves to new group | P2 |
| 6.7 | Delete/cancel a task | Task removed from active list | P2 |

---

## 7. Settings & Knowledge Base

**Goal**: Test profile editing, specialty picker, knowledge CRUD.

| # | Action | Expected | Severity |
|---|--------|----------|----------|
| 7.1 | Navigate to `/doctor/settings` | Settings page renders with profile rows | P0 |
| 7.2 | Edit name | Name dialog opens, saves on confirm | P1 |
| 7.3 | Select specialty (e.g., 神经内科) | Specialty grid picker works, saves | P1 |
| 7.4 | Navigate to knowledge base section | Knowledge list renders (empty initially) | P1 |
| 7.5 | Add knowledge item: "脑梗死急性期NIHSS评估流程" | Item created, appears in list | P1 |
| 7.6 | Delete knowledge item | Item removed | P2 |
| 7.7 | Test logout | Confirmation dialog → redirect to `/login` | P1 |

---

## 8. Cross-cutting Concerns

| # | Check | Expected | Severity |
|---|-------|----------|----------|
| 8.1 | Mobile responsive layout (375px viewport) | Bottom nav, cards stack vertically | P1 |
| 8.2 | Loading states | Skeleton/spinner shown during API calls | P2 |
| 8.3 | Error states (kill backend, retry) | Error message shown, not blank page | P1 |
| 8.4 | Empty states | Friendly "no data" messages, not blank | P2 |
| 8.5 | Navigation back button (mobile) | SubpageHeader back works correctly | P1 |
| 8.6 | URL deep linking | `/doctor/patients/1` loads directly | P2 |
| 8.7 | Token expiry / unauthorized | Redirects to login, not infinite loop | P1 |

---

## 9. Test Data Generation

If seed data is needed mid-test, use chat to create records naturally:

```
# Via AI chat (simulates real doctor workflow):
"录入患者：张三，男，58岁，主诉胸闷气短1月"
"给张三补充病史：高血压10年，糖尿病5年，规律服药"
"给张三安排心电图检查，下周一"
```

Or via API directly:

```bash
# Create patient via API
curl -X POST http://localhost:8000/api/manage/patients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"张三","gender":"男","year_of_birth":1968}'
```

---

## 10. Bug Report Template

For each issue found, record:

```markdown
### BUG-{N}: {one-line summary}

- **Severity**: P0 (blocker) | P1 (major) | P2 (minor) | P3 (cosmetic)
- **Section**: login | home | patients | records | chat | tasks | settings
- **Steps**: 1. ... 2. ... 3. ...
- **Expected**: ...
- **Actual**: ...
- **Screenshot**: (Playwright screenshot path)
- **Console errors**: (if any)
```

---

## Execution Notes

- Use `browser_snapshot` (accessibility tree) for finding element refs to click/fill
- Use `browser_take_screenshot` for visual evidence of bugs
- Test mobile-first (default Playwright viewport) then desktop (resize to 1280x800)
- After completing all sections, compile findings into `docs/qa/simulation-report-{date}.md`
