# Public ID Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace auto-increment integer IDs with opaque UUIDv4 `public_id` strings in all user-visible URLs (frontend routes + API paths) for `patients`, `medical_records`, `message_drafts`, and `doctor_tasks`, eliminating ID enumeration and weakening any future IDOR vulnerabilities.

**Architecture:** Additive-then-cutover migration. Phase 1 adds nullable `public_id` columns, backfills with UUIDv4, makes them NOT NULL + UNIQUE, and exposes them in API JSON responses alongside the existing `id`. Phase 2 changes API path params from `{id:int}` to `{public_id:str}` and adds lookup helpers that resolve public_id → internal int row, scoped by `doctor_id`. Phase 3 updates the frontend to navigate using `public_id`. Internal foreign keys keep using integer `id` for join performance — only the externally-visible surface changes.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, FastAPI, React Router v6, SQLite (dev) / MySQL (prod), pytest, vitest.

---

## Scope

**In scope (4 tables):**
- `patients` — used in `/doctor/patients/{id}` and `/api/manage/patients/{id}/...`
- `medical_records` (model: `MedicalRecordDB`) — used in `/doctor/review/{id}` and `/api/manage/records/{id}` family
- `message_drafts` — used in `/api/manage/drafts/{id}/send|edit|dismiss|...`
- `doctor_tasks` — used in `/api/manage/tasks/{id}` family and task detail subpages

**Out of scope:**
- `doctors` table — `doctor_id` is already an opaque string (`web_doctor`, etc.); no change.
- `patient_messages`, `ai_suggestions`, `doctor_personas`, etc. — these never appear in URLs.
- Foreign-key columns — internal joins continue to use integer `id`.
- WeChat / WeCom channels — they don't use REST URL params for these entities.

## Design Decisions

1. **UUIDv4, not hashids.** UUIDv4 is sufficient (122 bits of randomness, collision probability ~10⁻³⁶ per row). Hashids reverse to integer; not actually opaque.
2. **VARCHAR(36) string column, not native UUID type.** MySQL 8 and SQLite both lack native UUID. Storing as `CHAR(36)` (with dashes) keeps schema portable. The cross-engine cost is ~16 bytes vs binary UUID — negligible at our scale.
3. **Client-side default (`default=lambda: str(uuid4())`)**, not server-side. SQLAlchemy default fires on insert; works identically across engines.
4. **Three deployable phases.** Each phase ships independently and is reversible. Phase 1 cannot break the app (additive only). Phase 2 + 3 ship in one coordinated deploy because frontend stops generating int-ID URLs and backend stops accepting them at the same time.
5. **No backwards-compatibility for old int URLs after cutover.** After Phase 2/3, `/api/manage/patients/42` returns 404. Rationale: leaving dual-accept routes alive defeats the purpose (attackers still enumerate). Brief 410-Gone window is acceptable for the few seconds of in-flight requests during deploy.
6. **Lookup helpers enforce ownership at the same layer.** `get_patient_by_public_id(db, public_id, doctor_id)` returns 404 if the public_id doesn't exist OR belongs to another doctor — same response either way (no enumeration via timing or error message).

---

## File Structure

**New files:**
- `alembic/versions/<rev>_add_public_id_columns.py` — schema migration + backfill
- `src/db/crud/public_id_lookup.py` — `get_*_by_public_id` helpers (one per of 4 entity types)
- `tests/test_public_id_migration.py` — migration sanity checks (default population, uniqueness, model wiring)
- `tests/test_public_id_routes.py` — API route tests for the new path-param shape

**Modified files (Phase 1):**
- `src/db/models/patient.py` — add `public_id` mapped column
- `src/db/models/records.py` — add `public_id` to `MedicalRecordDB`
- `src/db/models/message_draft.py` — add `public_id` to `MessageDraft`
- `src/db/models/tasks.py` — add `public_id` to `DoctorTask`
- All handlers under `src/channels/web/doctor_dashboard/` that serialize these entities — add `public_id` field to JSON responses (read-only).

**Modified files (Phase 2):**
- `src/channels/web/doctor_dashboard/patient_detail_handlers.py` — convert `patient_id: int` path params to `public_id: str`
- `src/channels/web/doctor_dashboard/record_handlers.py` — same for record endpoints
- `src/channels/web/doctor_dashboard/draft_handlers.py` — same for draft endpoints
- `src/channels/web/doctor_dashboard/today_summary_handlers.py`, `review_queue_handlers.py`, `new_patient_handlers.py`, `onboarding_handlers.py` — sweep for any patient_id/record_id/draft_id/task_id path params

**Modified files (Phase 3):**
- `frontend/web/src/v2/App.jsx` — route paths
- `frontend/web/src/v2/pages/doctor/*.jsx` (~20 files) — `navigate()` callsites
- `frontend/web/src/v2/api/*.js` — API client wrappers if any encode IDs
- E2E specs under `frontend/web/tests/`

---

# PHASE 1 — Additive Schema + API Response Changes

Goal: ship a backend that has `public_id` populated everywhere and exposes it in responses. Frontend ignores it. App behavior unchanged.

## Task 1: Schema migration — add `public_id` columns + backfill

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_add_public_id_columns.py` (use `alembic revision -m "add public_id columns"` to generate the real revision id; replace `a1b2c3d4e5f6` below with what alembic produces)

- [ ] **Step 1: Generate the migration file**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "add public_id columns"
```

Note the generated filename. The revision id is the prefix before `_add_public_id_columns.py`.

- [ ] **Step 2: Write the migration body**

Replace the generated file's contents with:

```python
"""add public_id columns

Adds VARCHAR(36) public_id (UUIDv4) to four tables that appear in user-visible
URLs: patients, medical_records, message_drafts, doctor_tasks. Backfills
existing rows with fresh UUIDs, then enforces NOT NULL + UNIQUE.

Revision ID: <REPLACE_WITH_GENERATED>
Revises: f8b2c4e1a3d5
Create Date: 2026-04-26
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "<REPLACE_WITH_GENERATED>"
down_revision = "f8b2c4e1a3d5"
branch_labels = None
depends_on = None


_TABLES = ("patients", "medical_records", "message_drafts", "doctor_tasks")


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        op.add_column(table, sa.Column("public_id", sa.String(36), nullable=True))
        rows = bind.execute(
            sa.text(f"SELECT id FROM {table} WHERE public_id IS NULL")
        ).all()
        for (row_id,) in rows:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET public_id = :pid WHERE id = :rid"
                ),
                {"pid": str(uuid.uuid4()), "rid": row_id},
            )
        with op.batch_alter_table(table) as batch:
            batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        op.create_index(
            f"ix_{table}_public_id", table, ["public_id"], unique=True,
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_public_id", table_name=table)
        op.drop_column(table, "public_id")
```

- [ ] **Step 3: Run the migration on the dev DB and verify**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head
sqlite3 dev.db "SELECT id, public_id FROM patients LIMIT 3; SELECT id, public_id FROM medical_records LIMIT 3; SELECT id, public_id FROM message_drafts LIMIT 3; SELECT id, public_id FROM doctor_tasks LIMIT 3;"
```

Expected: every row shows a 36-char UUID. No NULLs.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/<generated>_add_public_id_columns.py
git commit -m "feat(db): add public_id columns to URL-exposed tables"
```

---

## Task 2: Model wiring — add `public_id` mapped column to each model

**Files:**
- Modify: `src/db/models/patient.py`
- Modify: `src/db/models/records.py`
- Modify: `src/db/models/message_draft.py`
- Modify: `src/db/models/tasks.py`
- Test: `tests/test_public_id_migration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_migration.py`:

```python
"""Sanity tests for public_id wiring on the four URL-exposed tables."""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.message_draft import MessageDraft
from db.models.tasks import DoctorTask


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _is_uuid_v4(value: str) -> bool:
    return bool(_UUID_RE.match(value or ""))


@pytest.mark.asyncio
async def test_patient_default_public_id():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="web_doctor", name="UUID-Test-Patient")
        db.add(p)
        await db.flush()
        assert _is_uuid_v4(p.public_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_record_default_public_id():
    async with AsyncSessionLocal() as db:
        r = MedicalRecordDB(doctor_id="web_doctor", patient_id=1, record_type="visit")
        db.add(r)
        await db.flush()
        assert _is_uuid_v4(r.public_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_draft_default_public_id():
    async with AsyncSessionLocal() as db:
        d = MessageDraft(doctor_id="web_doctor", patient_id=1, draft_text="hi")
        db.add(d)
        await db.flush()
        assert _is_uuid_v4(d.public_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_task_default_public_id():
    async with AsyncSessionLocal() as db:
        t = DoctorTask(doctor_id="web_doctor", task_type="followup", title="t")
        db.add(t)
        await db.flush()
        assert _is_uuid_v4(t.public_id)
        await db.rollback()
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_migration.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 FAIL with `AttributeError: 'Patient' object has no attribute 'public_id'` (or similar).

- [ ] **Step 3: Add `public_id` to `Patient`**

In `src/db/models/patient.py`, add at the top:

```python
import uuid as _uuid
```

In the `Patient` class body, add immediately after the `id` column (line 19):

```python
    public_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 4: Add `public_id` to `MedicalRecordDB`**

In `src/db/models/records.py`, add `import uuid as _uuid` if not already present, then add immediately after the `id` column on `MedicalRecordDB`:

```python
    public_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 5: Add `public_id` to `MessageDraft`**

In `src/db/models/message_draft.py`, add `import uuid as _uuid` if not already present, then add immediately after the `id` column (line 29):

```python
    public_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 6: Add `public_id` to `DoctorTask`**

In `src/db/models/tasks.py`, add `import uuid as _uuid` if not already present, then add immediately after the `id` column (line 32):

```python
    public_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 7: Run the test — confirm it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_migration.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 PASS.

- [ ] **Step 8: Run the full unit test suite to confirm no regressions**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x
```

Expected: all green. If any model-construction tests fail because they rely on positional args, fix by passing `public_id` explicitly OR confirming the default kicks in.

- [ ] **Step 9: Commit**

```bash
git add src/db/models/patient.py src/db/models/records.py src/db/models/message_draft.py src/db/models/tasks.py tests/test_public_id_migration.py
git commit -m "feat(db): wire public_id field on Patient/MedicalRecordDB/MessageDraft/DoctorTask"
```

---

## Task 3: Expose `public_id` in API responses (additive)

**Files:**
- Modify: every handler in `src/channels/web/doctor_dashboard/` that returns serialized patient/record/draft/task JSON
- Test: `tests/test_public_id_in_responses.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_in_responses.py`:

```python
"""Phase 1 contract: every list/detail endpoint that returns these entities
must include `public_id` alongside `id`. Frontend will pivot to public_id
in Phase 3; until then it's read-only and additive."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from main import app  # adjust import path if needed


@pytest.mark.asyncio
async def test_patient_list_includes_public_id(seeded_doctor_token, seeded_patient):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            "/api/manage/patients",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200
    items = r.json().get("patients") or r.json().get("items") or []
    assert items, "fixture should produce at least one patient"
    for p in items:
        assert "public_id" in p
        assert isinstance(p["public_id"], str)
        assert len(p["public_id"]) == 36


@pytest.mark.asyncio
async def test_records_list_includes_public_id(seeded_doctor_token, seeded_record):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            "/api/manage/records",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200
    items = r.json().get("records") or r.json().get("items") or []
    for rec in items:
        assert "public_id" in rec


@pytest.mark.asyncio
async def test_drafts_list_includes_public_id(seeded_doctor_token, seeded_draft):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            "/api/manage/drafts",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200
    items = r.json().get("drafts") or r.json().get("items") or []
    for d in items:
        assert "public_id" in d


@pytest.mark.asyncio
async def test_tasks_list_includes_public_id(seeded_doctor_token, seeded_task):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            "/api/manage/tasks",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200
    items = r.json().get("tasks") or r.json().get("items") or []
    for t in items:
        assert "public_id" in t
```

(Adjust fixtures to match the project's existing pytest fixture naming. If fixtures don't exist, add minimal ones that issue a JWT for `web_doctor` and seed one row of each entity.)

- [ ] **Step 2: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_in_responses.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 FAIL with `assert "public_id" in p`.

- [ ] **Step 3: Audit which handlers serialize these entities**

```bash
grep -rn '"id":\s*[a-zA-Z_.]*\.id' src/channels/web/doctor_dashboard/ --include="*.py" | grep -vE "patient_id|record_id|draft_id|task_id|doctor_id"
```

Each line is a place where a row's int `id` is serialized into a response. For each line, the same dict must also include `"public_id": <row>.public_id`.

Cluster results into 4 groups (patient / record / draft / task) and edit each handler.

- [ ] **Step 4: For each serialization site, add `public_id`**

Pattern for each Edit:

```python
# BEFORE
return {"id": p.id, "name": p.name, ...}

# AFTER
return {"id": p.id, "public_id": p.public_id, "name": p.name, ...}
```

Apply across `patient_detail_handlers.py`, `record_handlers.py`, `draft_handlers.py`, `today_summary_handlers.py`, `review_queue_handlers.py`, `new_patient_handlers.py`, `onboarding_handlers.py`, and any task handler files. Touch only response dicts; leave internal logic alone.

- [ ] **Step 5: Run the test — confirm it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_in_responses.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 PASS.

- [ ] **Step 6: Run the full backend test suite**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/channels/web/doctor_dashboard/ tests/test_public_id_in_responses.py
git commit -m "feat(api): expose public_id in patient/record/draft/task responses"
```

**Phase 1 complete. Backend can be deployed independently.**

---

# PHASE 2 — Backend Path Param Cutover

Goal: API routes accept `public_id` (string UUID) instead of integer `id`. Internal code resolves to int row at the request boundary.

## Task 4: Lookup helpers (public_id → row, doctor-scoped)

**Files:**
- Create: `src/db/crud/public_id_lookup.py`
- Test: `tests/test_public_id_lookup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_lookup.py`:

```python
"""Lookup helpers must enforce both existence AND doctor ownership.
Cross-doctor lookups must raise the same exception as missing rows
(no enumeration via differential errors)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.crud.public_id_lookup import (
    get_patient_by_public_id,
    get_record_by_public_id,
    get_draft_by_public_id,
    get_task_by_public_id,
)


@pytest.mark.asyncio
async def test_patient_lookup_owner_match():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="doctor_a", name="Owner-Match")
        db.add(p)
        await db.flush()
        found = await get_patient_by_public_id(db, p.public_id, "doctor_a")
        assert found.id == p.id
        await db.rollback()


@pytest.mark.asyncio
async def test_patient_lookup_wrong_doctor_raises_404():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="doctor_a", name="Wrong-Doctor")
        db.add(p)
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await get_patient_by_public_id(db, p.public_id, "doctor_b")
        assert exc.value.status_code == 404
        await db.rollback()


@pytest.mark.asyncio
async def test_patient_lookup_missing_raises_404():
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await get_patient_by_public_id(
                db, "00000000-0000-4000-8000-000000000000", "doctor_a"
            )
        assert exc.value.status_code == 404
```

(Add analogous tests for record, draft, task — same three cases each.)

- [ ] **Step 2: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_lookup.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: ImportError because `public_id_lookup.py` doesn't exist yet.

- [ ] **Step 3: Implement the lookup helpers**

Create `src/db/crud/public_id_lookup.py`:

```python
"""Doctor-scoped public_id → row lookups.

Every helper raises HTTPException(404) for both 'not found' and 'wrong doctor'.
Same response shape for both cases so the caller cannot distinguish them
(prevents enumeration via differential errors).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.message_draft import MessageDraft
from db.models.tasks import DoctorTask


_NOT_FOUND = HTTPException(status_code=404, detail="Not found")


async def get_patient_by_public_id(
    db: AsyncSession, public_id: str, doctor_id: str
) -> Patient:
    stmt = select(Patient).where(
        Patient.public_id == public_id, Patient.doctor_id == doctor_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


async def get_record_by_public_id(
    db: AsyncSession, public_id: str, doctor_id: str
) -> MedicalRecordDB:
    stmt = select(MedicalRecordDB).where(
        MedicalRecordDB.public_id == public_id,
        MedicalRecordDB.doctor_id == doctor_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


async def get_draft_by_public_id(
    db: AsyncSession, public_id: str, doctor_id: str
) -> MessageDraft:
    stmt = select(MessageDraft).where(
        MessageDraft.public_id == public_id, MessageDraft.doctor_id == doctor_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


async def get_task_by_public_id(
    db: AsyncSession, public_id: str, doctor_id: str
) -> DoctorTask:
    stmt = select(DoctorTask).where(
        DoctorTask.public_id == public_id, DoctorTask.doctor_id == doctor_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row
```

- [ ] **Step 4: Run the test — confirm it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_lookup.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db/crud/public_id_lookup.py tests/test_public_id_lookup.py
git commit -m "feat(db): doctor-scoped public_id lookup helpers"
```

---

## Task 5: Convert patient endpoints to public_id path params

**Files:**
- Modify: `src/channels/web/doctor_dashboard/patient_detail_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/admin_messages.py`
- Modify: `src/channels/web/doctor_dashboard/onboarding_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/new_patient_handlers.py`
- Test: `tests/test_patient_routes_use_public_id.py`

- [ ] **Step 1: Enumerate the patient_id path params to convert**

```bash
grep -n "patients/{patient_id}\|patient_id: int" src/channels/web/doctor_dashboard/*.py
```

Each match is a route handler that takes `patient_id: int` from the URL path. Build a checklist; expect ~6-8 handlers.

- [ ] **Step 2: Write the failing route test**

Create `tests/test_patient_routes_use_public_id.py`:

```python
"""Phase 2: patient endpoints accept public_id (UUID) and reject int IDs."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from main import app


@pytest.mark.asyncio
async def test_timeline_accepts_public_id(seeded_doctor_token, seeded_patient):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/patients/{seeded_patient.public_id}/timeline",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_timeline_rejects_integer_id(seeded_doctor_token, seeded_patient):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/patients/{seeded_patient.id}/timeline",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code in (404, 422)


@pytest.mark.asyncio
async def test_timeline_cross_doctor_returns_404(
    seeded_doctor_token_a, seeded_patient_b
):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/patients/{seeded_patient_b.public_id}/timeline",
            headers={"Authorization": f"Bearer {seeded_doctor_token_a}"},
        )
    assert r.status_code == 404
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_patient_routes_use_public_id.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: tests fail because route still accepts int.

- [ ] **Step 4: Convert each patient_id-keyed route**

For each route in the checklist from Step 1, transform:

```python
# BEFORE
@router.get("/api/manage/patients/{patient_id}/timeline")
async def manage_patient_timeline(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient_id, limit=limit)
    ...
```

Into:

```python
# AFTER
from db.crud.public_id_lookup import get_patient_by_public_id

@router.get("/api/manage/patients/{public_id}/timeline")
async def manage_patient_timeline(
    public_id: str,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    patient = await get_patient_by_public_id(db, public_id, doctor_id)
    data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient.id, limit=limit)
    ...
```

Key rules:
- Path param renamed `patient_id: int` → `public_id: str`.
- One lookup at the top of the handler (`patient = await get_patient_by_public_id(...)`).
- Internal helpers (CRUD, domain logic) keep using `patient.id` (int).
- Never reuse the variable name `patient_id` for both — pick one.

Apply to **every** match from Step 1. Common ones:
- `GET /api/manage/patients/{patient_id}/timeline`
- `DELETE /api/manage/patients/{patient_id}`
- `POST /api/manage/patients/{patient_id}/ai-summary/refresh`
- `GET /api/manage/patients/{patient_id}/chat`
- `POST /api/manage/patients/{patient_id}/reply` ← also fix the ownership gap from the audit by virtue of using `get_patient_by_public_id`
- Any in `onboarding_handlers.py`, `new_patient_handlers.py`, `admin_messages.py`

- [ ] **Step 5: Run the test — confirm it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_patient_routes_use_public_id.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Any test that hits `/api/manage/patients/<int>/...` will start failing — those are existing fixtures that need to switch to `public_id`. Update fixtures one by one. Do not loosen the route to accept both.

- [ ] **Step 7: Commit**

```bash
git add src/channels/web/doctor_dashboard/ tests/
git commit -m "feat(api): patient endpoints use public_id path params"
```

---

## Task 6: Convert record endpoints to public_id path params

**Files:**
- Modify: `src/channels/web/doctor_dashboard/record_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/record_edit_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/review_queue_handlers.py`
- Test: extend `tests/test_patient_routes_use_public_id.py` with record cases

- [ ] **Step 1: Enumerate**

```bash
grep -n "records/{record_id}\|record_id: int" src/channels/web/doctor_dashboard/*.py
```

- [ ] **Step 2: Write the failing record-route tests**

Add to `tests/test_patient_routes_use_public_id.py`:

```python
@pytest.mark.asyncio
async def test_record_detail_accepts_public_id(seeded_doctor_token, seeded_record):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/records/{seeded_record.public_id}",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_record_detail_rejects_integer_id(seeded_doctor_token, seeded_record):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/records/{seeded_record.id}",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code in (404, 422)
```

- [ ] **Step 3: Run — confirm fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_patient_routes_use_public_id.py::test_record_detail_accepts_public_id -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 4: Convert each record_id-keyed route**

Same transformation as Task 5, using `get_record_by_public_id` for the lookup. Sites include record detail, record edit, record delete, review-queue item fetch.

- [ ] **Step 5: Run — confirm passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_patient_routes_use_public_id.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/doctor_dashboard/ tests/
git commit -m "feat(api): record endpoints use public_id path params"
```

---

## Task 7: Convert draft endpoints to public_id path params

**Files:**
- Modify: `src/channels/web/doctor_dashboard/draft_handlers.py`
- Test: extend `tests/test_patient_routes_use_public_id.py`

- [ ] **Step 1: Enumerate**

```bash
grep -n "drafts/{draft_id}\|draft_id: int" src/channels/web/doctor_dashboard/draft_handlers.py
```

Expect 5 routes: `/send`, `/edit`, `/dismiss`, `/send-confirmation`, `/save-as-rule`.

- [ ] **Step 2: Write the failing draft tests**

Add to `tests/test_patient_routes_use_public_id.py`:

```python
@pytest.mark.asyncio
async def test_draft_send_accepts_public_id(seeded_doctor_token, seeded_draft):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post(
            f"/api/manage/drafts/{seeded_draft.public_id}/send",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_draft_send_rejects_integer_id(seeded_doctor_token, seeded_draft):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post(
            f"/api/manage/drafts/{seeded_draft.id}/send",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code in (404, 422)
```

- [ ] **Step 3: Run — confirm fails**

- [ ] **Step 4: Convert all 5 draft routes**

Same transformation as Task 5, using `get_draft_by_public_id`. Pattern reminder for `send_draft`:

```python
@router.post("/api/manage/drafts/{public_id}/send")
async def send_draft(
    public_id: str,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.send")
    draft = await get_draft_by_public_id(db, public_id, resolved)
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft is not in a sendable state")
    reply_text = draft.edited_text or draft.draft_text
    patient_id = int(draft.patient_id)
    disclosure = draft.ai_disclosure

    from domain.patient_lifecycle.reply import send_doctor_reply
    msg_id = await send_doctor_reply(
        doctor_id=resolved,
        patient_id=patient_id,
        text=reply_text,
        draft_id=draft.id,
        ai_disclosure=disclosure,
    )
    ...
```

The internal call to `send_doctor_reply(draft_id=draft.id, ...)` keeps using the integer id — that's a domain-layer signature, not exposed to URLs.

- [ ] **Step 5: Run — confirm passes**

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/doctor_dashboard/draft_handlers.py tests/
git commit -m "feat(api): draft endpoints use public_id path params"
```

---

## Task 8: Convert task endpoints to public_id path params

**Files:**
- Modify: `src/channels/web/doctor_dashboard/today_summary_handlers.py` and any other handler with `tasks/{task_id}` paths

- [ ] **Step 1: Enumerate**

```bash
grep -rn "tasks/{task_id}\|task_id: int" src/channels/web/doctor_dashboard/*.py
```

- [ ] **Step 2: Write tests, convert routes, run, commit**

Same shape as Tasks 5–7 using `get_task_by_public_id`.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): task endpoints use public_id path params"
```

**Phase 2 complete.** Backend rejects integer IDs in URL paths. Frontend will break until Phase 3 ships — these two phases must deploy together in production.

---

# PHASE 3 — Frontend Cutover

Goal: every navigate / link / API call uses `public_id` from the API response, never the integer `id`.

## Task 9: Switch React Router routes and navigation calls

**Files:**
- Modify: `frontend/web/src/v2/App.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/PatientsPage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/PatientDetail.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/IntakePage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/settings/TaskDetailSubpage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/settings/KnowledgeDetailSubpage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/settings/KnowledgeSubpage.jsx`
- Test: existing vitest + Playwright suites must pass

- [ ] **Step 1: Audit navigate callsites**

```bash
grep -rn "navigate(\`\|navigate(\"" frontend/web/src/v2 --include="*.jsx" | grep -E "patient\.id|record\.id|draft\.id|task\.id|/\\\${.*\\.id}"
```

Each match is a callsite that constructs a URL from an integer `id`. Convert each to use `public_id`.

- [ ] **Step 2: Convert each callsite**

Pattern:

```jsx
// BEFORE
navigate(`/doctor/patients/${patient.id}`);

// AFTER
navigate(`/doctor/patients/${patient.public_id}`);
```

Repeat for record, draft, task uses. The list/detail API responses already include `public_id` (Phase 1).

- [ ] **Step 3: Update useParams() consumers**

```bash
grep -rn "useParams()" frontend/web/src/v2 --include="*.jsx"
```

Each match destructures route params. The semantic meaning hasn't changed (it's still the patient/record/draft/task identifier), but the value is now a UUID string. Rename local variables for clarity:

```jsx
// BEFORE
const { patient_id } = useParams();
const { data } = useQuery(["patient", patient_id], () => api.getPatient(patient_id));

// AFTER
const { public_id: patientPublicId } = useParams();
const { data } = useQuery(["patient", patientPublicId], () => api.getPatient(patientPublicId));
```

- [ ] **Step 4: Update API client wrappers**

```bash
grep -rn "patients/\${\|records/\${\|drafts/\${\|tasks/\${" frontend/web/src --include="*.js" --include="*.jsx"
```

Anywhere a URL is built from an entity field, ensure it reads `.public_id` from the response object, not `.id`.

- [ ] **Step 5: Run vitest**

```bash
cd frontend/web && npm test -- --run
```

Expected: all green. Fix any frontend unit tests that asserted on integer IDs in URL params.

- [ ] **Step 6: Run Playwright E2E**

```bash
cd frontend/web && rm -rf test-results && npx playwright test
```

Two servers must be running: backend on :8000, frontend on :5173. All specs should pass; failures here usually mean a navigate site was missed.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
git add frontend/web
git commit -m "feat(ui): navigate by public_id everywhere"
```

---

## Task 10: Manual verification + cleanup

- [ ] **Step 1: Manual smoke test in dev**

Start both servers:

```bash
./dev.sh
```

In a browser:
1. Log in as test doctor.
2. Open patient list → click a patient → URL shows `/doctor/patients/<uuid>`, not an integer.
3. Open a record → URL shows `/doctor/review/<uuid>`.
4. Send a draft reply → succeeds.
5. Open a task → URL shows `<uuid>`.
6. Try `/doctor/patients/1` directly → app should render an empty / not-found state (router won't match `:public_id` if it's a UUID-shaped param OR backend lookup returns 404).

- [ ] **Step 2: Confirm no integer IDs leak in URL or DOM links**

Grep the running dev page DOM (or use browser DevTools network tab). API requests should be `/api/manage/patients/<uuid>/...`. If any request shows an integer in the path, find the missed callsite.

- [ ] **Step 3: Update README / architecture docs**

In `docs/architecture.md`, add a one-paragraph note under the data model section:

> **Public IDs.** Tables that appear in user-visible URLs (`patients`, `medical_records`, `message_drafts`, `doctor_tasks`) carry a `public_id` UUIDv4 column used for routing. Internal foreign keys still use integer `id` for join performance. Any new table that surfaces in the API should follow the same pattern. Lookup helpers in `src/db/crud/public_id_lookup.py` enforce doctor-scoped ownership at the request boundary.

- [ ] **Step 4: Final commit**

```bash
git add docs/architecture.md
git commit -m "docs: public_id pattern for URL-exposed tables"
```

---

## Self-Review Checklist (post-execution)

- [ ] All 4 tables have `public_id` populated, NOT NULL, UNIQUE.
- [ ] Every `@router.get/post/put/delete` path that previously took `{patient_id}|{record_id}|{draft_id}|{task_id}` now takes `{public_id}` and resolves via a `get_*_by_public_id` helper.
- [ ] `grep -rn "patient_id: int" src/channels/web/doctor_dashboard/` returns ONLY query-param uses (e.g. `Query(default=None)`), never path-param.
- [ ] `grep -rn "navigate.*\\.id" frontend/web/src/v2/` returns zero hits.
- [ ] All backend tests pass.
- [ ] Vitest + Playwright pass.
- [ ] Manual smoke test verified URLs in browser show UUIDs.

---

## Open Questions / Risks

1. **WeChat miniapp bundles a separate frontend.** This plan covers `frontend/web/`. If `frontend/wechat-miniprogram/` (or wherever the miniapp lives) makes API calls with integer IDs from cached state, those calls will start 404ing post-Phase-2. Audit before deploy.

2. **Cached deep links.** A user with a bookmarked `/doctor/patients/42` URL gets a "not found" page after Phase 3. Acceptable for an early-stage product, but worth a single sentry log line so we can quantify how often it happens.

3. **Database size impact.** ~36 bytes per row × 4 tables × n rows = trivial at our current scale. At 100k patients it's ~3.6 MB. Not a concern.

4. **Should the migration be reviewed by Codex before execution?** Per project convention (`Discuss with Codex on big tasks`), yes — run `/codex` over this plan after self-review and before kicking off Task 1.

---

## Execution Notes

- This plan should be executed in a dedicated worktree, not on `main` directly.
- Phases 2 and 3 must deploy together in production. Phase 1 is independently shippable.
- Each task ends in a commit so progress is recoverable.
- If anything in Phase 2 or 3 breaks unexpectedly, the rollback is `alembic downgrade -1` only AFTER reverting application code — never the other way around.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | FAIL | 12 findings, 0 fixed |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** flagged migration safety, scope undercount, broken tests, wrong alembic parent, layering issues, cutover hazards. Plan must be revised before execution.

**VERDICT:** PLAN BLOCKED — codex review identified critical issues. Eng review still required after revisions.

### Codex findings to address before re-running

1. **Wrong Alembic parent revision.** Plan hardcodes `down_revision = "f8b2c4e1a3d5"` but real head is `6a5d3c2e1f47`. Use `alembic heads` at execution time.
2. **Migration not safe under concurrent writes.** Add-nullable → backfill → flip-NOT-NULL has a write-window where new rows land with `public_id=NULL` and break the alter. Need either a write freeze, server-side default, or idempotent retry.
3. **Scope undercount.** Plan misses:
   - `src/channels/web/doctor_dashboard/diagnosis_handlers.py` (record paths)
   - `src/channels/web/tasks.py` (router prefix is `/api/tasks`, not `/api/manage/tasks`)
   - `src/channels/web/export/patient.py` (PDF exports leak int IDs in URLs and filenames)
   - `src/channels/web/patient_portal/tasks.py` (patient portal still exposes int task/record IDs)
   - `src/channels/web/doctor_dashboard/record_edit_handlers.py`
   - `frontend/web/src/api.js` (the main API client)
4. **Tests are broken before they test public_id.** `MessageDraft` requires `source_message_id`. `DoctorTask` valid type is `follow_up` not `followup`. Phase 1 response test hits `/api/manage/tasks` which doesn't exist.
5. **Phase 2+3 cutover is rosier than reality.** Cached clients hold int IDs in memory/localStorage/query-params. React Router `:public_id` matches `"1"` — old int URLs do NOT 404 at the route level. Need a route-side validator (UUID regex constraint) plus telemetry on int-shaped public_id values.
6. **Lookup helpers in wrong layer.** `HTTPException` in `src/db/crud/` couples HTTP into CRUD. Move helpers to a route-deps module.
7. **Existing type landmine ignored.** `MessageDraft.patient_id` is `String(64)`, joined to `Patient.id` (int). Already known issue. Plan must not regress this.
8. **"Audit/sweep" steps are underspecified.** Replace every "grep for matches" step with an explicit checklist of files derived during planning, not at execution.
9. **Integer leaks beyond URL paths:**
   - PDF download filenames embed int patient/record IDs
   - Audit rows store int `resource_id`
   - `triage_category` embeds `task.id`
10. **VARCHAR(36) vs CHAR(36) inconsistency** within the plan. Pick CHAR(36).
11. **No rollback story.** MySQL DDL autocommit means an interrupted migration leaves inconsistent state. Backfill loop not resumable.
12. **Repo fit issues.** Plan calls for full-suite runs and auto-commits which conflict with this project's "no auto-commit" and selective-test-running rules.

Until these are addressed and a re-run of `/codex review` returns a cleaner verdict, the plan is not ready for execution.

