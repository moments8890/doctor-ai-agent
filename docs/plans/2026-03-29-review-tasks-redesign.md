# Review + Tasks Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the remaining items from the review-tasks redesign spec: task detail subpage, "+ 新建" create button, DB schema additions (reminder_at, notes, completed_at), and a GET-single-task API endpoint.

**Architecture:** Backend adds 3 columns to `doctor_tasks` table and a new GET endpoint that joins patient name. Frontend restructures TaskPage to use PageSkeleton with mobileView for a task detail subpage, and adds a SheetDialog for task creation.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + MUI (frontend), design tokens from `theme.js`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/db/models/tasks.py` | Add `reminder_at`, `notes`, `completed_at` columns |
| Modify | `src/db/crud/tasks.py` | Add `update_task_notes` fn, set `completed_at` on completion |
| Modify | `src/db/repositories/tasks.py` | Add `update_notes` method, update `update_status` for completed_at |
| Modify | `src/channels/web/tasks.py` | Add GET `/{task_id}` endpoint, PATCH `/{task_id}/notes`, extend TaskOut |
| Modify | `frontend/web/src/api/mockApi.js` | Add `getTaskById`, `patchTaskNotes` |
| Create | `frontend/web/src/pages/doctor/subpages/TaskDetailSubpage.jsx` | Task detail view |
| Modify | `frontend/web/src/pages/doctor/TaskPage.jsx` | Restructure with PageSkeleton, add "+ 新建" |
| Modify | `tests/unit/test_task_crud.py` (or create) | Tests for new CRUD functions |

---

### Task 1: DB Schema — Add columns to DoctorTask

**Files:**
- Modify: `src/db/models/tasks.py:33-85`

- [ ] **Step 1: Add 3 new columns to DoctorTask model**

Open `src/db/models/tasks.py` and add after line 56 (`link_id`):

```python
    # --- Task detail & reminder support ---
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 2: Verify model loads**

Run: `.venv/bin/python -c "from db.models.tasks import DoctorTask; print([c.name for c in DoctorTask.__table__.columns])"`

Expected: column list includes `notes`, `reminder_at`, `completed_at`

- [ ] **Step 3: Commit**

```bash
git add src/db/models/tasks.py
git commit -m "feat(tasks): add notes, reminder_at, completed_at columns to DoctorTask"
```

---

### Task 2: Backend CRUD — completed_at + update_notes

**Files:**
- Modify: `src/db/repositories/tasks.py`
- Modify: `src/db/crud/tasks.py`

- [ ] **Step 1: Update repository update_status to set completed_at**

In `src/db/repositories/tasks.py`, find the `update_status` method. When `status == "completed"`, also set `completed_at = _utcnow()`. When status is not completed, set `completed_at = None`.

```python
async def update_status(self, task_id: int, doctor_id: str, status: str) -> Optional[DoctorTask]:
    from db.models.base import _utcnow
    task = await self.get_by_id(task_id, doctor_id)
    if task is None:
        return None
    task.status = status
    task.updated_at = _utcnow()
    if status == "completed":
        task.completed_at = _utcnow()
    elif task.completed_at is not None:
        task.completed_at = None
    await self._session.commit()
    await self._session.refresh(task)
    return task
```

- [ ] **Step 2: Add update_notes method to repository**

In `src/db/repositories/tasks.py`, add:

```python
async def update_notes(self, task_id: int, doctor_id: str, notes: str) -> Optional[DoctorTask]:
    from db.models.base import _utcnow
    task = await self.get_by_id(task_id, doctor_id)
    if task is None:
        return None
    task.notes = notes
    task.updated_at = _utcnow()
    await self._session.commit()
    await self._session.refresh(task)
    return task
```

- [ ] **Step 3: Add update_task_notes to CRUD layer**

In `src/db/crud/tasks.py`, add:

```python
async def update_task_notes(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    notes: str,
) -> Optional[DoctorTask]:
    return await TaskRepository(session).update_notes(
        task_id=task_id, doctor_id=doctor_id, notes=notes
    )
```

- [ ] **Step 4: Verify imports compile**

Run: `.venv/bin/python -c "from db.crud.tasks import update_task_notes; print('ok')"`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add src/db/repositories/tasks.py src/db/crud/tasks.py
git commit -m "feat(tasks): set completed_at on completion, add update_notes CRUD"
```

---

### Task 3: Backend API — GET single task + PATCH notes

**Files:**
- Modify: `src/channels/web/tasks.py`

- [ ] **Step 1: Extend TaskOut with new fields**

In `src/channels/web/tasks.py`, add the new fields to `TaskOut`:

```python
class TaskOut(BaseModel):
    id: int
    doctor_id: str
    task_type: str
    title: str
    content: Optional[str]
    status: str
    due_at: Optional[str]
    created_at: str
    patient_id: Optional[int]
    record_id: Optional[int]
    target: str = "doctor"
    # New fields
    notes: Optional[str] = None
    reminder_at: Optional[str] = None
    completed_at: Optional[str] = None
    patient_name: Optional[str] = None
    source_type: Optional[str] = None
```

Update `from_orm` to include them:

```python
@classmethod
def from_orm(cls, task: object, patient_name: Optional[str] = None) -> "TaskOut":
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

    return cls(
        id=task.id,
        doctor_id=task.doctor_id,
        task_type=task.task_type,
        title=task.title,
        content=task.content,
        status=task.status,
        due_at=_iso(task.due_at),
        created_at=_iso(task.created_at) or "",
        patient_id=task.patient_id,
        record_id=task.record_id,
        target=getattr(task, "target", "doctor"),
        notes=getattr(task, "notes", None),
        reminder_at=_iso(getattr(task, "reminder_at", None)),
        completed_at=_iso(getattr(task, "completed_at", None)),
        patient_name=patient_name,
        source_type=getattr(task, "source_type", None),
    )
```

- [ ] **Step 2: Add GET /api/tasks/{task_id} endpoint**

Add after the existing `get_tasks` endpoint (around line 108):

```python
@router.get("/{task_id}", response_model=TaskOut)
async def get_task_detail(
    task_id: int,
    doctor_id: str,
    authorization: Optional[str] = Header(default=None),
) -> TaskOut:
    """Fetch a single task with patient name."""
    from db.models.tasks import DoctorTask
    from db.models import Patient
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.get")
    async with AsyncSessionLocal() as session:
        stmt = select(DoctorTask).where(
            DoctorTask.id == task_id,
            DoctorTask.doctor_id == resolved_doctor_id,
        )
        task = (await session.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        patient_name = None
        if task.patient_id:
            pt = (await session.execute(
                select(Patient).where(Patient.id == task.patient_id)
            )).scalar_one_or_none()
            if pt:
                patient_name = pt.name
    return TaskOut.from_orm(task, patient_name=patient_name)
```

**Important:** This route MUST be defined BEFORE the `/{task_id}` PATCH route. Also ensure it's before `/record/{record_id}` GET route to avoid path conflicts. Place it right after line 108 (`_get_tasks_for_doctor`).

- [ ] **Step 3: Add PATCH /api/tasks/{task_id}/notes endpoint**

Add a new Pydantic model and endpoint:

```python
class TaskNotesUpdate(BaseModel):
    notes: str


@router.patch("/{task_id}/notes", response_model=TaskOut)
async def patch_task_notes(
    task_id: int,
    doctor_id: str,
    body: TaskNotesUpdate,
    authorization: Optional[str] = Header(default=None),
) -> TaskOut:
    from db.crud.tasks import update_task_notes
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.patch")
    async with AsyncSessionLocal() as session:
        task = await update_task_notes(session, task_id, resolved_doctor_id, body.notes)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.from_orm(task)
```

- [ ] **Step 4: Update import in crud __init__ if needed**

Check if `update_task_notes` needs to be added to `src/db/crud/__init__.py` exports.

- [ ] **Step 5: Verify routes compile**

Run: `.venv/bin/python -c "from channels.web.tasks import router; print([r.path for r in router.routes])"`

Expected: includes `/{task_id}` GET and `/{task_id}/notes` PATCH

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/tasks.py src/db/crud/__init__.py
git commit -m "feat(tasks): add GET single task and PATCH notes endpoints"
```

---

### Task 4: Frontend API — Add getTaskById and patchTaskNotes

**Files:**
- Modify: `frontend/web/src/api/mockApi.js`

- [ ] **Step 1: Add getTaskById mock function**

In `frontend/web/src/api/mockApi.js`, add after the existing `getTasks` function (around line 143):

```javascript
export async function getTaskById(taskId, doctorId) {
  const task = tasks.find((t) => t.id === Number(taskId));
  if (!task) return null;
  // Enrich with patient_name from patients mock data
  const patient = task.patient_id
    ? patients.find((p) => p.id === task.patient_id)
    : null;
  return {
    ...task,
    patient_name: patient?.name || task.patient_name || null,
    notes: task.notes || null,
    reminder_at: task.reminder_at || null,
    completed_at: task.completed_at || null,
    source_type: task.source_type || null,
  };
}
```

- [ ] **Step 2: Add patchTaskNotes mock function**

Add after `postponeTask` (around line 213):

```javascript
export async function patchTaskNotes(taskId, doctorId, notes) {
  tasks = tasks.map((t) => (t.id === Number(taskId) ? { ...t, notes } : t));
  return {};
}
```

- [ ] **Step 3: Register in ApiContext**

Check `frontend/web/src/api/ApiContext.jsx` — if it wraps mock functions, ensure `getTaskById` and `patchTaskNotes` are exported there too. Follow the same pattern as existing functions.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api/mockApi.js frontend/web/src/api/ApiContext.jsx
git commit -m "feat(tasks): add getTaskById and patchTaskNotes to frontend API"
```

---

### Task 5: Frontend — TaskDetailSubpage Component

**Files:**
- Create: `frontend/web/src/pages/doctor/subpages/TaskDetailSubpage.jsx`

This is the core UI component. It matches the "任务详情" mockup in the design spec.

- [ ] **Step 1: Create TaskDetailSubpage**

Create `frontend/web/src/pages/doctor/subpages/TaskDetailSubpage.jsx`:

```jsx
/**
 * TaskDetailSubpage — full task detail view.
 *
 * Shows task title + urgency, patient link, due date, source,
 * content, notes (editable), reminder, mark complete, delete.
 *
 * Props: { taskId, doctorId, onBack, isMobile }
 */
import { useCallback, useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { useApi } from "../../../api/ApiContext";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import SubpageHeader from "../../../components/SubpageHeader";
import AppButton from "../../../components/AppButton";
import SectionLoading from "../../../components/SectionLoading";
import ConfirmDialog from "../../../components/ConfirmDialog";
import Toast, { useToast } from "../../../components/Toast";
import { TYPE, COLOR, RADIUS } from "../../../theme";

const SOURCE_LABELS = {
  manual: "医生手动创建",
  rule: "知识规则 → 自动生成",
  diagnosis_auto: "AI诊断审核 → 自动生成",
};

const TYPE_LABELS = {
  general: "通用",
  review: "审核",
  follow_up: "随访",
  medication: "用药",
  checkup: "检查",
};

function dueLabel(dueAt) {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dDate = new Date(d);
  dDate.setHours(0, 0, 0, 0);

  const dateStr = dueAt.slice(0, 10);
  if (dDate.getTime() < today.getTime()) return { text: `${dateStr} (已过期)`, color: COLOR.danger };
  if (dDate.getTime() === today.getTime()) return { text: `${dateStr} (今天)`, color: COLOR.danger };
  if (dDate.getTime() === tomorrow.getTime()) return { text: `${dateStr} (明天)`, color: COLOR.warning };
  return { text: dateStr, color: COLOR.text2 };
}

function DetailField({ label, children, color }) {
  return (
    <Box sx={{ display: "flex", gap: 1.5, px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0, minWidth: 48 }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: color || COLOR.text2, lineHeight: 1.5, flex: 1 }}>
        {children}
      </Typography>
    </Box>
  );
}

export default function TaskDetailSubpage({ taskId, doctorId, onBack, isMobile }) {
  const api = useApi();
  const navigate = useAppNavigate();
  const [task, setTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState("");
  const [notesDirty, setNotesDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, showToast] = useToast();

  const load = useCallback(async () => {
    if (!taskId || !doctorId) return;
    setLoading(true);
    try {
      const data = await (api.getTaskById || (() => Promise.resolve(null)))(taskId, doctorId);
      setTask(data);
      setNotes(data?.notes || "");
    } catch {
      showToast("加载失败");
    } finally {
      setLoading(false);
    }
  }, [taskId, doctorId, api]);

  useEffect(() => { load(); }, [load]);

  const handleSaveNotes = async () => {
    if (!notesDirty || saving) return;
    setSaving(true);
    try {
      await (api.patchTaskNotes || (() => Promise.resolve()))(taskId, doctorId, notes);
      setNotesDirty(false);
      showToast("备注已保存");
    } catch {
      showToast("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleComplete = async () => {
    if (completing) return;
    setCompleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(taskId, doctorId, "completed");
      showToast("已标记完成");
      setTimeout(() => onBack?.(), 400);
    } catch {
      showToast("操作失败");
      setCompleting(false);
    }
  };

  const handleDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(taskId, doctorId, "cancelled");
      showToast("已删除");
      setTimeout(() => onBack?.(), 400);
    } catch {
      showToast("删除失败");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
        <SubpageHeader title="任务详情" onBack={onBack} />
        <SectionLoading py={6} />
      </Box>
    );
  }

  if (!task) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
        <SubpageHeader title="任务详情" onBack={onBack} />
        <Box sx={{ py: 6, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>任务不存在</Typography>
        </Box>
      </Box>
    );
  }

  const isCompleted = task.status === "completed";
  const due = dueLabel(task.due_at);
  const isUrgent = due?.color === COLOR.danger;
  const sourceLabel = SOURCE_LABELS[task.source_type] || "系统创建";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="任务详情" onBack={onBack} />

      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>
        {/* ── Task header card ── */}
        <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {/* Title row */}
          <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, display: "flex", alignItems: "center", gap: 1 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: isUrgent ? COLOR.danger : COLOR.warning, flexShrink: 0 }} />
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600, flex: 1 }}>
              {task.title}
            </Typography>
            {isUrgent && (
              <Box component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: COLOR.danger, color: COLOR.white, borderRadius: RADIUS.sm, px: 0.75, py: 0.25, lineHeight: 1.5 }}>
                紧急
              </Box>
            )}
          </Box>

          {/* Detail fields */}
          {task.patient_name && (
            <DetailField label="患者">
              <Typography
                component="span"
                onClick={() => task.patient_id && navigate(`/doctor/patients/${task.patient_id}`)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: task.patient_id ? "pointer" : "default", "&:active": { opacity: 0.6 } }}
              >
                {task.patient_name} ›
              </Typography>
            </DetailField>
          )}

          {due && (
            <DetailField label="截止" color={due.color}>
              {due.text}
            </DetailField>
          )}

          <DetailField label="来源">
            {sourceLabel}
          </DetailField>

          <DetailField label="类型">
            {TYPE_LABELS[task.task_type] || task.task_type}
          </DetailField>

          {task.content && (
            <DetailField label="详情">
              {task.content}
            </DetailField>
          )}

          {task.record_id && (
            <DetailField label="关联">
              <Typography
                component="span"
                onClick={() => navigate(`/doctor/review/${task.record_id}`)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.6 } }}
              >
                查看关联记录 ›
              </Typography>
            </DetailField>
          )}

          {/* Action buttons */}
          {!isCompleted && (
            <Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <AppButton variant="primary" size="md" fullWidth onClick={handleComplete} loading={completing}>
                标记完成
              </AppButton>
              {task.patient_id && (
                <AppButton variant="secondary" size="md" fullWidth onClick={() => navigate(`/doctor/patients/${task.patient_id}`)}>
                  查看患者
                </AppButton>
              )}
            </Box>
          )}

          {isCompleted && (
            <Box sx={{ px: 2, py: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 500 }}>
                ✓ 已完成 {task.completed_at ? task.completed_at.slice(0, 10) : ""}
              </Typography>
            </Box>
          )}
        </Box>

        {/* ── Notes section ── */}
        <Box sx={{ px: 2, py: 2 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text2, mb: 1 }}>
            备注
          </Typography>
          <Box
            component="textarea"
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
            onBlur={handleSaveNotes}
            placeholder="添加备注..."
            sx={{
              width: "100%", minHeight: 60, p: 1.5,
              bgcolor: COLOR.white, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.md, fontSize: TYPE.secondary.fontSize,
              color: COLOR.text2, resize: "vertical",
              fontFamily: "inherit", outline: "none",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
          {notesDirty && (
            <Typography
              onClick={handleSaveNotes}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, mt: 0.5, cursor: "pointer" }}
            >
              {saving ? "保存中..." : "保存备注"}
            </Typography>
          )}
        </Box>

        {/* ── Reminder + Delete ── */}
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Typography sx={{ fontSize: TYPE.body.fontSize, flex: 1 }}>提醒</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary }}>
              {task.reminder_at ? task.reminder_at.slice(0, 16).replace("T", " ") : "未设置"}
            </Typography>
            <Typography sx={{ fontSize: 14, color: COLOR.text4, ml: 1 }}>›</Typography>
          </Box>

          {!isCompleted && (
            <Box
              onClick={() => setConfirmDelete(true)}
              sx={{ px: 2, py: 1.5, cursor: "pointer", "&:active": { opacity: 0.6 } }}
            >
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.danger }}>
                删除任务
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="确认删除"
        message={`确定要删除任务"${task.title}"吗？`}
        confirmLabel="删除"
        onConfirm={handleDelete}
        loading={deleting}
        danger
      />

      <Toast message={toast} />
    </Box>
  );
}
```

- [ ] **Step 2: Verify file compiles**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`

Expected: no import errors for TaskDetailSubpage

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/TaskDetailSubpage.jsx
git commit -m "feat(tasks): add TaskDetailSubpage component"
```

---

### Task 6: Frontend — Restructure TaskPage with PageSkeleton + Create

**Files:**
- Modify: `frontend/web/src/pages/doctor/TaskPage.jsx`

This task restructures TaskPage to:
1. Use PageSkeleton with `mobileView` for task detail subpage routing
2. Add "+ 新建" button in header
3. Add a SheetDialog for creating tasks
4. Route `urlSubpage` (task ID) to TaskDetailSubpage

- [ ] **Step 1: Add imports**

At top of `TaskPage.jsx`, add:

```javascript
import PageSkeleton from "../../components/PageSkeleton";
import BarButton from "../../components/BarButton";
import TaskDetailSubpage from "./subpages/TaskDetailSubpage";
import { useMediaQuery, useTheme } from "@mui/material";
```

- [ ] **Step 2: Add create task SheetDialog**

Add a `CreateTaskSheet` component inside `TaskPage.jsx` (before the main export):

```jsx
function CreateTaskSheet({ open, onClose, doctorId, onCreated }) {
  const api = useApi();
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim() || creating) return;
    setCreating(true);
    try {
      const task = await (api.createTask || (() => Promise.resolve({})))(doctorId, {
        task_type: "general",
        title: title.trim(),
        due_at: dueAt || undefined,
      });
      onCreated?.(task);
      setTitle("");
      setDueAt("");
      onClose();
    } catch {
      // keep sheet open
    } finally {
      setCreating(false);
    }
  };

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="新建任务"
      footer={
        <Box sx={{ display: "flex", gap: 1 }}>
          <AppButton variant="secondary" size="lg" fullWidth onClick={onClose} disabled={creating}>
            取消
          </AppButton>
          <AppButton variant="primary" size="lg" fullWidth onClick={handleCreate} loading={creating} disabled={!title.trim()}>
            创建
          </AppButton>
        </Box>
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>任务标题</Typography>
          <Box
            component="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：术后复查CT"
            sx={{
              width: "100%", p: 1.5, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.sm, fontSize: TYPE.body.fontSize,
              outline: "none", fontFamily: "inherit",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
        </Box>
        <Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>截止日期（可选）</Typography>
          <Box
            component="input"
            type="date"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            sx={{
              width: "100%", p: 1.5, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.sm, fontSize: TYPE.body.fontSize,
              outline: "none", fontFamily: "inherit",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
        </Box>
      </Box>
    </SheetDialog>
  );
}
```

- [ ] **Step 3: Restructure TaskPage main component**

Wrap the existing content in PageSkeleton. Key changes:

1. Add state: `const [createOpen, setCreateOpen] = useState(false);`
2. Detect mobile: `const theme = useTheme(); const isMobile = useMediaQuery(theme.breakpoints.down("sm"));`
3. Determine if showing detail subpage: `const showDetail = !!urlSubpage && urlSubpage !== "tasks";`
4. Build `mobileView` when `showDetail` is true
5. Change task row `onClick` from navigating to patient → navigate to `/doctor/tasks/${item.id}`
6. Add `headerRight` with "+ 新建" BarButton

The render structure becomes:

```jsx
const mobileSubpage = showDetail ? (
  <TaskDetailSubpage
    taskId={urlSubpage}
    doctorId={doctorId}
    onBack={() => navigate(-1)}
    isMobile={isMobile}
  />
) : null;

return (
  <PageSkeleton
    title="任务"
    isMobile={isMobile}
    mobileView={mobileSubpage}
    headerRight={
      <BarButton onClick={() => setCreateOpen(true)}>+ 新建</BarButton>
    }
    listPane={/* existing list content */}
  />
);
```

- [ ] **Step 4: Update row navigation**

Change `onClick` in task rows from:

```javascript
onClick={() => item.patient_id ? navigate(`/doctor/patients/${item.patient_id}`) : undefined}
```

to:

```javascript
onClick={() => navigate(`/doctor/tasks/${item.id}`)}
```

Apply this change to both the urgent and upcoming task rows.

- [ ] **Step 5: Add CreateTaskSheet and reload handler**

At the bottom of the component return, add:

```jsx
<CreateTaskSheet
  open={createOpen}
  onClose={() => setCreateOpen(false)}
  doctorId={doctorId}
  onCreated={() => loadData()}
/>
```

- [ ] **Step 6: Verify build compiles**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -5`

Expected: build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/web/src/pages/doctor/TaskPage.jsx
git commit -m "feat(tasks): restructure TaskPage with detail subpage + create button"
```

---

### Task 7: Backend Tests

**Files:**
- Create or modify: `tests/unit/test_task_crud.py`

- [ ] **Step 1: Write test for completed_at being set**

```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_update_status_sets_completed_at():
    """When status → completed, completed_at should be set."""
    from db.repositories.tasks import TaskRepository

    mock_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.status = "pending"
    mock_task.completed_at = None

    repo = TaskRepository(mock_session)
    repo.get_by_id = AsyncMock(return_value=mock_task)

    result = await repo.update_status(task_id=1, doctor_id="doc1", status="completed")

    assert result is not None
    assert result.status == "completed"
    assert result.completed_at is not None


@pytest.mark.asyncio
async def test_update_status_clears_completed_at_on_reopen():
    """When status reverts from completed, completed_at should be cleared."""
    from db.repositories.tasks import TaskRepository

    mock_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.status = "completed"
    mock_task.completed_at = datetime.now(timezone.utc)

    repo = TaskRepository(mock_session)
    repo.get_by_id = AsyncMock(return_value=mock_task)

    result = await repo.update_status(task_id=1, doctor_id="doc1", status="pending")

    assert result is not None
    assert result.completed_at is None
```

- [ ] **Step 2: Write test for update_notes**

```python
@pytest.mark.asyncio
async def test_update_notes():
    """update_notes should set the notes field."""
    from db.repositories.tasks import TaskRepository

    mock_session = AsyncMock()
    mock_task = MagicMock()
    mock_task.notes = None

    repo = TaskRepository(mock_session)
    repo.get_by_id = AsyncMock(return_value=mock_task)

    result = await repo.update_notes(task_id=1, doctor_id="doc1", notes="Patient called, reschedule needed")

    assert result is not None
    assert result.notes == "Patient called, reschedule needed"
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/test_task_crud.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`

Expected: all 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_task_crud.py
git commit -m "test(tasks): add unit tests for completed_at and update_notes"
```

---

## Dependency Order

```
Task 1 (DB columns) → Task 2 (CRUD) → Task 3 (API endpoints) → Task 4 (Frontend API)
                                                                       ↓
Task 5 (TaskDetailSubpage) ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ┘
                                       ↓
Task 6 (TaskPage restructure) ← ← ← ← ┘
Task 7 (Backend tests) — can run in parallel with Task 5-6
```

Tasks 1→2→3 are sequential (each builds on previous).
Task 4 depends on Task 3 (needs to know API shape).
Task 5 depends on Task 4 (uses API functions).
Task 6 depends on Task 5 (imports TaskDetailSubpage).
Task 7 can run in parallel with Tasks 5-6 (independent backend tests).
