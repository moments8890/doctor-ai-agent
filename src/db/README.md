# DB Module

Purpose:
- Owns database schema, initialization, and CRUD operations.

Key areas:
- `models/` — SQLAlchemy ORM models.
- `crud/` — Async CRUD functions.
- `repositories/` — Higher-level query wrappers.
- `engine.py` — Async engine + session factory (`AsyncSessionLocal`).
- `init_db.py` — Test-only table creation + startup backfills.

Schema changes:
- Edit models in `models/`, then write an Alembic migration.
- Run `alembic revision -m "short description"` to create a new migration file.
- Migrations live in `alembic/versions/` with sequential numbering (0001, 0002, ...).
- Production migrations run automatically at startup (`src/startup/db_init.py`).
- Test fixtures use `Base.metadata.create_all` directly (no Alembic).
