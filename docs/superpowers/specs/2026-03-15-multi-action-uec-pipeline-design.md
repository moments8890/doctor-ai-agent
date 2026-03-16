# Multi-Action UEC Pipeline + Direct Save + Update Record

**Date:** 2026-03-15
**Status:** Draft — reviewed (3 passes)

## Problem

The UEC pipeline processes exactly one action per turn. When a doctor sends "患者李淑芳，女，68岁，血压135/85...继续当前治疗", this logically requires two actions (create/select patient + create record) but the system can only execute one — it picks `create_draft` and fails because no patient is selected.

Additionally, the draft confirmation flow (pending_records → confirm/abandon) adds blocking complexity that compounds this problem and creates poor UX.

## Design Decisions

All decisions were made collaboratively during brainstorming:

1. **Multi-action approach:** LLM returns an ordered `actions: [...]` array (not orchestrator loop or compound action types)
2. **Error policy:** Execute-then-stop — if action N fails/clarifies, actions 1..N-1 are already committed
3. **Output format:** Always-array, even for single actions
4. **Max actions:** 3 per turn
5. **Reply aggregation:** Concatenate with `\n\n`
6. **Metadata:** Last-write-wins for `view_payload`
7. **Draft removal:** Replace draft confirmation with direct save (Option B)
8. **Update records:** Add `update_record` action type using re-structuring (Level 2a), always targets latest record
9. **Switch notification:** Accumulate, join with `\n`
10. **`create_draft` removal:** Clean break — remove `create_draft` entirely from `ActionType` enum, `ARGS_TYPE_TABLE`, and `WRITE_ACTIONS`. Not in production, no cached responses to worry about.

## Changes Overview

### 1. Remove Draft Confirmation Flow

**Replace:** `create_draft` → `create_record` (clean removal, no alias)

`create_record` saves directly to `medical_records` instead of `pending_records`. The reply shows the structured content as a preview. The doctor can correct via `update_record` in chat or edit/delete via the patient detail UI.

**Remove:**
- `create_draft` from `ActionType` enum, `ARGS_TYPE_TABLE`, `WRITE_ACTIONS` — no alias, clean break
- `CreateDraftArgs` dataclass (replaced by `CreateRecordArgs`, same empty structure)
- `pending_records` table dependency from the pipeline (table kept for backward compat, no new writes)
- Pending-draft blocking logic in `resolve.py:51-79`
- Confirm/abandon regex handlers in `turn.py` (`_handle_pending_text`)
- `_confirm_draft` / `_abandon_draft` handlers in `turn.py`
- `TurnResult.pending_id`, `pending_patient_name`, `pending_expires_at` fields
- `compose_llm` `pending_patient_name` parameter and cross-patient reminder logic (lines 129-130, hardcoded Python string)
- `CommitResult.pending_id` field (no longer set)

**Retain (dead but kept for compat):**
- `ctx.workflow.pending_draft_id` in `WorkflowState` — retained as `Optional[str] = None`, never written. Removing it would break `context.py` serialization for existing rows and `ui/__init__.py` endpoint reads. Will be removed in a follow-up once all pending records are expired.
- `save_pending_record` function in `_confirm_pending.py` — still needed for existing pending records during migration
- `_handle_action` in `turn.py` for `draft_confirm`/`draft_abandon` — needed for in-flight pending records
- `has_pending_draft()` and `clear_pending_draft_id()` exports from `context.py` — imported by `wechat/router.py`
- `CONFIRM_RE` and `ABANDON_RE` in `turn.py` — imported by `wechat/router.py`. Keep the symbols; remove usage in `_handle_pending_text` only.

**commit_engine changes:**
- Delete `_create_draft` function entirely
- New `_create_record` function:
  1. Collect clinical text (existing `_collect_clinical_text`)
  2. Run structuring LLM (existing `structure_medical_record`)
  3. Save directly to `medical_records` via existing `save_record` from `db.crud.records` (INSERT — same function used by `_confirm_pending.py` today)
  4. Run `recompute_patient_category`
  5. Fire post-save background tasks via refactored `_fire_post_save_tasks`
  6. Return `CommitResult(status="ok", data={preview, record_id, patient_name})`

**`_fire_post_save_tasks` signature change:**

Before:
```python
def _fire_post_save_tasks(
    doctor_id: str, record: Any, record_id: int,
    patient_name: str, pending: Any,  # PendingRecord object
) -> None:
```

After:
```python
def _fire_post_save_tasks(
    doctor_id: str, record: Any, record_id: int,
    patient_name: str, patient_id: Optional[int],  # direct value
) -> None:
```

Only `pending.patient_id` is accessed (lines 194, 199). Change those two references to the new `patient_id` param. All other params are already passed directly.

**`record_type` in `create_record`:** The structuring LLM sets `record_type` via `MedicalRecord.record_type` (defaults to `"visit"`, can be `"dictation"`, `"import"`, etc.). This is unchanged from the current `_create_draft` behavior.

**Context update note:** For `create_patient` actions, `resolved.patient_id` is `None` (patient doesn't exist yet). Context binding (`patient_id`, `patient_name`) happens inside `_create_patient` → `_switch_context`, not in the pipeline's post-execute block. This is correct — the pipeline block guards with `if resolved.patient_id`, so it skips `create_patient`. The next action in the loop (e.g., `create_record`) will see the updated `ctx.workflow.patient_id` from `_switch_context`.

### 2. Add `update_record` Action Type

**New action type:** `update_record` — doctor corrects the most recent record via chat.

**Flow:**
1. Understand classifies: `{"action_type": "update_record", "args": {"instruction": "把诊断改成高血压2级"}}`
2. Resolve: requires current patient (same as `create_record`). Looks up the latest `medical_record` for the patient via a new private helper `_fetch_latest_record(patient_id, doctor_id)` in `resolve.py` (pure SELECT, not `update_latest_record_for_patient` which also mutates).
3. Execute: fetch existing record content → append instruction → re-run structuring LLM → PATCH the record
4. Compose: template reply showing what changed

**New types:**
```python
class ActionType(str, Enum):
    # ... existing (without create_draft) ...
    create_record = "create_record"   # replaces create_draft
    update_record = "update_record"   # new

@dataclass
class CreateRecordArgs:
    """Empty — clinical content collected from chat_archive by commit engine."""
    pass

@dataclass
class UpdateRecordArgs:
    instruction: str  # what the doctor wants to change
```

**Resolve behavior:**
- Requires `ctx.workflow.patient_id` (same check as current `create_draft`)
- Calls `_fetch_latest_record(patient_id, doctor_id)` — new helper, returns `(record_id, content)` or `None`
- If no record exists → clarification: "该患者暂无病历记录"
- Returns `ResolvedAction` with `record_id` set

**`_fetch_latest_record` helper (in resolve.py):**
```python
async def _fetch_latest_record(patient_id: int, doctor_id: str) -> Optional[Tuple[int, str]]:
    """Pure read — SELECT latest medical_record for patient. Returns (record_id, content) or None."""
    async with AsyncSessionLocal() as db:
        stmt = select(MedicalRecordDB).where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id == patient_id,
        ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return (record.id, record.content)
```

**Concurrency note:** `update_record` assumes sequential turn processing per doctor, which is already enforced by per-doctor turn serialization (dedup cache + WeChat sync handler).

**Commit behavior (`_update_record`):**
1. Fetch the existing record's `content` and `record_type` by `record_id`
2. Call `save_record_version` to snapshot the pre-update state (audit trail)
3. Construct input: `"{existing_content}\n\n---\n医生修改指令：{instruction}"`
4. Call `structure_medical_record` on the combined text
5. PATCH the record via a new `RecordRepository.update(record_id, doctor_id, content, tags, updated_at)` method — update `content`, `tags`, `updated_at`; **preserve `record_type`** from the existing record (do not let the structuring LLM re-classify it)
6. Return `CommitResult(status="ok", data={preview, record_id})`

**`record_type` in `update_record`:** Explicitly preserved from the existing record. The re-structuring only changes `content` and `tags`. This prevents the LLM from reclassifying a `"dictation"` as `"visit"` just because the content was amended.

### 3. Multi-Action Pipeline

**Full new prompt (`understand.md`):**

```markdown
# 意图识别

你是一个医疗助手的意图分析模块。你的任务是将医生的输入分解为一个或多个有序操作意图，并提取相关参数。

## 当前上下文
- 当前日期：{current_date}
- 时区：{timezone}
- 当前患者：{current_patient}
- 对话历史：系统会自动提供最近的对话记录，可据此理解指代关系（如"他""这个患者"）

## 输出格式

必须输出合法JSON，不要包含markdown标记。格式如下：

{
  "actions": [
    {"action_type": "...", "args": {}}
  ],
  "chat_reply": null,
  "clarification": null
}

- actions: 必须是数组，包含1-3个操作（按执行顺序排列）
- chat_reply: 仅当 actions 为 [{"action_type": "none", "args": {}}] 时可设置
- clarification: 当无法判断意图时设置（优先级高于 chat_reply）

## action_type 说明

### none — 闲聊/帮助/问候
当用户没有明确的操作意图时使用。这是唯一允许设置 chat_reply 的类型。
args: {}

### query_records — 查询病历
用户想查看某个患者的病历记录。
args: {"patient_name": "张三", "limit": 5}
- limit: 返回数量，默认5，最大10

### list_patients — 查看患者列表
用户想查看自己的患者列表。
args: {}

### schedule_task — 创建任务/预约
用户想创建预约、随访提醒或其他任务。
args: {"task_type": "appointment|follow_up|general", "patient_name": "张三", "title": "复诊", "notes": null, "scheduled_for": "2026-03-18T12:00:00", "remind_at": "2026-03-18T11:00:00"}
- task_type: 必填。"预约/复诊" → appointment，"随访/提醒" → follow_up，其他 → general
- scheduled_for: ISO-8601格式。根据{current_date}将相对日期转换为绝对日期。日期未指定时默认明天，时间未指定时默认中午12:00
- remind_at: ISO-8601格式。未指定时默认为scheduled_for前1小时

### select_patient — 选择/切换患者
用户想切换到某个已有患者。
args: {"patient_name": "张三"}

### create_patient — 创建新患者
用户想创建一个新的患者档案。
args: {"patient_name": "张三", "gender": "男", "age": 45}
- gender: 可选，"男"或"女"
- age: 可选，整数

### create_record — 保存病历记录
用户提供了临床内容，想为患者保存一份病历。
args: {}
- 无参数。临床内容由系统从对话历史和当前输入中收集。

### update_record — 修改最近病历
用户想修改当前患者最近的一条病历记录。
args: {"instruction": "把诊断改成高血压2级"}
- instruction: 必填，医生的修改指令

## 多操作规则

当一条消息包含多个意图时，将它们分解为有序的 actions 数组（最多3个）。常见模式：

1. 消息包含患者信息 + 临床内容，但当前未选择患者 → 先创建/选择患者，再保存病历
2. 报告临床信息后提到预约 → 先保存病历，再创建任务
3. 切换患者后查询 → 先选择患者，再查询病历

### 示例

医生输入："患者李淑芳，女，68岁，血压135/85，心电图正常，继续当前治疗，3个月复查"
当前患者：未选择
→ 需要先创建患者，再保存病历

{"actions": [
  {"action_type": "create_patient", "args": {"patient_name": "李淑芳", "gender": "女", "age": 68}},
  {"action_type": "create_record", "args": {}}
], "chat_reply": null, "clarification": null}

医生输入："查一下张三的血压记录"
当前患者：张三
→ 单个查询操作

{"actions": [
  {"action_type": "query_records", "args": {"patient_name": "张三", "limit": 5}}
], "chat_reply": null, "clarification": null}

医生输入："切换到王明，查他上次的病历"
当前患者：李淑芳
→ 先切换患者，再查询

{"actions": [
  {"action_type": "select_patient", "args": {"patient_name": "王明"}},
  {"action_type": "query_records", "args": {"patient_name": "王明", "limit": 5}}
], "chat_reply": null, "clarification": null}

医生输入："把诊断改成高血压2级，加上阿司匹林100mg"
当前患者：李淑芳
→ 修改病历

{"actions": [
  {"action_type": "update_record", "args": {"instruction": "把诊断改成高血压2级，加上阿司匹林100mg"}}
], "chat_reply": null, "clarification": null}

医生输入："你好"
→ 闲聊

{"actions": [
  {"action_type": "none", "args": {}}
], "chat_reply": "你好！有什么可以帮助您的？", "clarification": null}

## clarification 字段

当你不确定用户意图或缺少必要信息时，设置 clarification 而不是 chat_reply：
{"kind": "ambiguous_intent|missing_field|unsupported", "missing_fields": ["field_name"], "suggested_question": "你想查询还是创建？"}
- ambiguous_intent: 不确定用户想做什么
- missing_field: 必要字段缺失（如schedule_task缺少task_type）
- unsupported: 用户要求的操作系统不支持

## 关键规则

1. actions 必须是数组，即使只有一个操作
2. 当 actions 中有非 none 的操作时，chat_reply 必须为 null
3. 不要编造日期，scheduled_for 有默认值（明天中午12:00）
4. 如果同时出现 clarification 和 chat_reply，clarification 优先
5. 不要生成系统不支持的 action_type
6. patient_name 使用用户说的原始姓名，不要猜测或补全
7. 最多3个操作，超过时只保留最重要的3个
8. 当当前患者为"未选择"且消息提到了患者姓名，优先添加 select_patient 或 create_patient 作为第一个操作
```

**Type changes (`types.py`):**

```python
@dataclass
class ActionIntent:
    """Single action from the understand phase, before resolution."""
    action_type: ActionType
    args: Optional[Any] = None

@dataclass
class UnderstandResult:
    actions: List[ActionIntent]          # replaces action_type + args
    chat_reply: Optional[str] = None
    clarification: Optional[Clarification] = None
```

- Add `create_record` and `update_record` to `ActionType` enum
- Remove `create_draft` from `ActionType` enum entirely (clean break, not in production)
- Add `CreateRecordArgs` and `UpdateRecordArgs` to `ARGS_TYPE_TABLE`
- Remove `CreateDraftArgs` from `ARGS_TYPE_TABLE`
- Add `create_record` and `update_record` to `WRITE_ACTIONS`

**Parser changes (`understand.py`):**

`_parse_response`:
- Parse `actions` array from JSON
- Cap at 3 actions in `_parse_response` (boundary enforcement, not in the loop)
- Log warning if more than 3 returned
- Backward compat: if JSON has `action_type` key (old format), wrap in single-element `actions` list
- Enforce `chat_reply=None` when any action is non-`none`
- Raise `max_tokens` from 500 → 1000

**Pipeline changes (`turn.py` → `_run_pipeline`):**

```python
async def _run_pipeline(ctx, text, doctor_id):
    ur = await understand(text, recent_turns, ctx)

    # Top-level clarification → return immediately
    if ur.clarification:
        return TurnResult(reply=compose_clarification(ur.clarification))

    # Single none action → return chat_reply
    if len(ur.actions) == 1 and ur.actions[0].action_type == ActionType.none:
        return TurnResult(reply=ur.chat_reply or M.default_reply)

    # Multi-action loop
    replies = []
    view_payload = None
    switch_notifications = []
    record_id = None

    for action_intent in ur.actions:
        # Resolve
        resolved = await resolve(action_intent, ctx)
        if isinstance(resolved, Clarification):
            # Partial stop: return accumulated replies + clarification
            replies.append(compose_clarification(resolved))
            break

        # Execute
        prev_patient = ctx.workflow.patient_name

        if resolved.action_type in READ_ACTIONS:
            read_result = await read(resolved, doctor_id)
            reply = compose or template based on response_mode
            if read_result.data:
                view_payload = build_view_payload(resolved, read_result)
        else:
            commit_result = await commit(resolved, ctx, recent_turns, text)
            reply = compose_template(commit_result, ...)
            if commit_result.data and "record_id" in commit_result.data:
                record_id = commit_result.data["record_id"]
            if commit_result.data and "task_id" in commit_result.data:
                view_payload = {"type": "task_created", "data": commit_result.data}

        # Track patient switches — only when resolved has a concrete patient_id.
        # Note: create_patient has resolved.patient_id=None (patient doesn't exist yet);
        # context binding happens inside _create_patient → _switch_context instead.
        if resolved.patient_id and not resolved.scoped_only:
            if prev_patient and resolved.patient_name and prev_patient != resolved.patient_name:
                switch_notifications.append(f"已从【{prev_patient}】切换到【{resolved.patient_name}】")
            ctx.workflow.patient_id = resolved.patient_id
            ctx.workflow.patient_name = resolved.patient_name

        replies.append(reply)

    return TurnResult(
        reply="\n\n".join(replies),
        view_payload=view_payload,
        switch_notification="\n".join(switch_notifications) if switch_notifications else None,
        record_id=record_id,
    )
```

**Resolve changes (`resolve.py`):**

- Change signature: `resolve(action: ActionIntent, ctx)` instead of `resolve(result: UnderstandResult, ctx)`
- Read `action.action_type` and `action.args` instead of `result.action_type` and `result.args`
- Remove all `pending_draft` blocking logic (lines 51-79)
- Add `create_record` handling (same as current `create_draft` minus pending check)
- Add `update_record` handling: require `ctx.workflow.patient_id`, call `_fetch_latest_record` helper
- New private helper: `_fetch_latest_record(patient_id, doctor_id) -> Optional[Tuple[int, str]]` — pure SELECT on `medical_records` ORDER BY `created_at DESC` LIMIT 1, returns `(record_id, content)` or `None`

**Turn.py cleanup:**

Remove:
- `_handle_pending_text` function
- `_confirm_draft`, `_abandon_draft` functions
- Pending draft check block in the deterministic handler section
- `pending_patient_name` logic in `compose_llm` call

Keep (for migration):
- `CONFIRM_RE`, `ABANDON_RE` module-level symbols (imported by `wechat/router.py`)
- `_handle_action` for typed UI actions (draft_confirm/draft_abandon)
- Greeting/help fast paths

### 4. ResolvedAction Extension

Add optional `record_id` field for `update_record`:

```python
@dataclass
class ResolvedAction:
    action_type: ActionType
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    args: Optional[Any] = None
    scoped_only: bool = False
    record_id: Optional[int] = None  # resolve-time: target record for update_record (not the output record_id from commit)
```

Note: `ResolvedAction.record_id` is an **input** (which record to update, set by resolve). `CommitResult.data["record_id"]` is an **output** (which record was created/updated, set by commit). Different types, different pipeline stages.

## Files to Modify

| File | Change |
|------|--------|
| `src/services/runtime/types.py` | Remove `create_draft`/`CreateDraftArgs`. Add `ActionIntent`, `create_record`/`CreateRecordArgs`, `update_record`/`UpdateRecordArgs` to ActionType + tables. Remove `CommitResult.pending_id` |
| `src/services/runtime/understand.py` | Parse `actions[]`, backward compat wrapper for old flat format, raise `max_tokens` to 1000 |
| `src/services/runtime/turn.py` | Multi-action loop, remove `_handle_pending_text`/`_confirm_draft`/`_abandon_draft`, remove `pending_patient_name` from `compose_llm` call. Keep `CONFIRM_RE`/`ABANDON_RE` symbols and `_handle_action` |
| `src/services/runtime/resolve.py` | Change param to `ActionIntent`, remove pending blocking, add `create_record`/`update_record`, add `_fetch_latest_record` helper |
| `src/services/runtime/commit_engine.py` | Delete `_create_draft`. New `_create_record` (direct save via `save_record`), new `_update_record` |
| `src/services/runtime/models.py` | Remove `TurnResult.pending_id`/`pending_patient_name`/`pending_expires_at`. Keep `WorkflowState.pending_draft_id` as dead field (compat). `TurnResult.record_id` already exists (line 64) — no new field needed |
| `src/services/runtime/compose.py` | Add templates for `create_record`/`update_record`. Remove `pending_patient_name` parameter from `compose_llm` and the 2-line cross-patient reminder at lines 129-130 |
| `src/prompts/understand.md` | Full rewrite: `actions[]` format, compound examples, `create_record`/`update_record` docs (see §3 above) |
| `src/messages.py` | Add messages for `create_record`, `update_record`; remove draft-specific messages that are no longer needed |
| `src/channels/web/chat.py` | Remove `pending_id`/`pending_patient_name`/`pending_expires_at` from `ChatResponse` and corresponding `result.*` pass-throughs |
| `src/channels/wechat/router.py` | `_handle_stateful_sync` becomes inert (never fires when `pending_draft_id` is always None). No import changes needed since `CONFIRM_RE`/`ABANDON_RE`/`has_pending_draft` are retained |
| `src/db/repositories/records.py` | Add `RecordRepository.update(record_id, doctor_id, content, tags)` method for `_update_record` |
| `src/db/crud/records.py` | `save_record_version` already exists — used by `_update_record` before patching. `save_record` already exists — used by `_create_record` for INSERT |
| `src/services/domain/intent_handlers/_confirm_pending.py` | Refactor `_fire_post_save_tasks` signature: `pending: Any` → `patient_id: Optional[int]`. Change `pending.patient_id` → `patient_id` on lines 194, 199 |
| `tests/integration/test_uec_pipeline.py` | Replace all `pending_id` assertions with `record_id`, remove confirm/abandon test flows, add multi-action and update_record tests |

## Files Unchanged

| File | Why |
|------|-----|
| `src/services/runtime/read_engine.py` | Called per action, no API change |
| `src/services/runtime/context.py` | Serializes `pending_draft_id` but field is retained in `WorkflowState`. `has_pending_draft()`/`clear_pending_draft_id()` exports retained. No behavioral change |
| `src/channels/web/ui/__init__.py` | Reads `ctx.workflow.pending_draft_id` in 4 functions. Field retained as dead; these code paths become no-ops (always None). No runtime break |
| `src/services/ai/structuring.py` | Reused by both `create_record` and `update_record`, no API change |
| `src/main.py` | Scheduler job `_expire_stale_pending_records` becomes a no-op (no new pending records). Import chain intact. Remove in follow-up |
| `src/db/crud/records.py` | `save_record` (INSERT) and `save_record_version` (snapshot) already exist, no changes needed |

## Known Limitations

1. **Partial commit on multi-action failure** — If `[create_patient, create_record]` runs and `create_record` fails (e.g., structuring LLM timeout), the patient is committed but no record is created. The doctor sees "已创建患者【王明】\n\n病历生成失败，请稍后重试。" This is acceptable: the patient creation is useful, the clinical content is preserved in chat archive, and the doctor can retry `create_record` on the next turn. An all-or-nothing rollback would lose the patient creation and force the doctor to repeat everything.
2. **`compose_llm` gets full turn text** — in multi-action, the compose LLM for a read action receives the entire compound input, not just the query portion. Acceptable for MVP; compose handles this gracefully.
3. **`view_payload` last-write-wins** — if a turn has both a `query_records` (records list widget) and a `schedule_task` (task created widget), only the last one's `view_payload` survives in `TurnResult`. Acceptable until frontend supports multi-widget rendering.
4. **`update_record` re-structuring may change `tags`** — the structuring LLM infers tags from content. Re-structuring after an update may change tags. `record_type` is explicitly preserved (not re-inferred). Acceptable behavior.
5. **Archive gets joined reply** — multi-action turns archive the concatenated reply as a single assistant turn. This is correct behavior for the `_collect_clinical_text` scanner.
6. **`update_record` concurrency** — assumes sequential turn processing per doctor, which is already enforced by per-doctor turn serialization (dedup cache + WeChat sync handler). Not a new risk.

## Migration Notes

- `pending_draft_id` retained as dead field in `WorkflowState` and `context.py` serialization. Existing doctor context rows with a non-null value will simply be ignored (the pending handler still works via `_handle_action` for direct button clicks).
- Existing `pending_records` rows with status `awaiting`: auto-confirmed by the existing scheduler job or expired by TTL. No manual migration needed.
- `draft_confirm`/`draft_abandon` UI action handlers kept temporarily for in-flight pending records. Frontend pending record UI can be removed after one release cycle.
- `CONFIRM_RE`/`ABANDON_RE` kept as module-level symbols in `turn.py` for `wechat/router.py` import compat. `_handle_stateful_sync` in WeChat router becomes permanently inert since `has_pending_draft()` always returns False for new sessions. Schedule removal in follow-up.
