"""
医生账户、会话状态、知识库条目和对话历史的数据库操作。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from db.models import (
    Doctor,
    DoctorContext,
    DoctorKnowledgeItem,
    DoctorNotifyPreference,
    ChatArchive,
)
from utils.hashing import hash_wechat_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_WECHAT_ID_RE = re.compile(r"^(?:wm|wx|ww|wo)[A-Za-z0-9_-]{6,}$")


def _is_wechat_identifier(raw: str) -> bool:
    value = (raw or "").strip()
    return bool(_WECHAT_ID_RE.match(value))


def _infer_channel(doctor_id: str) -> str:
    return "wechat" if _is_wechat_identifier(doctor_id) else "app"


async def _lookup_doctor_by_wechat_id(
    session: AsyncSession, stored_wechat_id: str
) -> Optional[Doctor]:
    """按哈希后的微信 ID 查询医生记录。"""
    return (
        await session.execute(
            select(Doctor)
            .where(Doctor.channel == "wechat", Doctor.wechat_user_id == stored_wechat_id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _resolve_doctor_id(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    """将传入标识符解析为规范 doctor_id，并保持 doctors 注册表最新。"""
    incoming = (doctor_id or "").strip()
    if not incoming:
        return doctor_id

    now = _utcnow()
    channel = _infer_channel(incoming)
    wechat_user_id = incoming if channel == "wechat" else None
    stored_wechat_id = hash_wechat_id(wechat_user_id)

    existing_by_id = (
        await session.execute(select(Doctor).where(Doctor.doctor_id == incoming).limit(1))
    ).scalar_one_or_none()
    if existing_by_id is not None:
        existing_by_id.updated_at = now
        if name and not existing_by_id.name:
            existing_by_id.name = name
        if existing_by_id.channel != channel and existing_by_id.channel == "app":
            existing_by_id.channel = channel
        if stored_wechat_id and not existing_by_id.wechat_user_id:
            existing_by_id.wechat_user_id = stored_wechat_id
        return existing_by_id.doctor_id

    if stored_wechat_id:
        existing_by_wechat = await _lookup_doctor_by_wechat_id(session, stored_wechat_id)
        if existing_by_wechat is not None:
            existing_by_wechat.updated_at = now
            if name and not existing_by_wechat.name:
                existing_by_wechat.name = name
            return existing_by_wechat.doctor_id

    try:
        async with session.begin_nested():
            session.add(Doctor(
                doctor_id=incoming, name=name, channel=channel,
                wechat_user_id=stored_wechat_id, created_at=now, updated_at=now,
            ))
        return incoming
    except IntegrityError:
        if stored_wechat_id:
            row = await _lookup_doctor_by_wechat_id(session, stored_wechat_id)
            if row is not None:
                return row.doctor_id
        raise


async def _ensure_doctor_exists(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    return await _resolve_doctor_id(session, doctor_id, name=name)


async def get_doctor_by_id(session: AsyncSession, doctor_id: str) -> Optional[Doctor]:
    result = await session.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_doctor_wechat_user_id(session: AsyncSession, doctor_id: str) -> Optional[str]:
    row = await get_doctor_by_id(session, doctor_id)
    if row is None or not row.wechat_user_id:
        return None
    return str(row.wechat_user_id).strip() or None


async def get_doctor_context(session: AsyncSession, doctor_id: str) -> DoctorContext | None:
    result = await session.execute(
        select(DoctorContext).where(DoctorContext.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def upsert_doctor_context(
    session: AsyncSession, doctor_id: str, summary: str, *, commit: bool = True,
) -> None:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    ctx = await get_doctor_context(session, doctor_id)
    if ctx:
        ctx.summary = summary
        ctx.updated_at = _utcnow()
    else:
        try:
            session.add(DoctorContext(doctor_id=doctor_id, summary=summary))
            await session.flush()
        except Exception:
            # Concurrent insert race — row appeared between our check and insert.
            await session.rollback()
            ctx = await get_doctor_context(session, doctor_id)
            if ctx:
                ctx.summary = summary
                ctx.updated_at = _utcnow()
    if commit:
        await session.commit()


async def add_doctor_knowledge_item(session: AsyncSession, doctor_id: str, content: str) -> DoctorKnowledgeItem:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    now = _utcnow()
    row = DoctorKnowledgeItem(
        doctor_id=doctor_id,
        content=content.strip(),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_doctor_knowledge_items(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 30,
) -> List[DoctorKnowledgeItem]:
    stmt = (
        select(DoctorKnowledgeItem)
        .where(DoctorKnowledgeItem.doctor_id == doctor_id)
        .order_by(DoctorKnowledgeItem.updated_at.desc(), DoctorKnowledgeItem.id.desc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_doctor_notify_preference(
    session: AsyncSession, doctor_id: str
) -> Optional[DoctorNotifyPreference]:
    result = await session.execute(
        select(DoctorNotifyPreference).where(DoctorNotifyPreference.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def upsert_doctor_notify_preference(
    session: AsyncSession,
    doctor_id: str,
    *,
    notify_mode: Optional[str] = None,
    schedule_type: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    cron_expr: Optional[str] = None,
    last_auto_run_at: Optional[datetime] = None,
) -> DoctorNotifyPreference:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = await get_doctor_notify_preference(session, doctor_id)
    if row is None:
        row = DoctorNotifyPreference(doctor_id=doctor_id)
        session.add(row)

    if notify_mode is not None:
        row.notify_mode = notify_mode
    if schedule_type is not None:
        row.schedule_type = schedule_type
    if interval_minutes is not None:
        row.interval_minutes = interval_minutes
    if cron_expr is not None or schedule_type == "cron":
        row.cron_expr = cron_expr
    if last_auto_run_at is not None:
        row.last_auto_run_at = last_auto_run_at
    row.updated_at = _utcnow()

    await session.commit()
    await session.refresh(row)
    return row


async def append_chat_archive(
    session: AsyncSession,
    doctor_id: str,
    turns: List[dict],
) -> None:
    """Append turns to the chat archive (retained for 365 days by default).

    Does NOT commit — the caller is responsible for committing the session
    so that conversation turns and archive can be written atomically.
    """
    if not turns:
        return
    now = _utcnow()
    for turn in turns:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        session.add(ChatArchive(doctor_id=doctor_id, role=role, content=content, created_at=now))


async def get_doctor_mini_openid(session: AsyncSession, doctor_id: str) -> Optional[str]:
    row = await get_doctor_by_id(session, doctor_id)
    if row is None or not row.mini_openid:
        return None
    return str(row.mini_openid).strip() or None


async def get_doctor_by_mini_openid(session: AsyncSession, openid: str) -> Optional[Doctor]:
    stored = hash_wechat_id(openid)
    result = await session.execute(
        select(Doctor).where(Doctor.mini_openid == stored).limit(1)
    )
    return result.scalar_one_or_none()


async def link_mini_openid(session: AsyncSession, doctor_id: str, openid: str) -> None:
    """Store a mini app openid on an existing doctor record (idempotent)."""
    stored = hash_wechat_id(openid)
    row = await get_doctor_by_id(session, doctor_id)
    if row is None:
        raise ValueError(f"Doctor {doctor_id!r} not found")
    if row.mini_openid and row.mini_openid != stored:
        raise ValueError(
            f"Doctor {doctor_id!r} already linked to a different mini openid"
        )
    row.mini_openid = stored
    row.updated_at = _utcnow()
    await session.commit()
