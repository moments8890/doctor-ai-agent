"""Tests for routers/approvals.py — REST endpoints.

All DB and service I/O is mocked.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.approvals import router, _to_out
from db.models import ApprovalItem


DOCTOR = "router_approval_doc"


def _make_item(
    approval_id: int = 1,
    status: str = "pending",
    patient_id: int = None,
    record_id: int = None,
    reviewer_note: str = None,
) -> ApprovalItem:
    item = MagicMock(spec=ApprovalItem)
    item.id = approval_id
    item.doctor_id = DOCTOR
    item.item_type = "medical_record"
    item.status = status
    item.suggested_data = json.dumps({
        "record": {"chief_complaint": "胸痛", "history_of_present_illness": None, "past_medical_history": None, "physical_examination": None, "auxiliary_examinations": None, "diagnosis": "冠心病", "treatment_plan": None, "follow_up_plan": None},
        "patient_name": "张三",
        "gender": "男",
        "age": 58,
        "existing_patient_id": None,
    })
    item.source_text = "原始文字"
    item.patient_id = patient_id
    item.record_id = record_id
    item.reviewer_note = reviewer_note
    item.reviewed_at = None
    item.created_at = datetime(2026, 3, 1, 12, 0, 0)
    return item


def _session_ctx(return_value=None):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=return_value or MagicMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# GET /api/approvals
# ---------------------------------------------------------------------------


async def test_list_approvals_returns_filtered_list():
    items = [_make_item(1, "pending"), _make_item(2, "pending")]

    with (
        patch("routers.approvals.AsyncSessionLocal", return_value=_session_ctx()),
        patch("routers.approvals.list_approval_items", new_callable=AsyncMock, return_value=items),
    ):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get(f"/api/approvals?doctor_id={DOCTOR}&status=pending")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["status"] == "pending"


async def test_list_approvals_no_status_filter():
    items = [_make_item(1, "pending"), _make_item(2, "approved")]

    with (
        patch("routers.approvals.AsyncSessionLocal", return_value=_session_ctx()),
        patch("routers.approvals.list_approval_items", new_callable=AsyncMock, return_value=items),
    ):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get(f"/api/approvals?doctor_id={DOCTOR}")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# GET /api/approvals/{id}
# ---------------------------------------------------------------------------


async def test_get_approval_returns_404_for_wrong_doctor():
    with (
        patch("routers.approvals.AsyncSessionLocal", return_value=_session_ctx()),
        patch("routers.approvals.get_approval_item", new_callable=AsyncMock, return_value=None),
    ):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get(f"/api/approvals/1?doctor_id=wrong_doc")

    assert resp.status_code == 404


async def test_get_approval_returns_item():
    item = _make_item(1)

    with (
        patch("routers.approvals.AsyncSessionLocal", return_value=_session_ctx()),
        patch("routers.approvals.get_approval_item", new_callable=AsyncMock, return_value=item),
    ):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get(f"/api/approvals/1?doctor_id={DOCTOR}")

    assert resp.status_code == 200
    assert resp.json()["id"] == 1


# ---------------------------------------------------------------------------
# PATCH /api/approvals/{id}/approve
# ---------------------------------------------------------------------------


async def test_approve_calls_commit_approval_returns_out():
    approved = _make_item(1, status="approved", patient_id=5, record_id=10)

    with patch("routers.approvals.commit_approval", new_callable=AsyncMock, return_value=approved):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(f"/api/approvals/1/approve?doctor_id={DOCTOR}", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["record_id"] == 10


async def test_approve_with_edited_data_passes_through():
    approved = _make_item(1, status="approved")
    edited = {
        "record": {"chief_complaint": "头晕", "history_of_present_illness": None, "past_medical_history": None, "physical_examination": None, "auxiliary_examinations": None, "diagnosis": None, "treatment_plan": None, "follow_up_plan": None},
        "patient_name": "王五",
        "gender": None,
        "age": None,
        "existing_patient_id": None,
    }

    with patch("routers.approvals.commit_approval", new_callable=AsyncMock, return_value=approved) as mock_commit:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(
            f"/api/approvals/1/approve?doctor_id={DOCTOR}",
            json={"edited_data": edited},
        )

    assert resp.status_code == 200
    call_kwargs = mock_commit.call_args[1]
    assert call_kwargs["edited_data"] == edited


async def test_approve_returns_404_for_unknown_id():
    with patch("routers.approvals.commit_approval", new_callable=AsyncMock, side_effect=ValueError("not found")):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(f"/api/approvals/999/approve?doctor_id={DOCTOR}", json={})

    assert resp.status_code == 404


async def test_approve_returns_422_if_already_processed():
    with patch("routers.approvals.commit_approval", new_callable=AsyncMock, side_effect=ValueError("status is 'approved'")):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(f"/api/approvals/1/approve?doctor_id={DOCTOR}", json={})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/approvals/{id}/reject
# ---------------------------------------------------------------------------


async def test_reject_does_not_call_commit_approval():
    rejected = _make_item(1, status="rejected")

    with (
        patch("routers.approvals.reject_approval", new_callable=AsyncMock, return_value=rejected),
        patch("routers.approvals.commit_approval", new_callable=AsyncMock) as mock_commit,
    ):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(f"/api/approvals/1/reject?doctor_id={DOCTOR}", json={})

    assert resp.status_code == 200
    mock_commit.assert_not_called()
    assert resp.json()["status"] == "rejected"


async def test_reject_stores_reviewer_note():
    rejected = _make_item(1, status="rejected", reviewer_note="转录错误")

    with patch("routers.approvals.reject_approval", new_callable=AsyncMock, return_value=rejected) as mock_reject:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.patch(
            f"/api/approvals/1/reject?doctor_id={DOCTOR}",
            json={"reviewer_note": "转录错误"},
        )

    assert resp.status_code == 200
    call_kwargs = mock_reject.call_args[1]
    assert call_kwargs["reviewer_note"] == "转录错误"
