"""
数据库初始化：创建所有表。Schema 演进由 Alembic (alembic upgrade head) 管理。
"""

import db.models  # noqa: F401 — ensure models are registered before create_all
import re
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask, DoctorContext, PatientLabel
from sqlalchemy import select


async def create_tables() -> None:
    """Create all tables from ORM metadata (idempotent for new installs).

    Schema evolution (ADD COLUMN, indexes) is handled by Alembic migrations
    run separately via _run_alembic_migrations() in main.py startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_prompts() -> None:
    """No-op — prompts are file-defined in prompts/*.md (ADR 0011)."""
    pass


_WECHAT_RE = re.compile(r"^(?:wm|wx|ww|wo)[A-Za-z0-9_-]{6,}$")

_DOCTOR_SOURCES = [
    Patient.doctor_id,
    MedicalRecordDB.doctor_id,
    DoctorTask.doctor_id,
    DoctorContext.doctor_id,
    PatientLabel.doctor_id,
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


def _backfill_existing_row(row, seen_wechat: set) -> bool:
    """Apply channel/wechat_user_id backfill to an existing Doctor row. Returns True if changed."""
    if not isinstance(row.doctor_id, str):
        return False
    doctor_id = row.doctor_id.strip()
    if not doctor_id:
        return False
    is_wechat = bool(_WECHAT_RE.match(doctor_id))
    changed = False
    if not getattr(row, "channel", None):
        row.channel = "wechat" if is_wechat else "app"
        changed = True
    if is_wechat and not getattr(row, "wechat_user_id", None) and doctor_id not in seen_wechat:
        row.wechat_user_id = doctor_id
        changed = True
    if getattr(row, "wechat_user_id", None):
        seen_wechat.add(str(row.wechat_user_id))
    return changed


async def backfill_doctors_registry() -> int:
    """Populate doctors table from historical tables (idempotent)."""
    async with AsyncSessionLocal() as db:
        doctor_ids = await _collect_all_doctor_ids(db)
        existing_rows = (await db.execute(select(Doctor))).scalars().all()
        existing = {row.doctor_id for row in existing_rows}
        missing = sorted(doctor_ids - existing)
        for doctor_id in missing:
            is_wechat = bool(_WECHAT_RE.match(doctor_id))
            db.add(Doctor(
                doctor_id=doctor_id,
                channel="wechat" if is_wechat else "app",
                wechat_user_id=doctor_id if is_wechat else None,
            ))
        seen_wechat: set = set()
        updated_existing = any(
            _backfill_existing_row(row, seen_wechat) for row in existing_rows
        )
        if missing or updated_existing:
            await db.commit()
        return len(missing)
