# DB Module

Purpose:
- Owns database schema, initialization, and CRUD operations.

Key areas:
- `models/` — SQLAlchemy ORM models: `doctor.py` (Doctor, DoctorContext, ChatArchive), `patient.py` (Patient, PatientLabel), `records.py` (MedicalRecordDB, PendingRecord), `tasks.py` (DoctorTask), and more.
- `crud/` — Async CRUD functions: `doctor.py` (patient search, turn archiving), `patient.py`, `records.py` (save + versioning), `pending.py` (draft lifecycle), `tasks.py`.
- `repositories/` — Higher-level query wrappers: `patients.py`, `records.py`, `tasks.py`.
- `engine.py` — Async engine + session factory (`AsyncSessionLocal`).
- `init_db.py` — Table creation + startup backfill migrations.

Notes:
- Schema changes go in `models/`.
- No Alembic migrations until first production launch; `create_tables()` handles DDL.
- Startup migrations/backfills are in `init_db.py`.
