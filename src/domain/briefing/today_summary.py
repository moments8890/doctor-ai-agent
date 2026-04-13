"""Today Summary — LLM-generated daily briefing for the doctor.

Architecture: fact pack (SQL) → prompt composer → LLM → validated response.
Cached in runtime_tokens for 30 minutes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB
from db.models.tasks import DoctorTask, TaskStatus
from utils.log import log


# ── Response models ───────────────────────────────────────────────────


class TodaySummaryAction(BaseModel):
    type: Literal["open_patient", "open_task", "open_review", "open_knowledge"]
    label: str
    patient_id: Optional[int] = None
    task_id: Optional[int] = None
    record_id: Optional[int] = None
    knowledge_id: Optional[int] = None


class TodaySummaryItem(BaseModel):
    id: str
    kind: Literal["followup_due", "message_knowledge_match", "knowledge_gap"]
    priority: Literal["high", "medium", "low"]
    title: str
    detail: str
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    task_id: Optional[int] = None
    record_id: Optional[int] = None
    knowledge_ids: List[int] = Field(default_factory=list)
    fact_ids: List[str] = Field(default_factory=list)
    actions: List[TodaySummaryAction] = Field(default_factory=list)


class TodaySummaryResponse(BaseModel):
    section_title: str = "今日摘要"
    mode: Literal["llm", "fallback", "empty"]
    summary: str
    items: List[TodaySummaryItem] = Field(default_factory=list)
    generated_at: str
    expires_at: str
    cache_hit: bool = False
    empty_reason: Optional[Literal["no_data", "no_knowledge", "quiet_day"]] = None


# ── LLM response model (what the LLM returns) ────────────────────────


class LLMSummaryItem(BaseModel):
    kind: str
    priority: str = "medium"
    title: str
    detail: str
    fact_ids: List[str] = Field(default_factory=list)
    knowledge_ids: List[int] = Field(default_factory=list)


class LLMSummaryResponse(BaseModel):
    summary: str
    items: List[LLMSummaryItem] = Field(default_factory=list)


# ── Fact pack ─────────────────────────────────────────────────────────


async def build_fact_pack(
    session: AsyncSession,
    *,
    doctor_id: str,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Query DB and build a list of structured facts for the LLM."""
    if now is None:
        now = datetime.now(timezone.utc)

    facts: list[dict] = []

    # 1. Due/overdue tasks [-7d, +2d] with patient info
    task_window_start = now - timedelta(days=7)
    task_window_end = now + timedelta(days=2)
    task_stmt = (
        select(DoctorTask, Patient.name)
        .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
        .where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.status.in_([TaskStatus.pending, TaskStatus.notified]),
            DoctorTask.due_at.isnot(None),
            DoctorTask.due_at >= task_window_start,
            DoctorTask.due_at <= task_window_end,
        )
        .order_by(DoctorTask.due_at.asc())
        .limit(10)
    )
    task_rows = (await session.execute(task_stmt)).all()
    for task, patient_name in task_rows:
        facts.append({
            "id": f"task_{task.id}",
            "type": "task",
            "patient_name": patient_name or "未知",
            "patient_id": task.patient_id,
            "title": task.title or task.task_type,
            "task_type": task.task_type,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "record_id": task.record_id,
        })

    # 2. Recent inbound patient messages (72h, unhandled or escalated)
    msg_cutoff = now - timedelta(hours=72)
    msg_stmt = (
        select(PatientMessage, Patient.name)
        .outerjoin(Patient, PatientMessage.patient_id == Patient.id)
        .where(
            PatientMessage.doctor_id == doctor_id,
            PatientMessage.direction == "inbound",
            PatientMessage.created_at >= msg_cutoff,
        )
        .order_by(PatientMessage.created_at.desc())
        .limit(10)
    )
    msg_rows = (await session.execute(msg_stmt)).all()
    for msg, patient_name in msg_rows:
        facts.append({
            "id": f"msg_{msg.id}",
            "type": "message",
            "patient_name": patient_name or "未知",
            "patient_id": msg.patient_id,
            "content": (msg.content or "")[:200],
            "triage": msg.triage_category or "",
            "direction": msg.direction,
            "ai_handled": getattr(msg, "ai_handled", None),
        })

    # 3. Recent medical records (7d)
    record_cutoff = now - timedelta(days=7)
    record_stmt = (
        select(MedicalRecordDB, Patient.name)
        .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        .where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.created_at >= record_cutoff,
        )
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(15)
    )
    record_rows = (await session.execute(record_stmt)).all()
    for rec, patient_name in record_rows:
        facts.append({
            "id": f"record_{rec.id}",
            "type": "record",
            "patient_name": patient_name or "未知",
            "patient_id": rec.patient_id,
            "chief_complaint": rec.chief_complaint or "",
            "diagnosis": rec.diagnosis or "",
            "tags": rec.tags or "",
            "status": rec.status or "",
            "created_at": rec.created_at.isoformat() if rec.created_at else "",
        })

    return facts


# ── Cache helpers ─────────────────────────────────────────────────────

CACHE_TTL_MINUTES = 30
CACHE_KEY_PREFIX = "today_summary"


def _cache_key(doctor_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{CACHE_KEY_PREFIX}:{doctor_id}:{today}"


async def _get_cached(session: AsyncSession, doctor_id: str) -> Optional[TodaySummaryResponse]:
    from db.crud.runtime import get_runtime_token
    row = await get_runtime_token(session, _cache_key(doctor_id))
    if not row or not row.token_value:
        return None
    expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at and row.expires_at.tzinfo is None else row.expires_at
    if expires and expires < datetime.now(timezone.utc):
        return None
    try:
        data = json.loads(row.token_value)
        resp = TodaySummaryResponse(**data)
        resp.cache_hit = True
        return resp
    except Exception:
        return None


async def _set_cached(session: AsyncSession, doctor_id: str, response: TodaySummaryResponse) -> None:
    from db.crud.runtime import upsert_runtime_token
    expires = datetime.now(timezone.utc) + timedelta(minutes=CACHE_TTL_MINUTES)
    await upsert_runtime_token(
        session,
        _cache_key(doctor_id),
        json.dumps(response.model_dump(), ensure_ascii=False),
        expires,
    )


# ── Main entry point ─────────────────────────────────────────────────


async def get_today_summary(
    session: AsyncSession,
    *,
    doctor_id: str,
    refresh: bool = False,
) -> TodaySummaryResponse:
    """Generate or return cached today summary."""
    now = datetime.now(timezone.utc)

    # Check cache (skip if refresh requested)
    if not refresh:
        cached = await _get_cached(session, doctor_id)
        if cached:
            log(f"[today_summary] cache hit for {doctor_id}")
            return cached

    # Build fact pack
    facts = await build_fact_pack(session, doctor_id=doctor_id, now=now)

    # Check for empty states (no LLM call needed)
    if not facts:
        # Check if doctor has any knowledge
        from db.crud.knowledge import get_knowledge_items
        kb = await get_knowledge_items(session, doctor_id)
        kb_count = len(kb) if kb else 0

        # Check if doctor has any patients
        patient_count = (await session.execute(
            select(func.count()).select_from(Patient).where(Patient.doctor_id == doctor_id)
        )).scalar_one()

        if patient_count == 0 and kb_count == 0:
            reason = "no_data"
            summary = "添加患者和知识后，这里会显示今日工作摘要"
        elif kb_count == 0:
            reason = "no_knowledge"
            summary = "添加知识规则后，AI 能为你发现更多关联"
        else:
            reason = "quiet_day"
            summary = "今日暂无需要特别关注的事项"

        resp = TodaySummaryResponse(
            mode="empty",
            summary=summary,
            generated_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=CACHE_TTL_MINUTES)).isoformat(),
            empty_reason=reason,
        )
        await _set_cached(session, doctor_id, resp)
        return resp

    # Generate via LLM
    try:
        resp = await _generate_via_llm(doctor_id=doctor_id, facts=facts, now=now)
    except Exception as exc:
        log(f"[today_summary] LLM failed: {exc}", level="warning")
        resp = TodaySummaryResponse(
            mode="fallback",
            summary="摘要生成中，请稍后刷新",
            generated_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=5)).isoformat(),
        )

    await _set_cached(session, doctor_id, resp)
    return resp


async def _generate_via_llm(
    *,
    doctor_id: str,
    facts: list[dict],
    now: datetime,
) -> TodaySummaryResponse:
    """Call LLM with fact pack and return validated response."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_daily_summary

    facts_json = json.dumps(facts, ensure_ascii=False, default=str)

    messages = await compose_for_daily_summary(
        doctor_id=doctor_id,
        doctor_message=f"<today_facts>\n{facts_json}\n</today_facts>",
    )

    llm_result = await structured_call(
        response_model=LLMSummaryResponse,
        messages=messages,
        op_name="daily_summary.generate",
        env_var="DAILY_SUMMARY_LLM",
        temperature=0.2,
        max_tokens=1024,
    )

    # Validate fact_ids — drop items that reference non-existent facts
    valid_fact_ids = {f["id"] for f in facts}
    validated_items: list[TodaySummaryItem] = []
    for i, item in enumerate(llm_result.items[:3]):
        # Check that at least one fact_id is valid
        item_fact_ids = [fid for fid in item.fact_ids if fid in valid_fact_ids]
        if not item_fact_ids and item.kind != "knowledge_gap":
            log(f"[today_summary] dropping item {i}: no valid fact_ids")
            continue

        # Look up patient info from facts
        patient_id = None
        patient_name = None
        task_id = None
        record_id = None
        for fid in item_fact_ids:
            fact = next((f for f in facts if f["id"] == fid), None)
            if fact:
                if not patient_id and fact.get("patient_id"):
                    patient_id = fact["patient_id"]
                    patient_name = fact.get("patient_name")
                if not task_id and fact.get("id", "").startswith("task_"):
                    task_id = int(fact["id"].split("_", 1)[1])
                if not record_id and fact.get("record_id"):
                    record_id = fact["record_id"]

        validated_items.append(TodaySummaryItem(
            id=f"summary_{i}",
            kind=item.kind if item.kind in ("followup_due", "message_knowledge_match", "knowledge_gap") else "followup_due",
            priority=item.priority if item.priority in ("high", "medium", "low") else "medium",
            title=item.title,
            detail=item.detail,
            patient_id=patient_id,
            patient_name=patient_name,
            task_id=task_id,
            record_id=record_id,
            knowledge_ids=item.knowledge_ids,
            fact_ids=item_fact_ids,
        ))

    # Strip [KB-N] citations from user-facing summary text
    clean_summary = re.sub(r"\s*\[KB-\d+\]", "", llm_result.summary)

    expires = now + timedelta(minutes=CACHE_TTL_MINUTES)
    return TodaySummaryResponse(
        mode="llm",
        summary=clean_summary,
        items=validated_items,
        generated_at=now.isoformat(),
        expires_at=expires.isoformat(),
    )
