"""
医生账户、会话状态、知识库条目和对话历史的数据库操作。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from db.models import (
    Doctor,
    DoctorKnowledgeItem,
)
from db.crud._common import _utcnow


async def _resolve_doctor_id(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    """将传入标识符解析为规范 doctor_id，并保持 doctors 注册表最新。"""
    incoming = (doctor_id or "").strip()
    if not incoming:
        return doctor_id

    now = _utcnow()

    existing_by_id = (
        await session.execute(select(Doctor).where(Doctor.doctor_id == incoming).limit(1))
    ).scalar_one_or_none()
    if existing_by_id is not None:
        existing_by_id.updated_at = now
        if name and not existing_by_id.name:
            existing_by_id.name = name
        return existing_by_id.doctor_id

    try:
        async with session.begin_nested():
            session.add(Doctor(
                doctor_id=incoming, name=name, created_at=now, updated_at=now,
            ))
        return incoming
    except IntegrityError:
        raise


async def _ensure_doctor_exists(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    return await _resolve_doctor_id(session, doctor_id, name=name)


async def get_doctor_by_id(session: AsyncSession, doctor_id: str) -> Optional[Doctor]:
    result = await session.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_doctor_wechat_user_id(session: AsyncSession, doctor_id: str) -> Optional[str]:
    # TODO: migrate callers to query DoctorWechat table directly
    from db.models.doctor_wechat import DoctorWechat
    row = (
        await session.execute(
            select(DoctorWechat).where(DoctorWechat.doctor_id == doctor_id).limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.wechat_user_id:
        return None
    return str(row.wechat_user_id).strip() or None



async def add_doctor_knowledge_item(
    session: AsyncSession, doctor_id: str, content: str, category: str = "custom",
) -> DoctorKnowledgeItem:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    now = _utcnow()
    row = DoctorKnowledgeItem(
        doctor_id=doctor_id,
        content=content.strip(),
        category=category,
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
    categories: Optional[List[str]] = None,
) -> List[DoctorKnowledgeItem]:
    stmt = (
        select(DoctorKnowledgeItem)
        .where(DoctorKnowledgeItem.doctor_id == doctor_id)
    )
    if categories:
        stmt = stmt.where(DoctorKnowledgeItem.category.in_(categories))
    stmt = (
        stmt.order_by(DoctorKnowledgeItem.updated_at.desc(), DoctorKnowledgeItem.id.desc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def delete_knowledge_item(
    session: AsyncSession, doctor_id: str, item_id: int,
) -> bool:
    """Delete a knowledge item. Returns True if deleted, False if not found."""
    from sqlalchemy import delete as sa_delete
    result = await session.execute(
        sa_delete(DoctorKnowledgeItem).where(
            DoctorKnowledgeItem.id == item_id,
            DoctorKnowledgeItem.doctor_id == doctor_id,
        )
    )
    await session.commit()
    return result.rowcount > 0


async def get_doctor_mini_openid(session: AsyncSession, doctor_id: str) -> Optional[str]:
    # TODO: migrate callers to query DoctorWechat table directly
    from db.models.doctor_wechat import DoctorWechat
    row = (
        await session.execute(
            select(DoctorWechat).where(DoctorWechat.doctor_id == doctor_id).limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.mini_openid:
        return None
    return str(row.mini_openid).strip() or None


async def get_doctor_by_mini_openid(session: AsyncSession, openid: str) -> Optional[Doctor]:
    # TODO: migrate callers to use DoctorWechat table directly
    from db.models.doctor_wechat import DoctorWechat
    from utils.hashing import hash_wechat_id
    stored = hash_wechat_id(openid)
    wechat_row = (
        await session.execute(
            select(DoctorWechat).where(DoctorWechat.mini_openid == stored).limit(1)
        )
    ).scalar_one_or_none()
    if wechat_row is None:
        return None
    return await get_doctor_by_id(session, wechat_row.doctor_id)


async def link_mini_openid(session: AsyncSession, doctor_id: str, openid: str) -> None:
    """Store a mini app openid on the DoctorWechat record (idempotent)."""
    # TODO: migrate callers to use DoctorWechat table directly
    from db.models.doctor_wechat import DoctorWechat
    from utils.hashing import hash_wechat_id
    stored = hash_wechat_id(openid)
    doctor = await get_doctor_by_id(session, doctor_id)
    if doctor is None:
        raise ValueError(f"Doctor {doctor_id!r} not found")
    wechat_row = (
        await session.execute(
            select(DoctorWechat).where(DoctorWechat.doctor_id == doctor_id).limit(1)
        )
    ).scalar_one_or_none()
    if wechat_row is None:
        session.add(DoctorWechat(doctor_id=doctor_id, mini_openid=stored))
    else:
        if wechat_row.mini_openid and wechat_row.mini_openid != stored:
            raise ValueError(
                f"Doctor {doctor_id!r} already linked to a different mini openid"
            )
        wechat_row.mini_openid = stored
    doctor.updated_at = _utcnow()
    await session.commit()
