import os
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
if not DATABASE_URL:
    # Backward-compatible local SQLite default.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
else:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme.startswith("sqlite") and parsed.path:
        sqlite_path = Path(parsed.path).expanduser()
        if sqlite_path.is_absolute():
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
