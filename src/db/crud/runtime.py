"""
运行时游标和令牌缓存的数据库操作。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import RuntimeToken
from db.crud._common import _utcnow


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
