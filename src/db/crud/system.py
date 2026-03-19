"""
系统提示词的查询与版本管理的数据库操作。
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import SystemPrompt, SystemPromptVersion
from db.crud._common import _utcnow


async def get_system_prompt(session: AsyncSession, key: str) -> SystemPrompt | None:
    result = await session.execute(
        select(SystemPrompt).where(SystemPrompt.key == key)
    )
    return result.scalar_one_or_none()


async def upsert_system_prompt(
    session: AsyncSession, key: str, content: str, changed_by: Optional[str] = None
) -> None:
    row = await get_system_prompt(session, key)
    if row:
        # Archive current content before overwriting — enables rollback
        session.add(SystemPromptVersion(
            prompt_key=key,
            content=row.content,
            changed_by=changed_by,
        ))
        row.content = content
        row.updated_at = _utcnow()
    else:
        session.add(SystemPrompt(key=key, content=content))
    await session.commit()


async def list_system_prompt_versions(
    session: AsyncSession, key: str, limit: int = 20
) -> list[SystemPromptVersion]:
    """Return the version history for a prompt key, newest first."""
    result = await session.execute(
        select(SystemPromptVersion)
        .where(SystemPromptVersion.prompt_key == key)
        .order_by(SystemPromptVersion.changed_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def rollback_system_prompt(
    session: AsyncSession, key: str, version_id: int, changed_by: Optional[str] = None
) -> SystemPrompt | None:
    """Restore a system prompt to the content of a specific version entry."""
    ver_result = await session.execute(
        select(SystemPromptVersion).where(SystemPromptVersion.id == version_id)
    )
    version = ver_result.scalar_one_or_none()
    if version is None or version.prompt_key != key:
        return None
    await upsert_system_prompt(session, key, version.content, changed_by=changed_by)
    return await get_system_prompt(session, key)
