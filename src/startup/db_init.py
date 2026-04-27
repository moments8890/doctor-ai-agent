"""Database initialisation: table creation, migrations, seed data, production guards."""

import asyncio
import logging
import os


async def run_alembic_migrations() -> None:
    """Run pending Alembic migrations synchronously in a thread pool."""
    from alembic.config import Config
    from alembic import command

    log = logging.getLogger("startup")

    def _run_sync() -> None:
        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "alembic")
        command.upgrade(cfg, "head")

    status = "applied"
    error = ""
    try:
        await asyncio.get_event_loop().run_in_executor(None, _run_sync)
        log.info("[DB] Alembic migrations applied (or already at head)")
    except Exception as exc:
        status = "failed"
        error = str(exc)
        log.warning("[DB] Alembic migration failed -- continuing (schema may already be current): %s", exc)
    # GlitchTip Logs surface: body prefix "db." routes via _before_send_log
    # in main.py to service.name=db. One event per startup so the DB layer
    # is visible in the Service dropdown on every deploy. Defensive — must
    # never break the startup path.
    try:
        from sentry_sdk import logger as _slog
        _slog.info("db.migration", status=status, error=error)
    except Exception:
        pass


async def init_database(startup_log: logging.Logger) -> None:
    """Run migrations, backfill doctors, and seed prompts."""
    from db.init_db import seed_prompts, backfill_doctors_registry

    await run_alembic_migrations()
    _added_doctors = await backfill_doctors_registry()
    startup_log.info("[DB] doctors backfill completed | inserted=%s", _added_doctors)
    await seed_prompts()


def enforce_production_guards() -> None:
    """Production safety checks: ensure critical secrets are set."""
    from infra.auth import is_production
    if not is_production():
        return
    if not os.environ.get("WECHAT_ID_HMAC_KEY", "").strip():
        raise RuntimeError(
            "WECHAT_ID_HMAC_KEY must be set in production to ensure "
            "WeChat identifiers are hashed at rest. Refusing to start."
        )
    if not os.environ.get("PATIENT_PORTAL_SECRET", "").strip():
        raise RuntimeError(
            "PATIENT_PORTAL_SECRET must be set in production to ensure "
            "patient portal tokens are signed with a real secret. "
            "Refusing to start."
        )
    # CORS_ALLOW_ORIGINS is enforced at module level during CORS middleware setup.
