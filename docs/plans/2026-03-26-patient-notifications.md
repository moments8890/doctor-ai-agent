# Patient Notifications — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver in-app patient notifications as system messages in the chat feed, with a badge on the 主页 tab — covering P4.1 and P4.2 from the feature parity matrix.

**Architecture:** 3 new fields on the DoctorTask model (read_at, link_type, link_id). System chat messages inserted at 3 trigger points using the existing `save_patient_message()` function. Frontend renders `source="system"` messages as ListCard cards in the chat feed, with a Badge on the bottom nav.

**Tech Stack:** Python/FastAPI + SQLAlchemy (backend), React/MUI (frontend), existing components (ListCard, RecordAvatar, Badge)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/db/models/tasks.py` | Modify | Add `read_at`, `link_type`, `link_id` fields to DoctorTask |
| `src/channels/web/tasks.py` | Modify (~line 131) | Insert system chat message when patient task created |
| `src/channels/web/ui/diagnosis_handlers.py` | Modify (~line 320) | Insert system chat message when diagnosis finalized |
| `frontend/web/src/pages/patient/PatientPage.jsx` | Modify | Render system messages as ListCard + badge on 主页 tab |

---

### Task 1: Backend — Add fields to DoctorTask model

**Files:**
- Modify: `src/db/models/tasks.py:33-51`

- [ ] **Step 1: Read the current model**

Open `src/db/models/tasks.py` and find the `DoctorTask` class (line 33). Note the existing fields end around line 51 with `source_id`.

- [ ] **Step 2: Add 3 new fields**

After the `source_id` field (~line 51), add:

```python
    # --- Notification & linking support ---
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    link_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # record | task | chat
    link_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

Make sure `datetime` is already imported at the top of the file (it should be — it's used by `due_at` and `created_at`).

- [ ] **Step 3: Commit**

```bash
git add src/db/models/tasks.py
git commit -m "feat: add read_at, link_type, link_id fields to DoctorTask model"
```

---

### Task 2: Backend — Insert system message on patient task creation

**Files:**
- Modify: `src/channels/web/tasks.py:131-152`
- Reference: `src/db/crud/patient_message.py` (`save_patient_message` function)

- [ ] **Step 1: Read the task creation code**

Open `src/channels/web/tasks.py` and find `_create_task_for_doctor` (~line 131). This function creates a task and returns it. After the task is created and committed, we need to insert a system chat message if `target="patient"`.

Also check: `save_patient_message` is in `src/db/crud/patient_message.py` and takes `(session, patient_id, doctor_id, content, direction, source, sender_id, triage_category, ...)`. It creates a `PatientMessage` row.

- [ ] **Step 2: Add system message insertion**

After the task is created (after the `async with AsyncSessionLocal()` block), add a second block that inserts a system chat message when the task targets a patient:

```python
    # Notify patient via system chat message
    if task.target == "patient" and task.patient_id:
        try:
            async with AsyncSessionLocal() as notify_session:
                notify_content = (
                    f"复查提醒：{task.title}" if task.task_type == "follow_up"
                    else f"医生为您安排了新任务：{task.title}"
                )
                triage_cat = f"notification:task:{task.id}"
                await save_patient_message(
                    notify_session,
                    patient_id=task.patient_id,
                    doctor_id=doctor_id,
                    content=notify_content,
                    direction="outbound",
                    source="system",
                    triage_category=triage_cat,
                )
        except Exception:
            log.warning("Failed to send patient notification for task %s", task.id, exc_info=True)
```

Add the import at the top of the file:
```python
from src.db.crud.patient_message import save_patient_message
```

Also check if `log` is imported — the file likely uses `from src.utils.log import log` or similar. Follow the existing pattern.

- [ ] **Step 3: Handle the `target` field in task creation**

Check whether `TaskCreate` (the Pydantic request model) includes a `target` field. If not, check how `target="patient"` tasks are created. The `create_task` CRUD function may need a `target` parameter, or it may already accept `**kwargs`. Read the code and follow the existing pattern.

If `create_task()` doesn't pass `target`, add it:
```python
task = await create_task(
    session,
    doctor_id=doctor_id,
    task_type=body.task_type,
    title=body.title.strip(),
    content=body.content,
    patient_id=body.patient_id,
    due_at=due_at,
    target=getattr(body, "target", "doctor"),
)
```

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/tasks.py
git commit -m "feat: insert system chat message when patient task is created"
```

---

### Task 3: Backend — Insert system message on diagnosis finalize

**Files:**
- Modify: `src/channels/web/ui/diagnosis_handlers.py:245-325`
- Reference: `src/db/crud/patient_message.py` (`save_patient_message`)

- [ ] **Step 1: Read the finalize endpoint**

Open `src/channels/web/ui/diagnosis_handlers.py` and find `finalize_review` (~line 245). Find where `rec.status = RecordStatus.completed.value` is set (~line 320) and `await db.commit()` (~line 322). The record object `rec` has `patient_id` and `doctor_id` fields.

- [ ] **Step 2: Insert system message after finalize commit**

After the `await db.commit()` line in the finalize endpoint, add:

```python
    # Notify patient that diagnosis is ready
    if rec.patient_id:
        try:
            async with AsyncSessionLocal() as notify_session:
                await save_patient_message(
                    notify_session,
                    patient_id=rec.patient_id,
                    doctor_id=rec.doctor_id,
                    content="您的诊断结果已出，请查看病历",
                    direction="outbound",
                    source="system",
                    triage_category=f"notification:record:{rec.id}",
                )
        except Exception:
            log.warning("Failed to send diagnosis notification for record %s", rec.id, exc_info=True)
```

Add the import at the top of the file:
```python
from src.db.crud.patient_message import save_patient_message
```

Check how `AsyncSessionLocal` and `log` are imported in this file — follow the existing pattern.

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/ui/diagnosis_handlers.py
git commit -m "feat: insert system chat message when diagnosis is finalized"
```

---

### Task 4: Frontend — Render system messages as notification cards in chat

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (ChatTab, ~lines 300-370)

- [ ] **Step 1: Read the existing message rendering**

Open PatientPage.jsx and find the `renderMessage` function inside ChatTab. It currently handles 3 source types:
- `source === "doctor"` → `DoctorBubble`
- `source === "patient"` → right-aligned green bubble
- fallback (AI) → left-aligned white bubble

- [ ] **Step 2: Add system message rendering branch**

Before the AI fallback branch, add a branch for `source === "system"`. Parse `triage_category` to extract link info, then render a `ListCard`:

```jsx
// System notification card
if (src === "system") {
  const parts = (msg.triage_category || "").split(":");
  const linkType = parts[1] || null;   // "record" or "task"
  const linkId = parts[2] || null;     // entity ID

  // Choose avatar based on link type
  let avatar;
  let onTap;
  if (linkType === "record") {
    avatar = <RecordAvatar type="visit" size={32} />;
    onTap = () => navigate(`/patient/records/${linkId}`);
  } else if (linkType === "task") {
    avatar = (
      <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: COLOR.primaryLight,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <AssignmentOutlinedIcon sx={{ fontSize: 16, color: COLOR.primary }} />
      </Box>
    );
    onTap = () => setTab("tasks");
  } else {
    avatar = (
      <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: COLOR.surface,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <NotificationsNoneOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4 }} />
      </Box>
    );
    onTap = null;
  }

  return (
    <Box key={msg.id || idx} sx={{ px: 1.5, py: 0.5 }}>
      <ListCard
        avatar={avatar}
        title={msg.content}
        subtitle={onTap ? "点击查看" : undefined}
        chevron={!!onTap}
        onClick={onTap}
        sx={{ borderLeft: `3px solid ${COLOR.primary}`, borderRadius: "4px" }}
      />
    </Box>
  );
}
```

- [ ] **Step 3: Add missing imports**

Add to the MUI icon imports at the top of the file (if not already present):
```jsx
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
```

`AssignmentOutlinedIcon` should already be imported (used in NAV_TABS). `ListCard`, `RecordAvatar`, `COLOR` should already be imported from previous tasks.

Check that the `navigate` function and `setTab` function are accessible inside the `renderMessage` closure. They should be — `renderMessage` is defined inside `ChatTab` which has both in scope.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): render system messages as notification cards in chat feed"
```

---

### Task 5: Frontend — Add badge to 主页 tab

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (bottom nav, ~lines 1124-1134)

- [ ] **Step 1: Add Badge import**

Add `Badge` to the MUI imports at the top of PatientPage.jsx:

```jsx
import Badge from "@mui/material/Badge";
```

- [ ] **Step 2: Add unread count state and logic**

In the `PatientPage` root component (not ChatTab), add state and logic for the unread count. Find where `messages` are available or polled.

The challenge: messages are polled inside `ChatTab`, but the badge is in the parent `PatientPage`. The simplest approach: lift the unread count up. Add a callback from ChatTab to PatientPage:

In PatientPage root component, add:
```jsx
const [unreadCount, setUnreadCount] = useState(0);
```

Pass it to ChatTab:
```jsx
<ChatTab ... onUnreadCountChange={setUnreadCount} />
```

Inside ChatTab, add an effect that computes unread count after each poll:
```jsx
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";

useEffect(() => {
  if (onUnreadCountChange && messages.length > 0) {
    const lastSeen = parseInt(localStorage.getItem(LAST_SEEN_CHAT_KEY) || "0", 10);
    const unread = messages.filter(m => {
      const msgTime = new Date(m.created_at).getTime();
      return msgTime > lastSeen;
    }).length;
    onUnreadCountChange(unread);
  }
}, [messages, onUnreadCountChange]);
```

When the chat tab becomes active (user navigates to it), clear the badge:
```jsx
// In PatientPage, when tab changes to "chat":
useEffect(() => {
  if (tab === "chat") {
    localStorage.setItem(LAST_SEEN_KEY, String(Date.now()));
    setUnreadCount(0);
  }
}, [tab]);
```

Note: `LAST_SEEN_KEY` must be the same constant in both places. Define it near the other storage keys at the top of the file:
```jsx
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
```

- [ ] **Step 3: Add badge to bottom nav**

Modify the `BottomNavigation` rendering (~line 1130). Wrap the chat tab icon with `Badge` when `unreadCount > 0`:

```jsx
{NAV_TABS.map(t => (
  <BottomNavigationAction
    key={t.key}
    value={t.key}
    label={t.label}
    icon={
      t.key === "chat" && unreadCount > 0
        ? <Badge badgeContent={unreadCount} color="error">{t.icon}</Badge>
        : t.icon
    }
    sx={{ "&.Mui-selected": { color: "#07C160" } }}
  />
))}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): add unread badge to 主页 tab in bottom nav"
```

---

### Task 6: Verify end-to-end

- [ ] **Step 1: Test notification insertion (backend)**

Using curl, create a patient-facing task and verify a system message appears:

```bash
# Create a patient task
curl -X POST "http://localhost:8000/api/tasks?doctor_id=test_doctor" \
  -H "Content-Type: application/json" \
  -d '{"task_type":"follow_up","title":"复查CT","patient_id":13,"target":"patient"}'

# Check patient chat messages for system message
TOKEN="<patient_token>"
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/patient/chat/messages"
```

Verify a message with `source="system"` and `content="复查提醒：复查CT"` appears.

- [ ] **Step 2: Test frontend rendering**

1. Log in as patient at `http://localhost:5173/patient`
2. Go to 主页 tab (chat)
3. Verify system notification cards render with ListCard (green left border, icon avatar, chevron)
4. Verify tapping a notification card navigates to the correct page (tasks or records)
5. Verify badge count appears on 主页 tab when switching away and back

- [ ] **Step 3: Test edge cases**

1. System message with no triage_category → renders with bell icon, no chevron, no navigation
2. System message with `notification:record:999` (non-existent record) → navigates to record page (may show error — acceptable)
3. No system messages → no notification cards, no badge
4. Multiple system messages → all render as separate cards in feed order

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(patient): address edge cases in notification rendering"
```
