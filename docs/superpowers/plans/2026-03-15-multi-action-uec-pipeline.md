# Multi-Action UEC Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the UEC pipeline to support multiple actions per turn, replace draft confirmation with direct save, and add update_record action type.

**Architecture:** The LLM understand phase returns an ordered `actions: [...]` array (1-3 items). The pipeline loops resolve→execute for each action sequentially, threading context updates between steps. Draft confirmation is removed; records save directly. A new `update_record` action re-structures the latest record with the doctor's amendment.

**Tech Stack:** Python 3.9+, SQLAlchemy async, FastAPI, OpenAI-compatible LLM client

**Spec:** `docs/superpowers/specs/2026-03-15-multi-action-uec-pipeline-design.md`

---

## Chunk 1: Types + Models Foundation

### Task 1: Update types.py — ActionType enum, new dataclasses, table updates

**Files:**
- Modify: `src/services/runtime/types.py`

- [ ] **Step 1: Replace `create_draft` with `create_record` and add `update_record` in ActionType enum**

Replace lines 12-20:
```python
class ActionType(str, Enum):
    """All recognised operational action types."""
    query_records = "query_records"
    list_patients = "list_patients"
    schedule_task = "schedule_task"
    select_patient = "select_patient"
    create_patient = "create_patient"
    create_record = "create_record"
    update_record = "update_record"
    none = "none"
```

- [ ] **Step 2: Replace `CreateDraftArgs` with `CreateRecordArgs`, add `UpdateRecordArgs`**

Replace lines 84-87 and add after:
```python
@dataclass
class CreateRecordArgs:
    """Empty — clinical content collected from chat_archive by commit engine."""
    pass


@dataclass
class UpdateRecordArgs:
    """Doctor's instruction to amend the most recent record."""
    instruction: str
```

- [ ] **Step 3: Add `ActionIntent` dataclass after `UnderstandResult`**

Add after line 145:
```python
@dataclass
class ActionIntent:
    """Single action from the understand phase, before resolution."""
    action_type: ActionType
    args: Optional[Any] = None
```

- [ ] **Step 4: Update `UnderstandResult` to use `actions` list**

Replace lines 140-145:
```python
@dataclass
class UnderstandResult:
    actions: List["ActionIntent"]
    chat_reply: Optional[str] = None
    clarification: Optional[Clarification] = None
```

- [ ] **Step 5: Update const tables**

Replace `RESPONSE_MODE_TABLE` (lines 50-58):
```python
RESPONSE_MODE_TABLE: Dict[ActionType, ResponseMode] = {
    ActionType.none: ResponseMode.direct_reply,
    ActionType.query_records: ResponseMode.llm_compose,
    ActionType.list_patients: ResponseMode.llm_compose,
    ActionType.schedule_task: ResponseMode.template,
    ActionType.select_patient: ResponseMode.template,
    ActionType.create_patient: ResponseMode.template,
    ActionType.create_record: ResponseMode.template,
    ActionType.update_record: ResponseMode.template,
}
```

Replace `WRITE_ACTIONS` (lines 61-66):
```python
WRITE_ACTIONS = frozenset({
    ActionType.schedule_task,
    ActionType.select_patient,
    ActionType.create_patient,
    ActionType.create_record,
    ActionType.update_record,
})
```

Replace `ARGS_TYPE_TABLE` (lines 113-121):
```python
ARGS_TYPE_TABLE: Dict[ActionType, type] = {
    ActionType.select_patient: SelectPatientArgs,
    ActionType.create_patient: CreatePatientArgs,
    ActionType.create_record: CreateRecordArgs,
    ActionType.update_record: UpdateRecordArgs,
    ActionType.query_records: QueryRecordsArgs,
    ActionType.list_patients: ListPatientsArgs,
    ActionType.schedule_task: ScheduleTaskArgs,
    ActionType.none: type(None),
}
```

- [ ] **Step 6: Add `record_id` to `ResolvedAction`**

Replace lines 151-157:
```python
@dataclass
class ResolvedAction:
    action_type: ActionType
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    args: Optional[Any] = None
    scoped_only: bool = False
    record_id: Optional[int] = None  # resolve-time: target record for update_record
```

- [ ] **Step 7: Remove `pending_id` from `CommitResult`**

Replace lines 170-176:
```python
@dataclass
class CommitResult:
    status: str  # "ok" | "error"
    data: Optional[Any] = None
    message_key: Optional[str] = None
    error_key: Optional[str] = None
```

- [ ] **Step 8: Commit**

```bash
git add src/services/runtime/types.py
git commit -m "refactor(types): replace create_draft with create_record/update_record, add ActionIntent/UnderstandResult.actions"
```

### Task 2: Update models.py — Remove pending fields from TurnResult

**Files:**
- Modify: `src/services/runtime/models.py`

- [ ] **Step 1: Remove pending fields from TurnResult**

Replace lines 57-66:
```python
@dataclass
class TurnResult:
    """Final result returned to the channel adapter."""
    reply: str
    record_id: Optional[int] = None
    view_payload: Optional[Dict[str, Any]] = None
    switch_notification: Optional[str] = None
```

Note: `WorkflowState.pending_draft_id` is intentionally retained as a dead field for backward compat with serialized context rows.

- [ ] **Step 2: Commit**

```bash
git add src/services/runtime/models.py
git commit -m "refactor(models): remove pending_id/pending_patient_name/pending_expires_at from TurnResult"
```

### Task 3: Update messages.py — Add create_record/update_record messages

**Files:**
- Modify: `src/messages.py`

- [ ] **Step 1: Add new messages and update existing ones**

Replace the `draft_created` line (line 59) with:
```python
    record_created = "📋 已为【{patient}】保存病历：\n{preview}"
```

Add after `schedule_task_ok_noon` (line 91):
```python
    record_updated = "✅ 已更新【{patient}】的病历：\n{preview}"
    no_record_to_update = "该患者暂无病历记录，无法修改。"
```

- [ ] **Step 2: Commit**

```bash
git add src/messages.py
git commit -m "feat(messages): add record_created/record_updated templates, keep draft messages for migration"
```

## Chunk 2: Understand Phase

### Task 4: Rewrite understand.md prompt

**Files:**
- Modify: `src/prompts/understand.md`

- [ ] **Step 1: Replace entire file with new multi-action prompt**

The full prompt is specified in the design spec §3 "Full new prompt". Copy it verbatim from `docs/superpowers/specs/2026-03-15-multi-action-uec-pipeline-design.md` lines 152-289.

- [ ] **Step 2: Commit**

```bash
git add src/prompts/understand.md
git commit -m "feat(prompt): rewrite understand.md for multi-action actions[] format"
```

### Task 5: Update understand.py — Parse actions array

**Files:**
- Modify: `src/services/runtime/understand.py`

- [ ] **Step 1: Update imports**

Add to the imports from `services.runtime.types` (line 10-17):
```python
from services.runtime.types import (
    ARGS_TYPE_TABLE,
    ActionIntent,
    ActionType,
    Clarification,
    ClarificationKind,
    UnderstandError,
    UnderstandResult,
)
```

- [ ] **Step 2: Raise max_tokens**

Change line 83 from `max_tokens=500` to `max_tokens=1000`.

- [ ] **Step 3: Clear cached prompt on module reload**

The module-level `_UNDERSTAND_PROMPT` caches the old prompt. Add after line 29:
```python
def invalidate_prompt_cache() -> None:
    global _UNDERSTAND_PROMPT
    _UNDERSTAND_PROMPT = None
```

- [ ] **Step 4: Rewrite `_parse_response` to handle actions array**

Replace the entire `_parse_response` function (lines 93-144):

```python
_MAX_ACTIONS = 3


def _parse_response(raw: Optional[str]) -> UnderstandResult:
    """Parse LLM JSON response into UnderstandResult with invariant enforcement."""
    if not raw:
        raise UnderstandError("empty LLM response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UnderstandError(f"invalid JSON: {e}") from e

    # ── Parse clarification ──────────────────────────────────────────
    clarification: Optional[Clarification] = None
    raw_clar = data.get("clarification")
    if raw_clar and isinstance(raw_clar, dict):
        try:
            kind = ClarificationKind(raw_clar.get("kind", ""))
        except ValueError:
            kind = ClarificationKind.unsupported
        clarification = Clarification(
            kind=kind,
            missing_fields=raw_clar.get("missing_fields", []),
            options=raw_clar.get("options", []),
            suggested_question=raw_clar.get("suggested_question"),
        )

    # ── Parse actions (new array format) or legacy flat format ────────
    raw_actions = data.get("actions")
    if raw_actions and isinstance(raw_actions, list):
        actions = _parse_actions_list(raw_actions)
    elif "action_type" in data:
        # Backward compat: wrap old flat format
        action_type, args = _parse_single_action(data)
        actions = [ActionIntent(action_type=action_type, args=args)]
    else:
        actions = [ActionIntent(action_type=ActionType.none)]

    # Cap at max actions
    if len(actions) > _MAX_ACTIONS:
        log.warning("[understand] LLM returned %d actions, capping at %d", len(actions), _MAX_ACTIONS)
        actions = actions[:_MAX_ACTIONS]

    # ── Parse chat_reply ─────────────────────────────────────────────
    chat_reply: Optional[str] = data.get("chat_reply")

    # Invariant: chat_reply only when all actions are none
    if any(a.action_type != ActionType.none for a in actions):
        chat_reply = None

    # Precedence: clarification wins over chat_reply
    if clarification and chat_reply:
        chat_reply = None

    return UnderstandResult(
        actions=actions,
        chat_reply=chat_reply,
        clarification=clarification,
    )


def _parse_actions_list(raw_actions: list) -> List[ActionIntent]:
    """Parse the actions array from the new multi-action format."""
    actions: List[ActionIntent] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        raw_action = item.get("action_type", "none")
        try:
            action_type = ActionType(raw_action)
        except ValueError:
            log.warning("[understand] unknown action_type in array: %s", raw_action)
            continue
        raw_args = item.get("args") or {}
        args = _parse_args(action_type, raw_args)
        actions.append(ActionIntent(action_type=action_type, args=args))
    if not actions:
        actions = [ActionIntent(action_type=ActionType.none)]
    return actions


def _parse_single_action(data: Dict[str, Any]) -> tuple:
    """Parse the legacy single-action flat format. Returns (action_type, args)."""
    raw_action = data.get("action_type", "none")
    try:
        action_type = ActionType(raw_action)
    except ValueError:
        raise UnderstandError(f"unknown action_type: {raw_action}")
    args = _parse_args(action_type, data.get("args") or {})
    return action_type, args
```

- [ ] **Step 5: Commit**

```bash
git add src/services/runtime/understand.py
git commit -m "feat(understand): parse actions[] array, backward compat for flat format, raise max_tokens to 1000"
```

## Chunk 3: Resolve Phase

### Task 6: Update resolve.py — Change signature, remove pending blocking, add create_record/update_record

**Files:**
- Modify: `src/services/runtime/resolve.py`

- [ ] **Step 1: Update imports**

Replace lines 12-23:
```python
from services.runtime.types import (
    READ_ACTIONS,
    WRITE_ACTIONS,
    ActionIntent,
    ActionType,
    Clarification,
    ClarificationKind,
    QueryRecordsArgs,
    ResolvedAction,
    ScheduleTaskArgs,
    TaskType,
    UpdateRecordArgs,
)
from utils.log import log
```

- [ ] **Step 2: Change `resolve` signature and remove pending blocking**

Replace the entire `resolve` function (lines 27-145) with:

```python
async def resolve(
    action: ActionIntent,
    ctx: Any,  # DoctorCtx — avoid circular import
) -> Union[ResolvedAction, Clarification]:
    """Bind raw understand output to concrete patient/args or clarify."""
    action_type = action.action_type

    if action_type == ActionType.none:
        return ResolvedAction(action_type=action_type, args=action.args)

    # ── list_patients: unscoped, always allowed ─────────────────────────
    if action_type == ActionType.list_patients:
        return ResolvedAction(
            action_type=action_type,
            args=action.args,
            scoped_only=True,
        )

    # ── Extract patient_name from args ──────────────────────────────────
    patient_name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        patient_name = action.args.patient_name

    # ── Patient resolution ──────────────────────────────────────────────
    is_read = action_type in READ_ACTIONS

    # create_patient doesn't need an existing patient
    if action_type == ActionType.create_patient:
        return ResolvedAction(
            action_type=action_type,
            patient_name=patient_name,
            args=action.args,
        )

    # create_record requires current bound patient
    if action_type == ActionType.create_record:
        if ctx.workflow.patient_id is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        return ResolvedAction(
            action_type=action_type,
            patient_id=ctx.workflow.patient_id,
            patient_name=ctx.workflow.patient_name,
            args=action.args,
        )

    # update_record requires current bound patient + existing record
    if action_type == ActionType.update_record:
        if ctx.workflow.patient_id is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        latest = await _fetch_latest_record(ctx.workflow.patient_id, ctx.doctor_id)
        if latest is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                message_key="no_record_to_update",
            )
        record_id, _content = latest
        return ResolvedAction(
            action_type=action_type,
            patient_id=ctx.workflow.patient_id,
            patient_name=ctx.workflow.patient_name,
            args=action.args,
            record_id=record_id,
        )

    # For remaining actions, resolve patient
    if patient_name:
        match_result = await _match_patient(patient_name, ctx.doctor_id)
        if isinstance(match_result, Clarification):
            return match_result
        patient_id, resolved_name = match_result
    elif ctx.workflow.patient_id is not None:
        # Context fallback
        patient_id = ctx.workflow.patient_id
        resolved_name = ctx.workflow.patient_name or ""
    else:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["patient_name"],
            message_key="clarify_missing_field",
        )

    # ── Action-specific validation ──────────────────────────────────────
    if action_type == ActionType.schedule_task:
        validation = _validate_schedule_task(action.args)
        if validation is not None:
            return validation

    return ResolvedAction(
        action_type=action_type,
        patient_id=patient_id,
        patient_name=resolved_name,
        args=action.args,
        scoped_only=is_read,
    )
```

- [ ] **Step 3: Add `_fetch_latest_record` helper after `_match_patient`**

Add after the `_match_patient` function (after line 208):

```python
async def _fetch_latest_record(
    patient_id: int,
    doctor_id: str,
) -> Optional[tuple]:
    """Pure read — SELECT latest medical_record for patient.

    Returns (record_id, content) or None.
    """
    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        stmt = (
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.patient_id == patient_id,
            )
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return (record.id, record.content)
```

- [ ] **Step 4: Commit**

```bash
git add src/services/runtime/resolve.py
git commit -m "refactor(resolve): accept ActionIntent, remove pending blocking, add create_record/update_record/fetch_latest_record"
```

## Chunk 4: Execute Phase

### Task 7: Update commit_engine.py — Replace _create_draft, add _create_record and _update_record

**Files:**
- Modify: `src/services/runtime/commit_engine.py`

- [ ] **Step 1: Update imports**

Replace lines 16-23:
```python
from services.runtime.types import (
    ActionType,
    CommitResult,
    CreatePatientArgs,
    ResolvedAction,
    ScheduleTaskArgs,
    TaskType,
    UpdateRecordArgs,
)
```

- [ ] **Step 2: Update `commit` dispatch table**

Replace lines 49-50:
```python
    if at == ActionType.create_record:
        return await _create_record(action, ctx, recent_turns or [], user_input)
    if at == ActionType.update_record:
        return await _update_record(action, ctx)
```

- [ ] **Step 3: Delete entire `_create_draft` function (lines 200-273)**

Remove the function completely.

- [ ] **Step 4: Add `_create_record` function**

Add in the same location:

```python
async def _create_record(
    action: ResolvedAction,
    ctx: Any,
    recent_turns: List[dict],
    user_input: str,
) -> CommitResult:
    """Collect clinical content, structure, save directly to medical_records."""
    patient_name = action.patient_name or ctx.workflow.patient_name or ""
    patient_id = action.patient_id or ctx.workflow.patient_id

    # Collect clinical text
    clinical_text = await _collect_clinical_text(ctx.doctor_id, patient_id, recent_turns, user_input)
    if not clinical_text.strip():
        return CommitResult(status="error", error_key="no_clinical_content")

    # Structuring LLM call
    from services.ai.structuring import structure_medical_record, _NO_CLINICAL_CONTENT

    try:
        record = await structure_medical_record(clinical_text, doctor_id=ctx.doctor_id)
    except ValueError as e:
        log.warning("[commit] structuring validation error doctor=%s: %s", ctx.doctor_id, e)
        return CommitResult(status="error", error_key="no_clinical_content")
    except Exception as e:
        log.error("[commit] structuring FAILED doctor=%s: %s", ctx.doctor_id, e, exc_info=True)
        return CommitResult(status="error", error_key="structuring_failed")

    # Sentinel check
    if (record.content or "").strip() == _NO_CLINICAL_CONTENT:
        log.info("[commit] structuring returned sentinel doctor=%s", ctx.doctor_id)
        return CommitResult(status="error", error_key="no_clinical_content")

    # Save directly to medical_records
    from db.crud import save_record
    from db.engine import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            db_record = await save_record(db, ctx.doctor_id, record, patient_id)
            record_id = db_record.id
            # Recompute patient category
            if patient_id is not None:
                from services.patient.patient_categorization import recompute_patient_category
                await recompute_patient_category(patient_id, db, commit=False)
            await db.commit()
    except Exception as e:
        log.error("[commit] save_record FAILED doctor=%s: %s", ctx.doctor_id, e, exc_info=True)
        return CommitResult(status="error", error_key="structuring_failed")

    # Fire post-save background tasks
    from services.domain.intent_handlers._confirm_pending import _fire_post_save_tasks
    _fire_post_save_tasks(ctx.doctor_id, record, record_id, patient_name, patient_id)

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "..."

    log.info("[commit] record saved id=%s patient=%s doctor=%s", record_id, patient_name, ctx.doctor_id)
    return CommitResult(
        status="ok",
        data={
            "preview": content_preview,
            "record_id": record_id,
            "patient_name": patient_name,
        },
    )
```

- [ ] **Step 5: Add `_update_record` function**

Add after `_create_record`:

```python
async def _update_record(
    action: ResolvedAction,
    ctx: Any,
) -> CommitResult:
    """Fetch latest record, re-structure with amendment, PATCH."""
    if not isinstance(action.args, UpdateRecordArgs):
        return CommitResult(status="error", error_key="execute_error")

    record_id = action.record_id
    if record_id is None:
        return CommitResult(status="error", error_key="no_record_to_update")

    patient_name = action.patient_name or ctx.workflow.patient_name or ""
    instruction = action.args.instruction

    from db.crud.records import save_record_version
    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from db.repositories.records import RecordRepository
    from services.ai.structuring import structure_medical_record
    from sqlalchemy import select

    # Fetch existing record
    async with AsyncSessionLocal() as db:
        stmt = select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == ctx.doctor_id,
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

    if existing is None:
        return CommitResult(status="error", error_key="no_record_to_update")

    existing_content = existing.content or ""
    existing_record_type = existing.record_type or "visit"

    # Snapshot pre-update state for audit trail
    try:
        async with AsyncSessionLocal() as db:
            await save_record_version(db, existing, ctx.doctor_id)
            await db.commit()
    except Exception as e:
        log.warning("[commit] save_record_version failed record=%s: %s", record_id, e)

    # Re-structure with amendment
    combined_input = f"{existing_content}\n\n---\n医生修改指令：{instruction}"
    try:
        record = await structure_medical_record(combined_input, doctor_id=ctx.doctor_id)
    except Exception as e:
        log.error("[commit] update structuring FAILED doctor=%s: %s", ctx.doctor_id, e, exc_info=True)
        return CommitResult(status="error", error_key="structuring_failed")

    # PATCH the record — preserve record_type
    import json as _json
    from datetime import datetime, timezone

    try:
        async with AsyncSessionLocal() as db:
            repo = RecordRepository(db)
            await repo.update(
                record_id=record_id,
                doctor_id=ctx.doctor_id,
                content=record.content,
                tags=record.tags,
            )
            await db.commit()
    except Exception as e:
        log.error("[commit] update_record FAILED doctor=%s record=%s: %s",
                  ctx.doctor_id, record_id, e, exc_info=True)
        return CommitResult(status="error", error_key="execute_error")

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "..."

    log.info("[commit] record updated id=%s patient=%s doctor=%s", record_id, patient_name, ctx.doctor_id)
    return CommitResult(
        status="ok",
        data={
            "preview": content_preview,
            "record_id": record_id,
            "patient_name": patient_name,
        },
    )
```

- [ ] **Step 6: Commit**

```bash
git add src/services/runtime/commit_engine.py
git commit -m "feat(commit): replace _create_draft with _create_record (direct save), add _update_record"
```

### Task 8: Add RecordRepository.update method

**Files:**
- Modify: `src/db/repositories/records.py`

- [ ] **Step 1: Add update method to RecordRepository**

Add after the `create` method:

```python
    async def update(
        self,
        *,
        record_id: int,
        doctor_id: str,
        content: str,
        tags: List[str],
    ) -> MedicalRecordDB:
        """Update content and tags for an existing record. Preserves record_type."""
        import json as _json
        stmt = select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == doctor_id,
        ).limit(1)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError(f"Record {record_id} not found for doctor {doctor_id}")
        record.content = content
        record.tags = _json.dumps(tags, ensure_ascii=False) if tags else "[]"
        record.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return record
```

Add missing imports at the top of the file if not present:
```python
from datetime import datetime, timezone
```

- [ ] **Step 2: Commit**

```bash
git add src/db/repositories/records.py
git commit -m "feat(db): add RecordRepository.update() for update_record action"
```

### Task 9: Refactor _fire_post_save_tasks signature

**Files:**
- Modify: `src/services/domain/intent_handlers/_confirm_pending.py`

- [ ] **Step 1: Change signature from `pending: Any` to `patient_id: Optional[int]`**

Replace lines 175-177:
```python
def _fire_post_save_tasks(
    doctor_id: str, record: Any, record_id: int,
    patient_name: str, patient_id: Optional[int],
) -> None:
```

- [ ] **Step 2: Replace `pending.patient_id` references with `patient_id`**

Line 194: change `pending.patient_id` → `patient_id`
Line 199: change `pending.patient_id` → `patient_id`

- [ ] **Step 3: Update the call site in `save_pending_record`**

In `save_pending_record` (line 228), update the call:
```python
    _fire_post_save_tasks(doctor_id, record, record_id, patient_name, pending.patient_id)
```

- [ ] **Step 4: Commit**

```bash
git add src/services/domain/intent_handlers/_confirm_pending.py
git commit -m "refactor(confirm_pending): change _fire_post_save_tasks to accept patient_id directly"
```

## Chunk 5: Compose + Channel Cleanup

### Task 10: Update compose.py — Add create_record/update_record templates, remove pending_patient_name

**Files:**
- Modify: `src/services/runtime/compose.py`

- [ ] **Step 1: Update `_compose_commit` to handle new action types**

Replace lines 86-91 (the `create_draft` block):
```python
    if action_type == ActionType.create_record:
        preview = data.get("preview", "")
        return M.record_created.format(patient=name, preview=preview)

    if action_type == ActionType.update_record:
        preview = data.get("preview", "")
        return M.record_updated.format(patient=name, preview=preview)
```

- [ ] **Step 2: Remove `pending_patient_name` from `compose_llm`**

Replace lines 112-116:
```python
async def compose_llm(
    result: ReadResult,
    user_input: str,
    patient_name: Optional[str] = None,
) -> str:
```

Remove lines 128-130 (the cross-patient reminder):
```python
        # Cross-patient context reminder during pending draft
        if pending_patient_name and patient_name and pending_patient_name != patient_name:
            summary += f"\n\n（当前待确认病历为【{pending_patient_name}】）"
```

- [ ] **Step 3: Commit**

```bash
git add src/services/runtime/compose.py
git commit -m "feat(compose): add create_record/update_record templates, remove pending_patient_name"
```

### Task 11: Update ChatResponse in chat.py

**Files:**
- Modify: `src/channels/web/chat.py`

- [ ] **Step 1: Remove pending fields from ChatResponse**

Replace lines 60-68:
```python
class ChatResponse(BaseModel):
    """Output for the /chat endpoint."""
    reply: str
    record: Optional[MedicalRecord] = None
    record_id: Optional[int] = None
    view_payload: Optional[Dict[str, Any]] = None
    switch_notification: Optional[str] = None
```

- [ ] **Step 2: Update the chat endpoint response builder**

Find where `ChatResponse` is constructed (search for `pending_id=result.pending_id`) and remove the pending field pass-throughs. Add `record_id=result.record_id`.

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/chat.py
git commit -m "refactor(chat): remove pending fields from ChatResponse, add record_id"
```

## Chunk 6: Pipeline Orchestrator

### Task 12: Rewrite turn.py — Multi-action loop, remove draft handlers

**Files:**
- Modify: `src/services/runtime/turn.py`

- [ ] **Step 1: Update imports**

Add `ActionIntent` to the types import:
```python
from services.runtime.types import (
    READ_ACTIONS,
    RESPONSE_MODE_TABLE,
    WRITE_ACTIONS,
    ActionIntent,
    ActionType,
    Clarification,
    ResolvedAction,
    ResponseMode,
    UnderstandError,
)
```

- [ ] **Step 2: Remove `_handle_pending_text`, `_confirm_draft`, `_abandon_draft` functions**

Delete `_handle_pending_text` (lines 293-311), `_confirm_draft` (lines 314-340), `_abandon_draft` (lines 343-354).

Keep `CONFIRM_RE`, `ABANDON_RE` module-level symbols (imported by wechat/router.py).
Keep `_handle_action` (still handles draft_confirm/draft_abandon for migration).

- [ ] **Step 3: Remove the pending draft check from process_turn**

Remove the block at lines 136-143:
```python
        # 2. Pending draft confirm/cancel (regex)
        if ctx.workflow.pending_draft_id:
            det_result = await _handle_pending_text(ctx, turn_text)
            ...
```

- [ ] **Step 4: Rewrite `_run_pipeline` for multi-action loop**

Replace the entire `_run_pipeline` function (lines 177-277):

```python
async def _run_pipeline(ctx: DoctorCtx, text: str, doctor_id: str) -> TurnResult:
    """Understand → [Resolve → Dispatch → Compose]* (multi-action loop)."""
    from services.runtime.compose import (
        compose_clarification,
        compose_llm,
        compose_template,
    )
    from services.runtime.understand import understand

    recent_turns = await get_recent_turns(doctor_id)

    # ── Understand ────────────────────────────────────────────────────
    try:
        ur = await understand(text, recent_turns, ctx)
    except UnderstandError as e:
        log.warning("[turn] understand failed doctor=%s: %s", doctor_id, e)
        return TurnResult(reply=M.understand_error)

    # Top-level clarification → skip execute
    if ur.clarification:
        reply = compose_clarification(ur.clarification)
        return TurnResult(reply=reply)

    # Single none action → return chat_reply directly
    if len(ur.actions) == 1 and ur.actions[0].action_type == ActionType.none:
        return TurnResult(reply=ur.chat_reply or M.default_reply)

    # ── Multi-action loop ─────────────────────────────────────────────
    from services.runtime.resolve import resolve

    replies: list = []
    view_payload = None
    switch_notifications: list = []
    record_id = None

    for action_intent in ur.actions:
        # Resolve
        resolve_result = await resolve(action_intent, ctx)

        if isinstance(resolve_result, Clarification):
            replies.append(compose_clarification(resolve_result))
            break

        resolved: ResolvedAction = resolve_result

        # Dispatch to engine
        prev_patient = ctx.workflow.patient_name
        response_mode = RESPONSE_MODE_TABLE.get(resolved.action_type, ResponseMode.template)

        if resolved.action_type in READ_ACTIONS:
            from services.runtime.read_engine import read
            read_result = await read(resolved, doctor_id)

            if response_mode == ResponseMode.llm_compose:
                reply = await compose_llm(
                    read_result,
                    text,
                    patient_name=resolved.patient_name,
                )
            else:
                reply = compose_template(read_result, resolved.action_type, resolved.patient_name)

            if read_result.data:
                if resolved.action_type == ActionType.query_records:
                    view_payload = {"type": "records_list", "data": read_result.data}
                elif resolved.action_type == ActionType.list_patients:
                    view_payload = {"type": "patients_list", "data": read_result.data}

        elif resolved.action_type in WRITE_ACTIONS:
            from services.runtime.commit_engine import commit
            commit_result = await commit(resolved, ctx, recent_turns, text)
            reply = compose_template(commit_result, resolved.action_type, resolved.patient_name)

            if commit_result.data and isinstance(commit_result.data, dict):
                if "record_id" in commit_result.data:
                    record_id = commit_result.data["record_id"]
                if "task_id" in commit_result.data:
                    view_payload = {"type": "task_created", "data": commit_result.data}
        else:
            reply = M.default_reply

        # Track patient switches
        if resolved.patient_id and not resolved.scoped_only:
            if (prev_patient
                    and resolved.patient_name
                    and prev_patient != resolved.patient_name):
                switch_notifications.append(
                    f"已从【{prev_patient}】切换到【{resolved.patient_name}】"
                )
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

- [ ] **Step 5: Commit**

```bash
git add src/services/runtime/turn.py
git commit -m "feat(turn): multi-action pipeline loop, remove draft confirmation handlers"
```

## Chunk 7: Integration Verification

### Task 13: Verify the full pipeline works end-to-end

- [ ] **Step 1: Start the backend**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -m uvicorn src.main:app --port 8000 --reload
```

Verify no import errors on startup.

- [ ] **Step 2: Test single action (none — greeting)**

```bash
curl -s -X POST http://localhost:8000/api/records/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "doctor_id": "test_doctor"}' | python3 -m json.tool
```

Expected: a greeting reply, no errors.

- [ ] **Step 3: Test create_patient + create_record compound**

```bash
curl -s -X POST http://localhost:8000/api/records/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "患者李淑芳，女，68岁，血压135/85，心电图正常，继续当前治疗", "doctor_id": "test_doctor"}' | python3 -m json.tool
```

Expected: reply containing both patient creation confirmation and record preview, joined by `\n\n`.

- [ ] **Step 4: Test update_record**

```bash
curl -s -X POST http://localhost:8000/api/records/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "把诊断改成高血压2级", "doctor_id": "test_doctor"}' | python3 -m json.tool
```

Expected: reply showing updated record preview.

- [ ] **Step 5: Commit all remaining changes**

```bash
git add -u
git commit -m "feat: multi-action UEC pipeline — complete implementation"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Types: ActionType, ActionIntent, UnderstandResult, tables | `types.py` |
| 2 | Models: Remove pending from TurnResult | `models.py` |
| 3 | Messages: Add record_created/record_updated | `messages.py` |
| 4 | Prompt: Rewrite understand.md | `understand.md` |
| 5 | Understand: Parse actions[], backward compat | `understand.py` |
| 6 | Resolve: ActionIntent param, remove blocking, add update_record | `resolve.py` |
| 7 | Commit engine: _create_record, _update_record | `commit_engine.py` |
| 8 | DB: RecordRepository.update | `repositories/records.py` |
| 9 | Confirm pending: Refactor _fire_post_save_tasks | `_confirm_pending.py` |
| 10 | Compose: New templates, remove pending_patient_name | `compose.py` |
| 11 | Chat: Remove pending from ChatResponse | `chat.py` |
| 12 | Turn: Multi-action loop, remove draft handlers | `turn.py` |
| 13 | Integration verification | manual testing |
