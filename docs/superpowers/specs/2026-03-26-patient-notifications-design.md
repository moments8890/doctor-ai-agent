# Patient Notifications — Design Spec

> **Features:** P4.1 (Patient Notification Capability), P4.2 (Follow-up Reminders)
> **Scope:** Patient app only. In-app notifications via chat feed. No external push.
> **Date:** 2026-03-26

---

## 1. Architecture

Zero new infrastructure. Patient notifications are delivered as **system chat messages** (`source="system"`) in the existing chat feed. The existing polling loop (`GET /api/patient/chat/messages`, 10s interval) picks them up automatically.

**Additionally**, 3 general-purpose fields are added to the `DoctorTask` model (`read_at`, `link_type`, `link_id`) — useful for both doctor and patient workflows, not notification-specific.

---

## 2. Notification Triggers

Doctor actions only — 4 triggers:

| Trigger | When | System Message Content | Link |
|---------|------|----------------------|------|
| **Doctor reply** | Doctor sends reply to patient via chat | N/A — doctor reply already appears as `source="doctor"` message, no extra system message needed | — |
| **Task assigned** | Task created with `target="patient"` | `医生为您安排了新任务：{title}` | `link_type="task"`, `link_id={task_id}` |
| **Diagnosis ready** | Record review finalized (`/review/finalize` endpoint) | `您的诊断结果已出，请查看病历` | `link_type="record"`, `link_id={record_id}` |
| **Follow-up reminder** | Task with `task_type="follow_up"` created for patient | `复查提醒：{title}` | `link_type="task"`, `link_id={task_id}` |

Note: Doctor replies don't need a separate system message — they already show in chat as `source="doctor"` via `DoctorBubble`. The badge count includes all message sources.

**Effective triggers: 3** (task_assigned, diagnosis_ready, follow_up_reminder).

---

## 3. Backend Changes

### 3.1 DoctorTask Model — 3 New Fields

Add to `src/db/models/tasks.py`:

```
read_at: datetime nullable — when the task was first seen by the target
link_type: str nullable — "record", "task", "chat"
link_id: int nullable — ID of the linked entity
```

These are general-purpose fields useful for both doctor and patient task workflows.

### 3.2 System Message Insertion Points

Insert `source="system"` chat messages at these locations:

**1. Task assigned to patient** — in task creation code (`src/domain/tasks/task_crud.py` or `src/channels/web/tasks.py`), when a new task has `target="patient"`:
```
Insert chat message: source="system", content="医生为您安排了新任务：{task.title}"
```

**2. Diagnosis finalized** — in `src/channels/web/ui/diagnosis_handlers.py`, in the finalize endpoint, after setting record status to completed:
```
Insert chat message: source="system", content="您的诊断结果已出，请查看病历"
```

**3. Follow-up reminder created** — same as task assigned, but when `task_type="follow_up"`:
```
Insert chat message: source="system", content="复查提醒：{task.title}"
```

### 3.3 Chat Message Schema

System messages use the existing chat messages table with:
- `source`: `"system"` (new value, alongside existing `"patient"`, `"ai"`, `"doctor"`)
- `content`: notification text (Chinese)
- `sender_id`: `null`
- `triage_category`: `"notification"` (new value, used for frontend rendering branch)
- `patient_id`: target patient
- `doctor_id`: source doctor

No schema changes needed — the table already supports arbitrary `source` and `triage_category` string values.

---

## 4. Frontend Changes

### 4.1 Chat Feed — System Message Cards

In the chat message rendering loop (PatientPage.jsx ChatTab), add a branch for `source === "system"` messages. Render as a `ListCard`:

```jsx
<ListCard
  avatar={<RecordAvatar type="visit" size={32} />}
  title="您的诊断结果已出"
  subtitle="点击查看病历"
  chevron
  onClick={() => navigate(`/patient/records/${linkId}`)}
/>
```

**Avatar per notification type:**

| `triage_category` | Avatar | Navigate to |
|-------------------|--------|-------------|
| `notification:task:{id}` | Simple icon Box (task icon, `COLOR.primary`) | `/patient/tasks` |
| `notification:record:{id}` | `RecordAvatar type="visit"` | `/patient/records/{id}` |
| `notification` (no link) | Simple icon Box (bell icon, `COLOR.text4`) | non-navigable |

**Parsing link info:** Use `triage_category` to encode notification type and link info as a structured string:

```
triage_category: "notification:record:5"   → link_type="record", link_id=5
triage_category: "notification:task:12"    → link_type="task", link_id=12
triage_category: "notification"            → no link (informational only)
```

Frontend splits on `:` to extract link info. `content` stays clean human-readable text. No schema changes needed — `triage_category` is already a free-form string field.

### 4.2 Badge on 主页 Tab

Red dot + unread count on the 主页 tab icon in the bottom nav.

**Count logic:**
- Store `last_seen_chat` timestamp in localStorage (key: `patient_last_seen_chat`)
- On chat tab open: set `last_seen_chat = Date.now()`
- Badge count = messages (all sources) where `created_at > last_seen_chat`
- Poll count alongside existing chat message polling (no extra request)

**Implementation:** Use MUI `Badge` component (already used on doctor's task tab):
```jsx
<BottomNavigationAction
  icon={unreadCount > 0 ? <Badge badgeContent={unreadCount} color="error"><ChatIcon /></Badge> : <ChatIcon />}
  ...
/>
```

### 4.3 Reused Components

| Component | Usage |
|-----------|-------|
| `ListCard` | Notification card in chat feed |
| `RecordAvatar` | Avatar for diagnosis/record notifications |
| MUI `Badge` | Unread count on tab icon |

### 4.4 New Components

None. The notification icon avatars are simple inline `Box` elements (same pattern as existing quick action cards in chat tab).

---

## 5. Data Flow

```
Doctor action (create task / finalize diagnosis / create follow-up)
    │
    ▼
Backend inserts system chat message (source="system", triage_category="notification:...")
    │
    ▼
Patient portal polls GET /api/patient/chat/messages (every 10s)
    │
    ▼
Frontend renders source="system" messages as ListCard notification cards in chat feed
    │
    ▼
Badge count on 主页 tab = messages since last_seen_chat
    │
    ▼
Patient opens chat tab → last_seen_chat updated → badge clears
```

---

## 6. Design System Compliance

- [x] All `TYPE`/`COLOR`/`ICON` tokens from theme.js
- [x] No shadows, no gradients — flat only
- [x] Reuses existing components (ListCard, RecordAvatar, Badge)
- [x] Chinese-first labels
- [x] No new tabs or navigation changes
- [x] System messages visually distinct from patient/AI/doctor messages
