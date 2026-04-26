"""
数据库引擎配置：创建异步 SQLAlchemy 引擎和会话工厂，并在生产环境强制校验 DATABASE_URL。
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from utils.runtime_config import load_runtime_json

ROOT = Path(__file__).resolve().parent.parent.parent  # src/db/engine.py → project root
DEFAULT_DB_PATH = ROOT / "data" / "patients.db"
_RUNTIME_CONFIG = load_runtime_json()
DB_PATH = Path(
    str(os.environ.get("PATIENTS_DB_PATH") or _RUNTIME_CONFIG.get("PATIENTS_DB_PATH") or DEFAULT_DB_PATH)
).expanduser()

DATABASE_URL = str(os.environ.get("DATABASE_URL") or _RUNTIME_CONFIG.get("DATABASE_URL") or "").strip()
_environment = os.environ.get("ENVIRONMENT", "").strip().lower()
_is_dev = _environment in {"development", "dev", "test"}
_is_test = _environment == "test"
_is_pytest = (
    bool(os.environ.get("PYTEST_CURRENT_TEST"))
    or "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
)

# Backstop tripwire — when running under pytest or with ENVIRONMENT=test,
# the engine must never bind to a path the dev server uses. tests/conftest.py
# normally pins the env vars to a test-only DB before this module loads,
# but a contributor may bypass that path (e.g. importing this module
# directly from a script). This guard catches that case loudly instead of
# silently writing into patients.db.
_PROTECTED_DEV_DB_PATHS = frozenset(
    {
        str((ROOT / "patients.db").resolve()),
        str((ROOT / "data" / "patients.db").resolve()),
    }
)


def _resolve_sqlite_path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("sqlite") or not parsed.path:
        return None
    return Path(parsed.path).expanduser()


def _enforce_test_db_isolation(*candidates: Path | None) -> None:
    if not (_is_test or _is_pytest):
        return
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = str(candidate.expanduser().resolve())
        except OSError:
            continue
        if resolved in _PROTECTED_DEV_DB_PATHS:
            sys.exit(
                "ERROR: refusing to bind the test/pytest engine to a "
                f"protected dev DB path: {resolved}\n"
                "Tests must use a separate file (default: "
                ".pytest-data/patients.test.db). Unset DATABASE_URL / "
                "PATIENTS_DB_PATH or rely on tests/conftest.py to pin them."
            )


_enforce_test_db_isolation(DB_PATH, _resolve_sqlite_path_from_url(DATABASE_URL))

if not DATABASE_URL:
    if not _is_dev and not _is_pytest:
        sys.exit(
            "ERROR: DATABASE_URL must be set to a MySQL/PostgreSQL connection string in production. "
            "SQLite is not supported for production use. "
            "Set ENVIRONMENT=development to allow SQLite locally."
        )
    # Development / test fallback to SQLite.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
else:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme.startswith("sqlite") and parsed.path:
        if not _is_dev and not _is_pytest:
            sys.exit(
                "ERROR: DATABASE_URL points to SQLite, which is not supported in production. "
                "Set ENVIRONMENT=development to allow SQLite locally."
            )
        sqlite_path = Path(parsed.path).expanduser()
        if sqlite_path.is_absolute():
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)

_is_sqlite = DATABASE_URL.startswith("sqlite")
if _is_sqlite:
    engine = create_async_engine(
        DATABASE_URL,
        echo=os.environ.get("DB_ECHO", "false").lower() == "true",  # WARNING: logs SQL with params — may contain PHI. Dev/debug only.
        connect_args={"timeout": 30},
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=os.environ.get("DB_ECHO", "false").lower() == "true",  # WARNING: logs SQL with params — may contain PHI. Dev/debug only.
        pool_size=int(os.environ.get("DB_POOL_SIZE", "20")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),
        pool_pre_ping=True,
    )

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency that yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session
