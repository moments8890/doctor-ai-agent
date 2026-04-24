"""Doctor inline-edit (PATCH /field) must validate against the active
template's extractor field set — not the legacy hardcoded FIELD_LABELS.

Phase 4 r2 — bug C. Pre-fix behavior: any specialty field like
``onset_time`` / ``neuro_exam`` / ``vascular_risk_factors`` on a neuro
session returned 422 because the handler gated on ``FIELD_LABELS``.
Post-fix: the handler computes allowed fields from
``get_template(session.template_id).extractor.fields()``, so any field
declared by the session's template is accepted.

These are unit-level tests. External dependencies (JWT auth, session
lookup+ownership check, session persistence) are mocked so the tests
exercise only the validation branch.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from channels.web.doctor_interview.shared import FieldUpdateRequest
from channels.web.doctor_interview.turn import update_interview_field
from domain.interview.protocols import FieldSpec
from domain.patients.interview_session import InterviewSession


# ── helpers ──────────────────────────────────────────────────────────


def _make_session(
    template_id: str = "medical_general_v1",
    collected: dict[str, str] | None = None,
) -> InterviewSession:
    return InterviewSession(
        id="session-uuid-test",
        doctor_id="dr_test",
        patient_id=1,
        mode="doctor",
        template_id=template_id,
        collected=collected if collected is not None else {},
    )


def _fake_template(field_names: list[str]):
    """Build a fake template whose extractor.fields() returns FieldSpecs
    with the given names. Only ``name`` is read by the validation branch;
    other FieldSpec attrs get sensible defaults."""
    specs = [
        FieldSpec(name=n, type="string", description=f"desc-{n}")
        for n in field_names
    ]
    extractor = MagicMock()
    extractor.fields = MagicMock(return_value=specs)
    template = MagicMock()
    template.extractor = extractor
    return template


async def _call_patch(
    *,
    session: InterviewSession,
    field: str,
    value: str,
    template=None,
):
    """Invoke the handler with auth / session-lookup / save mocked out.

    If ``template`` is provided, ``get_template`` is patched to return it
    verbatim. Otherwise the real registry is used.
    """
    body = FieldUpdateRequest(
        session_id=session.id,
        doctor_id=session.doctor_id,
        field=field,
        value=value,
    )

    patchers = [
        patch(
            "channels.web.doctor_interview.turn._resolve_doctor_id",
            new_callable=AsyncMock,
            return_value=session.doctor_id,
        ),
        patch(
            "channels.web.doctor_interview.turn._verify_session",
            new_callable=AsyncMock,
            return_value=session,
        ),
        patch(
            "channels.web.doctor_interview.turn.save_session",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ]
    if template is not None:
        patchers.append(
            patch(
                "channels.web.doctor_interview.turn.get_template",
                return_value=template,
            )
        )

    for p in patchers:
        p.start()
    try:
        return await update_interview_field(body=body, authorization="fake-token")
    finally:
        for p in patchers:
            p.stop()


# ── tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inline_edit_legacy_general_field_still_works():
    """Editing a legacy medical_general_v1 field (past_history) still 200s.

    Regression guard: widening the validation from FIELD_LABELS to the
    template's extractor must not break the general-template happy path.
    Uses the real template registry (no template mock) so this exercises
    the full lookup.
    """
    session = _make_session(template_id="medical_general_v1")
    resp = await _call_patch(
        session=session,
        field="past_history",
        value="高血压10年",
    )
    assert resp.collected["past_history"] == "高血压10年"


@pytest.mark.asyncio
async def test_inline_edit_onset_time_on_neuro_session_succeeds():
    """A session whose template exposes ``onset_time`` accepts the PATCH.

    Task 8 hasn't registered medical_neuro_v1 yet, so we inject a fake
    template via ``get_template`` that advertises the neuro fields. The
    handler's validation must call through to ``template.extractor.fields()``
    and accept ``onset_time``.
    """
    session = _make_session(template_id="medical_neuro_v1")
    template = _fake_template(
        field_names=[
            "chief_complaint",
            "present_illness",
            "onset_time",
            "neuro_exam",
            "vascular_risk_factors",
        ]
    )
    resp = await _call_patch(
        session=session,
        field="onset_time",
        value="2小时前",
        template=template,
    )
    assert resp.collected["onset_time"] == "2小时前"


@pytest.mark.asyncio
async def test_inline_edit_unknown_field_422():
    """Unknown field name → 422 with a clear detail message."""
    session = _make_session(template_id="medical_general_v1")
    with pytest.raises(HTTPException) as exc:
        await _call_patch(
            session=session,
            field="not_a_real_field",
            value="whatever",
        )
    assert exc.value.status_code == 422
    assert "not_a_real_field" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_inline_edit_uses_active_template_not_hardcoded_labels():
    """Validation set comes from the template, not a hardcoded label map.

    The fake template exposes a field (``exotic_template_only_field``)
    that is NOT in the legacy medical_general_v1 FIELD_LABELS. Pre-fix,
    the gate would reject it with 422 even though the template declares
    it. Post-fix, the PATCH succeeds and the field is written.
    """
    session = _make_session(template_id="whatever_template_v1")
    template = _fake_template(
        field_names=[
            "chief_complaint",
            "exotic_template_only_field",
        ]
    )
    resp = await _call_patch(
        session=session,
        field="exotic_template_only_field",
        value="some-unusual-value",
        template=template,
    )
    assert resp.collected["exotic_template_only_field"] == "some-unusual-value"


@pytest.mark.asyncio
async def test_inline_edit_unknown_template_422():
    """Session referencing an un-registered template id → 422, not crash.

    If ``session.template_id`` points at a missing registry entry, the
    handler must surface a 422 (not raise UnknownTemplate up to the
    FastAPI transport layer).
    """
    session = _make_session(template_id="does_not_exist_v9")
    with pytest.raises(HTTPException) as exc:
        await _call_patch(
            session=session,
            field="chief_complaint",
            value="x",
        )
    assert exc.value.status_code == 422
