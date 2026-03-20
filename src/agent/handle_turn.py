"""Entry point for the ReAct agent pipeline."""
from __future__ import annotations

import re
from typing import Optional

from messages import M
from agent.identity import set_current_identity
from agent.session import get_or_create_agent
from agent.archive import archive_turns
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
    from db.models.pending import PendingRecord
    from db.crud.pending import abandon_pending_record
    from domain.records.confirm_pending import save_pending_record
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingRecord).where(
                PendingRecord.doctor_id == identity,
                PendingRecord.status == "awaiting",
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


async def handle_turn(text: str, role: str, identity: str, *, action_hint=None) -> str:
    """One turn. Channels call this directly."""
    agent = await get_or_create_agent(identity, role)
    set_current_identity(identity)

    # Fast path (0 LLM) — doctor only; patients always go through agent
    fast = await _try_fast_path(text, identity) if role == "doctor" else None
    if fast:
        agent._add_turn(text, fast)
        try:
            await archive_turns(identity, text, fast)
        except Exception as exc:
            log(f"[handle_turn] archive failed: {exc}", level="error")
        return fast

    # LangChain agent (1-4 LLM calls)
    try:
        reply = await agent.handle(text)
    except Exception as exc:
        log(f"[handle_turn] agent error: {exc}", level="error")
        reply = M.service_unavailable

    try:
        await archive_turns(identity, text, reply)
    except Exception as exc:
        log(f"[handle_turn] archive failed: {exc}", level="error")

    return reply
