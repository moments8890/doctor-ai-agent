"""
数据库初始化：创建所有表。Schema 演进由 Alembic (alembic upgrade head) 管理。
"""

import db.models  # noqa: F401 — ensure models are registered before create_all
import re
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask, NeuroCaseDB, DoctorContext, PatientLabel
from sqlalchemy import select


async def create_tables() -> None:
    """Create all tables from ORM metadata (idempotent for new installs).

    Schema evolution (ADD COLUMN, indexes) is handled by Alembic migrations
    run separately via _run_alembic_migrations() in main.py startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_prompts() -> None:
    """Seed default system prompts to DB on first startup (idempotent)."""
    from services.ai.structuring import _SEED_PROMPT
    from services.ai.neuro_structuring import _SEED_PROMPT as _NEURO_SEED
    from db.crud import get_system_prompt, upsert_system_prompt
    async with AsyncSessionLocal() as db:
        existing = await get_system_prompt(db, "structuring")
        if not existing:
            await upsert_system_prompt(db, "structuring", _SEED_PROMPT)
        existing_neuro = await get_system_prompt(db, "structuring.neuro_cvd")
        if not existing_neuro:
            await upsert_system_prompt(db, "structuring.neuro_cvd", _NEURO_SEED)


async def backfill_doctors_registry() -> int:
    """Populate doctors table from historical tables (idempotent)."""
    wechat_re = re.compile(r"^(?:wm|wx|ww|wo)[A-Za-z0-9_-]{6,}$")
    doctor_ids = set()
    doctor_sources = [
        Patient.doctor_id,
        MedicalRecordDB.doctor_id,
        DoctorTask.doctor_id,
        NeuroCaseDB.doctor_id,
        DoctorContext.doctor_id,
        PatientLabel.doctor_id,
    ]

    async with AsyncSessionLocal() as db:
        for col in doctor_sources:
            rows = (await db.execute(select(col).where(col.is_not(None)))).scalars().all()
            for value in rows:
                if isinstance(value, str) and value.strip():
                    doctor_ids.add(value.strip())

        existing_rows = (await db.execute(select(Doctor))).scalars().all()
        existing = {row.doctor_id for row in existing_rows}
        missing = sorted(doctor_ids - existing)
        for doctor_id in missing:
            is_wechat = bool(wechat_re.match(doctor_id))
            db.add(
                Doctor(
                    doctor_id=doctor_id,
                    channel="wechat" if is_wechat else "app",
                    wechat_user_id=doctor_id if is_wechat else None,
                )
            )

        # Backfill existing rows with identity metadata where possible.
        updated_existing = False
        seen_wechat = set()
        for row in existing_rows:
            if not isinstance(row.doctor_id, str):
                continue
            doctor_id = row.doctor_id.strip()
            if not doctor_id:
                continue
            is_wechat = bool(wechat_re.match(doctor_id))
            if not getattr(row, "channel", None):
                row.channel = "wechat" if is_wechat else "app"
                updated_existing = True
            if is_wechat and not getattr(row, "wechat_user_id", None) and doctor_id not in seen_wechat:
                row.wechat_user_id = doctor_id
                updated_existing = True
            if getattr(row, "wechat_user_id", None):
                seen_wechat.add(str(row.wechat_user_id))
        if missing or updated_existing:
            await db.commit()
        return len(missing)
