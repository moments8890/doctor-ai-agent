"""
核心端到端冒烟测试共享 Fixtures。

Shared DB fixtures for core E2E smoke tests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401


@pytest_asyncio.fixture
async def session_factory():
    """In-memory SQLite engine + session factory, tables created fresh each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory):
    """Single open session for direct CRUD-style E2E setup."""
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def reset_doctor_sessions():
    """Clear in-memory rate-limit state between tests."""
    try:
        from infra.auth.rate_limit import clear_rate_limits_for_tests
        clear_rate_limits_for_tests()
    except Exception:
        pass
    yield
    try:
        from infra.auth.rate_limit import clear_rate_limits_for_tests
        clear_rate_limits_for_tests()
    except Exception:
        pass
