# Understand Simplification — Action Type Reduction

## Goal

Reduce the ActionType enum from 9 types to 5, eliminating redundant
classifications that the LLM frequently confuses, and remove `task_type`
from task args (inferred by commit engine instead).

## Motivation

- **LLM accuracy**: Fewer action types = fewer misclassification errors.
  The LLM often confuses `select_patient` vs `create_patient` vs
  `create_record`, and `query_records` vs `list_patients`.
- **Code simplification**: 4 fewer branches in resolve, commit engine,
  compose, and turn orchestrator.
- **Prompt size**: Shorter understand prompt = faster inference, less cost.
- `create_record` already auto-creates patients via `_ensure_patient`.
  Standalone `create_patient` is redundant.
- `select_patient` is functionally identical to a patient-scoped
  `query_records` (binds context as side effect).
- `task_type` classification (`appointment`/`follow_up`/`general`) is
  trivially inferrable from keywords; removing it eliminates a common
  validation failure.

## New action types

| Type | Replaces | Behavior |
|---|---|---|
| `none` | `none` | Chat/help — unchanged |
| `query` | `query_records`, `list_patients`, `list_tasks`, `select_patient` | All reads. `target` field disambiguates. |
| `record` | `create_record`, `create_patient` | Clinical content → save record. Demographics only → create patient. |
| `update` | `update_record` | Modify existing record — unchanged semantics. |
| `task` | `schedule_task` | Create task — `task_type` inferred, not LLM-classified. |

### `query` action

```python
class QueryTarget(str, Enum):
    records = "records"
    patients = "patients"
    tasks = "tasks"

@dataclass
class QueryArgs:
    target: Optional[str] = None      # "records" | "patients" | "tasks"; default "records"
    patient_name: Optional[str] = None
    limit: Optional[int] = None
    status: Optional[str] = None      # for tasks: "pending" | "completed"
```

Resolution:
- `target=records` + `patient_name` → resolve patient, fetch records (was `query_records`)
- `target=patients` → unscoped, fetch patient list (was `list_patients`)
- `target=tasks` → unscoped, fetch task list (was `list_tasks`)
- `patient_name` only, no target → default to `records` (was `select_patient`)

### `record` action

```python
@dataclass
class RecordArgs:
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
```

Commit engine behavior:
1. Collect clinical text from chat_archive + current input
2. If clinical text is non-empty → structure + save record (existing path)
3. If clinical text is empty but patient_name present → create/bind patient
   only, return `CommitResult(data={"patient_only": True, ...})`
4. If both empty → error `no_clinical_content`

Demographics (`gender`, `age`) are passed through to `create_patient` when
auto-creating. Previously these were only available via `CreatePatientArgs`.

### `task` action

```python
@dataclass
class TaskArgs:
    patient_name: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    scheduled_for: Optional[str] = None   # ISO-8601
    remind_at: Optional[str] = None       # ISO-8601
```

`task_type` removed entirely. `DoctorTask.task_type` column kept in schema
(backward compat) but always written as `"general"`. No inference, no labels —
the task title carries the semantic meaning.

### `update` action

```python
@dataclass
class UpdateArgs:
    instruction: str
    patient_name: Optional[str] = None
```

Unchanged semantics from current `UpdateRecordArgs`. Renamed for consistency.

---

## Affected files

### `types.py` — enum + args overhaul

- `ActionType`: 9 values → 5 (`none`, `query`, `record`, `update`, `task`)
- Replace 8 args dataclasses with 4: `QueryArgs`, `RecordArgs`, `UpdateArgs`, `TaskArgs`
- No `QueryTarget` enum — `QueryArgs.target` is `Optional[str]` validated by code
- `ARGS_TYPE_TABLE`: 9 entries → 5
- `READ_ACTIONS = frozenset({ActionType.query})`
- `WRITE_ACTIONS = frozenset({ActionType.record, ActionType.update, ActionType.task})`
- `RESPONSE_MODE_TABLE`: 9 entries → 5
- Remove `TaskType` enum
- Remove `ClarificationKind.invalid_time` (was only for schedule_task validation)

### `prompts/understand.md` — rewrite

Shrink from 112 lines to ~60. Five action types, simpler examples. Key change:
`record` covers both clinical content and demographics-only patient creation.
`query` uses `target` field. `task` has no `task_type`.

### `understand.py` — no change

The parser is generic — it reads `action_type` and `args` from JSON. The enum
change is transparent as long as `ActionType(raw_action)` works.

### `resolve.py` — simplify branches

Delete:
- `select_patient` branch (lines 56-61)
- `create_patient` branch (lines 56-61)
- `_validate_schedule_task` function (lines 285-342)

Change:
- `create_record` branch → `record` branch (same logic via `_ensure_patient`)
- `update_record` branch → `update` branch (same logic)
- `query` branch: if `target=patients` or `target=tasks`, skip patient
  resolution (unscoped). If `target=records` or default, resolve patient.
- Generic patient resolution block (lines 103-131) handles `task` action
  (unchanged — it already does patient lookup for `schedule_task`)
- Remove `TaskType` validation entirely

### `commit_engine.py` — merge + infer

Delete:
- `_select_patient()` function
- `_create_patient()` function
- `TASK_TYPE_LABELS` dict

Change:
- `commit()` dispatch: 5 branches instead of 7
- `_create_record()`: add demographics-only fallback when clinical text is
  empty but patient_name present. Pass `gender`/`age` from `RecordArgs` to
  `create_patient`.
- `_schedule_task()`: read `task_type` from `_infer_task_type()` instead of
  `args.task_type`. Remove validation that rejects missing task_type.

### `read_engine.py` — target dispatch

Replace 3-branch `if/elif` with target-based dispatch:

```python
async def read(action: ResolvedAction, doctor_id: str) -> ReadResult:
    target = _get_target(action)
    if target == "patients":
        return await _list_patients(doctor_id)
    if target == "tasks":
        return await _list_tasks(action, doctor_id)
    return await _query_records(action, doctor_id)
```

Internal functions `_query_records`, `_list_patients`, `_list_tasks` unchanged.

### `compose.py` — template consolidation

Delete:
- `ActionType.select_patient` template branch
- `ActionType.create_patient` template branch

Change:
- `ActionType.record` → two sub-templates:
  - `patient_only=True` → patient created message
  - else → record created message (existing)
- `ActionType.task` → remove `task_label` from data (infer display label
  from title)
- Clarification: remove `task_type` from `field_labels` dict

### `turn.py` — update references + remove `scoped_only`

- `view_payload` type mapping: use `target` to determine payload type
- **Remove `scoped_only` check** from context binding (lines 252-260).
  Change `if resolved.patient_id and not resolved.scoped_only:` to
  `if resolved.patient_id:`. All patient-scoped actions now bind context
  unconditionally.

### `messages.py` — template cleanup

- Remove `select_patient_ok`, `create_patient_ok`, `schedule_task_ok`,
  `schedule_task_ok_noon`
- Add `patient_registered = "✅ 已建档【{name}】。"` for demographics-only path
- Remove `task_type` from `clarify_missing_field` label dict

### `types.py` — remove `scoped_only` from `ResolvedAction`

Delete the `scoped_only: bool = False` field. No consumer remains.

---

## Unchanged

| Component | Why |
|---|---|
| `_ensure_patient` (resolve.py) | Same patient resolution logic, just fewer callers |
| `_collect_clinical_text` (commit_engine.py) | Reads chat_archive, unchanged |
| `structure_medical_record` (structuring.py) | Receives text, unchanged |
| All DB models | No schema changes |
| All repositories/CRUD | No changes |
| Export, serialization, frontend | No changes |
| WeChat channel | Uses `process_turn`, transparent |

---

## Backward compatibility

- The understand prompt is a code-managed `.md` file — change is atomic with
  code deploy.
- Old action types in inflight LLM responses hit `UnderstandError` — same
  error path as any malformed output.
- `DoctorTask.task_type` column: kept, written via inference. No schema change.
- E2E test fixtures referencing old action types need updating.

---

## Risks

1. **Multi-action regression**: "张三头痛3天，3个月后复查" currently produces
   `[create_record, schedule_task]`. With the new types it should produce
   `[record, task]`. The prompt examples must cover this.

2. **Query target misclassification**: The LLM might default `target` to
   `records` when the doctor meant `tasks`. Mitigation: clear keyword triggers
   in the prompt ("待办/任务/提醒 → tasks").

3. **Demographics-only detection**: When `_create_record` gets no clinical
   text, it needs to detect `gender`/`age` in args and create the patient.
   If `RecordArgs` has no name either, it falls through to error — same as
   today.
