from __future__ import annotations

from logging.config import fileConfig
import os
from typing import Optional

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.engine import Base, DATABASE_URL

config = context.config

# Do NOT call fileConfig here — it resets the root logger's handlers (removing
# the RotatingFileHandler for app.log set up by utils/log.py init_logging()).
# Logging is fully managed by utils/log.py when running inside the application.
# The [loggers] sections in alembic.ini are kept for standalone `alembic` CLI
# usage but are intentionally skipped when migrating inside the app process.
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _to_sync_url(url: Optional[str]) -> str:
    raw = (url or "").strip()
    if not raw:
        return "sqlite:///./patients.db"
    if raw.startswith("sqlite+aiosqlite://"):
        return raw.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if raw.startswith("mysql+aiomysql://"):
        return raw.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    return raw


config.set_main_option("sqlalchemy.url", _to_sync_url(os.environ.get("DATABASE_URL") or DATABASE_URL))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
