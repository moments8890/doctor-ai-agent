"""Shared helpers for pending-item routing (persona + kb tracks)."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Callable, Type

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import Base
from utils.log import log


# PII patterns — applied to proposed_rule, summary, evidence_summary
_PII_PATTERNS = [
    (re.compile(r"(?:姓名|名字)[：:]\s*[\u4e00-\u9fa5A-Za-z]{1,6}"), "[已脱敏]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[已脱敏]"),                 # mobile
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[已脱敏]"),               # ID card
    (re.compile(r"(?:住院号|病历号)[：:]*\s*\d{4,}"), "[已脱敏]"),
    (re.compile(r"(?<!\d)\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?(?!\d)"), "[已脱敏]"),  # date
]


def scrub_pii(text: str) -> str:
    """Replace recognised PII patterns with `[已脱敏]`. Returns cleaned text."""
    if not text:
        return text
    cleaned = text
    for pat, repl in _PII_PATTERNS:
        cleaned = pat.sub(repl, cleaned)
    return cleaned


async def is_pattern_suppressed(
    session: AsyncSession,
    table_cls: Type[Base],
    doctor_id: str,
    pattern: str,
    window_days: int = 90,
) -> bool:
    """True if a matching rejected pending row exists within the suppression window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    count = (await session.execute(
        select(func.count()).select_from(table_cls).where(
            table_cls.doctor_id == doctor_id,
            table_cls.pattern_hash == pattern,
            table_cls.status == "rejected",
            table_cls.updated_at > cutoff,
        )
    )).scalar() or 0
    return count > 0


async def savepoint_insert_pending(
    session: AsyncSession,
    table_cls: Type[Base],
    doctor_id: str,
    pattern: str,
    row_factory: Callable,
) -> object | None:
    """Insert a pending row inside a savepoint. On duplicate or race, returns None.

    `row_factory` is a zero-arg callable returning a new ORM instance to add.
    """
    try:
        async with session.begin_nested():  # SAVEPOINT
            stmt = select(table_cls).where(
                table_cls.doctor_id == doctor_id,
                table_cls.pattern_hash == pattern,
                table_cls.status == "pending",
            ).with_for_update()   # no-op on SQLite; row lock on MySQL
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                log(f"[pending_common] duplicate pending pattern={pattern}, skipping")
                return None
            row = row_factory()
            session.add(row)
            await session.flush()
            return row
    except IntegrityError:
        log(f"[pending_common] unique-constraint race on pattern={pattern}, skipping")
        return None
