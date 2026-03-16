# Understand Simplification — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce ActionType from 9 to 5, remove task_type from LLM classification, simplify resolve/commit/compose.

**Architecture:** Replace enum + args dataclasses in types.py, rewrite understand prompt, simplify branching in resolve/commit/read/compose/turn. No DB changes.

**Tech Stack:** Python 3.9+ / SQLAlchemy / Pydantic v2 / FastAPI

**Spec:** `docs/superpowers/specs/2026-03-16-understand-simplification-design.md`

**Testing policy:** Per AGENTS.md, do not add unit tests unless explicitly asked.

---

## Chunk 1: Types Foundation

### Task 1: Rewrite `types.py`

**Files:**
- Modify: `src/services/runtime/types.py`

- [ ] **Step 1: Replace ActionType enum**

Replace the 9-value enum (lines 12-22) with:

```python
class ActionType(str, Enum):
    """Operational action types (simplified)."""
    none = "none"
    query = "query"
    record = "record"
    update = "update"
    task = "task"
```

- [ ] **Step 2: Add QueryTarget enum**

Add after ActionType:

```python
class QueryTarget(str, Enum):
    """Sub-target for query actions."""
    records = "records"
    patients = "patients"
    tasks = "tasks"
```

- [ ] **Step 3: Remove TaskType enum**

Delete the `TaskType` enum (lines 25-29). It's no longer needed — task_type
is inferred by commit engine.

- [ ] **Step 4: Replace args dataclasses**

Replace all 8 args dataclasses (lines 77-127) with 4:

```python
@dataclass
class QueryArgs:
    target: Optional[str] = None       # "records" | "patients" | "tasks"
    patient_name: Optional[str] = None
    limit: Optional[int] = None
    status: Optional[str] = None       # for tasks: "pending" | "completed"


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

- [ ] **Step 5: Update ARGS_TYPE_TABLE**

Replace (lines 130-140):

```python
ARGS_TYPE_TABLE: Dict[ActionType, type] = {
    ActionType.none: type(None),
    ActionType.query: QueryArgs,
    ActionType.record: RecordArgs,
    ActionType.update: UpdateArgs,
    ActionType.task: TaskArgs,
}
```

- [ ] **Step 6: Update READ_ACTIONS / WRITE_ACTIONS / RESPONSE_MODE_TABLE**

```python
READ_ACTIONS = frozenset({ActionType.query})
WRITE_ACTIONS = frozenset({ActionType.record, ActionType.update, ActionType.task})

RESPONSE_MODE_TABLE: Dict[ActionType, ResponseMode] = {
    ActionType.none: ResponseMode.direct_reply,
    ActionType.query: ResponseMode.llm_compose,
    ActionType.record: ResponseMode.template,
    ActionType.update: ResponseMode.template,
    ActionType.task: ResponseMode.template,
}
```

- [ ] **Step 7: Remove ClarificationKind.invalid_time**

Delete `invalid_time` from ClarificationKind enum (line 38). It was only used
by `_validate_schedule_task` which is being removed.

- [ ] **Step 8: Clean up old exports**

Remove old dataclass names from any `__all__` or re-exports. Ensure these old
names are NOT exported: `SelectPatientArgs`, `CreatePatientArgs`,
`CreateRecordArgs`, `UpdateRecordArgs`, `QueryRecordsArgs`, `ListPatientsArgs`,
`ListTasksArgs`, `ScheduleTaskArgs`, `TaskType`.

- [ ] **Step 9: Commit**

```bash
git add src/services/runtime/types.py
git commit -m "refactor: simplify ActionType 9→5, remove TaskType, merge args dataclasses"
```

---

## Chunk 2: Understand Prompt

### Task 2: Rewrite understand prompt

**Files:**
- Modify: `src/prompts/understand.md`

- [ ] **Step 1: Rewrite the prompt**

Replace entire file with the simplified 5-action-type prompt:

```markdown
# 意图识别

你是一个医疗助手的意图分析模块。将医生输入分解为操作意图并提取参数。

## 当前上下文
- 当前日期：{current_date}
- 时区：{timezone}
- 当前患者：{current_patient}

## 输出格式

必须输出合法JSON：

{
  "actions": [{"action_type": "...", "args": {}}],
  "chat_reply": null,
  "clarification": null
}

- actions: 数组，1-3个操作（按执行顺序）
- chat_reply: 仅当 actions 为 [{"action_type": "none"}] 时设置
- clarification: 无法判断意图时设置

## action_type 说明

### none — 闲聊/帮助/问候
args: {}

### query — 查询信息
查看病历、患者列表、任务列表。
args: {"target": "records|patients|tasks", "patient_name": "张三", "limit": 5, "status": "pending"}
- target: "records"（默认）、"patients"、"tasks"
- patient_name: 查看特定患者病历时填写
- limit: records专用，默认5，最大10
- status: tasks专用，"pending"（默认）或 "completed"
- 触发词：查看/查询/病历 → records；患者列表/我的患者 → patients；待办/任务/随访提醒 → tasks

### record — 保存病历 / 建立患者
用户提供了临床内容或要建立新患者。
args: {"patient_name": "张三", "gender": "男", "age": 45}
- 有临床内容 → 保存病历（系统自动查找或创建患者）
- 仅有姓名/性别/年龄 → 建立患者档案
- patient_name: 必须从消息中提取人名

### update — 修改最近病历
args: {"instruction": "把诊断改成高血压2级", "patient_name": "张三"}
- instruction: 必填，修改指令

### task — 创建任务/预约
args: {"patient_name": "张三", "title": "复诊", "notes": null, "scheduled_for": "2026-03-18T12:00:00", "remind_at": "2026-03-18T11:00:00"}
- scheduled_for: ISO-8601。相对日期转绝对日期。未指定日期默认明天，时间默认中午12:00
- remind_at: 未指定默认scheduled_for前1小时

## 多操作示例

医生："李淑芳，女68岁，血压135/85，继续治疗，3个月复查"
{"actions": [{"action_type": "record", "args": {"patient_name": "李淑芳", "gender": "女", "age": 68}}, {"action_type": "task", "args": {"patient_name": "李淑芳", "title": "3个月复查", "scheduled_for": "2026-06-16T12:00:00"}}]}

医生："查看张三的病历"
{"actions": [{"action_type": "query", "args": {"target": "records", "patient_name": "张三"}}]}

医生："今天有什么任务"
{"actions": [{"action_type": "query", "args": {"target": "tasks"}}]}

医生："新患者王芳，女，30岁"
{"actions": [{"action_type": "record", "args": {"patient_name": "王芳", "gender": "女", "age": 30}}]}

医生："把诊断改成紧张型头痛"
{"actions": [{"action_type": "update", "args": {"instruction": "把诊断改成紧张型头痛"}}]}

## 关键规则

1. actions 必须是数组
2. 非 none 操作时 chat_reply 必须为 null
3. 不要编造日期
4. patient_name 使用用户原文中的姓名
5. 最多3个操作
6. 消息含临床内容时优先 record，系统自动查找或创建患者
```

- [ ] **Step 2: Commit**

```bash
git add src/prompts/understand.md
git commit -m "refactor: rewrite understand prompt for 5 action types"
```

---

## Chunk 3: Resolve

### Task 3: Simplify `resolve.py`

**Files:**
- Modify: `src/services/runtime/resolve.py`

- [ ] **Step 1: Rewrite the main `resolve()` function**

Replace the entire body of `resolve()` (lines 28-132) with simplified routing:

```python
async def resolve(
    action: ActionIntent,
    ctx: Any,
) -> Union[ResolvedAction, Clarification]:
    at = action.action_type

    if at == ActionType.none:
        return ResolvedAction(action_type=at, args=action.args)

    # query: unscoped targets skip patient resolution
    if at == ActionType.query:
        target = _get_query_target(action)
        if target in ("patients", "tasks"):
            return ResolvedAction(
                action_type=at, args=action.args, scoped_only=True,
            )
        # target=records: resolve patient
        return await _resolve_patient_scoped(action, ctx, scoped_only=True)

    # record: resolve patient (auto-create if not found)
    if at == ActionType.record:
        pid, pname = await _ensure_patient(action, ctx)
        if pid is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        return ResolvedAction(
            action_type=at, patient_id=pid, patient_name=pname,
            args=action.args,
        )

    # update: resolve patient + fetch latest record
    if at == ActionType.update:
        pid, pname = await _ensure_patient(action, ctx)
        if pid is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        latest = await _fetch_latest_record(pid, ctx.doctor_id)
        if latest is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                message_key="no_record_to_update",
            )
        record_id, _ = latest
        return ResolvedAction(
            action_type=at, patient_id=pid, patient_name=pname,
            args=action.args, record_id=record_id,
        )

    # task: resolve patient
    if at == ActionType.task:
        return await _resolve_patient_scoped(action, ctx, scoped_only=False)

    log(f"[resolve] unknown action type: {at}", level="error")
    return Clarification(kind=ClarificationKind.unsupported)
```

- [ ] **Step 2: Add helper functions**

```python
def _get_query_target(action: ActionIntent) -> str:
    if action.args and hasattr(action.args, "target") and action.args.target:
        return action.args.target
    # Default: if patient_name present, assume records; else patients
    if action.args and hasattr(action.args, "patient_name") and action.args.patient_name:
        return "records"
    return "records"


async def _resolve_patient_scoped(
    action: ActionIntent,
    ctx: Any,
    scoped_only: bool,
) -> Union[ResolvedAction, Clarification]:
    """Generic patient resolution for patient-scoped actions."""
    patient_name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        patient_name = action.args.patient_name

    if patient_name:
        match = await _match_patient(patient_name, ctx.doctor_id)
        if isinstance(match, Clarification):
            return match
        pid, pname = match
    elif ctx.workflow.patient_id is not None:
        pid = ctx.workflow.patient_id
        pname = ctx.workflow.patient_name or ""
    else:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["patient_name"],
            message_key="clarify_missing_field",
        )

    return ResolvedAction(
        action_type=action.action_type,
        patient_id=pid,
        patient_name=pname,
        args=action.args,
        scoped_only=scoped_only,
    )
```

- [ ] **Step 3: Delete `_validate_schedule_task`**

Remove the entire function (lines 285-342). No longer called.

- [ ] **Step 4: Update imports**

Remove `TaskType` and `ScheduleTaskArgs` from imports. Add `QueryArgs` if
needed for type hints.

- [ ] **Step 5: Commit**

```bash
git add src/services/runtime/resolve.py
git commit -m "refactor: simplify resolve for 5 action types, remove task validation"
```

---

## Chunk 4: Engines

### Task 4: Simplify `commit_engine.py`

**Files:**
- Modify: `src/services/runtime/commit_engine.py`

- [ ] **Step 1: Simplify `commit()` dispatch**

Replace the dispatch (lines 40-54) with:

```python
async def commit(action, ctx, recent_turns=None, user_input=""):
    at = action.action_type
    if at == ActionType.record:
        return await _create_record(action, ctx, recent_turns or [], user_input)
    if at == ActionType.update:
        return await _update_record(action, ctx)
    if at == ActionType.task:
        return await _schedule_task(action, ctx)
    log(f"[commit] unknown action type: {at}", level="error")
    return CommitResult(status="error", error_key="execute_error")
```

- [ ] **Step 2: Add demographics-only fallback to `_create_record`**

After the `clinical_text.strip()` check (line 210-211), instead of returning
error immediately, check for demographics:

```python
clinical_text = await _collect_clinical_text(ctx.doctor_id, patient_id, recent_turns, user_input)
if not clinical_text.strip():
    # Demographics-only: patient already created by resolve._ensure_patient
    # Just confirm the patient binding
    log(f"[commit] patient-only registration patient={patient_name} doctor={ctx.doctor_id}")
    return CommitResult(
        status="ok",
        data={"patient_only": True, "name": patient_name},
    )
```

- [ ] **Step 3: Pass gender/age to `_ensure_patient` for auto-create**

In resolve.py `_ensure_patient`, the auto-create call (line 176) currently
passes `None, None` for gender/age:

```python
patient, _ = await db_create_patient(db, ctx.doctor_id, name, None, None)
```

Update to extract from action args:

```python
gender = getattr(action.args, "gender", None)
age = getattr(action.args, "age", None)
patient, _ = await db_create_patient(db, ctx.doctor_id, name, gender, age)
```

(This change is in `resolve.py` but listed here because it serves the
demographics-only flow.)

- [ ] **Step 4: Add `_infer_task_type` and update `_schedule_task`**

Add helper:

```python
def _infer_task_type(title: str, notes: str, has_datetime: bool) -> str:
    text = (title or "") + (notes or "")
    if any(kw in text for kw in ("复诊", "复查", "随访")):
        return "follow_up"
    if has_datetime or any(kw in text for kw in ("预约", "门诊")):
        return "appointment"
    return "general"
```

In `_schedule_task`, replace `args.task_type` references:

```python
task_type_str = _infer_task_type(
    args.title or "", args.notes or "",
    has_datetime=bool(args.scheduled_for),
)
```

- [ ] **Step 5: Delete `_select_patient` and `_create_patient` functions**

Remove both functions entirely. Their logic is now handled by `_ensure_patient`
(resolve) and the demographics-only branch in `_create_record`.

- [ ] **Step 6: Remove `TASK_TYPE_LABELS` dict**

Delete the dict (lines 26-30). Task label is derived from title or defaults:

```python
task_label = args.title or "任务"
```

- [ ] **Step 7: Update imports**

Remove `CreatePatientArgs`, `ScheduleTaskArgs`, `TaskType`. Add `RecordArgs`,
`UpdateArgs`, `TaskArgs`.

- [ ] **Step 8: Commit**

```bash
git add src/services/runtime/commit_engine.py src/services/runtime/resolve.py
git commit -m "refactor: simplify commit engine, infer task_type, demographics-only path"
```

---

### Task 5: Simplify `read_engine.py`

**Files:**
- Modify: `src/services/runtime/read_engine.py`

- [ ] **Step 1: Replace dispatch with target-based routing**

Replace `read()` (lines 15-25):

```python
async def read(action: ResolvedAction, doctor_id: str) -> ReadResult:
    target = _get_target(action)
    if target == "patients":
        return await _list_patients(doctor_id)
    if target == "tasks":
        return await _list_tasks(action, doctor_id)
    return await _query_records(action, doctor_id)


def _get_target(action: ResolvedAction) -> str:
    if action.args and hasattr(action.args, "target") and action.args.target:
        return action.args.target
    return "records"
```

- [ ] **Step 2: Update imports**

Replace `ActionType` usage in the dispatch. The internal functions
`_query_records`, `_list_patients`, `_list_tasks` stay unchanged.

- [ ] **Step 3: Commit**

```bash
git add src/services/runtime/read_engine.py
git commit -m "refactor: target-based dispatch in read engine"
```

---

## Chunk 5: Compose, Turn, Messages

### Task 6: Simplify `compose.py`

**Files:**
- Modify: `src/services/runtime/compose.py`

- [ ] **Step 1: Update `_compose_commit` template branches**

Replace the 5 branches (lines 61-94) with 3:

```python
def _compose_commit(result, action_type, patient_name):
    name = patient_name or ""
    data = result.data or {}

    if action_type == ActionType.record:
        if data.get("patient_only"):
            return M.patient_registered.format(name=name)
        preview = data.get("preview", "")
        return M.record_created.format(patient=name, preview=preview)

    if action_type == ActionType.update:
        preview = data.get("preview", "")
        return M.record_updated.format(patient=name, preview=preview)

    if action_type == ActionType.task:
        dt_display = data.get("datetime_display", "")
        task_label = data.get("title") or "任务"
        if not dt_display:
            return f"已为【{name}】创建{task_label}。"
        noon_default = data.get("noon_default", False)
        if noon_default:
            return M.schedule_task_ok_noon.format(
                patient=name, task_label=task_label, datetime_display=dt_display,
            )
        return M.schedule_task_ok.format(
            patient=name, task_label=task_label, datetime_display=dt_display,
        )

    return M.default_reply
```

- [ ] **Step 2: Remove `task_type` from clarification field_labels**

In `compose_clarification()` (line 203), remove `"task_type"` from the dict:

```python
field_labels = {
    "patient_name": "患者姓名",
    "scheduled_for": "预约时间",
}
```

- [ ] **Step 3: Remove `ClarificationKind.invalid_time` branch**

Delete the `invalid_time` handler (lines 223-224). No longer generated.

- [ ] **Step 4: Commit**

```bash
git add src/services/runtime/compose.py
git commit -m "refactor: simplify compose templates for 5 action types"
```

---

### Task 7: Update `turn.py` view_payload mapping

**Files:**
- Modify: `src/services/runtime/turn.py`

- [ ] **Step 1: Update view_payload assignment for query actions**

Replace the 3-branch view_payload mapping (lines 231-236) with target-based:

```python
if read_result.data:
    target = getattr(resolved.args, "target", "records") or "records"
    type_map = {
        "records": "records_list",
        "patients": "patients_list",
        "tasks": "tasks_list",
    }
    view_payload = {"type": type_map.get(target, "records_list"), "data": read_result.data}
```

- [ ] **Step 2: Commit**

```bash
git add src/services/runtime/turn.py
git commit -m "refactor: target-based view_payload in turn orchestrator"
```

---

### Task 8: Update `messages.py`

**Files:**
- Modify: `src/messages.py`

- [ ] **Step 1: Remove obsolete templates**

Delete:
- `select_patient_ok`
- `create_patient_ok`

- [ ] **Step 2: Add `patient_registered` template**

```python
patient_registered = "✅ 已建档【{name}】。"
```

- [ ] **Step 3: Commit**

```bash
git add src/messages.py
git commit -m "refactor: update message templates for simplified action types"
```

---

## Final: Verification

### Task 9: Manual smoke test

- [ ] **Step 1: Start the app and test all 5 action types**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

Test each:
- `none`: "你好" → greeting
- `query`: "查看张三的病历" → records; "我的患者" → patient list; "今日任务" → tasks
- `record`: "张三头痛3天" → creates record; "新患者王芳，女30岁" → creates patient only
- `update`: "把诊断改成高血压" → updates latest record
- `task`: "张三3个月后复查" → creates task with inferred follow_up type

- [ ] **Step 2: Test multi-action**

"李淑芳，血压135/85，3个月复查" → should produce `[record, task]`

- [ ] **Step 3: Verify task_type inference**

Check DB: `SELECT task_type FROM doctor_tasks ORDER BY id DESC LIMIT 5` — should
show inferred values, not "general" everywhere.
