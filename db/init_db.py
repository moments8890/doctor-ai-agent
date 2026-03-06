import db.models  # noqa: F401 — ensure models are registered before create_all
import re
from sqlalchemy import text
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask, NeuroCaseDB, DoctorContext, PatientLabel
from sqlalchemy import select


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # One-shot migration: rename age→year_of_birth if old schema exists
        cols = await conn.run_sync(
            lambda c: [r[1] for r in c.execute(text("PRAGMA table_info(patients)")).fetchall()]
        )
        if "age" in cols and "year_of_birth" not in cols:
            await conn.execute(text("ALTER TABLE patients RENAME COLUMN age TO year_of_birth"))
        # Safe column-add migration for patient categorization fields (v1)
        _cat_cols = {
            "primary_category": "VARCHAR(32)",
            "category_tags": "TEXT",
            "category_computed_at": "DATETIME",
            "category_rules_version": "VARCHAR(16)",
        }
        for col_name, col_type in _cat_cols.items():
            if col_name not in cols:
                await conn.execute(
                    text(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type} DEFAULT NULL")
                )
        # Safe column-add migration for patient risk fields (v1)
        _risk_cols = {
            "primary_risk_level": "VARCHAR(16)",
            "risk_tags": "TEXT",
            "risk_score": "INTEGER",
            "follow_up_state": "VARCHAR(16)",
            "risk_computed_at": "DATETIME",
            "risk_rules_version": "VARCHAR(16)",
        }
        for col_name, col_type in _risk_cols.items():
            if col_name not in cols:
                await conn.execute(
                    text(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type} DEFAULT NULL")
                )
        # Safe column-add migration for doctor task trigger metadata.
        _task_cols = await conn.run_sync(
            lambda c: [r[1] for r in c.execute(text("PRAGMA table_info(doctor_tasks)")).fetchall()]
        )
        _trigger_cols = {
            "trigger_source": "VARCHAR(32)",
            "trigger_reason": "TEXT",
        }
        for col_name, col_type in _trigger_cols.items():
            if col_name not in _task_cols:
                await conn.execute(
                    text(f"ALTER TABLE doctor_tasks ADD COLUMN {col_name} {col_type} DEFAULT NULL")
                )

        # Safe migration for doctors identity fields.
        _doctor_cols = await conn.run_sync(
            lambda c: [r[1] for r in c.execute(text("PRAGMA table_info(doctors)")).fetchall()]
        )
        _doctor_extra_cols = {
            "channel": "VARCHAR(32)",
            "wechat_user_id": "VARCHAR(128)",
        }
        for col_name, col_type in _doctor_extra_cols.items():
            if col_name not in _doctor_cols:
                await conn.execute(
                    text(f"ALTER TABLE doctors ADD COLUMN {col_name} {col_type} DEFAULT NULL")
                )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_doctors_channel_wechat_user_id "
                "ON doctors(channel, wechat_user_id)"
            )
        )


async def seed_prompts() -> None:
    """Seed default system prompts to DB on first startup (idempotent)."""
    from services.structuring import _SEED_PROMPT
    from services.neuro_structuring import _SEED_PROMPT as _NEURO_SEED
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
