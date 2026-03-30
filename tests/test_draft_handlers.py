"""Tests for draft handler logic: model CRUD, status transitions, and teaching loop integration."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from db.models.message_draft import DraftStatus, MessageDraft


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


# ── Helper ───────────────────────────────────────────────────────


async def _create_seed_data(session):
    """Seed a doctor, patient, and patient message so FK constraints pass."""
    from db.models.doctor import Doctor
    from db.models.patient import Patient
    from db.models.patient_message import PatientMessage

    doctor = Doctor(doctor_id="doc_1", name="Test Doctor")
    session.add(doctor)
    await session.flush()

    patient = Patient(id=1, doctor_id="doc_1", name="Test Patient")
    session.add(patient)
    await session.flush()

    msg = PatientMessage(
        id=1, patient_id=1, doctor_id="doc_1",
        content="I have a headache", direction="inbound", source="patient",
    )
    session.add(msg)
    await session.flush()
    return doctor, patient, msg


# ── Dismiss draft ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dismiss_draft(async_session):
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="test", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    assert draft.status == "generated"

    draft.status = DraftStatus.dismissed.value
    await async_session.commit()
    assert draft.status == "dismissed"


# ── Edit draft ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_draft(async_session):
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="original reply", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    draft.edited_text = "edited reply with more detail"
    draft.status = DraftStatus.edited.value
    await async_session.commit()
    assert draft.edited_text == "edited reply with more detail"
    assert draft.status == "edited"


# ── Stale draft ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_draft(async_session):
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="will be stale", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    # Simulate stale: new message arrives, mark old draft stale
    draft.status = DraftStatus.stale.value
    await async_session.commit()
    assert draft.status == "stale"


# ── Send draft (status transition) ──────────────────────────────


@pytest.mark.asyncio
async def test_send_draft_transitions_to_sent(async_session):
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="Your headache should improve with rest.",
        status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    # Simulate send
    draft.status = DraftStatus.sent.value
    await async_session.commit()
    assert draft.status == "sent"


# ── Edit triggers teaching loop ──────────────────────────────────


@pytest.mark.asyncio
async def test_significant_edit_triggers_teaching(async_session):
    """A large edit should be flagged by should_prompt_teaching."""
    from domain.knowledge.teaching import should_prompt_teaching

    original = "建议观察"
    edited = "患者头痛伴呕吐，需紧急CT检查排除颅内出血，同时监测生命体征和血压变化"
    assert should_prompt_teaching(original, edited) is True


@pytest.mark.asyncio
async def test_minor_edit_does_not_trigger_teaching(async_session):
    """A minor edit should not trigger teaching."""
    from domain.knowledge.teaching import should_prompt_teaching

    original = "建议休息观察"
    edited = "建议休息观察。"
    assert should_prompt_teaching(original, edited) is False


# ── Edited text takes precedence ─────────────────────────────────


@pytest.mark.asyncio
async def test_edited_text_takes_precedence(async_session):
    """When edited_text is set, it should be the 'active' reply text."""
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="AI original", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    draft.edited_text = "Doctor revision"
    draft.status = DraftStatus.edited.value
    await async_session.commit()

    active_text = draft.edited_text or draft.draft_text
    assert active_text == "Doctor revision"


# ── AI disclosure label ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_disclosure_default(async_session):
    """Default AI disclosure label is set."""
    await _create_seed_data(async_session)

    draft = MessageDraft(
        doctor_id="doc_1", patient_id="1", source_message_id=1,
        draft_text="reply", status=DraftStatus.generated.value,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    assert draft.ai_disclosure == "AI辅助生成，经医生审核"


# ── Helper: parse cited IDs ──────────────────────────────────────


def test_parse_cited_ids():
    from channels.web.doctor_dashboard.draft_handlers import _parse_cited_ids

    assert _parse_cited_ids(None) == []
    assert _parse_cited_ids("") == []
    assert _parse_cited_ids("[1, 2, 3]") == [1, 2, 3]
    assert _parse_cited_ids("invalid json") == []
    assert _parse_cited_ids("[10]") == [10]


# ── Query: only pending drafts returned ──────────────────────────


@pytest.mark.asyncio
async def test_only_pending_drafts_in_query(async_session):
    """Sent and dismissed drafts should not appear in pending queries."""
    from sqlalchemy import select

    await _create_seed_data(async_session)

    for status in [DraftStatus.generated, DraftStatus.edited, DraftStatus.sent, DraftStatus.dismissed]:
        d = MessageDraft(
            doctor_id="doc_1", patient_id="1", source_message_id=1,
            draft_text=f"draft {status.value}", status=status.value,
        )
        async_session.add(d)
    await async_session.commit()

    # Query pending only
    stmt = (
        select(MessageDraft)
        .where(
            MessageDraft.doctor_id == "doc_1",
            MessageDraft.status.in_([DraftStatus.generated.value, DraftStatus.edited.value]),
        )
    )
    rows = (await async_session.execute(stmt)).scalars().all()

    statuses = {r.status for r in rows}
    assert statuses == {"generated", "edited"}
    assert len(rows) == 2
