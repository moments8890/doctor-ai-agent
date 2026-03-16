# ADR 0013: Execution Plan

## Goal

Implement the action type simplification as specified in
[ADR 0013](../adr/0013-action-type-simplification.md): reduce ActionType
from 9 to 5, remove `scoped_only`, remove `task_type`, simplify resolve /
commit / compose / turn.

## Source of Truth

- **ADR**: `docs/adr/0013-action-type-simplification.md`
- **Diagrams**: `docs/adr/0013-architecture-diagram.md`

When in doubt, the ADR text wins over this plan.

## Dependency Graph

```text
A (types.py + understand.py) ─── gate ───┬──→ B (understand prompt)
                                          ├──→ C (resolve)
                                          ├──→ D (commit engine)
                                          ├──→ E (read engine)
                                          └──→ F (compose + messages)

A is the gate. B-F can run in parallel after A lands.

C ──→ D (commit engine uses ResolvedAction shape from resolve)
F ──→ G (turn.py — needs compose + messages + read/commit shapes)
G ──→ H (E2E fixture sweep — investigate only)
H ──→ I (smoke test)
```

**A is the gate.** Types define the interfaces. After A lands, resolve, engines,
and compose can fan out. Turn orchestrator (G) goes last because it imports
from all other modules.

---

## Stream A: Types (gate)

### A. Rewrite `types.py` + fix `understand.py`

**Files:**
- `src/services/runtime/types.py`
- `src/services/runtime/understand.py`

**Changes to `types.py`:**

1. Replace `ActionType` enum (9 values → 5):
   ```python
   class ActionType(str, Enum):
       none = "none"
       query = "query"
       record = "record"
       update = "update"
       task = "task"
   ```

2. Delete `TaskType` enum

3. Replace 8 args dataclasses with 4:
   ```python
   @dataclass
   class QueryArgs:
       target: Optional[str] = None       # "records" | "patients" | "tasks"
       patient_name: Optional[str] = None
       limit: Optional[int] = None
       status: Optional[str] = None       # tasks: "pending" | "completed"

   @dataclass
   class RecordArgs:
       patient_name: Optional[str] = None
       gender: Optional[str] = None
       age: Optional[int] = None

   @dataclass
   class UpdateArgs:
       instruction: str
       patient_name: Optional[str] = None

   @dataclass
   class TaskArgs:
       patient_name: Optional[str] = None
       title: Optional[str] = None
       notes: Optional[str] = None
       scheduled_for: Optional[str] = None
       remind_at: Optional[str] = None
   ```

4. Update `ARGS_TYPE_TABLE` (9 → 5 entries)

5. Update const sets:
   ```python
   READ_ACTIONS = frozenset({ActionType.query})
   WRITE_ACTIONS = frozenset({ActionType.record, ActionType.update, ActionType.task})
   ```

6. Update `RESPONSE_MODE_TABLE` (9 → 5 entries):
   - `query` → `llm_compose`
   - `record`, `update`, `task` → `template`

7. Remove `scoped_only` field from `ResolvedAction`

8. Keep `ClarificationKind.invalid_time` (used by `_validate_task_dates`)

9. Delete old exports: `SelectPatientArgs`, `CreatePatientArgs`,
   `CreateRecordArgs`, `UpdateRecordArgs`, `QueryRecordsArgs`,
   `ListPatientsArgs`, `ListTasksArgs`, `ScheduleTaskArgs`, `TaskType`

**Changes to `understand.py`:**

10. Line 191: `ActionType.query_records` → `ActionType.query` (limit clamping)

---

## Stream B: Understand Prompt

### B. Rewrite `prompts/understand.md`

**File:** `src/prompts/understand.md`

Rewrite with 5 action types (~60 lines, down from 112). Key rules:

- `query`: target field disambiguates records/patients/tasks.
  Trigger: 查看/查询/病历 → records; 患者列表 → patients; 待办/任务 → tasks;
  选择/切换患者 → records (returns records + binds context)
- `record`: clinical content → save record; demographics only → create patient.
  `patient_name`: fill when mentioned, else system uses current patient.
- `update`: instruction required, patient_name optional
- `task`: title + scheduled_for. No task_type field.
- Multi-action example: "李淑芳，血压135/85，3个月复查" → `[record, task]`

---

## Stream C: Resolve

### C. Simplify `resolve.py`

**File:** `src/services/runtime/resolve.py`

1. **Rewrite `resolve()` dispatch** — 5 branches:
   - `none` → pass through
   - `query` → check target; unscoped (`patients`/`tasks`) skip patient
     resolution; `records` (default) → `_resolve_patient_scoped()`
   - `record` → `_ensure_patient()`, clarify if no patient
   - `update` → `_ensure_patient()` + `_fetch_latest_record()`
   - `task` → `_validate_task_dates()` + `_resolve_patient_scoped()`

2. **Add `_get_query_target()` helper**:
   ```python
   def _get_query_target(action):
       if action.args and hasattr(action.args, "target") and action.args.target:
           return action.args.target
       return "records"
   ```

3. **Add `_resolve_patient_scoped()` helper** — generic patient lookup from
   args or context fallback. Used by `query(target=records)` and `task`.

4. **Replace `_validate_schedule_task` with `_validate_task_dates`** —
   date-only validation (not past, not >1 year, valid ISO). No task_type
   check. Returns `Clarification(kind=invalid_time)` on failure.

5. **Pass gender/age in `_ensure_patient` auto-create** — extract from
   `action.args` and pass to `db_create_patient()` instead of `None, None`.

6. Delete: `select_patient` branch, `create_patient` branch,
   `_validate_schedule_task()`, `TaskType` imports.

---

## Stream D: Commit Engine

### D. Simplify `commit_engine.py`

**File:** `src/services/runtime/commit_engine.py`

1. **Simplify `commit()` dispatch** — 3 branches:
   - `record` → `_create_record()`
   - `update` → `_update_record()`
   - `task` → `_schedule_task()`

2. **Demographics-only fallback in `_create_record()`** — when clinical text
   is empty but patient_name present:
   ```python
   if not clinical_text.strip():
       if not patient_name:
           return CommitResult(status="error", error_key="need_patient_name")
       return CommitResult(status="ok", data={"patient_only": True, "name": patient_name})
   ```
   Note: "切换到张三" routes through `query`, not `record`. This path only
   fires for explicit new patient creation ("新患者王芳，女30岁").

3. **Hardcode `task_type="general"` in `_schedule_task()`** — replace all
   `args.task_type` references with literal `"general"`.

4. **Delete:** `_select_patient()`, `_create_patient()`, `TASK_TYPE_LABELS`

5. **Update imports:** remove old args/enum types, add new ones.

---

## Stream E: Read Engine

### E. Target-based dispatch in `read_engine.py`

**File:** `src/services/runtime/read_engine.py`

Replace `ActionType`-based dispatch with target-based:

```python
async def read(action, doctor_id):
    target = _get_target(action)
    if target == "patients":
        return await _list_patients(doctor_id)
    if target == "tasks":
        return await _list_tasks(action, doctor_id)
    return await _query_records(action, doctor_id)

def _get_target(action):
    if action.args and hasattr(action.args, "target") and action.args.target:
        return action.args.target
    return "records"
```

Internal functions `_query_records`, `_list_patients`, `_list_tasks` unchanged.

---

## Stream F: Compose + Messages

### F1. Update `messages.py`

**File:** `src/messages.py`

- Delete: `select_patient_ok`, `create_patient_ok`, `schedule_task_ok`,
  `schedule_task_ok_noon`
- Add: `patient_registered = "✅ 已建档【{name}】。"`
- Remove `task_type` from `clarify_missing_field` label dict

### F2. Simplify `compose.py`

**File:** `src/services/runtime/compose.py`

- **`_compose_commit()`** — 3 branches (was 5):
  - `record` → `patient_only` ? `M.patient_registered` : `M.record_created`
  - `update` → `M.record_updated`
  - `task` → inline format with title + datetime
- Remove `task_type`/`task_label` references
- Keep `ClarificationKind.invalid_time` handler in `compose_clarification()`
- Delete: `select_patient`, `create_patient` template branches

---

## Stream G: Turn Orchestrator

### G. Update `turn.py`

**File:** `src/services/runtime/turn.py`

Depends on: A, E, F (imports from types, read_engine, compose)

1. **View payload** — replace 3-branch ActionType mapping with target-based:
   ```python
   if read_result.data:
       target = getattr(resolved.args, "target", "records") or "records"
       type_map = {"records": "records_list", "patients": "patients_list", "tasks": "tasks_list"}
       view_payload = {"type": type_map.get(target, "records_list"), "data": read_result.data}
   ```

2. **Remove `scoped_only` from context binding** — change:
   ```python
   if resolved.patient_id and not resolved.scoped_only:
   ```
   to:
   ```python
   if resolved.patient_id:
   ```

---

## Stream H: E2E Fixture Sweep

### H. Identify broken fixtures (investigate only)

Per AGENTS.md E2E debug policy: investigate, do not auto-fix.

```bash
grep -rn '"action_type"' tests/fixtures/ | grep -E '"(query_records|list_patients|list_tasks|select_patient|create_patient|create_record|update_record|schedule_task)"'
```

Report findings to user for direction.

---

## Stream I: Smoke Test

### I. Manual verification

Start app, test all 5 action types:

| Input | Expected action | Expected behavior |
|---|---|---|
| "你好" | `none` | Greeting reply |
| "查看张三的病历" | `query(target=records)` | Records + context switch to 张三 |
| "切换到张三" | `query(target=records)` | Records + context switch to 张三 |
| "我的患者" | `query(target=patients)` | Patient list, no context change |
| "今日任务" | `query(target=tasks)` | Task list, no context change |
| "张三头痛3天" | `record` | Record saved + context switch |
| "新患者王芳，女30岁" | `record` | Patient created (demographics-only) |
| "把诊断改成高血压" | `update` | Latest record updated |
| "张三3个月后复查" | `task` | Task created, task_type="general" |
| "李淑芳，血压135/85，3个月复查" | `[record, task]` | Multi-action: record + task |

Verify:
- `SELECT task_type FROM doctor_tasks ORDER BY id DESC LIMIT 5` → all "general"
- Context switches work for both query and record paths
- Date validation rejects past dates for task
