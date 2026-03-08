"""
运行时游标、令牌缓存、配置文档和调度器租约的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import RuntimeCursor, RuntimeToken, RuntimeConfig, SchedulerLease


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_runtime_cursor(
    session: AsyncSession,
    cursor_key: str,
) -> Optional[str]:
    result = await session.execute(
        select(RuntimeCursor).where(RuntimeCursor.cursor_key == cursor_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return row.cursor_value


async def upsert_runtime_cursor(
    session: AsyncSession,
    cursor_key: str,
    cursor_value: Optional[str],
) -> None:
    result = await session.execute(
        select(RuntimeCursor).where(RuntimeCursor.cursor_key == cursor_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeCursor(cursor_key=cursor_key)
        session.add(row)
    row.cursor_value = cursor_value
    row.updated_at = _utcnow()
    await session.commit()


async def get_runtime_token(
    session: AsyncSession,
    token_key: str,
) -> Optional[RuntimeToken]:
    result = await session.execute(
        select(RuntimeToken).where(RuntimeToken.token_key == token_key).limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_runtime_token(
    session: AsyncSession,
    token_key: str,
    token_value: Optional[str],
    expires_at: Optional[datetime],
) -> None:
    result = await session.execute(
        select(RuntimeToken).where(RuntimeToken.token_key == token_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeToken(token_key=token_key)
        session.add(row)
    row.token_value = token_value
    row.expires_at = expires_at
    row.updated_at = _utcnow()
    await session.commit()


async def get_runtime_config(
    session: AsyncSession,
    config_key: str,
) -> Optional[RuntimeConfig]:
    result = await session.execute(
        select(RuntimeConfig).where(RuntimeConfig.config_key == config_key).limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_runtime_config(
    session: AsyncSession,
    config_key: str,
    content_json: str,
) -> RuntimeConfig:
    result = await session.execute(
        select(RuntimeConfig).where(RuntimeConfig.config_key == config_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeConfig(config_key=config_key, content_json=content_json)
        session.add(row)
    else:
        row.content_json = content_json
        row.updated_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def try_acquire_scheduler_lease(
    session: AsyncSession,
    lease_key: str,
    owner_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> bool:
    """Attempt to acquire distributed lease for scheduler execution."""
    ttl_seconds = max(1, int(lease_ttl_seconds))
    lease_until = now + timedelta(seconds=ttl_seconds)

    existing = await session.execute(
        select(SchedulerLease).where(SchedulerLease.lease_key == lease_key).limit(1)
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(
            SchedulerLease(
                lease_key=lease_key,
                owner_id=owner_id,
                lease_until=lease_until,
                updated_at=now,
            )
        )
        await session.commit()
        return True

    can_take = (
        row.owner_id == owner_id
        or row.lease_until is None
        or row.lease_until <= now
    )
    if not can_take:
        return False

    row.owner_id = owner_id
    row.lease_until = lease_until
    row.updated_at = now
    await session.commit()
    return True


async def release_scheduler_lease(
    session: AsyncSession,
    lease_key: str,
    owner_id: str,
    now: datetime,
) -> None:
    row = (
        await session.execute(
            select(SchedulerLease).where(SchedulerLease.lease_key == lease_key).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if row.owner_id != owner_id:
        return
    row.lease_until = now
    row.updated_at = now
    await session.commit()
