import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "patients.db"
DB_PATH = Path(os.environ.get("PATIENTS_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()

# Ensure SQLite parent directory exists (e.g. shared DB path from .env).
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
