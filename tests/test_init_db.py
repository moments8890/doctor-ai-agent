from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import db.init_db as init_db


class _SyncResult:
    def __init__(self, cols):
        self._cols = cols

    def fetchall(self):
        return [(0, col) for col in self._cols]


class _SyncConn:
    def __init__(self, cols):
        self._cols = cols

    def execute(self, _stmt):
        return _SyncResult(self._cols)


class _AsyncConn:
    def __init__(self, cols):
        self.cols = cols
        self.executed_sql = []

    async def run_sync(self, fn):
        return fn(_SyncConn(self.cols))

    async def execute(self, stmt):
        self.executed_sql.append(str(stmt))


class _BeginCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return _BeginCtx(self._conn)


async def test_create_tables_runs_age_to_year_of_birth_migration(monkeypatch):
    conn = _AsyncConn(cols=["id", "doctor_id", "name", "age"])
    monkeypatch.setattr(init_db, "engine", _Engine(conn))

    create_all = MagicMock()
    monkeypatch.setattr(init_db.Base.metadata, "create_all", create_all)

    await init_db.create_tables()

    create_all.assert_called_once()
    assert any("RENAME COLUMN age TO year_of_birth" in s for s in conn.executed_sql)


async def test_create_tables_skips_migration_when_column_already_renamed(monkeypatch):
    conn = _AsyncConn(cols=["id", "doctor_id", "name", "year_of_birth"])
    monkeypatch.setattr(init_db, "engine", _Engine(conn))

    create_all = MagicMock()
    monkeypatch.setattr(init_db.Base.metadata, "create_all", create_all)

    await init_db.create_tables()

    create_all.assert_called_once()
    assert conn.executed_sql == []


async def test_seed_prompts_inserts_both_defaults_when_missing(monkeypatch):
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _SessionCtx())
    with patch("db.crud.get_system_prompt", new=AsyncMock(side_effect=[None, None])) as get_prompt, \
         patch("db.crud.upsert_system_prompt", new=AsyncMock()) as upsert:
        await init_db.seed_prompts()

    assert get_prompt.await_count == 2
    assert upsert.await_count == 2
    first_call = upsert.await_args_list[0].args
    second_call = upsert.await_args_list[1].args
    assert first_call[1] == "structuring"
    assert second_call[1] == "structuring.neuro_cvd"


async def test_seed_prompts_is_idempotent_when_rows_exist(monkeypatch):
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _SessionCtx())
    with patch("db.crud.get_system_prompt", new=AsyncMock(side_effect=[object(), object()])) as get_prompt, \
         patch("db.crud.upsert_system_prompt", new=AsyncMock()) as upsert:
        await init_db.seed_prompts()

    assert get_prompt.await_count == 2
    upsert.assert_not_awaited()
