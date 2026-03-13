"""
Pending-record confirmation logic — shared by Web and WeChat channels.

Moved from services/wechat/wechat_domain.py to eliminate cross-channel
dependency and enable both channels to use identical save/confirm logic.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from db.crud import (
    confirm_pending_record,
    save_record,
)
from db.crud.pending import force_confirm_pending_record
from db.engine import AsyncSessionLocal
from services.notify.tasks import create_follow_up_task
from services.observability.audit import audit
from utils.log import log, safe_create_task


# ── Background helpers (channel-agnostic, imported from source packages) ─────

_CVD_KEYWORDS = frozenset({
    "动脉瘤", "蛛网膜下腔", "脑出血", "颅内出血", "ICH", "SAH",
    "Hunt", "Fisher", "AVM", "动静脉畸形", "Spetzler", "开颅",
    "夹闭", "栓塞", "介入", "GCS", "格拉斯哥",
})


def _detect_cvd_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in _CVD_KEYWORDS)


async def _bg_extract_cvd_context(
    doctor_id: str, record_id: int, patient_id: Optional[int], content: str,
) -> None:
    try:
        from services.ai.neuro_structuring import extract_neuro_case
        from db.crud.specialty import save_cvd_context
        _, __, cvd_ctx = await extract_neuro_case(content)
        if cvd_ctx and cvd_ctx.has_data():
            async with AsyncSessionLocal() as session:
                await save_cvd_context(
                    session, doctor_id, patient_id, record_id, cvd_ctx, source="chat"
                )
            log(f"[CVD] context saved for record={record_id}")
    except Exception as exc:
        log(f"[CVD] extraction failed (non-fatal) record={record_id}: {exc}")


async def _bg_create_follow_up(
    doctor_id: str, record_id: int, patient_name: str,
    follow_up_plan: str, patient_id: Optional[int],
) -> None:
    """Create a follow-up task with dedup — skip if one already exists for this record."""
    try:
        from db.models import DoctorTask
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(DoctorTask).where(
                    DoctorTask.doctor_id == doctor_id,
                    DoctorTask.record_id == record_id,
                    DoctorTask.task_type == "follow_up",
                    DoctorTask.status == "pending",
                )
            )
            if existing.scalar_one_or_none() is not None:
                log(f"[FollowUp] dedup: follow_up task already exists for record={record_id}")
                return
        await create_follow_up_task(
            doctor_id, record_id, patient_name, follow_up_plan, patient_id,
        )
    except Exception as exc:
        log(f"[FollowUp] failed to create follow-up task record={record_id}: {exc}")


async def _bg_auto_tasks(
    doctor_id: str, record_id: int, patient_name: str,
    patient_id: Optional[int], content: str,
) -> None:
    from services.notify.task_rules import detect_auto_tasks, refine_due_days
    from services.notify.tasks import create_task as _create_task
    from db.models import DoctorTask
    from sqlalchemy import select
    from datetime import timedelta, timezone

    specs = detect_auto_tasks(content, patient_name)
    for spec in specs:
        try:
            # Dedup: skip if a pending task of the same type already exists for this record
            async with AsyncSessionLocal() as session:
                existing = await session.execute(
                    select(DoctorTask).where(
                        DoctorTask.doctor_id == doctor_id,
                        DoctorTask.record_id == record_id,
                        DoctorTask.task_type == spec.task_type,
                        DoctorTask.status == "pending",
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    log(f"[TaskRules] dedup: {spec.task_type} task already exists for record={record_id}")
                    continue

            due_days = refine_due_days(content, spec.due_days, anchor_keyword=spec.triggered_keyword)
            due_at = datetime.now(timezone.utc) + timedelta(days=due_days)
            async with AsyncSessionLocal() as session:
                await _create_task(
                    session,
                    doctor_id=doctor_id,
                    task_type=spec.task_type,
                    title=spec.title,
                    content=spec.content,
                    patient_id=patient_id,
                    record_id=record_id,
                    due_at=due_at,
                )
            log(f"[TaskRules] auto-created {spec.task_type} task for {patient_name} in {due_days}d")
        except Exception as exc:
            log(f"[TaskRules] failed to create {spec.task_type} task: {exc}")


async def _bg_auto_learn(doctor_id: str, raw_input: str, record: Any) -> None:
    from services.knowledge.doctor_knowledge import maybe_auto_learn_knowledge
    try:
        async with AsyncSessionLocal() as session:
            await maybe_auto_learn_knowledge(
                session, doctor_id, raw_input,
                structured_fields=record.model_dump(exclude_none=True),
            )
    except Exception as e:
        log(f"[bg] auto-learn FAILED doctor={doctor_id}: {e}")


# ── Core pending-record functions ───────────────────────────────────────────

async def _parse_pending_draft(pending: Any, doctor_id: str) -> Optional[tuple]:
    """解析草稿 JSON，返回 (record, cvd_raw) 或 None。"""
    from db.models.medical_record import MedicalRecord
    try:
        draft = json.loads(pending.draft_json)
        cvd_raw = draft.pop("cvd_context", None)
        record = MedicalRecord(**{k: draft.get(k) for k in MedicalRecord.model_fields})
        return record, cvd_raw
    except Exception as e:
        log(f"[PendingRecord] parse draft FAILED doctor={doctor_id} id={pending.id}: {e}")
        return None


async def _persist_pending_record(
    pending: Any, record: Any, cvd_raw: Any, doctor_id: str,
    *, force_confirm: bool = False,
) -> Optional[Any]:
    """将记录、分数、CVD上下文入库并确认草稿。返回 db_record 或 None。

    Uses a single commit at the end to reduce SQLite write-lock contention
    when multiple coroutines access the database concurrently.

    When *force_confirm* is True (used by the stale-draft auto-save scheduler),
    the pending row is marked 'confirmed' unconditionally — bypassing the
    ``expires_at > now`` guard that would otherwise silently skip already-expired
    drafts and leave them re-processable on the next scheduler tick.
    """
    from db.models.neuro_case import NeuroCVDSurgicalContext
    try:
        async with AsyncSessionLocal() as session:
            # Claim-first: atomically transition the pending row from 'awaiting'
            # BEFORE writing the medical record.  This prevents two concurrent
            # confirms from both persisting data — the loser's claim returns
            # False and the transaction is rolled back.
            if force_confirm:
                claimed = await force_confirm_pending_record(
                    session, pending.id, doctor_id=doctor_id, commit=False,
                )
                if not claimed:
                    log(f"[PendingRecord] force-claim FAILED (already confirmed) doctor={doctor_id} id={pending.id}")
                    await session.rollback()
                    return None
            else:
                claimed = await confirm_pending_record(
                    session, pending.id, doctor_id=doctor_id, commit=False,
                )
                if not claimed:
                    log(f"[PendingRecord] claim FAILED (already confirmed/expired) doctor={doctor_id} id={pending.id}")
                    await session.rollback()
                    return None

            db_record = await save_record(session, doctor_id, record, pending.patient_id, commit=False)
            if record.specialty_scores:
                from db.crud.scores import save_specialty_scores
                await save_specialty_scores(session, db_record.id, doctor_id, record.specialty_scores)
            if cvd_raw:
                try:
                    from db.crud.specialty import save_cvd_context
                    cvd_ctx = NeuroCVDSurgicalContext.model_validate(cvd_raw)
                    if cvd_ctx.has_data():
                        await save_cvd_context(
                            session, doctor_id, pending.patient_id, db_record.id, cvd_ctx,
                            source="chat", commit=False,
                        )
                        log(f"[CVD] context saved inline for record={db_record.id}")
                except Exception as exc:
                    log(f"[CVD] inline save failed (non-fatal): {exc}")
            await session.commit()
        return db_record
    except Exception as e:
        log(f"[PendingRecord] save FAILED doctor={doctor_id} id={pending.id}: {e}")
        return None


def _fire_post_save_tasks(
    doctor_id: str, record: Any, record_id: int,
    patient_name: str, pending: Any, cvd_raw: Any,
) -> None:
    """将保存后的后台任务（审计、随访、自学习等）全部触发。"""
    safe_create_task(audit(doctor_id, "WRITE", resource_type="record", resource_id=str(record_id)))
    # Follow-up task: save_record already creates one (with dedup) when
    # AUTO_FOLLOWUP_TASKS_ENABLED=true.  Only create here if that flag is off.
    import os
    _auto_followup = os.getenv("AUTO_FOLLOWUP_TASKS_ENABLED", "").lower() in ("1", "true", "yes")
    if not _auto_followup:
        _follow_up_words = ("随访", "复诊", "复查")
        # Prefer a specific tag; fall back to a 200-char snippet from content
        _follow_up_hint = next(
            (t for t in (record.tags or []) if any(word in t for word in _follow_up_words)), None
        )
        if not _follow_up_hint:
            _content = record.content or ""
            if any(word in _content for word in _follow_up_words):
                _follow_up_hint = _content[:200]
        if _follow_up_hint:
            safe_create_task(_bg_create_follow_up(
                doctor_id, record_id, patient_name, _follow_up_hint, pending.patient_id
            ))
    content = record.content or ""
    if content:
        safe_create_task(_bg_auto_tasks(
            doctor_id, record_id, patient_name, pending.patient_id, content
        ))
    learn_text = record.content or ""
    safe_create_task(_bg_auto_learn(doctor_id, learn_text, record))
    if not cvd_raw and _detect_cvd_keywords(learn_text):
        safe_create_task(_bg_extract_cvd_context(
            doctor_id, record_id, pending.patient_id, record.content or ""
        ))


async def try_draft_correction(
    text: str, doctor_id: str, pending: Any,
) -> Optional[tuple]:
    """If *text* matches a correction pattern, edit the pending draft in-place.

    Returns ``(reply_text, updated_draft_dict)`` on success, ``None`` otherwise.
    Channel adapters convert this into their wire format.
    """
    from services.domain.chat_constants import DRAFT_CORRECTION_RE

    if not DRAFT_CORRECTION_RE.search(text):
        return None

    import json as _json
    try:
        draft = _json.loads(pending.draft_json or "{}")
    except Exception:
        return None

    old_content = draft.get("content", "")
    if not old_content:
        return None

    from services.domain.intent_handlers._simple_intents import _merge_structured_into_content

    try:
        from services.ai.agent import dispatch as agent_dispatch
        llm_result = await agent_dispatch(text)
        corrected = dict(llm_result.structured_fields or {})
    except Exception as e:
        log(f"[draft_correction] LLM failed doctor={doctor_id}: {e}")
        return None

    if not corrected:
        return None

    merged = _merge_structured_into_content(old_content, corrected)
    if merged is None:
        return None

    draft["content"] = merged
    new_json = _json.dumps(draft, ensure_ascii=False)

    from db.crud.pending import update_pending_draft

    # Use the runtime-configured draft TTL (same as _create_draft) instead of
    # the hardcoded 10-minute default in update_pending_draft.
    from utils.runtime_config import get_pending_record_ttl_minutes
    _draft_ttl = get_pending_record_ttl_minutes()

    async with AsyncSessionLocal() as db:
        await update_pending_draft(db, pending.id, doctor_id, new_json, ttl_minutes=_draft_ttl)

    _pname = pending.patient_name or "未关联患者"
    preview = merged[:100] + ("…" if len(merged) > 100 else "")
    log(f"[draft_correction] corrected doctor={doctor_id} patient={_pname} fields={list(corrected.keys())}")

    return (
        f"✏️ 已更正【{_pname}】的病历草稿：\n{preview}\n\n回复「确认」保存，「取消」放弃。",
        draft,
    )


async def save_pending_record(
    doctor_id: str, pending: Any, *, force_confirm: bool = False,
) -> Optional[tuple]:
    """解析 PendingRecord 并保存到 medical_records。

    成功返回 (patient_name, record_id)，失败返回 None。
    副作用：触发审计、随访任务和自学习后台任务。
    不更改会话状态——调用方负责清除 pending_record_id。

    When *force_confirm* is True the pending row is confirmed
    unconditionally (bypasses the ``expires_at > now`` guard).
    """
    parsed = await _parse_pending_draft(pending, doctor_id)
    if parsed is None:
        return None
    record, cvd_raw = parsed
    db_record = await _persist_pending_record(
        pending, record, cvd_raw, doctor_id, force_confirm=force_confirm,
    )
    if db_record is None:
        return None
    patient_name = pending.patient_name or "未关联患者"
    record_id = db_record.id
    _fire_post_save_tasks(doctor_id, record, record_id, patient_name, pending, cvd_raw)
    return patient_name, record_id
