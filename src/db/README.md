# DB Module

Purpose:
- Owns database schema, initialization, and CRUD operations.

Key files:
- `models.py`: SQLAlchemy ORM models (patients, records, tasks, doctors, runtime tables).
- `engine.py`: async engine/session setup.
- `init_db.py`: table creation + startup/backfill migrations.
- `crud.py`: application DB operations used by routers/services.

Notes:
- Schema changes should be made in `models.py`.
- Startup migrations/backfills are handled in `init_db.py`.
