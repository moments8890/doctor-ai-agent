"""
数据库初始化：创建所有表。Schema 演进由 Alembic (alembic upgrade head) 管理。
"""

import logging
import db.models  # noqa: F401 — ensure models are registered before create_all
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask
from sqlalchemy import select, text

_log = logging.getLogger("db.init")


async def create_tables() -> None:
    """Create all tables from ORM metadata (idempotent for new installs).

    Schema evolution (ADD COLUMN, indexes) is handled by Alembic migrations
    run separately via _run_alembic_migrations() in main.py startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _backfill_missing_columns()


async def _backfill_missing_columns() -> None:
    """Add columns present in ORM models but missing from SQLite tables.

    SQLite supports ADD COLUMN but not DROP/RENAME, so this only handles
    the common case of new nullable columns added to models.
    """
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = await conn.execute(text(f"PRAGMA table_info('{table.name}')"))
            existing_cols = {row[1] for row in existing}
            for col in table.columns:
                if col.name not in existing_cols:
                    col_type = col.type.compile(dialect=conn.dialect)
                    await conn.execute(
                        text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}")
                    )
                    _log.info("[DB] Added missing column %s.%s (%s)", table.name, col.name, col_type)


async def seed_prompts() -> None:
    """No-op — prompts are file-defined in prompts/*.md (ADR 0011)."""
    pass


_DOCTOR_SOURCES = [
    Patient.doctor_id,
    MedicalRecordDB.doctor_id,
    DoctorTask.doctor_id,
]


async def _collect_all_doctor_ids(db) -> set:
    """Scan historical tables for all doctor_id values."""
    doctor_ids = set()
    for col in _DOCTOR_SOURCES:
        rows = (await db.execute(select(col).where(col.is_not(None)))).scalars().all()
        for value in rows:
            if isinstance(value, str) and value.strip():
                doctor_ids.add(value.strip())
    return doctor_ids


async def backfill_doctors_registry() -> int:
    """Populate doctors table from historical tables (idempotent)."""
    async with AsyncSessionLocal() as db:
        doctor_ids = await _collect_all_doctor_ids(db)
        existing_rows = (await db.execute(select(Doctor))).scalars().all()
        existing = {row.doctor_id for row in existing_rows}
        missing = sorted(doctor_ids - existing)
        for doctor_id in missing:
            db.add(Doctor(doctor_id=doctor_id))
        if missing:
            await db.commit()
        return len(missing)
