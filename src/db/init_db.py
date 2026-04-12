"""
数据库初始化：测试夹具用表创建。生产环境 DDL 由 Alembic 管理。
"""

import logging
import db.models  # noqa: F401 — ensure models are registered before create_all
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask
from sqlalchemy import select

_log = logging.getLogger("db.init")


async def create_tables() -> None:
    """Create all tables from ORM metadata.

    Used by test fixtures only. Production DDL is managed by Alembic.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
