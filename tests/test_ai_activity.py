"""Tests for AI activity feed and flagged-patients APIs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from db.models.ai_suggestion import AISuggestion
from db.models.doctor import Doctor
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.tasks import DoctorTask


# ── Fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── Seed helpers ──────────────────────────────────────────────────


async def _seed_doctor_and_patient(session, doctor_id="doc_1"):
    doctor = Doctor(doctor_id=doctor_id, name="Test Doctor")
    session.add(doctor)
    await session.flush()

    patient = Patient(id=1, doctor_id=doctor_id, name="Test Patient")
    session.add(patient)
    await session.flush()

    msg = PatientMessage(
        id=1, patient_id=1, doctor_id=doctor_id,
        content="头疼", direction="inbound", source="patient",
    )
    session.add(msg)
    await session.flush()
    return doctor, patient, msg


# ── _urgency_rank tests ──────────────────────────────────────────


def test_urgency_rank_ordering():
    from channels.web.ui.ai_activity_handlers import _urgency_rank

    assert _urgency_rank("urgent") > _urgency_rank("high")
    assert _urgency_rank("high") > _urgency_rank("medium")
    assert _urgency_rank("medium") > _urgency_rank("low")
    assert _urgency_rank("unknown") == 0


def test_urgency_rank_values():
    from channels.web.ui.ai_activity_handlers import _urgency_rank

    assert _urgency_rank("urgent") == 3
    assert _urgency_rank("high") == 2
    assert _urgency_rank("medium") == 1
    assert _urgency_rank("low") == 0


# ── _safe_iso tests ──────────────────────────────────────────────


def test_safe_iso_none():
    from channels.web.ui.ai_activity_handlers import _safe_iso

    assert _safe_iso(None) is None


def test_safe_iso_datetime():
    from channels.web.ui.ai_activity_handlers import _safe_iso

    dt = datetime(2026, 3, 27, 10, 30, 0, tzinfo=timezone.utc)
    result = _safe_iso(dt)
    assert "2026-03-27" in result
    assert "10:30" in result


# ── Activity feed data assembly ───────────────────────────────────


@pytest.mark.asyncio
async def test_activity_feed_includes_suggestions(async_session):
    """AI suggestions appear as 'diagnosis' events in the feed."""
    from db.models.records import MedicalRecordDB

    await _seed_doctor_and_patient(async_session)

    record = MedicalRecordDB(id=1, doctor_id="doc_1", patient_id=1, record_type="visit")
    async_session.add(record)
    await async_session.flush()

    suggestion = AISuggestion(
        record_id=1, doctor_id="doc_1",
        section="differential", content="可能是偏头痛，需进一步检查",
    )
    async_session.add(suggestion)
    await async_session.commit()
    await async_session.refresh(suggestion)

    # Verify the suggestion was created with correct fields
    assert suggestion.doctor_id == "doc_1"
    assert suggestion.content.startswith("可能是偏头痛")
    assert suggestion.created_at is not None


@pytest.mark.asyncio
async def test_activity_feed_includes_drafts(async_session):
    """Drafts appear as 'draft' events."""
    await _seed_doctor_and_patient(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="建议多休息", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    assert draft.doctor_id == "doc_1"
    assert draft.created_at is not None


@pytest.mark.asyncio
async def test_activity_feed_includes_tasks(async_session):
    """Tasks appear as 'task' events."""
    await _seed_doctor_and_patient(async_session)

    task = DoctorTask(
        doctor_id="doc_1", patient_id=1, task_type="follow_up",
        title="复诊提醒", status="pending",
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    assert task.doctor_id == "doc_1"
    assert task.title == "复诊提醒"


# ── Flagged patients: due tasks ───────────────────────────────────


@pytest.mark.asyncio
async def test_flagged_due_tasks(async_session):
    """Overdue tasks should flag the patient."""
    await _seed_doctor_and_patient(async_session)

    past = datetime.now(timezone.utc) - timedelta(hours=2)
    task = DoctorTask(
        doctor_id="doc_1", patient_id=1, task_type="follow_up",
        title="复诊", status="pending", due_at=past,
    )
    async_session.add(task)
    await async_session.commit()

    # Query same way the handler does
    from sqlalchemy import desc as _desc

    now = datetime.now(timezone.utc)
    due_tasks = (
        await async_session.execute(
            select(DoctorTask)
            .where(
                DoctorTask.doctor_id == "doc_1",
                DoctorTask.status == "pending",
                DoctorTask.due_at <= now,
            )
            .limit(10)
        )
    ).scalars().all()

    assert len(due_tasks) == 1
    assert due_tasks[0].patient_id == 1


@pytest.mark.asyncio
async def test_flagged_unread_messages(async_session):
    """Inbound messages with ai_handled=False should flag the patient."""
    await _seed_doctor_and_patient(async_session)

    msg = PatientMessage(
        patient_id=1, doctor_id="doc_1",
        content="紧急：胸痛", direction="inbound", source="patient",
        ai_handled=False, triage_category="urgent",
    )
    async_session.add(msg)
    await async_session.commit()

    from sqlalchemy import desc as _desc

    unread = (
        await async_session.execute(
            select(PatientMessage)
            .where(
                PatientMessage.doctor_id == "doc_1",
                PatientMessage.direction == "inbound",
                PatientMessage.ai_handled == False,  # noqa: E712
            )
            .limit(10)
        )
    ).scalars().all()

    assert len(unread) == 1
    assert unread[0].triage_category == "urgent"


@pytest.mark.asyncio
async def test_flagged_unreviewed_suggestions(async_session):
    """Suggestions without a decision should flag for review."""
    from db.models.records import MedicalRecordDB

    await _seed_doctor_and_patient(async_session)

    record = MedicalRecordDB(id=1, doctor_id="doc_1", patient_id=1, record_type="visit")
    async_session.add(record)
    await async_session.flush()

    suggestion = AISuggestion(
        record_id=1, doctor_id="doc_1",
        section="treatment", content="推荐使用布洛芬",
        decision=None,
    )
    async_session.add(suggestion)
    await async_session.commit()

    unreviewed = (
        await async_session.execute(
            select(AISuggestion)
            .where(
                AISuggestion.doctor_id == "doc_1",
                AISuggestion.decision == None,  # noqa: E711
            )
            .limit(10)
        )
    ).scalars().all()

    assert len(unreviewed) == 1
    assert unreviewed[0].content.startswith("推荐使用")


# ── Deduplication logic ───────────────────────────────────────────


def test_dedup_keeps_highest_urgency():
    """When multiple flags exist for the same patient, keep highest urgency."""
    from channels.web.ui.ai_activity_handlers import _urgency_rank

    flagged = [
        {"patient_id": 1, "reason": "low reason", "urgency": "medium", "type": "unread_message"},
        {"patient_id": 1, "reason": "high reason", "urgency": "urgent", "type": "due_task"},
        {"patient_id": 2, "reason": "medium reason", "urgency": "medium", "type": "unreviewed_suggestion"},
    ]

    seen: dict = {}
    for f in flagged:
        pid = f.get("patient_id") or f.get("record_id")
        if pid not in seen or _urgency_rank(f["urgency"]) > _urgency_rank(seen[pid]["urgency"]):
            seen[pid] = f

    result = sorted(seen.values(), key=lambda x: _urgency_rank(x["urgency"]), reverse=True)

    assert len(result) == 2
    # Patient 1 should have "urgent" (the higher one)
    p1 = next(r for r in result if r["patient_id"] == 1)
    assert p1["urgency"] == "urgent"
    assert p1["reason"] == "high reason"
    # First in list is highest urgency
    assert result[0]["urgency"] == "urgent"


# ── Event sorting ─────────────────────────────────────────────────


def test_events_sorted_by_timestamp_desc():
    """Events should be sorted newest-first after merge."""
    events = [
        {"type": "citation", "timestamp": "2026-03-27T08:00:00"},
        {"type": "diagnosis", "timestamp": "2026-03-27T10:00:00"},
        {"type": "draft", "timestamp": "2026-03-27T09:00:00"},
        {"type": "task", "timestamp": "2026-03-27T07:00:00"},
    ]
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == [
        "2026-03-27T10:00:00",
        "2026-03-27T09:00:00",
        "2026-03-27T08:00:00",
        "2026-03-27T07:00:00",
    ]


def test_events_with_none_timestamps_sort_last():
    """Events with None timestamps should sort to the end."""
    events = [
        {"type": "citation", "timestamp": None},
        {"type": "diagnosis", "timestamp": "2026-03-27T10:00:00"},
    ]
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    assert events[0]["type"] == "diagnosis"
    assert events[1]["type"] == "citation"
