"""Shared fixtures for all test modules."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.engine import Base
import db.models  # noqa: F401 — register ORM models before create_all


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
    """Single open session for direct CRUD tests."""
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
def reset_doctor_sessions():
    """Clear in-memory doctor sessions and locks between tests."""
    import services.session as sess_mod
    for task in list(sess_mod._persist_tasks.values()):
        task.cancel()
    for task in list(sess_mod._persist_turn_tasks.values()):
        task.cancel()
    sess_mod._sessions.clear()
    sess_mod._locks.clear()
    sess_mod._loaded_from_db.clear()
    sess_mod._persist_tasks.clear()
    sess_mod._persist_turn_tasks.clear()
    sess_mod._pending_turns.clear()
    try:
        import routers.records as records_mod
        records_mod._RATE_WINDOWS.clear()
    except Exception:
        pass
    yield
    for task in list(sess_mod._persist_tasks.values()):
        task.cancel()
    for task in list(sess_mod._persist_turn_tasks.values()):
        task.cancel()
    sess_mod._sessions.clear()
    sess_mod._locks.clear()
    sess_mod._loaded_from_db.clear()
    sess_mod._persist_tasks.clear()
    sess_mod._persist_turn_tasks.clear()
    sess_mod._pending_turns.clear()
    try:
        import routers.records as records_mod
        records_mod._RATE_WINDOWS.clear()
    except Exception:
        pass
