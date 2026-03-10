"""数据库引擎单元测试：验证 DATABASE_URL 和 PATIENTS_DB_PATH 环境变量的优先级与路径创建行为。"""

from __future__ import annotations

import importlib
from pathlib import Path


def test_engine_uses_patients_db_path_when_database_url_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PATIENTS_DB_PATH", str(tmp_path / "nested" / "patients.db"))

    import db.engine as eng
    eng = importlib.reload(eng)

    assert eng.DATABASE_URL.startswith("sqlite+aiosqlite:///")
    assert "patients.db" in eng.DATABASE_URL
    assert (tmp_path / "nested").exists()


def test_engine_prefers_database_url(monkeypatch, tmp_path):
    sqlite_file = tmp_path / "shared" / "remote.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{sqlite_file}")
    monkeypatch.setenv("PATIENTS_DB_PATH", str(tmp_path / "ignored.db"))

    import db.engine as eng
    eng = importlib.reload(eng)

    assert eng.DATABASE_URL == f"sqlite+aiosqlite:///{sqlite_file}"
    assert (tmp_path / "shared").exists()
