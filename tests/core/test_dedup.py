"""Dedup detection tests — chief_complaint similarity AND episode signals.

Spec §5a: same complaint text after a doctor decision or status advance
is by definition a NEW clinical episode, never a duplicate. The episode
signals override similarity even at very high scores.

Three bands by similarity:
  ≥ 0.7         auto_merge (with episode signals clear)
  [0.5, 0.7)    patient_prompt
  < 0.5         no dedup
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_high_similarity_clear_signals_returns_same_episode():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛",
            target_complaint="头疼",
            signals=signals,
        )
    assert result.same_episode is True
    assert result.band == "auto_merge"


@pytest.mark.asyncio
async def test_high_similarity_but_treatment_event_returns_new_episode():
    # Treatment event since last → patient came back about a complication
    # or a related-but-distinct issue. Never auto-merge.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=True,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_high_similarity_but_status_change_returns_new_episode():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=True,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_high_similarity_but_over_24h_returns_new_episode():
    # 24h+ gap = different episode regardless of text similarity.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.85),
    ):
        signals = EpisodeSignals(
            hours_since_last=25.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头疼", signals=signals,
        )
    assert result.same_episode is False


@pytest.mark.asyncio
async def test_band_in_ambiguous_range_returns_prompt():
    # 0.6 is in [0.5, 0.7) — match enough to suspect, not enough to merge
    # without checking with the patient.
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.6),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="头晕", signals=signals,
        )
    assert result.same_episode is True
    assert result.band == "patient_prompt"


@pytest.mark.asyncio
async def test_low_similarity_returns_no_dedup():
    from domain.patient_lifecycle.dedup import EpisodeSignals, detect_same_episode

    with patch(
        "domain.patient_lifecycle.dedup._llm_chief_complaint_similarity",
        AsyncMock(return_value=0.3),
    ):
        signals = EpisodeSignals(
            hours_since_last=2.0,
            treatment_event_since_last=False,
            status_change_since_last=False,
        )
        result = await detect_same_episode(
            draft_complaint="头痛", target_complaint="腿肿", signals=signals,
        )
    assert result.same_episode is False
    assert result.band == "none"


# ── Append-only merge (§5b) ────────────────────────────────────────
# Tests use the in-memory db_session fixture from tests/core/conftest.py
# (fresh SQLite :memory: each test, all tables created via Base.metadata).


import uuid
from datetime import datetime as _dt


async def _seed_record_with_chief(session, chief_text="头痛"):
    """Seed a minimal doctor + record + chief_complaint FieldEntry row."""
    from db.models.doctor import Doctor
    from db.models.records import FieldEntryDB, MedicalRecordDB

    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    session.add(Doctor(doctor_id=doc_id))
    await session.flush()

    record = MedicalRecordDB(
        doctor_id=doc_id,
        record_type="visit",
        chief_complaint=chief_text,
    )
    session.add(record)
    await session.flush()

    session.add(
        FieldEntryDB(
            record_id=record.id,
            field_name="chief_complaint",
            text=chief_text,
            intake_segment_id="segment_1",
            created_at=_dt.utcnow(),
        )
    )
    await session.flush()
    return record


@pytest.mark.asyncio
async def test_merge_appends_field_entries_no_overwrite(db_session):
    from sqlalchemy import select

    from db.models.records import FieldEntryDB
    from domain.patient_lifecycle.dedup import merge_into_existing

    record = await _seed_record_with_chief(db_session, "头痛")
    rid = record.id

    await merge_into_existing(
        db_session,
        target_record_id=rid,
        new_fields={"chief_complaint": "头痛加重", "present_illness": "今天又痛了"},
        intake_segment_id="segment_2",
    )

    entries = (
        await db_session.execute(
            select(FieldEntryDB)
            .where(FieldEntryDB.record_id == rid)
            .order_by(FieldEntryDB.id)
        )
    ).scalars().all()

    chief = [e for e in entries if e.field_name == "chief_complaint"]
    assert len(chief) == 2, "expected original + new chief_complaint entries"
    assert chief[0].text == "头痛"
    assert chief[1].text == "头痛加重"
    assert chief[1].intake_segment_id == "segment_2"

    pi = [e for e in entries if e.field_name == "present_illness"]
    assert len(pi) == 1
    assert pi[0].text == "今天又痛了"


@pytest.mark.asyncio
async def test_merge_skips_duplicate_chief_complaint(db_session):
    from sqlalchemy import select

    from db.models.records import FieldEntryDB
    from domain.patient_lifecycle.dedup import merge_into_existing

    record = await _seed_record_with_chief(db_session, "头痛")
    rid = record.id

    # Same complaint text — should be skipped (no point appending duplicate).
    await merge_into_existing(
        db_session,
        target_record_id=rid,
        new_fields={"chief_complaint": "头痛"},
        intake_segment_id="segment_2",
    )

    chief = (
        await db_session.execute(
            select(FieldEntryDB).where(
                FieldEntryDB.record_id == rid,
                FieldEntryDB.field_name == "chief_complaint",
            )
        )
    ).scalars().all()
    assert len(chief) == 1, "duplicate chief_complaint should be skipped"


# ── Supplement for reviewed records (§5c) ─────────────────────────


async def _seed_completed_record(session):
    """Seed a minimal doctor + completed MedicalRecordDB (no FieldEntryDB rows)."""
    from db.models.doctor import Doctor
    from db.models.records import MedicalRecordDB, RecordStatus

    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    session.add(Doctor(doctor_id=doc_id))
    await session.flush()

    record = MedicalRecordDB(
        doctor_id=doc_id,
        record_type="visit",
        status=RecordStatus.completed.value,
    )
    session.add(record)
    await session.flush()
    return record


# test_create_supplement_* removed 2026-04-25 — record_supplements table dropped.
# Patient submissions to closed records now create their own pending_review
# medical_record (the doctor reviews it as a new case). See chat.py:691 for
# the new behavior — the merge action with target_reviewed=True declines
# the merge and leaves the draft as-is.
