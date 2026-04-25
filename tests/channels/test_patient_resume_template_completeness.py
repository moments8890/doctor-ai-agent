"""Patient-portal resume/current readiness must route through the active
template's extractor, not the legacy ``medical_general_v1`` helper (Phase 4
r2 — bug B).

The /turn endpoint already routes through ``InterviewEngine.next_turn``
which internally calls ``template.extractor.completeness``. The bug lived
in the /current handler and the resume branch of /start, which hardcoded
``check_completeness`` against ``medical_general_v1`` fields — so a
neuro session was being judged complete without its required
``onset_time`` field, and the status transition to ``reviewing`` fired
at the wrong moment.

These tests:

1. Patch ``get_template`` to inject a fake template whose extractor
   reports a known ``CompletenessState``; assert the routes reflect it.
2. Exercise the legacy ``medical_general_v1`` path end-to-end so we
   don't silently lose existing coverage.
3. Cover the full flow: /current + /start resume both consult the
   template extractor, and transition to ``reviewing`` once
   ``can_complete`` flips True.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.web.patient_interview_routes import (
    InterviewStartRequest,
    current_session,
    start_interview,
)
from db.models.interview_session import InterviewStatus
from domain.interview.protocols import CompletenessState
from domain.patients.interview_session import InterviewSession


# ── helpers ──────────────────────────────────────────────────────────


def _make_patient(patient_id: int = 1, doctor_id: str = "dr_test") -> MagicMock:
    p = MagicMock()
    p.id = patient_id
    p.doctor_id = doctor_id
    p.name = f"Patient {patient_id}"
    return p


def _active_session(
    *,
    template_id: str,
    status: str = InterviewStatus.interviewing,
    collected: dict | None = None,
) -> InterviewSession:
    return InterviewSession(
        id="session-uuid",
        doctor_id="dr_test",
        patient_id=1,
        mode="patient",
        status=status,
        template_id=template_id,
        collected=collected or {},
        conversation=[],
    )


class _FakeExtractor:
    """Extractor whose ``completeness`` returns a preset ``CompletenessState``.

    Captures call args so tests can assert the route actually invoked us
    with the session's collected + ``"patient"`` mode.
    """

    def __init__(self, state: CompletenessState) -> None:
        self.state = state
        self.calls: list[tuple[dict, str]] = []

    def completeness(self, collected, mode):
        # Tests pass a real dict or None — normalize for comparison.
        self.calls.append((dict(collected or {}), mode))
        return self.state


class _FakeTemplate:
    def __init__(self, extractor: _FakeExtractor) -> None:
        self.extractor = extractor


@asynccontextmanager
async def _noop_async_session():
    yield MagicMock()


def _patch_current(active, get_template_side_effect=None, save_mock=None):
    """Patcher stack for /current."""
    patchers = [
        patch(
            "channels.web.patient_interview_routes._authenticate_patient",
            new_callable=AsyncMock,
            return_value=_make_patient(),
        ),
        patch(
            "channels.web.patient_interview_routes.get_active_session",
            new_callable=AsyncMock,
            return_value=active,
        ),
        patch(
            "channels.web.patient_interview_routes.save_session",
            save_mock or AsyncMock(),
        ),
    ]
    if get_template_side_effect is not None:
        patchers.append(
            patch(
                "channels.web.patient_interview_routes.get_template",
                side_effect=get_template_side_effect,
            ),
        )
    return patchers


def _patch_start(active, get_template_side_effect=None, save_mock=None):
    """Patcher stack for /start resume branch (active session exists)."""
    patchers = [
        patch(
            "channels.web.patient_interview_routes._authenticate_patient",
            new_callable=AsyncMock,
            return_value=_make_patient(),
        ),
        patch(
            "channels.web.patient_interview_routes._get_doctor_name",
            new_callable=AsyncMock,
            return_value="测试医生",
        ),
        patch(
            "channels.web.patient_interview_routes.get_active_session",
            new_callable=AsyncMock,
            return_value=active,
        ),
        patch(
            "channels.web.patient_interview_routes.save_session",
            save_mock or AsyncMock(),
        ),
    ]
    if get_template_side_effect is not None:
        patchers.append(
            patch(
                "channels.web.patient_interview_routes.get_template",
                side_effect=get_template_side_effect,
            ),
        )
    return patchers


def _start_patchers(patchers):
    for p in patchers:
        p.start()


def _stop_patchers(patchers):
    for p in patchers:
        p.stop()


# ── tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_current_uses_template_extractor_completeness():
    """/current must ask the active template's extractor, not the legacy helper.

    We patch ``get_template`` to return a fake whose ``completeness`` yields
    a known ``CompletenessState`` with ``can_complete=False``. The route's
    response must reflect that state exactly.
    """
    extractor = _FakeExtractor(
        CompletenessState(
            can_complete=False,
            required_missing=["onset_time"],
            recommended_missing=[],
            optional_missing=[],
            next_focus="onset_time",
        ),
    )
    template = _FakeTemplate(extractor)
    active = _active_session(
        template_id="medical_neuro_v1_fake",
        collected={"chief_complaint": "左侧肢体无力"},
    )

    patchers = _patch_current(
        active, get_template_side_effect=lambda _tid: template,
    )
    _start_patchers(patchers)
    try:
        resp = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    # Route called extractor.completeness exactly once with the session's
    # collected dict and patient mode.
    assert len(extractor.calls) == 1
    called_collected, called_mode = extractor.calls[0]
    assert called_collected == {"chief_complaint": "左侧肢体无力"}
    assert called_mode == "patient"

    # Response mirrors state: can_complete=False → ready_to_review=False
    # and status stays interviewing.
    assert resp["ready_to_review"] is False
    assert resp["status"] == InterviewStatus.interviewing


@pytest.mark.asyncio
async def test_current_flips_status_when_template_says_can_complete():
    """When the template extractor reports ``can_complete=True`` and status
    is still ``interviewing``, /current must flip it to ``reviewing`` and
    persist the change.
    """
    extractor = _FakeExtractor(
        CompletenessState(
            can_complete=True,
            required_missing=[],
            recommended_missing=["past_history"],
            optional_missing=[],
            next_focus=None,
        ),
    )
    template = _FakeTemplate(extractor)
    active = _active_session(
        template_id="medical_neuro_v1_fake",
        status=InterviewStatus.interviewing,
        collected={
            "chief_complaint": "左侧肢体无力",
            "onset_time": "2小时前",
            "present_illness": "突发左侧肢体无力",
        },
    )

    save_mock = AsyncMock()
    patchers = _patch_current(
        active,
        get_template_side_effect=lambda _tid: template,
        save_mock=save_mock,
    )
    _start_patchers(patchers)
    try:
        resp = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    assert resp["ready_to_review"] is True
    assert resp["status"] == InterviewStatus.reviewing
    # Transition was persisted.
    save_mock.assert_awaited_once()
    # The session object we passed in has been mutated in place.
    assert active.status == InterviewStatus.reviewing


@pytest.mark.asyncio
async def test_start_resume_uses_template_extractor_completeness():
    """The /start "resume" branch (active session already exists) must also
    route through the template extractor, not the legacy helper."""
    extractor = _FakeExtractor(
        CompletenessState(
            can_complete=False,
            required_missing=["onset_time"],
            recommended_missing=[],
            optional_missing=[],
            next_focus="onset_time",
        ),
    )
    template = _FakeTemplate(extractor)
    active = _active_session(
        template_id="medical_neuro_v1_fake",
        collected={"chief_complaint": "头痛"},
    )

    patchers = _patch_start(
        active, get_template_side_effect=lambda _tid: template,
    )
    _start_patchers(patchers)
    try:
        resp = await start_interview(
            authorization="tok",
            template_id=None,
            body=None,
        )
    finally:
        _stop_patchers(patchers)

    assert len(extractor.calls) == 1
    called_collected, called_mode = extractor.calls[0]
    assert called_collected == {"chief_complaint": "头痛"}
    assert called_mode == "patient"
    assert resp["resumed"] is True
    assert resp["ready_to_review"] is False
    assert resp["status"] == InterviewStatus.interviewing


@pytest.mark.asyncio
async def test_start_resume_transitions_to_reviewing_when_can_complete():
    """When the template extractor flips ``can_complete=True``, the resume
    branch transitions the session to ``reviewing`` and persists.

    This models the neuro case end-to-end: once ``onset_time`` is filled,
    the template reports ``can_complete=True`` and the resume path flips
    the session. If the route still used ``check_completeness`` against
    ``medical_general_v1`` fields, the transition would fire at the wrong
    moment — this test guards against regression.
    """
    extractor = _FakeExtractor(
        CompletenessState(
            can_complete=True,
            required_missing=[],
            recommended_missing=[],
            optional_missing=[],
            next_focus=None,
        ),
    )
    template = _FakeTemplate(extractor)
    active = _active_session(
        template_id="medical_neuro_v1_fake",
        status=InterviewStatus.interviewing,
        collected={
            "chief_complaint": "左侧肢体无力",
            "onset_time": "2小时前",
            "present_illness": "突发",
        },
    )

    save_mock = AsyncMock()
    patchers = _patch_start(
        active,
        get_template_side_effect=lambda _tid: template,
        save_mock=save_mock,
    )
    _start_patchers(patchers)
    try:
        resp = await start_interview(
            authorization="tok",
            template_id=None,
            body=None,
        )
    finally:
        _stop_patchers(patchers)

    assert resp["ready_to_review"] is True
    assert resp["status"] == InterviewStatus.reviewing
    save_mock.assert_awaited_once()
    assert active.status == InterviewStatus.reviewing


@pytest.mark.asyncio
async def test_medical_general_v1_legacy_path_still_works():
    """Regression: the default ``medical_general_v1`` flow is unchanged.

    No ``get_template`` patch — we exercise the real template registry.
    An empty ``collected`` dict has no required fields filled, so the real
    ``GeneralMedicalExtractor.completeness`` reports ``can_complete=False``.
    The route reports ``ready_to_review=False`` and leaves status alone.
    """
    active = _active_session(
        template_id="medical_general_v1",
        status=InterviewStatus.interviewing,
        collected={},
    )

    patchers = _patch_current(active)  # no fake template override
    _start_patchers(patchers)
    try:
        resp = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    assert resp["ready_to_review"] is False
    assert resp["status"] == InterviewStatus.interviewing


@pytest.mark.asyncio
async def test_medical_general_v1_legacy_path_completes_when_required_filled():
    """Regression: filling all ``medical_general_v1`` patient-mode required
    fields (every subjective field) really does mark the session ready.

    Patient mode requires the full pre-consultation loop — ``chief_complaint``
    + ``present_illness`` + 既往/过敏/家族/个人/婚育史 — to match the prompt's
    stop condition. This proves the route still flips when all are filled.
    """
    active = _active_session(
        template_id="medical_general_v1",
        status=InterviewStatus.interviewing,
        collected={
            "chief_complaint": "头痛三天",
            "present_illness": "持续性头痛，无呕吐",
            "past_history": "无",
            "allergy_history": "无",
            "family_history": "无",
            "personal_history": "无",
            "marital_reproductive": "无",
        },
    )

    save_mock = AsyncMock()
    patchers = _patch_current(active, save_mock=save_mock)
    _start_patchers(patchers)
    try:
        resp = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    assert resp["ready_to_review"] is True
    assert resp["status"] == InterviewStatus.reviewing
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_neuro_style_session_not_complete_without_onset_time():
    """Mimics the Task 3 neuro extractor: the patient-mode subject subset
    is widened to include ``onset_time`` as required, so a session with
    only ``chief_complaint`` is NOT complete — even though the legacy
    ``medical_general_v1`` path would have called it done.

    We simulate this with a ``_FakeExtractor`` because
    ``medical_neuro_v1`` is not yet registered (that lands in Task 8).
    The neuro-specific end-to-end test follows after Task 8.
    """
    # Mirror GeneralNeuroExtractor.completeness semantics: required adds
    # ``onset_time`` to the patient subject subset.
    def _neuro_like_completeness(collected, _mode):
        required = ("chief_complaint", "onset_time")
        missing = [f for f in required if not collected.get(f)]
        return CompletenessState(
            can_complete=len(missing) == 0,
            required_missing=missing,
            recommended_missing=[],
            optional_missing=[],
            next_focus=missing[0] if missing else None,
        )

    extractor = MagicMock()
    extractor.completeness = MagicMock(side_effect=_neuro_like_completeness)
    template = _FakeTemplate(extractor)

    # Step 1: only chief_complaint filled → NOT ready.
    active = _active_session(
        template_id="medical_neuro_v1_fake",
        collected={"chief_complaint": "左侧肢体无力"},
    )
    patchers = _patch_current(
        active, get_template_side_effect=lambda _tid: template,
    )
    _start_patchers(patchers)
    try:
        resp_before = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    assert resp_before["ready_to_review"] is False
    assert resp_before["status"] == InterviewStatus.interviewing

    # Step 2: onset_time now filled → ready + transitions.
    active2 = _active_session(
        template_id="medical_neuro_v1_fake",
        collected={
            "chief_complaint": "左侧肢体无力",
            "onset_time": "2小时前",
        },
    )
    save_mock = AsyncMock()
    patchers = _patch_current(
        active2,
        get_template_side_effect=lambda _tid: template,
        save_mock=save_mock,
    )
    _start_patchers(patchers)
    try:
        resp_after = await current_session(authorization="tok")
    finally:
        _stop_patchers(patchers)

    assert resp_after["ready_to_review"] is True
    assert resp_after["status"] == InterviewStatus.reviewing
    save_mock.assert_awaited_once()
    # TODO(phase4): after Task 8 registers medical_neuro_v1, swap this
    # MagicMock extractor for the real GeneralNeuroExtractor and drop the
    # ``_fake`` template_id suffix.
