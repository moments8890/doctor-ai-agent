import db.models  # noqa: F401 — ensure models are registered before create_all
from sqlalchemy import text
from db.engine import Base, engine, AsyncSessionLocal


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
