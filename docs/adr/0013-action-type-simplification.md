# ADR 0013: Action Type Simplification

## Status

Accepted

## Date

2026-03-16

## Implementation Status

Not Started

Last reviewed: 2026-03-16

Notes:

- This ADR supersedes the action type and binding model defined in ADR 0012 §3,
  §6, §10. The three-phase pipeline architecture (Understand → Execute →
  Compose) remains unchanged.
- Scope: action enum reduction, patient binding simplification, task_type
  removal.
- Spec: `docs/superpowers/specs/2026-03-16-understand-simplification-design.md`
- Plan: `docs/superpowers/plans/2026-03-16-understand-simplification.md`

## Context

ADR 0012 defined 9 action types with different patient binding rules:

| ADR 0012 Action | Engine | Binding rule |
|---|---|---|
| `none` | — | no binding |
| `query_records` | read | scoped_only (no context switch) |
| `list_patients` | read | unscoped |
| `list_tasks` | read | unscoped |
| `schedule_task` | commit | switch context |
| `select_patient` | commit | switch context |
| `create_patient` | commit | switch context |
| `create_record` | commit | switch context |
| `update_record` | commit | switch context |

Problems observed during MVP iteration:

1. **LLM misclassification.** 9 types with overlapping semantics cause frequent
   errors. The LLM confuses `select_patient` vs `create_patient` vs
   `create_record` (all mention a patient name). It confuses `query_records` vs
   `list_patients` (both are reads).

2. **`scoped_only` breaks the natural workflow.** A doctor saying "查看张三的
   病历" expects to work with 张三 afterward. But `scoped_only=True` prevents
   context switch, so a follow-up "把诊断改成X" silently applies to the
   *previous* patient. The flag was designed for "cross-reference peek" — a rare
   pattern that doesn't justify the common-case confusion.

3. **`select_patient` is redundant.** Every patient-scoped action already
   resolves and binds the patient. `_ensure_patient` (resolve) auto-creates
   patients for writes. With `scoped_only` removed, reads also bind context.
   There is no case where "switch context without doing anything" is the best
   user experience — `query` always returns useful data alongside the switch.

4. **`create_patient` is redundant.** `_ensure_patient` auto-creates patients
   when a name is given but not found. The standalone `create_patient` only
   served registration-without-clinical-content ("新患者张三，男45岁"), which
   maps cleanly to `record` with a demographics-only fallback.

5. **`task_type` causes validation failures.** The LLM must classify
   `appointment` vs `follow_up` vs `general`, and `_validate_schedule_task`
   rejects the action if the type is missing or wrong. The distinction is
   trivially inferrable from keywords in the title and not needed for MVP.

## Decision

### 1. Reduce ActionType to 5 values

```
none    — chat/help/greeting (unchanged)
query   — all reads (records, patients, tasks) via `target` field
record  — save record or register patient (demographics-only fallback)
update  — modify existing record (unchanged semantics)
task    — create task (task_type always "general")
```

### 2. Remove `scoped_only` — all patient-scoped actions bind context

Every action that resolves a `patient_id` switches context unconditionally:

```
turn.py (after dispatch):
    if resolved.patient_id:
        ctx.workflow.patient_id = resolved.patient_id
        ctx.workflow.patient_name = resolved.patient_name
```

No `scoped_only` flag. No `ResolvedAction.scoped_only` field. The binding rule
is simple: **if you mentioned a patient, you're working with that patient.**

This matches doctor expectation: "查看张三的病历" followed by "把诊断改成X"
naturally applies to 张三.

### 3. `query` action with `target` field

```python
@dataclass
class QueryArgs:
    target: Optional[str] = None       # "records" | "patients" | "tasks"
    patient_name: Optional[str] = None
    limit: Optional[int] = None
    status: Optional[str] = None       # for tasks: "pending" | "completed"
```

`target` is `Optional[str]`, not an enum. Default: `"records"`.

Routing in resolve:
- `target=patients` or `target=tasks` → no patient resolution needed
- `target=records` (or default) → resolve patient, bind context

Routing in read_engine:
- `target=patients` → `_list_patients()`
- `target=tasks` → `_list_tasks()`
- default → `_query_records()`

### 4. `record` action absorbs `create_patient` and `select_patient`

```python
@dataclass
class RecordArgs:
    patient_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
```

Commit engine behavior:
1. Collect clinical text from chat_archive + current input
2. If clinical text present → structure + save record (existing path)
3. If clinical text empty and patient_name present → patient-only registration.
   Return `CommitResult(data={"patient_only": True, "name": ...})`
4. If both empty → error

"切换到张三" maps to `query` (not `record`), providing context switch +
useful record summary. `record` is only for content or demographics.

### 5. Remove `task_type` entirely

`TaskType` enum deleted. `DoctorTask.task_type` column kept in schema but
always written as `"general"`. No inference, no labels — the task title carries
the semantic meaning.

```python
@dataclass
class TaskArgs:
    patient_name: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    scheduled_for: Optional[str] = None
    remind_at: Optional[str] = None
```

`_validate_schedule_task` in resolve deleted entirely.

### 6. Updated pipeline flow

```text
user_input + DoctorCtx
      |
  Understand     — classify 1 of 5 action types
  |                no task_type, no scoped_only
  |
  Execute
  |  ├── Resolve       — patient lookup, binding (all actions bind context)
  |  └── dispatch:
  |       ├── read_engine   — query → target-based dispatch
  |       └── commit_engine — record (+ demographics-only), update, task
  |
  Compose        — template (writes) or LLM (reads)
  |
  Context bind   — unconditional: if patient_id, switch context
```

## Consequences

### Positive

- LLM classifies 5 types instead of 9 — fewer misclassification errors
- Understand prompt shrinks ~45% (112 lines → ~60)
- Resolve loses 3 branches and `_validate_schedule_task` (~60 lines)
- Commit engine loses 2 functions (`_select_patient`, `_create_patient`)
- No `scoped_only` concept — simpler mental model for developers
- Patient binding is uniform and predictable

### Negative

- "Cross-reference peek" (read another patient's records without switching) is
  no longer possible. Accepted: the doctor can switch back.
- `DoctorTask.task_type` column becomes dead (always "general"). Kept for
  backward compat; can be cleaned up later.

### Deferred

- Task type inference from keywords (if the distinction proves needed later)
- `DoctorTask.task_type` column removal (schema change, deferred to production)
- `encounter_type` column removal (discussed, explicitly deferred)

## What changes from ADR 0012

| ADR 0012 | ADR 0013 |
|---|---|
| 9 action types | 5 action types |
| `query_records`, `list_patients`, `list_tasks` | `query` with `target` field |
| `select_patient`, `create_patient`, `create_record` | `record` (demographics-only fallback) |
| `update_record` | `update` |
| `schedule_task` with `task_type` | `task` (no task_type) |
| `scoped_only=True` for reads | Removed — all actions bind context |
| `TaskType` enum | Removed |
| `_validate_schedule_task` in resolve | Removed |
| `TASK_TYPE_LABELS` in commit engine | Removed |
| Patient binding asymmetry (reads scope, writes switch) | Uniform: all bind |
