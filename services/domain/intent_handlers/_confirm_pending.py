"""
Pending-record confirmation logic — shared by Web and WeChat channels.

Moved from services/wechat/wechat_domain.py to eliminate cross-channel
dependency and enable both channels to use identical save/confirm logic.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from db.crud import (
    confirm_pending_record,
    save_record,
)
from db.engine import AsyncSessionLocal
from services.notify.tasks import create_follow_up_task
from services.observability.audit import audit
from utils.log import log


# ── Background helpers (imported lazily or from wechat_bg) ──────────────────

def _detect_cvd_keywords(text: str) -> bool:
    from services.wechat.wechat_bg import detect_cvd_keywords
    return detect_cvd_keywords(text)


async def _bg_extract_cvd_context(
    doctor_id: str, record_id: int, patient_id: Optional[int], content: str,
) -> None:
    from services.wechat.wechat_bg import bg_extract_cvd_context
    await bg_extract_cvd_context(doctor_id, record_id, patient_id, content)


async def _bg_auto_tasks(
    doctor_id: str, record_id: int, patient_name: str,
    patient_id: Optional[int], content: str,
) -> None:
    from services.wechat.wechat_bg import bg_auto_tasks
    await bg_auto_tasks(doctor_id, record_id, patient_name, patient_id, content)


async def _bg_auto_learn(doctor_id: str, raw_input: str, record: Any) -> None:
    from services.wechat.wechat_bg import bg_auto_learn
    await bg_auto_learn(doctor_id, raw_input, record)


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
) -> Optional[Any]:
    """将记录、分数、CVD上下文入库并确认草稿。返回 db_record 或 None。

    Uses a single commit at the end to reduce SQLite write-lock contention
    when multiple coroutines access the database concurrently.
    """
    from db.models.neuro_case import NeuroCVDSurgicalContext
    try:
        async with AsyncSessionLocal() as session:
            db_record = await save_record(session, doctor_id, record, pending.patient_id)
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
            await confirm_pending_record(session, pending.id, doctor_id=doctor_id, commit=False)
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
    asyncio.create_task(audit(doctor_id, "WRITE", resource_type="record", resource_id=str(record_id)))
    _follow_up_words = ("随访", "复诊", "复查")
    _follow_up_hint = next(
        (t for t in (record.tags or []) if any(word in t for word in _follow_up_words)), None
    ) or (any(word in (record.content or "") for word in _follow_up_words) and record.content) or None
    if _follow_up_hint:
        asyncio.create_task(create_follow_up_task(
            doctor_id, record_id, patient_name, str(_follow_up_hint), pending.patient_id
        ))
    content = record.content or ""
    if content:
        asyncio.create_task(_bg_auto_tasks(
            doctor_id, record_id, patient_name, pending.patient_id, content
        ))
    raw_input = getattr(pending, "raw_input", None) or record.content or ""
    asyncio.create_task(_bg_auto_learn(doctor_id, raw_input, record))
    if not cvd_raw and _detect_cvd_keywords(raw_input):
        asyncio.create_task(_bg_extract_cvd_context(
            doctor_id, record_id, pending.patient_id, record.content or ""
        ))


async def save_pending_record(doctor_id: str, pending: Any) -> Optional[tuple]:
    """解析 PendingRecord 并保存到 medical_records。

    成功返回 (patient_name, record_id)，失败返回 None。
    副作用：触发审计、随访任务和自学习后台任务。
    不更改会话状态——调用方负责清除 pending_record_id。
    """
    parsed = await _parse_pending_draft(pending, doctor_id)
    if parsed is None:
        return None
    record, cvd_raw = parsed
    db_record = await _persist_pending_record(pending, record, cvd_raw, doctor_id)
    if db_record is None:
        return None
    patient_name = pending.patient_name or "未关联患者"
    record_id = db_record.id
    _fire_post_save_tasks(doctor_id, record, record_id, patient_name, pending, cvd_raw)
    return patient_name, record_id
