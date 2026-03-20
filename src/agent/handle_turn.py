"""Entry point for the ReAct agent pipeline."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from messages import M
from agent.identity import set_current_identity
from agent.session import get_or_create_agent
from agent.archive import archive_turns
from agent.actions import Action
from db.models.tasks import TaskStatus
from infra.auth import UserRole
from agent.tools.doctor import _fetch_tasks, _fetch_patients, _fetch_recent_records
from agent.tools.diagnosis import _build_case_context
from utils.log import log

# Fast-path patterns
_GREETING_RE = re.compile(
    r"^(你好|您好|hi|hello|hey|嗨|早上好|下午好|晚上好)\s*[。！.!?]*$",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(
    r"^(确认|确定|保存|是的?|对|好的?|ok|yes|save|confirm)\s*[。？！.?!]*$",
    re.IGNORECASE,
)
_ABANDON_RE = re.compile(
    r"^(取消|放弃|不要|不保存|不了|算了|cancel|abandon|discard|no)\s*[。？！.?!]*$",
    re.IGNORECASE,
)


async def _try_fast_path(text: str, identity: str) -> Optional[str]:
    """Check deterministic fast paths. Returns reply or None."""
    if _GREETING_RE.match(text):
        return M.greeting

    # Pending record confirm/abandon — query DB directly
    from db.engine import AsyncSessionLocal
    from db.models.pending import PendingRecord, PendingRecordStatus
    from db.crud.pending import abandon_pending_record
    from domain.records.confirm_pending import save_pending_record
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingRecord).where(
                PendingRecord.doctor_id == identity,
                PendingRecord.status == PendingRecordStatus.awaiting,
            ).order_by(PendingRecord.created_at.desc()).limit(1)
        )
        pending = result.scalar_one_or_none()
        if pending:
            if _CONFIRM_RE.match(text):
                saved = await save_pending_record(identity, pending)
                if saved:
                    return "已保存"
                return "保存失败，草稿可能已过期，请重新创建"
            if _ABANDON_RE.match(text):
                await abandon_pending_record(session, pending.id, identity)
                return "已取消"

    return None


_QUERY_LABEL = re.compile(r"^查询患者[：:]?\s*$")


def _format_patient_list(patients: list) -> str:
    if not patients:
        return "暂无患者记录。"
    lines = [f"共{len(patients)}位患者："]
    for i, p in enumerate(patients, 1):
        parts = [p["name"]]
        if p.get("gender"):
            parts.append(p["gender"])
        if p.get("year_of_birth"):
            age = datetime.now().year - p["year_of_birth"]
            parts.append(f"{age}岁")
        lines.append(f"{i}. {'，'.join(parts)}")
    return "\n".join(lines)


def _format_daily_summary(tasks: list, records: list) -> str:
    lines = ["**今日工作摘要**", ""]
    if tasks:
        pending = [t for t in tasks if t.get("status") == TaskStatus.pending]
        done = [t for t in tasks if t.get("status") == TaskStatus.completed]
        lines.append(f"**待处理任务** ({len(pending)})")
        for t in pending:
            lines.append(f"- {t.get('title', '未命名')}")
        if done:
            lines.append(f"\n**已完成** ({len(done)})")
            for t in done:
                lines.append(f"- ~~{t.get('title', '未命名')}~~")
    else:
        lines.append("今日暂无任务。")
    lines.append("")
    if records:
        lines.append(f"**最近病历** ({len(records)}条)")
        for r in records:
            date = (r.get("created_at") or "")[:10]
            content_preview = (r.get("content") or "")[:40]
            lines.append(f"- {date} {content_preview}")
    else:
        lines.append("暂无近期病历。")
    return "\n".join(lines)


async def _dispatch_action_hint(
    action: Action, text: str, identity: str, agent,
) -> Optional[str]:
    """Fast path for known intents. Returns reply str or None to fall through."""

    if action == Action.query_patient:
        patients = await _fetch_patients(identity)
        search = text.strip()
        if _QUERY_LABEL.match(search) or not search:
            return _format_patient_list(patients)
        filtered = [p for p in patients if search in p.get("name", "")]
        return _format_patient_list(filtered)

    if action == Action.daily_summary:
        tasks = await _fetch_tasks(identity)
        records = await _fetch_recent_records(identity, limit=10)
        return _format_daily_summary(tasks, records)

    if action == Action.create_record:
        if agent is None:
            return None
        return await agent.handle(text)

    if action == Action.diagnosis:
        log(f"[dispatch] diagnosis action triggered for {identity}")
        from agent.tools.diagnosis import diagnose as _diagnose_tool
        from agent.identity import set_current_identity
        set_current_identity(identity)
        try:
            result = await _diagnose_tool.ainvoke({})
            log(f"[dispatch] diagnosis result length: {len(result) if result else 0}")
            return result
        except Exception as e:
            log(f"[dispatch] diagnosis failed: {e}", level="error")
            import traceback
            traceback.print_exc()
            return None

    # Unknown or future actions → fall through
    return None


async def _get_active_chief_complaint(doctor_id: str) -> Optional[str]:
    """Return the chief_complaint from the most recent medical record, or None."""
    try:
        from db.engine import AsyncSessionLocal
        from db.models import MedicalRecordDB
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MedicalRecordDB.structured)
                .where(
                    MedicalRecordDB.doctor_id == doctor_id,
                    MedicalRecordDB.structured.isnot(None),
                )
                .order_by(MedicalRecordDB.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()

        if not row:
            return None
        structured = json.loads(row) if isinstance(row, str) else row
        return structured.get("chief_complaint") or None
    except Exception as exc:
        log(f"[handle_turn] chief_complaint lookup failed: {exc}", level="warning")
        return None


async def handle_turn(text: str, role: str, identity: str, *, action_hint=None) -> str:
    """One turn. Channels call this directly."""
    agent = await get_or_create_agent(identity, role)
    set_current_identity(identity)

    # Fast path (0 LLM) — doctor only; patients always go through agent
    fast = await _try_fast_path(text, identity) if role == UserRole.doctor else None
    if fast:
        agent._add_turn(text, fast)
        try:
            await archive_turns(identity, text, fast)
        except Exception as exc:
            log(f"[handle_turn] archive failed: {exc}", level="error")
        return fast

    # Action hint fast paths
    if action_hint:
        try:
            reply = await _dispatch_action_hint(action_hint, text, identity, agent)
        except Exception as exc:
            log(f"[handle_turn] action_hint={action_hint} error: {exc}", level="error")
            reply = None
        if reply:
            agent._add_turn(text, reply)
            try:
                await archive_turns(identity, text, reply)
            except Exception as exc:
                log(f"[handle_turn] archive failed: {exc}", level="error")
            return reply

    # LangChain agent (1-4 LLM calls)
    # Inject case context for doctor role (non-disruptive: only enriches the
    # text sent to the agent; archiving still uses the original user text).
    agent_text = text
    if role == UserRole.doctor:
        try:
            chief_complaint = await _get_active_chief_complaint(identity)
            if chief_complaint:
                case_ctx = await _build_case_context(identity, chief_complaint)
                if case_ctx:
                    agent_text = f"{case_ctx}\n\n{text}"
        except Exception as exc:
            log(f"[handle_turn] case_context injection failed: {exc}", level="warning")

    try:
        reply = await agent.handle(agent_text)
    except Exception as exc:
        log(f"[handle_turn] agent error: {exc}", level="error")
        reply = M.service_unavailable

    try:
        await archive_turns(identity, text, reply)
    except Exception as exc:
        log(f"[handle_turn] archive failed: {exc}", level="error")

    return reply
