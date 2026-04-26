# Public ID Migration Implementation Plan (v2 — post-codex-review)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 changelog:** Rewrote to address all `/codex review` findings on the v1 plan. Major changes:
> 1. Alembic parent revision is now resolved at execution time, not hardcoded (head moves between sessions).
> 2. Migration backfill is idempotent (`WHERE public_id IS NULL`) and tolerant of new rows arriving during the window.
> 3. Explicit file inventory replaces every "audit/sweep" step.
> 4. Lookup helpers live in `src/channels/web/doctor_dashboard/public_id_resolver.py` (HTTP layer), not `src/db/crud/`.
> 5. Tests fixed: `MessageDraft` requires `source_message_id`, `DoctorTask` type is `follow_up` (not `followup`), task list endpoint is `/api/tasks` (not `/api/manage/tasks`).
> 6. `CHAR(36)` everywhere (was inconsistently `VARCHAR(36)`).
> 7. Per-phase rollback sections.
> 8. No auto-commits between tasks; commit only when the user asks.
> 9. Selective `pytest -k` over full-suite runs.
> 10. Acknowledges `MessageDraft.patient_id String(64)` landmine — plan must not regress this.

**Goal:** Replace auto-increment integer IDs with opaque UUIDv4 `public_id` strings in all user-visible URLs and API path params for `patients`, `medical_records`, `message_drafts`, and `doctor_tasks`. Eliminates ID enumeration and weakens any future IDOR vulnerabilities.

**Architecture:** Three phases, additive then cutover. Phase 1 adds `public_id` columns (nullable → backfill → NOT NULL + UNIQUE), wires the field on each model, and exposes `public_id` in API JSON responses alongside the existing integer `id`. Phase 2 introduces a doctor-scoped `public_id` resolver in the HTTP layer and switches every URL-exposed route from `{int_id}` path params to `{public_id}` (string). Phase 3 updates the frontend so every `navigate()` call and every `api.js` URL builder forwards `public_id` from the API response. Internal foreign keys keep using integer `id` for join performance.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, FastAPI, React Router v6, SQLite (dev) / MySQL (prod), pytest, vitest, Playwright.

---

## Scope

**In scope (4 tables):**

| Table | Model | URL surface |
|-------|-------|-------------|
| `patients` | `db.models.patient.Patient` | `/doctor/patients/{id}`, `/api/manage/patients/{id}/...`, `/api/admin/patients/{id}/...`, `/api/patients/{id}/form_responses`, PDF export endpoints |
| `medical_records` | `db.models.records.MedicalRecordDB` | `/doctor/review/{id}`, `/api/manage/records/{id}`, `/api/admin/records/{id}`, `/api/doctor/records/{id}/...`, `/api/tasks/record/{id}`, `/api/patient/records/{id}` |
| `message_drafts` | `db.models.message_draft.MessageDraft` | `/api/manage/drafts/{id}/{send,edit,dismiss,send-confirmation,save-as-rule}` |
| `doctor_tasks` | `db.models.tasks.DoctorTask` | `/api/tasks/{id}/...`, `/api/patient/tasks/{id}/...`, `/patient/tasks/{id}` |

**Explicitly out of scope:**

- `doctors` — `doctor_id` is already an opaque string.
- `patient_messages`, `ai_suggestions`, `doctor_personas`, `doctor_knowledge_items`, `audit_log`, `intake_sessions` — not in URLs.
- `knowledge_items` — `/doctor/settings/knowledge/{id}` exists but is not part of this plan.
- WeChat / WeCom channels — they don't use REST URL params for these entities.
- Internal foreign-key columns — `medical_records.patient_id`, `doctor_tasks.patient_id`, `message_drafts.patient_id|source_message_id`, etc. all keep integer `id` for join performance.
- PDF download filenames that embed integer IDs (user's local Downloads folder, not a URL surface).
- `audit_log.resource_id` (internal, never rendered).
- `patient_messages.triage_category` even when it embeds `task.id` (internal label, not a URL).

## Design Decisions

1. **UUIDv4, not hashids.** UUIDv4 has 122 bits of randomness; collision probability is ~10⁻³⁶ per row. Hashids reverse to integer and aren't actually opaque.
2. **`CHAR(36)` (UUID with dashes) everywhere.** Both SQLite and MySQL accept it. Cross-engine portable. ~16 bytes more per row than binary UUID, negligible at our scale.
3. **Client-side default (`default=lambda: str(uuid4())`)**, not server-side. SQLAlchemy default fires on every insert; works identically across SQLite and MySQL.
4. **Idempotent backfill.** All `UPDATE ... SET public_id = :pid WHERE public_id IS NULL` so the migration can be retried after partial failure. New rows inserted between `ADD COLUMN` and `ALTER COLUMN NOT NULL` are filled by the same statement.
5. **No write freeze required for beta.** Write volume is low. The migration runs in seconds. If ever deployed at higher scale, prepend a brief read-only window via the application layer.
6. **Three deployable phases.** Phase 1 is independently shippable (zero behavior change). Phase 2 + 3 must deploy together — backend stops accepting integer-id paths the same moment the frontend stops generating them.
7. **No backwards-compatibility for old int URLs after cutover.** Stale clients hit 404 at the API. Acceptable in beta. (`React Router :public_id` will happily match `"42"` on the route; the API call fails and the page renders an error state — that's the correct UX for a stale bookmark.)
8. **Lookup helpers live in the HTTP layer (`src/channels/web/doctor_dashboard/public_id_resolver.py`)**, not in `src/db/crud/`. Raising `HTTPException` from CRUD couples the data layer to FastAPI; the resolver is the right place.
9. **Resolver returns identical 404 for "not found" and "wrong doctor"** so the caller can't enumerate via differential errors.
10. **`MessageDraft.patient_id` is `String(64)` (existing landmine).** Plan must not regress this — `draft.patient_id` is already coerced to int at every call site. We propagate the existing pattern; no new coercions added.

---

## Concrete File Inventory (verified at planning time)

This replaces every "audit/sweep" or "grep for X" step in v1.

### Backend — handlers with `{patient_id|record_id|draft_id|task_id}` path params (all must convert in Phase 2)

| File | Lines | Endpoints |
|------|-------|-----------|
| `src/channels/web/form_responses.py` | 53 | `GET /api/patients/{patient_id}/form_responses` |
| `src/channels/web/tasks.py` | 138, 247, 275, 296, 324 | `/api/tasks/{task_id}`, `/notes`, `/due`, `/api/tasks/record/{record_id}` |
| `src/channels/web/patient_portal/tasks.py` | 120, 154, 197, 314 | patient-portal task endpoints |
| `src/channels/web/doctor_dashboard/patient_detail_handlers.py` | 131, 197, 294, 324 | `/api/manage/patients/{patient_id}/{timeline,'',chat,reply}` (delete is on line 197) |
| `src/channels/web/doctor_dashboard/record_edit_handlers.py` | 39, 118, 133, 178 | `/api/manage/records/{record_id}` PATCH/DELETE/entries, `/api/admin/records/{record_id}` |
| `src/channels/web/doctor_dashboard/diagnosis_handlers.py` | 164, 207, 371, 415 | `/api/doctor/records/{record_id}/{diagnose,suggestions,review/finalize}` |
| `src/channels/web/doctor_dashboard/draft_handlers.py` | 358, 408, 473, 501, 581 | `/api/manage/drafts/{draft_id}/{send,edit,dismiss,send-confirmation,save-as-rule}` |
| `src/channels/web/doctor_dashboard/admin_overview.py` | 1689 | `/api/admin/patients/{patient_id}/related` |
| `src/channels/web/export/patient.py` | 138, 208, 240 | `/api/export/...` (PDF endpoints — URLs only; filenames stay int per "out of scope") |
| `src/channels/web/doctor_dashboard/feedback_handlers.py` | 71 | record_id (verify path at execution) |

### Backend — handlers that take patient_id/record_id as Query/body (NOT path) — review for whether they should accept public_id too

| File | Lines | Notes |
|------|-------|-------|
| `src/channels/web/doctor_dashboard/admin_messages.py` | 235 | `?patient_id=...` Query — keep int? It's an admin route. **Decision:** keep int for admin-only routes. |
| `src/channels/web/doctor_dashboard/admin_overview.py` | 1255 | Same — admin route, keep int. |
| `src/channels/web/doctor_dashboard/new_patient_handlers.py` | 65 | Inspect at execution; if it constructs URLs the frontend hits, convert. |
| `src/channels/web/doctor_dashboard/onboarding_handlers.py` | 46, 158, 275, 353 | Inspect at execution. |
| `src/channels/web/patient_portal/registration.py` | 37, 41 | Inspect at execution. |
| `src/channels/web/patient_portal/auth.py` | 52 | Internal auth helper, keep int. |

### Frontend — `navigate()` callsites that use entity `.id` (Phase 3)

| File | Lines | Pattern |
|------|-------|---------|
| `frontend/web/src/v2/pages/doctor/PatientDetail.jsx` | 848, 852 | `/doctor/review/${pending.id\|record.id}` |
| `frontend/web/src/v2/pages/doctor/PatientsPage.jsx` | 253, 337 | `/doctor/patients/${patient.id}`, `?patient_id=${patient.id}` |
| `frontend/web/src/v2/pages/doctor/MyAIPage.jsx` | 754 | `dp(\`patients/${item.id}\`)` |
| `frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx` | 307, 311, 316, 319, 321 | `item.patient_id`, `item.record_id` |
| `frontend/web/src/v2/pages/doctor/settings/TaskDetailSubpage.jsx` | 84, 309, 310, 362 | `task.patient_id`, `task.record_id` |
| `frontend/web/src/v2/pages/doctor/settings/KnowledgeDetailSubpage.jsx` | 281 | `usage.patient_id` |
| `frontend/web/src/v2/pages/doctor/settings/KnowledgeSubpage.jsx` | 537, 541 | `link.record_id`, `link.patient_id` |
| `frontend/web/src/v2/pages/doctor/IntakePage.jsx` | 710 | `recordId` (verify at execution) |
| `frontend/web/src/v2/pages/patient/TasksTab.jsx` | 199 | `/patient/tasks/${item.id}` |

### Frontend — `api.js` URL builders that take entity IDs (Phase 3)

| Group | Lines |
|-------|-------|
| Patient endpoints | 221, 508, 514, 520, 550, 1187, 1191 |
| Record endpoints | 489, 498, 503, 670, 1123, 1201, 1209, 1221, 1321 |
| Draft endpoints | 1286, 1290, 1298, 1302 |
| Task endpoints | 613, 622, 646, 651, 1131, 1135, 1139 |

Every function in these line ranges currently accepts an integer ID parameter and embeds it in a path. Each must be updated to accept and forward `public_id` instead. The function names and signatures change; every caller (≈ all the files in the navigate table above) must update.

---

# PHASE 1 — Additive Schema + Model + API Response Changes

Goal: ship a backend that has `public_id` populated everywhere and exposes it in JSON responses. No URL changes yet. App behavior unchanged. Independently deployable.

## Task 1: Schema migration — add `public_id` columns + idempotent backfill + UNIQUE

**Files:**
- Create: `alembic/versions/<rev>_add_public_id_columns.py` (alembic generates the rev id)

- [ ] **Step 1: Resolve current head**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic heads
```

Note the printed revision id. **Use whatever alembic prints**; do not hardcode. (As of this writing it was `4d8e7a2c1f93`, but it changes with every merged migration.)

- [ ] **Step 2: Generate the migration file**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "add public_id columns"
```

Note the generated filename and its `revision = "..."` line. Confirm `down_revision` is set to the head from Step 1.

- [ ] **Step 3: Replace the migration body**

```python
"""add public_id columns

Adds CHAR(36) public_id (UUIDv4) to four tables that appear in user-visible
URLs: patients, medical_records, message_drafts, doctor_tasks. Backfills
existing rows with fresh UUIDs (idempotent — only fills WHERE public_id IS
NULL), then enforces NOT NULL + UNIQUE.

Revision ID: <leave whatever alembic generated>
Revises: <whatever Step 1 returned>
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "<as generated>"
down_revision = "<from Step 1>"
branch_labels = None
depends_on = None


_TABLES = ("patients", "medical_records", "message_drafts", "doctor_tasks")


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        op.add_column(table, sa.Column("public_id", sa.CHAR(36), nullable=True))
        # Idempotent backfill — fills any row missing a public_id, including
        # rows that arrived between ADD COLUMN and this UPDATE.
        rows = bind.execute(
            sa.text(f"SELECT id FROM {table} WHERE public_id IS NULL")
        ).all()
        for (row_id,) in rows:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET public_id = :pid "
                    f"WHERE id = :rid AND public_id IS NULL"
                ),
                {"pid": str(uuid.uuid4()), "rid": row_id},
            )
        # Re-check: anything still NULL means a row arrived after our SELECT.
        # Fill again before the NOT NULL flip.
        leftover = bind.execute(
            sa.text(f"SELECT id FROM {table} WHERE public_id IS NULL")
        ).all()
        for (row_id,) in leftover:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET public_id = :pid "
                    f"WHERE id = :rid AND public_id IS NULL"
                ),
                {"pid": str(uuid.uuid4()), "rid": row_id},
            )
        with op.batch_alter_table(table) as batch:
            batch.alter_column("public_id", existing_type=sa.CHAR(36), nullable=False)
        op.create_index(
            f"ix_{table}_public_id", table, ["public_id"], unique=True,
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_public_id", table_name=table)
        op.drop_column(table, "public_id")
```

- [ ] **Step 4: Run the migration on the dev DB and verify**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head
sqlite3 dev.db "SELECT id, public_id FROM patients LIMIT 3; SELECT id, public_id FROM medical_records LIMIT 3; SELECT id, public_id FROM message_drafts LIMIT 3; SELECT id, public_id FROM doctor_tasks LIMIT 3;"
```

Expected: each row shows a 36-character UUID. No NULLs.

- [ ] **Step 5: Verify uniqueness was enforced**

```bash
sqlite3 dev.db "SELECT public_id, COUNT(*) c FROM patients GROUP BY public_id HAVING c>1; SELECT public_id, COUNT(*) c FROM medical_records GROUP BY public_id HAVING c>1; SELECT public_id, COUNT(*) c FROM message_drafts GROUP BY public_id HAVING c>1; SELECT public_id, COUNT(*) c FROM doctor_tasks GROUP BY public_id HAVING c>1;"
```

Expected: no rows returned. **Do not commit.** Wait for user instruction.

---

## Task 2: Wire `public_id` field on each of the four models

**Files:**
- Modify: `src/db/models/patient.py`
- Modify: `src/db/models/records.py`
- Modify: `src/db/models/message_draft.py`
- Modify: `src/db/models/tasks.py`
- Test: `tests/test_public_id_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_models.py`:

```python
"""Phase 1 contract: every URL-exposed model gets a UUIDv4 public_id by default."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.message_draft import MessageDraft
from db.models.patient_message import PatientMessage
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
        # MedicalRecordDB requires patient_id; seed a patient first.
        p = Patient(doctor_id="web_doctor", name="Rec-Test-Patient")
        db.add(p); await db.flush()
        r = MedicalRecordDB(doctor_id="web_doctor", patient_id=p.id, record_type="visit")
        db.add(r); await db.flush()
        assert _is_uuid_v4(r.public_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_draft_default_public_id():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="web_doctor", name="Draft-Test-Patient")
        db.add(p); await db.flush()
        # MessageDraft requires source_message_id; seed an inbound message first.
        msg = PatientMessage(
            patient_id=p.id, doctor_id="web_doctor",
            content="hi", direction="inbound", source="patient",
        )
        db.add(msg); await db.flush()
        d = MessageDraft(
            doctor_id="web_doctor",
            patient_id=str(p.id),  # pre-existing String(64) landmine — see Design Decision 10
            source_message_id=msg.id,
            draft_text="reply",
        )
        db.add(d); await db.flush()
        assert _is_uuid_v4(d.public_id)
        await db.rollback()


@pytest.mark.asyncio
async def test_task_default_public_id():
    async with AsyncSessionLocal() as db:
        # DoctorTask valid types are general | follow_up (NOT followup).
        t = DoctorTask(doctor_id="web_doctor", task_type="follow_up", title="t")
        db.add(t); await db.flush()
        assert _is_uuid_v4(t.public_id)
        await db.rollback()
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_models.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 FAIL with `AttributeError: ... no attribute 'public_id'`.

- [ ] **Step 3: Add `public_id` to `Patient`**

In `src/db/models/patient.py`, add at module top (near the other imports):

```python
import uuid as _uuid
```

In the `Patient` class body, immediately after the `id` column (currently line 19):

```python
    public_id: Mapped[str] = mapped_column(
        sa.CHAR(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 4: Add `public_id` to `MedicalRecordDB`**

In `src/db/models/records.py`, ensure `import uuid as _uuid` and `import sqlalchemy as sa` are present. In the `MedicalRecordDB` class, immediately after the `id` column:

```python
    public_id: Mapped[str] = mapped_column(
        sa.CHAR(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 5: Add `public_id` to `MessageDraft`**

In `src/db/models/message_draft.py`, ensure `import uuid as _uuid` and `import sqlalchemy as sa`. Immediately after the `id` column:

```python
    public_id: Mapped[str] = mapped_column(
        sa.CHAR(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 6: Add `public_id` to `DoctorTask`**

In `src/db/models/tasks.py`, ensure `import uuid as _uuid` and `import sqlalchemy as sa`. Immediately after the `id` column:

```python
    public_id: Mapped[str] = mapped_column(
        sa.CHAR(36),
        nullable=False,
        unique=True,
        default=lambda: str(_uuid.uuid4()),
    )
```

- [ ] **Step 7: Run only the new tests — confirm they pass**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_models.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 PASS.

- [ ] **Step 8: Run the model-related test subset (selective, not full suite)**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "model or patient or record or draft or task" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: all green. Fix any test that constructs these models with positional args by either (a) confirming the default still kicks in, or (b) passing `public_id` explicitly.

**Do not commit.** Stop and report.

---

## Task 3: Expose `public_id` in API responses (additive)

**Files (response sites — every dict returned from these handlers must add `"public_id"` next to `"id"`):**
- `src/channels/web/doctor_dashboard/patient_detail_handlers.py`
- `src/channels/web/doctor_dashboard/record_handlers.py`
- `src/channels/web/doctor_dashboard/draft_handlers.py`
- `src/channels/web/doctor_dashboard/today_summary_handlers.py`
- `src/channels/web/doctor_dashboard/review_queue_handlers.py`
- `src/channels/web/doctor_dashboard/new_patient_handlers.py`
- `src/channels/web/doctor_dashboard/onboarding_handlers.py`
- `src/channels/web/tasks.py` — `TaskOut` Pydantic model and any dict construction
- `src/channels/web/patient_portal/tasks.py`
- `src/channels/web/patient_portal/routes.py` — `PatientRecordOut`
- Test: `tests/test_public_id_in_responses.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_in_responses.py`:

```python
"""Phase 1 contract: every list/detail endpoint that returns these entities
includes `public_id` alongside `id`."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from main import app


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
    # Task router is mounted at /api/tasks (not /api/manage/tasks).
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            "/api/tasks",
            headers={"Authorization": f"Bearer {seeded_doctor_token}"},
        )
    assert r.status_code == 200
    items = r.json() if isinstance(r.json(), list) else (r.json().get("tasks") or [])
    for t in items:
        assert "public_id" in t
```

(Adjust fixtures to match the project's existing pytest fixture naming. If fixtures don't exist, add minimal ones that issue a JWT for `web_doctor` and seed one row of each entity. Note: `seeded_task` requires `task_type="follow_up"`.)

- [ ] **Step 2: Run the test — confirm it fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_in_responses.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: 4 FAIL with `assert "public_id" in p`.

- [ ] **Step 3: Audit serialization sites**

```bash
grep -rn '"id":\s*[a-zA-Z_.]*\.id' src/channels/web/ --include="*.py" \
  | grep -vE "patient_id|record_id|draft_id|task_id|doctor_id|message_id|knowledge_id|edit_id|usage_id"
```

Each match is a place where a row's int `id` is serialized. Cluster matches into 4 groups (patient / record / draft / task) and edit each.

For Pydantic models (`TaskOut`, `PatientRecordOut`, etc.) add `public_id: str` to the schema and ensure the `from_orm`/dict construction includes it.

- [ ] **Step 4: Edit each serialization site**

Pattern:

```python
# BEFORE
return {"id": p.id, "name": p.name, ...}

# AFTER
return {"id": p.id, "public_id": p.public_id, "name": p.name, ...}
```

For Pydantic schemas:

```python
class TaskOut(BaseModel):
    id: int
    public_id: str   # <-- add
    title: str
    ...
```

Confirm coverage by re-running the grep from Step 3 and checking each match has been updated.

- [ ] **Step 5: Run only the new test — confirm it passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_in_responses.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 6: Run the API-related test subset (selective)**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "api or response or endpoint" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

**Do not commit.** Stop and report. Phase 1 is now ready for the user to commit and deploy independently if they wish.

### Phase 1 Rollback

- Application code: revert the model + handler edits with `git revert` or branch reset.
- Schema: `alembic downgrade -1` drops the `public_id` columns and indexes. Safe — no other code reads `public_id` yet.

---

# PHASE 2 — Backend Path-Param Cutover

Goal: every URL-exposed route accepts `{public_id}` (string UUID) instead of `{int_id}`. A doctor-scoped resolver enforces ownership at the request boundary. **Phase 2 must deploy together with Phase 3.**

## Task 4: Public-ID resolver (HTTP layer)

**Files:**
- Create: `src/channels/web/doctor_dashboard/public_id_resolver.py`
- Test: `tests/test_public_id_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_id_resolver.py`:

```python
"""Resolver returns identical 404 for not-found AND wrong-doctor — the caller
must not be able to enumerate via differential errors."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.message_draft import MessageDraft
from db.models.patient_message import PatientMessage
from db.models.tasks import DoctorTask
from channels.web.doctor_dashboard.public_id_resolver import (
    resolve_patient,
    resolve_record,
    resolve_draft,
    resolve_task,
)


@pytest.mark.asyncio
async def test_resolve_patient_owner_match():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="doctor_a", name="Owner-Match")
        db.add(p); await db.flush()
        found = await resolve_patient(db, p.public_id, "doctor_a")
        assert found.id == p.id
        await db.rollback()


@pytest.mark.asyncio
async def test_resolve_patient_wrong_doctor_404():
    async with AsyncSessionLocal() as db:
        p = Patient(doctor_id="doctor_a", name="Wrong-Doctor")
        db.add(p); await db.flush()
        with pytest.raises(HTTPException) as exc:
            await resolve_patient(db, p.public_id, "doctor_b")
        assert exc.value.status_code == 404
        await db.rollback()


@pytest.mark.asyncio
async def test_resolve_patient_missing_404():
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await resolve_patient(db, "00000000-0000-4000-8000-000000000000", "doctor_a")
        assert exc.value.status_code == 404


# Repeat the three cases (owner match / wrong doctor / missing) for record,
# draft, task. For draft fixture: seed Patient + PatientMessage first, then
# MessageDraft with patient_id=str(p.id), source_message_id=msg.id.
# For task fixture: task_type="follow_up".
```

- [ ] **Step 2: Run — confirm fails**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_resolver.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: ImportError (resolver module doesn't exist).

- [ ] **Step 3: Implement the resolver**

Create `src/channels/web/doctor_dashboard/public_id_resolver.py`:

```python
"""Doctor-scoped public_id → row resolvers (HTTP-layer).

Every helper raises HTTPException(404) for both "not found" and "wrong doctor".
Same response shape for both cases so the caller cannot distinguish them
(prevents enumeration via differential errors).

Lives in the HTTP layer (channels/web/) rather than in db/crud/ because it
returns HTTP exceptions. CRUD code stays HTTP-agnostic and reusable in jobs.
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


async def resolve_patient(
    db: AsyncSession, public_id: str, doctor_id: str
) -> Patient:
    stmt = select(Patient).where(
        Patient.public_id == public_id, Patient.doctor_id == doctor_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


async def resolve_record(
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


async def resolve_draft(
    db: AsyncSession, public_id: str, doctor_id: str
) -> MessageDraft:
    stmt = select(MessageDraft).where(
        MessageDraft.public_id == public_id,
        MessageDraft.doctor_id == doctor_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row


async def resolve_task(
    db: AsyncSession, public_id: str, doctor_id: str
) -> DoctorTask:
    stmt = select(DoctorTask).where(
        DoctorTask.public_id == public_id,
        DoctorTask.doctor_id == doctor_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _NOT_FOUND
    return row
```

- [ ] **Step 4: Run — confirm passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_public_id_resolver.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

**Do not commit.** Stop and report.

---

## Task 5: Convert patient endpoints

**Files (one entry per route line from the inventory above):**
- `src/channels/web/doctor_dashboard/patient_detail_handlers.py:131,197,294,324`
- `src/channels/web/doctor_dashboard/admin_overview.py:1689` (admin route — convert)
- `src/channels/web/form_responses.py:53`

For each route: rename path param `{patient_id}` → `{public_id}`, change Python signature `patient_id: int` → `public_id: str`, add `db: AsyncSession = Depends(get_db)` if not present, and call `resolve_patient(db, public_id, resolved)` to get the `Patient` row. Use `patient.id` (the integer) for any internal CRUD or domain calls.

Worked example for `/api/manage/patients/{patient_id}/timeline`:

```python
# BEFORE — patient_detail_handlers.py:131
@router.get("/api/manage/patients/{patient_id}/timeline")
async def manage_patient_timeline(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"doctor_id": doctor_id, **data}

# AFTER
from channels.web.doctor_dashboard.public_id_resolver import resolve_patient

@router.get("/api/manage/patients/{public_id}/timeline")
async def manage_patient_timeline(
    public_id: str,
    doctor_id: str = Query(default="web_doctor"),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    patient = await resolve_patient(db, public_id, doctor_id)
    data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient.id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"doctor_id": doctor_id, **data}
```

- [ ] **Step 1: Write the failing route test**

Create `tests/test_patient_routes_use_public_id.py`:

```python
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
async def test_timeline_cross_doctor_404(seeded_doctor_token_a, seeded_patient_b):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(
            f"/api/manage/patients/{seeded_patient_b.public_id}/timeline",
            headers={"Authorization": f"Bearer {seeded_doctor_token_a}"},
        )
    assert r.status_code == 404
```

- [ ] **Step 2: Run — confirm fails**

- [ ] **Step 3: Convert each route in the file list above**

Apply the worked-example pattern to every line in the inventory. Do not leave dual-accept variants.

- [ ] **Step 4: Run — confirm passes**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/test_patient_routes_use_public_id.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 5: Run patient-related test subset**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "patient" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Existing patient tests will need fixture updates (URLs change from int to UUID). Update them; do not loosen the route.

**Do not commit.** Stop and report.

---

## Task 6: Convert record endpoints

**Files:**
- `src/channels/web/doctor_dashboard/record_edit_handlers.py:39,118,133,178`
- `src/channels/web/doctor_dashboard/diagnosis_handlers.py:164,207,371,415`
- `src/channels/web/tasks.py:324` — `/api/tasks/record/{record_id}`

Pattern: `{record_id}: int` → `{public_id}: str` + `record = await resolve_record(db, public_id, doctor_id)`.

- [ ] **Step 1: Write failing tests** (mirror the patient route test pattern for `/api/manage/records/{public_id}`)

- [ ] **Step 2: Convert each route**

- [ ] **Step 3: Run record-related test subset**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "record or diagnosis" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

**Do not commit.** Stop and report.

---

## Task 7: Convert draft endpoints

**Files:**
- `src/channels/web/doctor_dashboard/draft_handlers.py:358,408,473,501,581`

Five routes: `/send`, `/edit`, `/dismiss`, `/send-confirmation`, `/save-as-rule`. Each currently does its own `draft.doctor_id == resolved` check; replace that with the resolver call which does the same work in one line.

Worked example:

```python
# BEFORE
@router.post("/api/manage/drafts/{draft_id}/send")
async def send_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.send")
    draft = await db.get(MessageDraft, draft_id)
    if draft is None or draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft is not in a sendable state")
    ...
    msg_id = await send_doctor_reply(
        doctor_id=resolved,
        patient_id=int(draft.patient_id),  # String(64) → int — pre-existing landmine
        text=reply_text,
        draft_id=draft.id,
        ai_disclosure=disclosure,
    )

# AFTER
@router.post("/api/manage/drafts/{public_id}/send")
async def send_draft(
    public_id: str,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.send")
    draft = await resolve_draft(db, public_id, resolved)
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft is not in a sendable state")
    ...
    msg_id = await send_doctor_reply(
        doctor_id=resolved,
        patient_id=int(draft.patient_id),  # KEEP — pre-existing String(64) coercion, not regressed
        text=reply_text,
        draft_id=draft.id,
        ai_disclosure=disclosure,
    )
```

**Do not "fix" `int(draft.patient_id)` — it's an existing landmine documented in `feedback/project_patient_id_type_mismatch.md`. Out of scope here.**

- [ ] **Step 1: Write failing tests**

- [ ] **Step 2: Convert all five routes**

- [ ] **Step 3: Run draft test subset**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "draft" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

**Do not commit.** Stop and report.

---

## Task 8: Convert task endpoints

**Files:**
- `src/channels/web/tasks.py:138,247,275,296` (doctor task endpoints; router prefix `/api/tasks`)
- `src/channels/web/patient_portal/tasks.py:120,154,197,314` (patient task endpoints; router prefix `/api/patient/tasks`)

Note: patient-portal task endpoints are reached via patient JWT, not doctor JWT. The resolver helper takes a `doctor_id` argument; for patient-portal calls, pass `patient.doctor_id` (already extracted by `_authenticate_patient`).

- [ ] **Step 1: Write failing tests** for both doctor-side and patient-portal task endpoints

- [ ] **Step 2: Convert each route**

- [ ] **Step 3: Run task test subset**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "task" -q --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

**Do not commit.** Stop and report.

### Phase 2 Rollback

- Application code: revert all edits in Tasks 4–8. The resolver module can stay (it's harmless if unused).
- Schema: no rollback needed (Phase 2 makes no schema changes).
- **Caution:** if Phase 3 has already been deployed, rolling back Phase 2 alone leaves the frontend sending UUIDs to int-only routes. Always roll back Phases 2+3 together.

---

# PHASE 3 — Frontend Cutover

Goal: every `navigate()` and every `api.js` URL builder forwards `public_id` from the API response. **Phase 3 must deploy together with Phase 2.**

## Task 9: `api.js` URL builders

**File:** `frontend/web/src/api.js`

For each line in the api.js inventory above, change the function signature from `(patientId, ...)` to `(patientPublicId, ...)` (and similar for records/drafts/tasks). The function rename is for clarity — the actual URL string substitutes the new value.

- [ ] **Step 1: Find all callers of each function**

```bash
grep -rn -E "(getPatient|deletePatient|fetchTimeline|refreshAiSummary|getPatientChat|sendPatientReply|getRecord|deleteRecord|getRecordEntries|getAdminRecord|diagnoseRecord|getRecordSuggestions|saveRecordSuggestions|finalizeReview|sendDraft|editDraft|dismissDraft|sendDraftConfirmation|saveDraftAsRule|getTask|patchTask|patchTaskNotes|patchTaskDue|completeTask|uncompleteTask|getPatientTask)\(" frontend/web/src --include="*.jsx" --include="*.js"
```

(Replace function names with whatever they actually are in api.js; the inventory has line numbers, not names.)

- [ ] **Step 2: Convert one entity-group at a time**

Patient functions first (api.js lines 221, 508, 514, 520, 550, 1187, 1191). Update each function. Then update all callers found in Step 1 to read `patient.public_id` instead of `patient.id`.

Repeat for record, draft, task groups.

- [ ] **Step 3: Run vitest**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npm test -- --run
```

Fix any frontend unit test that asserts on integer IDs in URL params.

**Do not commit.** Stop and report.

---

## Task 10: `navigate()` callsites and route params

**Files:** every entry from the navigate inventory table above.

For each callsite, change `${something.id}` → `${something.public_id}`. For routes that carry an entity id in `useParams()`, rename the destructured param for clarity:

```jsx
// BEFORE
const { patient_id } = useParams();

// AFTER
const { public_id: patientPublicId } = useParams();
```

The route definition in `frontend/web/src/v2/App.jsx` uses `:patient_id` as the URL param name. Either:
(a) Rename to `:public_id` everywhere (cleaner), OR
(b) Keep `:patient_id` and treat the value as a UUID string at the consumer (less churn but misleading variable name).

**Decision: rename to `:public_id`** — fewer surprises.

- [ ] **Step 1: Update route definitions in `App.jsx`**

Find every `<Route path="/doctor/patients/:patient_id" ...>` etc. and rename to `:public_id`. Same for record, task routes.

- [ ] **Step 2: Update every `navigate()` callsite** from the inventory.

- [ ] **Step 3: Update every `useParams()` consumer**

```bash
grep -rn "useParams()" frontend/web/src --include="*.jsx"
```

- [ ] **Step 4: Run vitest + Playwright**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npm test -- --run
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && rm -rf test-results && npx playwright test
```

Both servers must be running (backend on :8000, frontend on :5173). E2E will need `VITE_ROUTER_MODE=browser` set so URL navigation in tests still works.

**Do not commit.** Stop and report.

### Phase 3 Rollback

- Frontend: revert all edits. Pair this revert with a Phase 2 revert (frontend sending UUIDs to int-only routes won't work; old int IDs to UUID-only routes won't work either).
- The dual-revert sequence is: revert Phase 3 + Phase 2 application code together, deploy, leave Phase 1 schema in place.

---

## Task 11: Manual verification + docs

- [ ] **Step 1: Manual smoke test in dev**

```bash
./dev.sh
```

In a browser:
1. Log in as test doctor.
2. Open patient list → click a patient → URL shows `/doctor/patients/<uuid>`.
3. Open a record → URL shows `/doctor/review/<uuid>`.
4. Send a draft reply → succeeds, no console errors.
5. Open a task → URL shows `<uuid>`.
6. Visit `/doctor/patients/1` directly → page renders, then API returns 404, UI shows "patient not found".

- [ ] **Step 2: Verify no integer IDs leak in URL or DOM**

In DevTools network tab, confirm every `/api/manage/...`, `/api/doctor/...`, `/api/tasks/...` request uses a UUID, not an integer.

- [ ] **Step 3: Update `docs/architecture.md`**

Add a paragraph under the data model section:

> **Public IDs.** Tables that appear in user-visible URLs (`patients`, `medical_records`, `message_drafts`, `doctor_tasks`) carry a `public_id` UUIDv4 column used for routing and as the canonical identifier in API path params. Internal foreign keys still use integer `id` for join performance. Lookup helpers in `src/channels/web/doctor_dashboard/public_id_resolver.py` enforce doctor-scoped ownership at the request boundary and return identical 404s for "not found" and "wrong doctor" so callers cannot enumerate via differential errors.

- [ ] **Step 4: Stop and report.** Wait for the user to commit.

---

## Self-Review Checklist (run before reporting completion)

- [ ] All four tables have `public_id` populated, NOT NULL, UNIQUE.
- [ ] Every `@router.{get,post,put,patch,delete}` path that previously took a `{patient_id|record_id|draft_id|task_id}` int now takes `{public_id}` and resolves via the resolver.
- [ ] `grep -rn "patient_id: int\|record_id: int\|draft_id: int\|task_id: int" src/channels/web/` returns ONLY query-param uses (e.g. `Query(default=None)`), not path-param.
- [ ] `grep -rn "navigate.*\\.id" frontend/web/src/v2/` returns zero hits for patient/record/draft/task entities.
- [ ] `grep -rn "/\\\${.*\\.id}" frontend/web/src/api.js` returns zero hits in the patient/record/draft/task URL builders.
- [ ] All Phase 1 tests pass.
- [ ] All Phase 2 route tests pass.
- [ ] Vitest + Playwright (with `VITE_ROUTER_MODE=browser`) pass.
- [ ] Manual smoke test verified UUIDs in URL and network tab.
- [ ] No new auto-commits (commit only when user asks).
- [ ] `int(draft.patient_id)` coercions still present (pre-existing landmine, not regressed).

---

## Open Questions / Risks

1. **WeChat miniapp.** This plan targets `frontend/web/`. If a separate miniapp codebase makes API calls with cached integer IDs from local storage, those calls will start 404ing post-Phase-2 deploy. Audit before deploy.

2. **Cached deep links / bookmarks.** A user with a bookmarked `/doctor/patients/42` URL gets a "patient not found" page after Phase 3. Acceptable for beta. Consider a single sentry log line on these to quantify.

3. **Database size impact.** ~36 bytes per row × 4 tables × n rows. At 100k patients ≈ 3.6 MB extra. Negligible.

4. **`MessageDraft.patient_id` is `String(64)`** (existing landmine, plan does not regress). Search the codebase for `int(draft.patient_id)` and `str(p.id)` after the migration to confirm nothing was accidentally touched.

5. **Re-run `/codex review` after this plan is implemented in a worktree** — but before final merge. The current revision is significantly more concrete than v1; should clear cleanly.

---

## Execution Notes

- This plan should be executed in a dedicated worktree, not on `main`.
- Phases 2 and 3 must deploy together. Phase 1 ships independently.
- Each task ends in **stop and report** — never auto-commit. The user commits when satisfied.
- All test runs are selective (`pytest -k`) per project rules; no full-suite runs unless explicitly requested.
- If a phase breaks unexpectedly, see the per-phase rollback section above.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review (v1) | `/codex review` | Independent 2nd opinion | 1 | FAIL | 12 findings — partially addressed in v2 |
| Codex Review (v2) | `/codex review` | Re-review of revised plan | 1 | **FAIL** | 5 fixed, 7 still broken, 3 new issues |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | n/a | No UI surface change |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | n/a | Internal migration |

**v2 codex re-review verdict (2026-04-26):** **FAIL** — plan still not ready for execution.

| # | Finding | Verdict | Notes |
|---|---|---|---|
| 1 | Wrong Alembic parent | FIXED | resolved at execution time |
| 2 | Concurrent-write race | **STILL BROKEN** | model defaults wired in Task 2 (after the migration runs in Task 1); inserts during the window have no default |
| 3 | Scope undercount | **STILL BROKEN** | missing patient-portal frontend (`PatientPage.jsx`, `RecordsTab.jsx`, `PatientTaskDetailPage.jsx`, `ChatTab.jsx`); `new_patient_handlers` flow not enumerated |
| 4 | Test scaffolding bugs | FIXED | |
| 5 | Phase 3 routing pointing at wrong file | **STILL BROKEN** | doctor/patient subroutes are NOT in `App.jsx` — they live in `DoctorPage.jsx:263` and `PatientPage.jsx:130` with manual pathname parsing |
| 6 | Lookup helpers layer | FIXED | |
| 7 | `MessageDraft.patient_id String(64)` | **STILL BROKEN** | acknowledged but not solved; drafts-per-patient filter (`MessageDraft.patient_id == str(patient_id)`) breaks when frontend starts passing UUIDs |
| 8 | "Audit/sweep" too vague | **STILL BROKEN** | several entries still say "inspect at execution" |
| 9 | Integer leaks beyond URL paths | **STILL BROKEN** | PDF filenames are user-visible (saved to Downloads); `triage_category` is returned in API responses |
| 10 | `VARCHAR(36)` vs `CHAR(36)` | FIXED | |
| 11 | Rollback story | FIXED | |
| 12 | Repo fit | **STILL BROKEN** | tests cadence still conflicts with project rules |

**New issues found in v2:**
- `App.jsx` does not own doctor/patient entity sub-routes; manual pathname parsing in `DoctorPage.jsx` / `PatientPage.jsx`.
- `new_patient_handlers` user flow omitted from concrete migration set despite being wired end-to-end.
- Patient portal local storage stores int IDs (`patient_portal_patient_id`, `unified_auth_patient_id`); plan doesn't say if these need migration hygiene.

---

## STATUS: DEFERRED to Q3 (≈ 2026-06)

**Decision (2026-04-26):** Public_id migration is genuinely a 3-week dedicated project, not a 1-week fix. Two rounds of codex review surfaced progressively deeper coupling — that's a sign of project-wide scope, not of a planning gap.

**What we shipped instead (Q2 quick wins, ≈ 2 hours of work):**
- `MemoryRouter` for native/wrapper builds (`frontend/web/src/main.jsx`) — kills URL enumeration in iOS/Android/miniapp wrappers, the original concern.
- Ownership check on `POST /api/manage/patients/{patient_id}/reply` (`src/channels/web/doctor_dashboard/patient_detail_handlers.py:330`) — closes the cross-tenant write gap.

These cover ~80% of the practical security benefit of public_id at ~5% of the engineering cost.

**Before resuming this plan:**
1. Address the 7 still-broken findings, especially #2 (migration sequencing) and #3 (scope).
2. Audit `DoctorPage.jsx` / `PatientPage.jsx` route parsers and add them to the inventory.
3. Decide whether `MessageDraft.patient_id String(64)` gets fixed in this migration or kept frozen.
4. Re-run `/codex review` until verdict is PASS.
5. Run `/plan-eng-review` before execution.
