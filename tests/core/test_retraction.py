"""Tests for red-flag retraction — Task 1.6 of chat-interview-merge plan."""
import pytest
import pytest_asyncio
from sqlalchemy import select

from db.models.patient_message import PatientMessage
from domain.patient_lifecycle.retraction import retract_recent_whitelist_replies


@pytest.mark.asyncio
async def test_retract_marks_recent_whitelist_replies_in_segment(db_session):
    """Whitelist AI replies in the target segment are marked retracted; patient turns are not."""
    seg_id = "seg_test_123"
    # Patient turn — should never be retracted
    patient_turn = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        direction="inbound",
        source="patient",
        content="挂号怎么改",
        intake_segment_id=seg_id,
        is_whitelist_reply=False,
        retracted=False,
    )
    # AI whitelist reply — should be retracted
    ai_whitelist = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        direction="outbound",
        source="ai",
        content="改预约时间...",
        intake_segment_id=seg_id,
        is_whitelist_reply=True,
        retracted=False,
    )
    db_session.add_all([patient_turn, ai_whitelist])
    await db_session.flush()

    count = await retract_recent_whitelist_replies(db_session, intake_segment_id=seg_id)
    assert count == 1

    msgs = (
        await db_session.execute(
            select(PatientMessage).where(PatientMessage.intake_segment_id == seg_id)
        )
    ).scalars().all()

    ai_msgs = [m for m in msgs if m.is_whitelist_reply and m.source == "ai"]
    assert all(m.retracted is True for m in ai_msgs), "whitelist AI replies must be retracted"

    non_whitelist = [m for m in msgs if not m.is_whitelist_reply]
    assert all(m.retracted is False for m in non_whitelist), "patient turns must remain unretracted"


@pytest.mark.asyncio
async def test_retract_does_not_touch_other_segments(db_session):
    """Retraction is scoped strictly to the given intake_segment_id."""
    other = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        direction="outbound",
        source="ai",
        content="其他",
        intake_segment_id="seg_other",
        is_whitelist_reply=True,
        retracted=False,
    )
    db_session.add(other)
    await db_session.flush()

    await retract_recent_whitelist_replies(db_session, intake_segment_id="seg_test_x")

    refreshed = (
        await db_session.execute(
            select(PatientMessage).where(PatientMessage.intake_segment_id == "seg_other")
        )
    ).scalar_one()
    assert refreshed.retracted is False


@pytest.mark.asyncio
async def test_retract_returns_zero_when_nothing_to_retract(db_session):
    """Returns 0 when segment has no un-retracted whitelist replies."""
    count = await retract_recent_whitelist_replies(db_session, intake_segment_id="seg_empty")
    assert count == 0


@pytest.mark.asyncio
async def test_retract_skips_already_retracted(db_session):
    """Already-retracted replies are not double-counted in the return value."""
    seg_id = "seg_already_done"
    already = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        direction="outbound",
        source="ai",
        content="already retracted",
        intake_segment_id=seg_id,
        is_whitelist_reply=True,
        retracted=True,
    )
    db_session.add(already)
    await db_session.flush()

    count = await retract_recent_whitelist_replies(db_session, intake_segment_id=seg_id)
    assert count == 0
