# Interview Pipeline Extensibility — Phase 0 (Skeleton + Plumbing)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the DB and type foundation for the polymorphic interview pipeline — `template_id` column on `interview_sessions`, `preferred_template_id` on `doctors`, a new `form_responses` table, and retirement of the dead `draft_created` status. **Zero user-visible behavior change.** Every session continues to run under `medical_general_v1`.

**Architecture:** Additive DB migration (new columns + new table + data backfill). ORM + dataclass + CRUD thread `template_id` through create / load / save. `prompt_composer` accepts an ignored `template_id` passthrough so Phase 1 can wire it for real without another signature churn. An empty `src/domain/interview/` package gets created and stays empty until Phase 1.

**Tech Stack:** SQLAlchemy 2.x (`Mapped` / `mapped_column`), Alembic, pytest + pytest-asyncio, SQLite dev DB (MySQL in prod — migration is dialect-neutral).

**Reference:** Spec `docs/superpowers/specs/2026-04-22-interview-pipeline-extensibility-design.md` §§ 4a, 5a, 6a (Phase 0 row).

---

## Preconditions

- Working tree clean; branch = `main` (per repo convention, no feature branches).
- `.venv` is the project venv at `/Volumes/ORICO/Code/doctor-ai-agent/.venv`.
- All test runs use the pinned command form:
  ```
  /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest <args> \
      --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
  ```
- Current Alembic head (for `down_revision`) is `a3f8c912de75` (verify with `alembic heads` before starting).
- Spec is committed at `fa857fac`; nothing else Phase 0-related has landed yet.

## File map

Create:
- `alembic/versions/c9f8d2e14a20_interview_template_id.py` — migration
- `src/db/models/form_response.py` — `FormResponseDB` ORM model
- `src/domain/interview/__init__.py` — empty package placeholder
- `tests/db/test_migration_interview_template_id.py` — forward + round-trip test
- `tests/core/test_form_response_model.py` — FormResponseDB smoke test
- `tests/core/test_interview_session_template_id.py` — dataclass / CRUD round-trip

Modify:
- `src/db/models/interview_session.py` — add `template_id`; drop `draft_created` from `InterviewStatus`
- `src/db/models/doctor.py` — add `preferred_template_id`
- `src/domain/patients/interview_session.py` — dataclass field + CRUD threading
- `src/agent/prompt_composer.py` — add `template_id` kwarg (ignored passthrough) to `compose_for_doctor_interview` and `compose_for_patient_interview`
- `src/channels/web/doctor_interview/turn.py` — accept `template_id` form field; forward into `create_session`. (Patient endpoint unchanged — see Task 7 scope note.)
- `src/channels/web/doctor_dashboard/admin_overview.py:145` — `_completed_statuses = ("confirmed",)`
- `tests/core/test_interview_session_mode.py:31-33` — flip assertion (status is gone, not present)

---

## Task 1: Alembic migration — add `template_id`, `preferred_template_id`, `form_responses`, backfill `draft_created`

**Files:**
- Create: `alembic/versions/c9f8d2e14a20_interview_template_id.py`
- Create: `tests/db/test_migration_interview_template_id.py`

- [ ] **Step 1: Write the failing migration round-trip test**

`tests/db/test_migration_interview_template_id.py`:

```python
"""Forward + downgrade round-trip for the interview_template_id migration.

Applies every migration up to the revision under test against a fresh SQLite
DB, asserts the schema matches the spec (§4a), then downgrades one step and
asserts the change is gone.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "c9f8d2e14a20"


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture()
def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"
    yield url, path
    os.unlink(path)


def test_upgrade_creates_template_id_and_form_responses(fresh_db):
    url, _ = fresh_db
    cfg = _alembic_cfg(url)

    # Start with a session row in the old schema via pre-migration upgrade
    command.upgrade(cfg, REVISION + "^")  # one step before target
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO doctors (doctor_id) VALUES ('doc1')"))
        conn.execute(text(
            "INSERT INTO interview_sessions (id, doctor_id, status, mode, turn_count, created_at, updated_at) "
            "VALUES ('s1', 'doc1', 'draft_created', 'doctor', 0, '2026-01-01', '2026-01-01')"
        ))

    command.upgrade(cfg, REVISION)

    insp = inspect(eng)
    session_cols = {c["name"] for c in insp.get_columns("interview_sessions")}
    assert "template_id" in session_cols

    doctor_cols = {c["name"] for c in insp.get_columns("doctors")}
    assert "preferred_template_id" in doctor_cols

    assert "form_responses" in insp.get_table_names()

    # Existing session row backfilled to medical_general_v1, status retagged
    with eng.begin() as conn:
        row = conn.execute(text(
            "SELECT template_id, status FROM interview_sessions WHERE id='s1'"
        )).first()
    assert row.template_id == "medical_general_v1"
    assert row.status == "confirmed"  # draft_created → confirmed


def test_downgrade_removes_everything(fresh_db):
    url, _ = fresh_db
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, REVISION)
    command.downgrade(cfg, REVISION + "^")

    eng = create_engine(url)
    insp = inspect(eng)
    session_cols = {c["name"] for c in insp.get_columns("interview_sessions")}
    assert "template_id" not in session_cols
    doctor_cols = {c["name"] for c in insp.get_columns("doctors")}
    assert "preferred_template_id" not in doctor_cols
    assert "form_responses" not in insp.get_table_names()
```

- [ ] **Step 2: Run the test, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/db/test_migration_interview_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... FileNotFoundError` or `alembic.util.exc.CommandError: Can't locate revision identified by 'c9f8d2e14a20'`.

- [ ] **Step 3: Write the migration**

`alembic/versions/c9f8d2e14a20_interview_template_id.py`:

```python
"""Interview template_id + form_responses + retire draft_created.

Phase 0 of the interview-pipeline-extensibility work. See the spec at
docs/superpowers/specs/2026-04-22-interview-pipeline-extensibility-design.md
§4a. Additive only — zero behavior change. Existing sessions backfill to
medical_general_v1.

Revision ID: c9f8d2e14a20
Revises: a3f8c912de75
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9f8d2e14a20"
down_revision = "a3f8c912de75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. interview_sessions.template_id — server_default fills existing rows,
    #    NOT NULL guarantees every session has a template going forward.
    op.add_column(
        "interview_sessions",
        sa.Column(
            "template_id",
            sa.String(64),
            nullable=False,
            server_default="medical_general_v1",
        ),
    )
    op.create_index(
        "ix_interview_template", "interview_sessions", ["template_id"],
    )

    # 2. doctors.preferred_template_id — NULL means "follow current default".
    op.add_column(
        "doctors",
        sa.Column("preferred_template_id", sa.String(64), nullable=True),
    )

    # 3. Retire draft_created. The enum value was only read by
    #    admin_overview.py:145; we flip it to confirmed so the 7-day
    #    "completed" metric stays continuous.
    op.execute(
        "UPDATE interview_sessions SET status='confirmed' "
        "WHERE status='draft_created'"
    )

    # 4. New form_responses table.
    op.create_table(
        "form_responses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "doctor_id",
            sa.String(64),
            sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.Integer,
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="draft"
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_form_response_doctor_patient_template",
        "form_responses",
        ["doctor_id", "patient_id", "template_id"],
    )
    op.create_index(
        "ix_form_response_patient_template_created",
        "form_responses",
        ["patient_id", "template_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_form_response_patient_template_created", "form_responses",
    )
    op.drop_index(
        "ix_form_response_doctor_patient_template", "form_responses",
    )
    op.drop_table("form_responses")
    op.drop_column("doctors", "preferred_template_id")
    op.drop_index("ix_interview_template", "interview_sessions")
    op.drop_column("interview_sessions", "template_id")
```

- [ ] **Step 4: Re-run the test, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/db/test_migration_interview_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `2 passed`.

- [ ] **Step 5: Sanity-check against the live dev DB**

```
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/alembic upgrade head
.venv/bin/python -c "from sqlalchemy import create_engine, inspect; e = create_engine('sqlite:///local.db'); i = inspect(e); print('template_id' in {c[\"name\"] for c in i.get_columns('interview_sessions')}); print('form_responses' in i.get_table_names())"
```

Expected: `True` + `True`. (If your local DB path differs, substitute it; production DB is not touched.)

- [ ] **Step 6: Commit**

```
git add alembic/versions/c9f8d2e14a20_interview_template_id.py \
        tests/db/test_migration_interview_template_id.py
git commit -m "feat(db): add template_id + form_responses + retire draft_created"
```

---

## Task 2: ORM — `InterviewSessionDB.template_id` + drop `draft_created` from enum

**Files:**
- Modify: `src/db/models/interview_session.py`
- Modify: `tests/core/test_interview_session_mode.py:31-33`

- [ ] **Step 1: Flip the stale assertion**

Existing `tests/core/test_interview_session_mode.py:31-33`:

```python
def test_interview_status_has_draft_created():
    assert hasattr(InterviewStatus, "draft_created")
    assert InterviewStatus.draft_created == "draft_created"
```

Replace with:

```python
def test_interview_status_does_not_have_draft_created():
    """draft_created was retired by the c9f8d2e14a20 migration. The enum
    must not re-expose it or stale callsites will silently insert a value
    the DB no longer understands."""
    assert not hasattr(InterviewStatus, "draft_created")
```

- [ ] **Step 2: Run the test, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_mode.py::test_interview_status_does_not_have_draft_created -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... AssertionError` (the enum still has the value).

- [ ] **Step 3: Update the ORM model**

In `src/db/models/interview_session.py`, change the `InterviewStatus` enum (currently at lines 15-22) to:

```python
class InterviewStatus(str, Enum):
    """Patient interview session lifecycle.

    draft_created was retired in migration c9f8d2e14a20. It was set by a
    legacy doctor-side save-as-draft flow that no longer exists; the
    backfill flips any existing rows to 'confirmed'.
    """
    interviewing = "interviewing"
    reviewing = "reviewing"
    confirmed = "confirmed"
    abandoned = "abandoned"
```

Then in the `InterviewSessionDB` class body (currently lines 25-41), add `template_id` between `mode` and `collected`:

```python
    template_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="medical_general_v1",
    )
```

Update `__table_args__` to include the new index:

```python
    __table_args__ = (
        Index("ix_interview_patient", "patient_id", "status"),
        Index("ix_interview_doctor", "doctor_id", "status"),
        Index("ix_interview_template", "template_id"),
    )
```

- [ ] **Step 4: Run the test, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_mode.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all tests in the file pass.

- [ ] **Step 5: Grep for other `draft_created` references and confirm nothing else breaks**

```
grep -rn "draft_created" src tests --include="*.py"
```

Expected: only two remaining references, both to be fixed in later tasks:
- `src/channels/web/doctor_dashboard/admin_overview.py:145` (Task 7)
- Nothing else.

If anything else shows up, stop and reassess — the enum removal may be breaking callers this plan didn't account for.

- [ ] **Step 6: Commit**

```
git add src/db/models/interview_session.py tests/core/test_interview_session_mode.py
git commit -m "refactor(db): add InterviewSessionDB.template_id + drop draft_created enum"
```

---

## Task 3: ORM — `Doctor.preferred_template_id`

**Files:**
- Modify: `src/db/models/doctor.py`
- Create (append to): `tests/core/test_interview_session_template_id.py`

- [ ] **Step 1: Write a failing test**

`tests/core/test_interview_session_template_id.py` (new file — Task 5 appends more to it):

```python
"""Template id threading: Doctor.preferred_template_id + InterviewSession CRUD."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_defaults_to_null(fresh_db):
    async with AsyncSessionLocal() as db:
        d = Doctor(doctor_id="test_pref_null", name="Test Doctor")
        db.add(d)
        await db.commit()

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == "test_pref_null")
        )).scalar_one()
        assert row.preferred_template_id is None


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_can_be_set(fresh_db):
    async with AsyncSessionLocal() as db:
        d = Doctor(
            doctor_id="test_pref_set",
            name="Test Doctor",
            preferred_template_id="medical_general_v1",
        )
        db.add(d)
        await db.commit()

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == "test_pref_set")
        )).scalar_one()
        assert row.preferred_template_id == "medical_general_v1"
```

The `fresh_db` fixture already exists in `tests/conftest.py` — it runs Alembic head against an in-memory SQLite. Confirm with `grep -n "fresh_db" tests/conftest.py`. If it does not exist, add this to `tests/core/test_interview_session_template_id.py` above the tests:

```python
@pytest.fixture()
async def fresh_db():
    """Apply head Alembic migrations to a fresh SQLite, yield, tear down."""
    import os, tempfile
    from alembic import command
    from alembic.config import Config
    from db.engine import engine  # noqa

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite:///{path}"
    # Swap engine URL — project-specific glue; check db/engine.py for the
    # correct override hook if this fixture ends up being needed.
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    yield
    os.unlink(path)
```

(In practice the project uses a session-scoped auto-migrate pattern — check `tests/conftest.py` before committing this.)

- [ ] **Step 2: Run the test, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... AttributeError: 'Doctor' object has no attribute 'preferred_template_id'`.

- [ ] **Step 3: Add the column to `Doctor`**

In `src/db/models/doctor.py`, inside the `Doctor` class body (after `finished_onboarding`, before `__table_args__`):

```python
    preferred_template_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
```

- [ ] **Step 4: Run the test, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `2 passed`.

- [ ] **Step 5: Grep-verify onboarding does not write `preferred_template_id` as a literal**

Spec §4d requires onboarding to write `NULL` (not `"medical_general_v1"` or any other literal) so auto-migration on future version bumps keeps working. The column is nullable and unset by default, so this is a *negative* requirement — nothing should explicitly set it.

```
grep -rn "preferred_template_id" src frontend --include="*.py" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"
```

Expected: only matches are the ORM definition in `src/db/models/doctor.py` you just added. If any onboarding code, admin script, or signup flow assigns a string literal to `preferred_template_id`, stop and remove that assignment — the plan does not mask that regression.

- [ ] **Step 6: Commit**

```
git add src/db/models/doctor.py tests/core/test_interview_session_template_id.py
git commit -m "refactor(db): add Doctor.preferred_template_id column"
```

---

## Task 4: ORM new model — `FormResponseDB`

**Files:**
- Create: `src/db/models/form_response.py`
- Create: `tests/core/test_form_response_model.py`
- Modify: `src/db/models/__init__.py` (only if the project re-exports models there — verify before editing)

- [ ] **Step 1: Write a failing smoke test**

`tests/core/test_form_response_model.py`:

```python
"""FormResponseDB ORM smoke test — round-trip a row through SQLAlchemy."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient


@pytest.mark.asyncio
async def test_form_response_round_trip(fresh_db):
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id="doc_fr"))
        await db.flush()
        patient = Patient(doctor_id="doc_fr", name="王五")
        db.add(patient)
        await db.commit()
        patient_id = patient.id

    async with AsyncSessionLocal() as db:
        row = FormResponseDB(
            doctor_id="doc_fr",
            patient_id=patient_id,
            template_id="form_satisfaction_v1",
            payload={"q1": "5", "q2": "very good"},
        )
        db.add(row)
        await db.commit()
        fr_id = row.id

    async with AsyncSessionLocal() as db:
        fetched = (await db.execute(
            select(FormResponseDB).where(FormResponseDB.id == fr_id)
        )).scalar_one()
        assert fetched.template_id == "form_satisfaction_v1"
        assert fetched.payload == {"q1": "5", "q2": "very good"}
        assert fetched.status == "draft"  # server_default
        assert fetched.session_id is None
```

- [ ] **Step 2: Run the test, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_form_response_model.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... ModuleNotFoundError: No module named 'db.models.form_response'`.

- [ ] **Step 3: Create the ORM model**

`src/db/models/form_response.py`:

```python
"""Form response persistence (Phase 0 of interview-pipeline-extensibility).

A form response is the non-medical-record output of an interview template
whose kind is "form" (e.g. form_satisfaction_v1). Medical templates still
write to medical_records; this table is for everything else.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class FormResponseDB(Base):
    __tablename__ = "form_responses"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    doctor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow,
    )

    __table_args__ = (
        Index(
            "ix_form_response_doctor_patient_template",
            "doctor_id", "patient_id", "template_id",
        ),
        Index(
            "ix_form_response_patient_template_created",
            "patient_id", "template_id", "created_at",
        ),
    )
```

- [ ] **Step 4: If the project re-exports models, register the new one**

```
grep -n "from db.models" src/db/models/__init__.py 2>/dev/null
grep -n "form_response\|FormResponseDB" src/db/models/__init__.py 2>/dev/null
```

If `__init__.py` contains explicit re-exports (e.g. `from db.models.doctor import Doctor`), add a matching line. If it's empty or just a namespace file, skip this step.

- [ ] **Step 5: Run the test, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_form_response_model.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```
git add src/db/models/form_response.py tests/core/test_form_response_model.py
# plus src/db/models/__init__.py if you edited it
git commit -m "feat(db): add FormResponseDB ORM model"
```

---

## Task 5: Dataclass + CRUD — `InterviewSession.template_id`

**Files:**
- Modify: `src/domain/patients/interview_session.py`
- Modify: `tests/core/test_interview_session_template_id.py` (append)

- [ ] **Step 1: Append failing tests for CRUD threading**

In `tests/core/test_interview_session_template_id.py`, append:

```python
import pytest
from domain.patients.interview_session import (
    create_session, load_session, save_session,
)


@pytest.mark.asyncio
async def test_create_session_defaults_template_id_to_medical_general_v1(fresh_db):
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id="doc_ct"))
        await db.commit()

    session = await create_session(doctor_id="doc_ct", patient_id=None)
    assert session.template_id == "medical_general_v1"

    loaded = await load_session(session.id)
    assert loaded is not None
    assert loaded.template_id == "medical_general_v1"


@pytest.mark.asyncio
async def test_create_session_accepts_explicit_template_id(fresh_db):
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id="doc_ex"))
        await db.commit()

    session = await create_session(
        doctor_id="doc_ex",
        patient_id=None,
        template_id="form_satisfaction_v1",
    )
    assert session.template_id == "form_satisfaction_v1"

    loaded = await load_session(session.id)
    assert loaded.template_id == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_save_session_preserves_template_id(fresh_db):
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id="doc_sv"))
        await db.commit()

    session = await create_session(
        doctor_id="doc_sv",
        patient_id=None,
        template_id="form_satisfaction_v1",
    )
    session.turn_count = 3
    await save_session(session)

    loaded = await load_session(session.id)
    assert loaded.template_id == "form_satisfaction_v1"
    assert loaded.turn_count == 3
```

- [ ] **Step 2: Run, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: three failures, all `TypeError: create_session() got an unexpected keyword argument 'template_id'` or `AttributeError: 'InterviewSession' object has no attribute 'template_id'`.

- [ ] **Step 3: Thread `template_id` through the dataclass and CRUD**

In `src/domain/patients/interview_session.py`:

Add the field to the dataclass (line 16-24 range):

```python
@dataclass
class InterviewSession:
    id: str
    doctor_id: str
    patient_id: Optional[int]
    mode: str = "patient"
    status: str = InterviewStatus.interviewing
    template_id: str = "medical_general_v1"
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
```

Update `create_session` signature (line 27-32):

```python
async def create_session(
    doctor_id: str,
    patient_id: Optional[int],
    mode: str = "patient",
    initial_fields: Optional[Dict[str, str]] = None,
    template_id: str = "medical_general_v1",
) -> InterviewSession:
```

Inside `create_session`, update the `InterviewSessionDB(...)` construction (around line 73-85) to pass `template_id=template_id`, and update the returned dataclass construction (around line 90-97) to include `template_id=template_id`.

Update `load_session` (around lines 100-122) — add `template_id=row.template_id` to the returned `InterviewSession(...)`.

Update `save_session` (around lines 125-146) — add `row.template_id = session.template_id` to the field updates.

Update `get_active_session` (around lines 149-175) — add `template_id=row.template_id` to the returned `InterviewSession(...)`.

- [ ] **Step 4: Run, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `5 passed` (2 from Task 3 + 3 from Task 5).

- [ ] **Step 5: Commit**

```
git add src/domain/patients/interview_session.py \
        tests/core/test_interview_session_template_id.py
git commit -m "refactor(interview): thread template_id through dataclass + CRUD"
```

---

## Task 6: `prompt_composer` passthrough

**Files:**
- Modify: `src/agent/prompt_composer.py`

- [ ] **Step 1: Write a failing test**

Append to `tests/core/test_interview_session_template_id.py`:

```python
@pytest.mark.asyncio
async def test_prompt_composer_accepts_template_id_kwarg():
    """Passthrough only — Phase 0 doesn't wire template_id into prompt
    selection yet, but the signature must accept it so Phase 1 can plumb
    it without another churn."""
    from agent.prompt_composer import (
        compose_for_doctor_interview, compose_for_patient_interview,
    )
    import inspect

    for fn in (compose_for_doctor_interview, compose_for_patient_interview):
        sig = inspect.signature(fn)
        assert "template_id" in sig.parameters
        assert sig.parameters["template_id"].default == "medical_general_v1"
```

- [ ] **Step 2: Run, confirm it fails**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py::test_prompt_composer_accepts_template_id_kwarg -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: `FAILED ... AssertionError`.

- [ ] **Step 3: Add the kwarg**

In `src/agent/prompt_composer.py`:

- `compose_for_doctor_interview` (around line 198) — add `template_id: str = "medical_general_v1"` as a keyword-only parameter, after the existing trailing params. Do not reference it inside the function body yet. Add a one-line docstring note: `# Accepted for Phase-1 plumbing; currently ignored.`
- `compose_for_patient_interview` (around line 238) — same change.

Example (shape only — match each function's existing signature style):

```python
async def compose_for_patient_interview(
    ...,
    template_id: str = "medical_general_v1",  # Accepted for Phase 1 plumbing; currently ignored.
) -> ...:
    ...
```

- [ ] **Step 4: Run, confirm it passes**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_template_id.py -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all six tests pass.

- [ ] **Step 5: Commit**

```
git add src/agent/prompt_composer.py tests/core/test_interview_session_template_id.py
git commit -m "refactor(prompt): accept template_id kwarg in interview composers"
```

---

## Task 7: API surface — thread `template_id` through the doctor session-create endpoint

**Files:**
- Modify: `src/channels/web/doctor_interview/turn.py` (endpoint around line 60-85, `_first_turn` around line 88-107)

**Scope note:** only the doctor endpoint changes. The patient endpoint (`/patient/interview/start` at `patient_interview_routes.py:49-90`) takes no request body — patients don't choose their template; the doctor's `preferred_template_id` would, but that fallback lands in Phase 1. For Phase 0, the patient endpoint keeps calling `create_session(...)` with no `template_id` argument, so `InterviewSession.template_id` defaults to `"medical_general_v1"` (Task 5). Nothing else to wire on the patient side.

The doctor endpoint uses FastAPI `Form(...)` parameters, not a Pydantic body model — confirmed by reading lines 58-75. The change is to add one more `Form` field and forward it to the internal `_first_turn` helper.

- [ ] **Step 1: Inspect the current callsite**

```
sed -n '58,115p' src/channels/web/doctor_interview/turn.py
```

You'll see:
- `interview_turn_endpoint` route handler with `text`, `session_id`, `doctor_id`, `patient_id`, `file`, `authorization` as `Form`/`File`/`Header` params.
- `_first_turn(doctor_id, text, pre_patient_id=None)` helper that calls `create_session(...)`.

- [ ] **Step 2: Add the new form field to the endpoint**

In `src/channels/web/doctor_interview/turn.py`, update `interview_turn_endpoint` to accept one more form field (insert it between `patient_id` and `file` to keep positional arg clustering readable):

```python
@router.post("/turn", response_model=DoctorInterviewResponse)
async def interview_turn_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(default=None),
    doctor_id: str = Form(default=""),
    patient_id: Optional[str] = Form(default=None),
    template_id: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
```

Then change the first-turn branch call (currently `return await _first_turn(resolved_doctor, merged_text, resolved_patient_id)`) to forward the new value:

```python
return await _first_turn(
    resolved_doctor, merged_text, resolved_patient_id,
    template_id=template_id,
)
```

- [ ] **Step 3: Update the `_first_turn` helper to accept and use it**

Current `_first_turn` signature (around line 88):

```python
async def _first_turn(doctor_id, text, pre_patient_id=None):
```

Change to:

```python
async def _first_turn(doctor_id, text, pre_patient_id=None, *, template_id=None):
```

The existing `create_session(...)` call inside this helper (around line 107):

```python
session = await create_session(
    doctor_id, patient_id=pre_patient_id, mode="doctor",
    initial_fields=initial_fields,
)
```

Changes to:

```python
session = await create_session(
    doctor_id, patient_id=pre_patient_id, mode="doctor",
    initial_fields=initial_fields,
    template_id=template_id or "medical_general_v1",
)
```

- [ ] **Step 4: Write an integration test**

First, grep for an existing doctor-interview endpoint test to copy its auth setup:

```
ls tests/channels/ 2>/dev/null
grep -rln "doctor_interview\|doctor/interview/turn" tests/ --include="*.py"
```

If a harness exists (likely in `tests/channels/` or `tests/api/`), add a test in the same style:

```python
# tests/channels/test_doctor_interview_template_id.py
"""Doctor /turn endpoint accepts optional template_id form field."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

# Import pattern must match project convention — copy from an existing
# channels test. Example shape:
# from tests.channels.conftest import build_authed_client


@pytest.mark.asyncio
async def test_doctor_turn_honors_explicit_template_id(authed_doctor_client):
    resp = await authed_doctor_client.post(
        "/api/doctor/interview/turn",
        data={"text": "患者主诉头痛", "template_id": "form_satisfaction_v1"},
    )
    assert resp.status_code == 200

    from domain.patients.interview_session import load_session
    session = await load_session(resp.json()["session_id"])
    assert session.template_id == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_doctor_turn_defaults_template_id_when_omitted(authed_doctor_client):
    resp = await authed_doctor_client.post(
        "/api/doctor/interview/turn",
        data={"text": "患者主诉头痛"},
    )
    assert resp.status_code == 200

    from domain.patients.interview_session import load_session
    session = await load_session(resp.json()["session_id"])
    assert session.template_id == "medical_general_v1"
```

If the project has no HTTP-level test harness for doctor_interview, add a thinner unit test against `_first_turn` instead, mocking `create_session`:

```python
# tests/core/test_doctor_first_turn_template_id.py
from unittest.mock import patch, AsyncMock
import pytest
from channels.web.doctor_interview.turn import _first_turn


@pytest.mark.asyncio
async def test_first_turn_passes_template_id_to_create_session():
    with patch(
        "channels.web.doctor_interview.turn.create_session",
        new=AsyncMock(),
    ) as mock_create:
        mock_create.return_value = type("S", (), {"id": "s1", "collected": {}})()
        with patch(
            "channels.web.doctor_interview.turn.interview_turn",
            new=AsyncMock(),
        ), patch(
            "channels.web.doctor_interview.turn.resolve",
            new=AsyncMock(),
        ):
            await _first_turn("doc", "hi", template_id="form_satisfaction_v1")

    args, kwargs = mock_create.call_args
    assert kwargs["template_id"] == "form_satisfaction_v1"
```

Pick whichever style matches the project's existing patterns — don't invent a new harness.

- [ ] **Step 5: Run the tests you just added**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/channels/test_doctor_interview_template_id.py \
    tests/core/test_doctor_first_turn_template_id.py \
    -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

(Whichever of the two you created.) Expected: pass.

- [ ] **Step 6: Commit**

```
git add src/channels/web/doctor_interview/turn.py \
        tests/channels/test_doctor_interview_template_id.py  # or tests/core/test_doctor_first_turn_template_id.py
git commit -m "feat(api): accept optional template_id on doctor interview /turn"
```

---

## Task 8: `admin_overview.py` — drop `draft_created` from `_completed_statuses`

**Files:**
- Modify: `src/channels/web/doctor_dashboard/admin_overview.py:145`

- [ ] **Step 1: Inspect the current line**

```
sed -n '140,155p' src/channels/web/doctor_dashboard/admin_overview.py
```

Current line 145 is:

```python
    _completed_statuses = ("confirmed", "draft_created")
```

- [ ] **Step 2: Grep for any test covering admin_overview**

```
grep -rln "admin_overview\|_completed_statuses" tests
```

If a test exists, read it to understand what `_completed_statuses` drives (likely a 7-day completed-sessions metric). Update the test to no longer reference `draft_created`.

- [ ] **Step 3: Update the tuple**

Change line 145 to:

```python
    _completed_statuses = ("confirmed",)
```

The migration in Task 1 already flipped every historical `draft_created` row to `confirmed`, so the metric stays continuous.

- [ ] **Step 4: Run any admin_overview test + the full interview suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_mode.py \
    tests/core/test_interview_session_template_id.py \
    -k "admin or interview" -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add src/channels/web/doctor_dashboard/admin_overview.py
# plus any test file adjusted
git commit -m "refactor(dashboard): drop draft_created from completed-status set"
```

---

## Task 9: Empty `src/domain/interview/` package

**Files:**
- Create: `src/domain/interview/__init__.py`

- [ ] **Step 1: Verify the directory does not exist yet**

```
ls src/domain/interview 2>/dev/null || echo "does not exist — good"
```

- [ ] **Step 2: Create the package stub**

`src/domain/interview/__init__.py`:

```python
"""Polymorphic interview pipeline (spec 2026-04-22).

Phase 0 reserves this package. Phase 1 will add protocols.py (FieldExtractor,
BatchExtractor, Writer, PostConfirmHook, Template) and contract.py
(build_response_schema). No code imports from here in Phase 0.
"""
```

- [ ] **Step 3: Verify nothing imports from here yet**

```
grep -rn "from domain.interview\|import domain.interview" src tests
```

Expected: zero matches. If anything appears, stop — Phase 1 leaked into Phase 0.

- [ ] **Step 4: Commit**

```
git add src/domain/interview/__init__.py
git commit -m "chore(interview): reserve domain/interview package for Phase 1"
```

---

## Task 10: Final regression sweep

**Files:** none — verification only.

- [ ] **Step 1: Run the full test suite**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -q
```

Expected: pre-existing failures (if any) match `main` baseline. No new failures.

If new failures appear, investigate — Phase 0 is additive and must not regress.

- [ ] **Step 2: Run the interview-specific suite in full verbose**

```
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest \
    tests/core/test_interview_session_mode.py \
    tests/core/test_interview_session_template_id.py \
    tests/core/test_form_response_model.py \
    tests/db/test_migration_interview_template_id.py \
    tests/channels/test_session_create_template_id.py \
    -v \
    --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: every file passes.

- [ ] **Step 3: Grep-verify all Phase 0 invariants hold**

```
# draft_created has been fully retired
grep -rn "draft_created" src tests --include="*.py" \
    | grep -v "retired\|migration\|c9f8d2e14a20"
# Expected: zero matches (only references are in the migration itself or docstrings)

# template_id is threaded everywhere a session is read or written
grep -rn "InterviewSession\b" src --include="*.py"
# Expected: every result site either has template_id or only touches the
# dataclass id/doctor_id — eyeball-check.

# domain/interview is still empty apart from __init__.py
ls src/domain/interview/
# Expected: __init__.py only.
```

- [ ] **Step 4: Run the interview sim baseline (if available)**

```
# Check what the current sim entrypoint is
ls tests/sim/ 2>/dev/null || ls scripts/ | grep -i sim
```

Run whatever `reply_sim` / `interview_sim` script the repo exposes, against `main` HEAD and against the current HEAD, and diff pass rates. Phase 0 target: **delta ≤ 2%**, per spec §7a.

If no sim infrastructure is scripted yet, note that the sim baseline capture is deferred to Phase 1 (when engine extraction creates a real risk surface) and move on.

- [ ] **Step 5: No commit — Phase 0 complete**

At this point nine tasks have produced nine commits, each green in isolation. The working tree should be clean. Phase 1 can begin.

```
git status
git log --oneline main..HEAD
```

Expected: clean tree; nine commits listed, all of form `feat|refactor|chore(...): ...`.

---

## Phase 0 completion checklist

- [ ] Alembic head is `c9f8d2e14a20` (run `.venv/bin/alembic heads`)
- [ ] `interview_sessions.template_id` exists, NOT NULL, indexed
- [ ] Every existing row has `template_id = 'medical_general_v1'`
- [ ] `doctors.preferred_template_id` exists, nullable, all existing rows NULL
- [ ] `form_responses` table exists with the two indexes from §4a
- [ ] No row in `interview_sessions` has status `draft_created`
- [ ] `InterviewStatus` enum has exactly 4 values: interviewing, reviewing, confirmed, abandoned
- [ ] `InterviewSession` dataclass carries `template_id`; `create_session` / `load_session` / `save_session` / `get_active_session` all thread it
- [ ] `compose_for_doctor_interview` / `compose_for_patient_interview` accept `template_id` (ignored)
- [ ] Session-create endpoints (doctor + patient) accept optional `template_id` in the request body
- [ ] `admin_overview.py:145` uses `("confirmed",)`
- [ ] `src/domain/interview/__init__.py` exists and is empty
- [ ] Full test suite matches main baseline (no new failures)

## What Phase 0 does NOT do (saved for Phase 1)

- Introduce protocols (`FieldExtractor`, `Writer`, `PostConfirmHook`, `Template`).
- Move any medical logic out of `interview_models.py` / `completeness.py` / `doctor_interview/shared.py`.
- Wire `preferred_template_id` into session-create precedence (Phase 0 only honors the explicit request param).
- Change prompt selection (both modes still load the hardcoded prompt files).
- Build the `/form_responses` read-back endpoints.
- Add specialty variants.
- Resolve the §8 open product question about doctor-mode diagnosis.

Phase 0 is plumbing. Everything visible happens in Phase 1 and beyond.
