# Doctor Tasks — Automatic Notification Feature

## Goal
Add a persistent `DoctorTask` system that automatically notifies doctors via WeChat when follow-up reminders, emergency records, or scheduled appointments are due.

## Affected Files

| File | Action |
|---|---|
| `services/wechat_notify.py` | **CREATE** — shared WeChat push helper (prevents circular import) |
| `db/models.py` | **MODIFY** — add `DoctorTask` ORM class |
| `db/crud.py` | **MODIFY** — add 5 task CRUD functions |
| `services/tasks.py` | **CREATE** — task creation, date extraction, scheduler job |
| `services/intent.py` | **MODIFY** — add 3 new `Intent` enum members |
| `services/agent.py` | **MODIFY** — add 3 LLM tools, update `_INTENT_MAP`/`_SYSTEM_PROMPT`, populate `extra_data` |
| `routers/wechat.py` | **MODIFY** — import refactored notify; add 3 intent handlers + regex shortcut; hooks in `_handle_add_record` |
| `routers/tasks.py` | **CREATE** — REST API: GET/PATCH `/api/tasks` |
| `main.py` | **MODIFY** — APScheduler lifespan; tasks router + admin view |
| `requirements.txt` | **MODIFY** — add `apscheduler` |
| `tests/test_tasks.py` | **CREATE** — unit tests, all I/O mocked |
| `ARCHITECTURE.md` | **MODIFY** — document new table, endpoints, scheduler |

## Steps

### Step 1 — Refactor WeChat push into `services/wechat_notify.py`
Move these from `routers/wechat.py` to a new `services/wechat_notify.py`:
- `_token_cache` dict
- `_get_config()`
- `_get_access_token()`
- `_split_message()`
- `_send_customer_service_msg()`

In `routers/wechat.py`, replace moved code with:
```python
from services.wechat_notify import _get_config, _get_access_token, _split_message, _send_customer_service_msg, _token_cache
```

Update `tests/test_wechat_routes.py` patch targets:
- `routers.wechat.httpx.AsyncClient` → `services.wechat_notify.httpx.AsyncClient`
- `routers.wechat._get_access_token` inside `_send_customer_service_msg` test → `services.wechat_notify._get_access_token`

**Why first:** `services/tasks.py` must call WeChat push; importing from `routers/` into `services/` creates a circular dependency.

### Step 2 — Add `DoctorTask` model to `db/models.py`
Append after `NeuroCaseDB`:
```python
class DoctorTask(Base):
    __tablename__ = "doctor_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id"), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medical_records.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # follow_up | emergency | appointment
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending | completed | cancelled
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```
No migration needed — `create_tables()` calls `Base.metadata.create_all` which is additive.

### Step 3 — Add CRUD functions to `db/crud.py`
Five new async functions (all take `AsyncSession` as first param):
- `create_task(session, doctor_id, task_type, title, content?, patient_id?, record_id?, due_at?) -> DoctorTask`
- `list_tasks(session, doctor_id, status?) -> List[DoctorTask]`
- `update_task_status(session, task_id, doctor_id, status) -> Optional[DoctorTask]`
- `get_due_tasks(session, now) -> List[DoctorTask]` — pending + `due_at <= now` + `notified_at IS NULL` (cross-doctor)
- `mark_task_notified(session, task_id) -> None` — sets `notified_at = utcnow()`

### Step 4 — Create `services/tasks.py`
Key functions:
```python
def extract_follow_up_days(follow_up_plan: str) -> int:
    # Regex for: N天, N周, N个月, 两/三/... (Chinese digits), 下周, 明天
    # Default fallback: 7 days

async def create_follow_up_task(doctor_id, record_id, patient_name, follow_up_plan, patient_id?) -> DoctorTask
    # due_at = utcnow() + timedelta(days=extract_follow_up_days(follow_up_plan))

async def create_emergency_task(doctor_id, record_id, patient_name, diagnosis?, patient_id?) -> DoctorTask
    # due_at = None; immediately calls send_task_notification() after creation

async def create_appointment_task(doctor_id, patient_name, appointment_dt, notes?, patient_id?) -> DoctorTask
    # due_at = appointment_dt - timedelta(hours=1)

async def send_task_notification(doctor_id, task) -> None
    # Formats message with icon prefix + "回复「完成 {task.id}」标记完成"
    # Calls _send_customer_service_msg(); then mark_task_notified()

async def check_and_send_due_tasks() -> None
    # APScheduler job: query get_due_tasks(), call send_task_notification() for each
    # Swallows per-task exceptions so one failure doesn't stop others
```
Each function opens its own `AsyncSessionLocal()` context (matches codebase pattern).

### Step 5 — Add 3 new `Intent` enum members to `services/intent.py`
```python
list_tasks = "list_tasks"
complete_task = "complete_task"
schedule_appointment = "schedule_appointment"
```

### Step 6 — Extend `services/agent.py`
**6a.** Add 3 tool definitions to `_TOOLS`:
- `list_tasks` — no params — trigger: "我的任务/待办/提醒"
- `complete_task` — param: `task_id: int` — trigger: "完成任务X"
- `schedule_appointment` — params: `patient_name`, `appointment_time` (ISO 8601), `notes?`

**6b.** Add to `_INTENT_MAP`:
```python
"list_tasks": Intent.list_tasks,
"complete_task": Intent.complete_task,
"schedule_appointment": Intent.schedule_appointment,
```

**6c.** Extend `_SYSTEM_PROMPT` routing rules:
```
- 查看任务/待办/提醒 → list_tasks
- 完成任务/标记完成 + 编号 → complete_task
- 预约/安排/约诊 + 时间 → schedule_appointment
```

**6d.** In `dispatch()`, populate `extra_data` before return:
```python
extra_data: dict = {}
if fn_name == "complete_task":
    extra_data["task_id"] = args.get("task_id")
elif fn_name == "schedule_appointment":
    extra_data["appointment_time"] = args.get("appointment_time")
    extra_data["notes"] = args.get("notes")
return IntentResult(..., extra_data=extra_data)
```

### Step 7 — Modify `routers/wechat.py`
**7a. Integration hook in `_handle_add_record()`:**
- Change `await save_record(...)` → `db_record = await save_record(...)` (function already returns `MedicalRecordDB`)
- After the `async with` block, add fire-and-forget tasks:
```python
if record.follow_up_plan:
    asyncio.create_task(create_follow_up_task(...))
if intent_result.is_emergency:
    asyncio.create_task(create_emergency_task(...))
```

**7b. Regex shortcut** at the top of `_handle_intent()`:
```python
_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')
m = _COMPLETE_RE.match(text.strip())
if m:
    # Directly call update_task_status; return formatted reply
```

**7c. Three new handler functions:**
- `_handle_list_tasks(doctor_id)` — queries `list_tasks(status="pending")`, formats numbered list
- `_handle_complete_task(doctor_id, intent_result)` — reads `extra_data["task_id"]`, calls `update_task_status`
- `_handle_schedule_appointment(doctor_id, intent_result)` — parses ISO datetime, calls `create_appointment_task`

**7d.** Add the 3 new intent routing branches in `_handle_intent()`.

### Step 8 — Create `routers/tasks.py`
```
GET  /api/tasks?doctor_id=&status=   → List[TaskOut]
PATCH /api/tasks/{task_id}?doctor_id= body: {"status": "completed"|"cancelled"} → TaskOut
```
`TaskOut` is a Pydantic model serializing datetime fields as ISO strings.

### Step 9 — Update `main.py`
- Add `apscheduler` import + `AsyncIOScheduler`
- In `lifespan`: start scheduler with `check_and_send_due_tasks` job every 1 minute; shutdown on exit
- Register `tasks_router` with `app.include_router()`
- Add `DoctorTaskAdmin` SQLAdmin view (columns: id, doctor_id, task_type, title, status, due_at, created_at)
- Log count of pending unnotified tasks on startup

### Step 10 — Write `tests/test_tasks.py`
Five test groups, all I/O mocked:
- **Group A** — `extract_follow_up_days`: 12 pure unit tests (两周→14, 3天→3, 一个月→30, fallback→7, etc.)
- **Group B** — CRUD: create_task, list_tasks filter, get_due_tasks (due vs. notified), update_task_status wrong doctor
- **Group C** — `services/tasks.py`: follow_up creates correct due_at; emergency sends immediately; scheduler sends for all due tasks; scheduler continues on per-task error; notification message format
- **Group D** — Agent dispatch: list_tasks/complete_task/schedule_appointment intents + extra_data extraction (follow existing `test_agent.py` mock pattern)
- **Group E** — REST API: GET list, filter by status, PATCH complete, 422 on invalid status, 404 on missing task

### Step 11 — Update `ARCHITECTURE.md`
Document: new `doctor_tasks` table schema, new API endpoints (`GET/PATCH /api/tasks`), APScheduler job, WeChat notification flow, and `services/wechat_notify.py` refactoring rationale.

## Risks / Open Questions

1. **Circular import (critical):** Step 1 must be done first. `services/tasks.py` cannot import from `routers/`. The `_token_cache` dict is shared by reference after the move — tests that mutate `wechat._token_cache` directly still work because `from services.wechat_notify import _token_cache` binds the same dict object. `httpx.AsyncClient` patches must be updated to `services.wechat_notify.httpx.AsyncClient`.

2. **`save_record` return value not captured today:** The call in `wechat.py` discards the return value. Step 7a changes this. No other call sites are affected.

3. **LLM hallucinating non-ISO `appointment_time`:** `datetime.fromisoformat()` will fail gracefully with a user-facing error asking for correct format. Acceptable for MVP.

4. **"完成 N" not reliably dispatched by LLM:** Mitigated by regex shortcut (Step 7b) that bypasses LLM for this exact pattern.

5. **APScheduler in-memory only:** Jobs are not persisted. On server restart, unnotified tasks with `notified_at IS NULL` will be re-queued within 1 minute by the scheduler job querying `get_due_tasks()`. No data loss.

6. **No patient linked to record:** Task title will say "未关联患者" — acceptable for MVP.
