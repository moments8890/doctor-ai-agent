"""engine.confirm must save reconciled collected back to the session row.

Bug E regression test. Pre-fix behavior: session.collected stays at the
pre-edit, pre-batch-extract value; rendered record uses the reconciled
value. Post-fix: both are equal.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.engine import IntakeEngine
from domain.intake.protocols import PersistRef
from domain.patients.intake_session import create_session, load_session


@pytest.mark.asyncio
async def test_confirm_persists_reconciled_collected_to_session():
    """Post-confirm, the session row must reflect the reconciled collected
    (doctor-edit merged + batch-extracted value)."""
    # Arrange: real session in DB seeded with a 'stale' value.
    doc_id = f"doc_ecp_{uuid.uuid4().hex[:8]}"
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    sess = await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode="doctor",
        initial_fields={"chief_complaint": "old", "_patient_name": "张三"},
    )

    fake_ref = PersistRef(kind="medical_record", id=4242)

    # Mock the template's batch_extractor to return a DIFFERENT value than
    # either the seed or the doctor edit — this is the post-reconcile truth.
    # Mock the writer (don't want to actually write a medical_record row).
    # Mock the doctor-mode hook (best-effort — isolate from engine save).
    with patch.object(
        __import__(
            "domain.intake.templates.medical_general",
            fromlist=["MedicalBatchExtractor"],
        ).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "newer"}),
    ), patch.object(
        __import__(
            "domain.intake.templates.medical_general",
            fromlist=["MedicalRecordWriter"],
        ).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ):
        engine = IntakeEngine()
        ref = await engine.confirm(
            session_id=sess.id,
            doctor_edits={"chief_complaint": "new"},
        )

    assert ref == fake_ref

    # Reload session row from DB — this is the crux of bug E.
    reloaded = await load_session(sess.id)
    assert reloaded is not None
    assert reloaded.collected["chief_complaint"] == "newer", (
        f"expected batch-extracted 'newer', got {reloaded.collected!r}"
    )


@pytest.mark.asyncio
async def test_confirm_persists_collected_before_hook_dispatch():
    """Hook failures must not unwind the reconciled collected. If a hook
    raises after persist, the session row still has the reconciled state.
    """
    doc_id = f"doc_echp_{uuid.uuid4().hex[:8]}"
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    sess = await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode="doctor",
        initial_fields={"chief_complaint": "old", "_patient_name": "张三"},
    )

    fake_ref = PersistRef(kind="medical_record", id=4343)

    with patch.object(
        __import__(
            "domain.intake.templates.medical_general",
            fromlist=["MedicalBatchExtractor"],
        ).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "newer"}),
    ), patch.object(
        __import__(
            "domain.intake.templates.medical_general",
            fromlist=["MedicalRecordWriter"],
        ).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        engine = IntakeEngine()
        # Hook failure is best-effort; confirm must NOT raise.
        await engine.confirm(
            session_id=sess.id,
            doctor_edits={"chief_complaint": "new"},
        )

    reloaded = await load_session(sess.id)
    assert reloaded is not None
    assert reloaded.collected["chief_complaint"] == "newer"
