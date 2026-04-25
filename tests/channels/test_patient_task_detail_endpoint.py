"""Patient task list endpoint surfaces ``completed_at`` and ``source_record_id``.

Task 0.1 of the patient-app doctor-UI parity plan: the patient-portal task
schema needs two extra fields so the upcoming patient task-detail subpage
can render the "完成时间" row and the "来源" card linking back to the
related medical record.

- ``completed_at`` is a column already on ``DoctorTask``; just exposing it.
- ``source_record_id`` derives from ``DoctorTask.record_id`` (FK to
  ``medical_records.id``) — NOT from ``DoctorTask.source_id``, which is a
  different semantic field. The test seeds ``source_id=999`` as a decoy
  to lock that distinction in.

Test infrastructure mirrors ``tests/test_finalize_review.py``: build a bare
``FastAPI()`` instance, mount only the patient-portal tasks router, swap
``AsyncSessionLocal`` for a sqlite-memory session factory so the
``_authenticate_patient`` helper (which uses ``AsyncSessionLocal()``
directly, not the FastAPI dependency) hits the test DB.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
from db.models.doctor import Doctor
from db.models.patient import Patient
from db.models.records import MedicalRecordDB, RecordStatus
from db.models.tasks import DoctorTask, TaskStatus, TaskType
from channels.web.patient_portal.tasks import tasks_router
from infra.auth import UserRole
from infra.auth.unified import issue_token


TEST_DOCTOR_ID = "doc_patient_task_detail"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(_engine, monkeypatch):
    """Build a FastAPI app with only ``tasks_router`` and route both the
    request-scoped ``get_db`` dependency AND the standalone
    ``AsyncSessionLocal()`` (used by ``_authenticate_patient``) at the
    in-memory test engine.
    """
    Session = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    # _authenticate_patient uses AsyncSessionLocal() from db.engine directly
    # (not via the FastAPI dependency), so we have to swap it both at the
    # source and at the auth.py import site.
    monkeypatch.setattr("db.engine.AsyncSessionLocal", Session)
    monkeypatch.setattr(
        "channels.web.patient_portal.auth.AsyncSessionLocal", Session
    )

    app = FastAPI()
    app.include_router(tasks_router)
    app.dependency_overrides[get_db] = _override_get_db

    os.environ.setdefault("ENVIRONMENT", "development")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver",
    ) as client:
        yield client


async def _seed_patient_with_task(db_session) -> tuple[Patient, MedicalRecordDB, DoctorTask]:
    """Seed a doctor + patient + record + completed patient-targeted task.

    Returns (patient, record, task). The task has:
      - ``record_id`` set to the seeded record (this should surface as
        ``source_record_id`` on the response).
      - ``source_id=999`` as a decoy to confirm the schema does NOT
        accidentally pull from ``source_id``.
      - ``completed_at`` set to a known timestamp so the test can assert it
        comes back in the response.
    """
    db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Patient Task Test Doc"))
    await db_session.flush()

    patient = Patient(
        doctor_id=TEST_DOCTOR_ID,
        name="Task Detail Test Patient",
    )
    db_session.add(patient)
    await db_session.flush()

    record = MedicalRecordDB(
        doctor_id=TEST_DOCTOR_ID,
        patient_id=patient.id,
        record_type="visit",
        status=RecordStatus.completed.value,
        content="chief complaint stub",
    )
    db_session.add(record)
    await db_session.flush()

    completed_at = datetime(2026, 4, 20, 10, 30, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    task = DoctorTask(
        doctor_id=TEST_DOCTOR_ID,
        patient_id=patient.id,
        record_id=record.id,
        task_type=TaskType.follow_up.value,
        title="复查甲状腺功能",
        content="请于下周到院复查 TSH/FT4",
        status=TaskStatus.completed.value,
        target="patient",
        source_type="manual",
        source_id=999,  # decoy — must NOT show up as source_record_id
        completed_at=completed_at,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    await db_session.refresh(record)
    await db_session.refresh(patient)

    return patient, record, task


def _patient_token(patient: Patient) -> str:
    return issue_token(
        UserRole.patient,
        doctor_id=patient.doctor_id,
        patient_id=patient.id,
        name=patient.name,
    )


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tasks_includes_completed_at_and_source_record_id(
    async_client, db_session,
):
    """GET /tasks should expose completed_at + source_record_id on each task.

    source_record_id must come from DoctorTask.record_id, NOT source_id
    (the seeded source_id=999 is a decoy to lock this in).
    """
    patient, record, task = await _seed_patient_with_task(db_session)
    token = _patient_token(patient)

    resp = await async_client.get(
        "/tasks", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    tasks = resp.json()
    assert len(tasks) == 1, tasks
    out = tasks[0]

    # Sanity: the task we seeded came back.
    assert out["id"] == task.id
    assert out["status"] == "completed"

    # New fields exist on the response.
    assert "completed_at" in out, "PatientTaskOut missing completed_at"
    assert "source_record_id" in out, "PatientTaskOut missing source_record_id"

    # completed_at round-trips.
    assert out["completed_at"] is not None
    assert out["completed_at"].startswith("2026-04-20T10:30:00")

    # source_record_id derives from task.record_id, NOT from source_id.
    assert out["source_record_id"] == record.id
    assert out["source_record_id"] != 999  # explicit decoy guard


# ── Task 0.2 — GET /api/patient/tasks/{task_id} ────────────────────────────


@pytest.mark.asyncio
async def test_get_patient_task_by_id_happy_path(async_client, db_session):
    """GET /tasks/{id} returns the task body when owned + patient-targeted."""
    patient, _record, task = await _seed_patient_with_task(db_session)
    token = _patient_token(patient)

    resp = await async_client.get(
        f"/tasks/{task.id}", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["id"] == task.id
    assert body["title"] == task.title
    assert body["status"] == task.status
    assert body["task_type"] == task.task_type


@pytest.mark.asyncio
async def test_get_patient_task_by_id_404_when_not_found(
    async_client, db_session,
):
    """Unknown task id → 404 (don't reveal whether the row exists)."""
    patient, _record, _task = await _seed_patient_with_task(db_session)
    token = _patient_token(patient)

    resp = await async_client.get(
        "/tasks/9999999", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_get_patient_task_by_id_404_for_other_patients_task(
    async_client, db_session,
):
    """Cross-patient access returns 404 (not 403) to hide ownership info."""
    # Patient A owns the seeded task.
    patient_a, _record_a, task_a = await _seed_patient_with_task(db_session)

    # Seed a second patient (B) under the same doctor — token used to probe.
    patient_b = Patient(
        doctor_id=TEST_DOCTOR_ID,
        name="Other Patient B",
    )
    db_session.add(patient_b)
    await db_session.commit()
    await db_session.refresh(patient_b)

    token_b = _patient_token(patient_b)

    resp = await async_client.get(
        f"/tasks/{task_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404, resp.text
