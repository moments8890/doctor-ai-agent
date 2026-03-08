"""
数据库引擎配置：创建异步 SQLAlchemy 引擎和会话工厂，并在生产环境强制校验 DATABASE_URL。
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from utils.runtime_json import load_runtime_json

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "patients.db"
_RUNTIME_CONFIG = load_runtime_json()
DB_PATH = Path(
    str(os.environ.get("PATIENTS_DB_PATH") or _RUNTIME_CONFIG.get("PATIENTS_DB_PATH") or DEFAULT_DB_PATH)
).expanduser()

DATABASE_URL = str(os.environ.get("DATABASE_URL") or _RUNTIME_CONFIG.get("DATABASE_URL") or "").strip()
_is_dev = os.environ.get("ENVIRONMENT", "").strip().lower() in {"development", "dev", "test"}
_is_pytest = (
    bool(os.environ.get("PYTEST_CURRENT_TEST"))
    or "pytest" in sys.modules
    or any("pytest" in arg for arg in sys.argv)
)

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
    engine = create_async_engine(DATABASE_URL, echo=False)
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "20")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),
        pool_pre_ping=True,
    )

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
