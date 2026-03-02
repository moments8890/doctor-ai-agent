from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.ui as ui


class _SessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _record(**kwargs):
    defaults = dict(
        id=1,
        patient_id=11,
        doctor_id="doc_default",
        chief_complaint="胸闷",
        history_of_present_illness="两周",
        past_medical_history="高血压",
        physical_examination="血压偏高",
        auxiliary_examinations="心电图异常",
        diagnosis="冠心病",
        treatment_plan="随访",
        follow_up_plan="两周复诊",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
        patient=SimpleNamespace(name="张三"),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def test_chat_page_and_manage_page_return_html():
    chat_resp = await ui.chat_page()
    manage_resp = await ui.manage_page()

    assert chat_resp.status_code == 200
    assert b"Doctor AI Chat" in chat_resp.body
    assert manage_resp.status_code == 200
    assert b"Doctor Management Console" in manage_resp.body


def test_fmt_ts():
    assert ui._fmt_ts(None) is None
    assert ui._fmt_ts(datetime(2026, 3, 2, 10, 30, 0)) == "2026-03-02 10:30:00"


def test_parse_tags_empty_invalid_and_valid_json():
    assert ui._parse_tags(None) == []
    assert ui._parse_tags("") == []
    assert ui._parse_tags("not-json") == []
    assert ui._parse_tags('["recent_visit"]') == ["recent_visit"]


def _patient_ns(**kwargs):
    """SimpleNamespace patient with all required fields including category."""
    defaults = dict(
        id=11,
        name="张三",
        gender="男",
        year_of_birth=1980,
        created_at=datetime(2026, 3, 1, 8, 0, 0),
        primary_category="new",
        category_tags="[]",
        category_computed_at=None,
        category_rules_version="v1",
        primary_risk_level="low",
        risk_tags='["no_records"]',
        risk_score=0,
        follow_up_state="not_needed",
        risk_computed_at=None,
        risk_rules_version="risk-v1",
        labels=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def test_manage_patients_includes_record_counts():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 2), (12, 1)]))
    )
    patients = [
        _patient_ns(id=11, name="张三", gender="男", year_of_birth=1980, created_at=datetime(2026, 3, 1, 8, 0, 0)),
        _patient_ns(id=12, name="李四", gender=None, year_of_birth=None, created_at=None),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)

    assert data["doctor_id"] == "doc1"
    assert data["items"][0]["record_count"] == 2
    assert data["items"][0]["created_at"] == "2026-03-01 08:00:00"
    assert data["items"][1]["record_count"] == 1
    assert data["items"][1]["created_at"] is None


async def test_manage_records_with_patient_filter():
    db = SimpleNamespace()
    records = [_record(id=21, patient_id=11, patient=None)]
    patients = [SimpleNamespace(id=11, name="张三"), SimpleNamespace(id=12, name="李四")]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_records_for_patient", new=AsyncMock(return_value=records)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_records(doctor_id="doc1", patient_id=11, limit=5)

    assert data["doctor_id"] == "doc1"
    assert len(data["items"]) == 1
    assert data["items"][0]["patient_name"] == "张三"
    assert data["items"][0]["created_at"] == "2026-03-02 10:00:00"


async def test_manage_records_without_patient_filter():
    db = SimpleNamespace()
    records = [
        _record(id=31, patient=SimpleNamespace(name="王五")),
        _record(id=32, patient=None, created_at=None),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_records_for_doctor", new=AsyncMock(return_value=records)):
        data = await ui.manage_records(doctor_id="doc2", patient_id=None, limit=10)

    assert data["doctor_id"] == "doc2"
    assert data["items"][0]["patient_name"] == "王五"
    assert data["items"][0]["treatment_plan"] == "随访"
    assert data["items"][0]["follow_up_plan"] == "两周复诊"
    assert data["items"][1]["patient_name"] is None
    assert data["items"][1]["treatment_plan"] == "随访"
    assert data["items"][1]["follow_up_plan"] == "两周复诊"
    assert data["items"][1]["created_at"] is None


async def test_manage_prompts_present_and_empty():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_system_prompt", new=AsyncMock(side_effect=[SimpleNamespace(content="base"), None])):
        data = await ui.manage_prompts()
    assert data["structuring"] == "base"
    assert data["structuring_extension"] == ""


async def test_update_prompt_validation_and_success():
    with pytest.raises(HTTPException) as exc:
        await ui.update_prompt("not-allowed", ui.PromptUpdate(content="x"))
    assert exc.value.status_code == 400

    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.upsert_system_prompt", new=AsyncMock()) as upsert:
        data = await ui.update_prompt("structuring", ui.PromptUpdate(content="new"))

    upsert.assert_awaited_once()
    assert data == {"ok": True, "key": "structuring"}


def _patient(**kwargs):
    defaults = dict(
        id=11,
        name="张三",
        gender="男",
        year_of_birth=1980,
        created_at=datetime(2026, 3, 1, 8, 0, 0),
        primary_category="new",
        category_tags='["recent_visit"]',
        category_computed_at=datetime(2026, 3, 2, 10, 0, 0),
        category_rules_version="v1",
        primary_risk_level="low",
        risk_tags='["no_records"]',
        risk_score=0,
        follow_up_state="not_needed",
        risk_computed_at=datetime(2026, 3, 2, 10, 5, 0),
        risk_rules_version="risk-v1",
        labels=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _label_ns(**kwargs):
    defaults = dict(id=1, name="转诊候选", color="#FF4444", created_at=datetime(2026, 3, 2, 9, 0, 0), doctor_id="doc1")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


async def test_manage_patients_includes_category_fields():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 3)]))
    )
    patients = [_patient()]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)

    item = data["items"][0]
    assert item["primary_category"] == "new"
    assert item["category_tags"] == ["recent_visit"]
    assert item["category_computed_at"] == "2026-03-02 10:00:00"
    assert item["category_rules_version"] == "v1"
    assert item["primary_risk_level"] == "low"
    assert item["risk_tags"] == ["no_records"]
    assert item["risk_score"] == 0
    assert item["follow_up_state"] == "not_needed"
    assert item["risk_rules_version"] == "risk-v1"


async def test_manage_patients_category_filter():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )
    patients = [
        _patient_ns(id=11, name="高风险患者", primary_category="high_risk"),
        _patient_ns(id=12, name="新患者", primary_category="new"),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category="high_risk")

    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "高风险患者"


async def test_manage_patients_risk_filter():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )
    patients = [
        _patient_ns(id=11, name="高风险患者", primary_risk_level="high"),
        _patient_ns(id=12, name="低风险患者", primary_risk_level="low"),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", risk="high")

    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "高风险患者"


async def test_manage_patients_grouped():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )
    patients = [
        _patient_ns(id=11, name="高风险患者", primary_category="high_risk"),
        _patient_ns(id=12, name="随访患者", primary_category="active_followup"),
        _patient_ns(id=13, name="新患者", primary_category="new"),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients_grouped("doc1")

    assert data["doctor_id"] == "doc1"
    assert "groups" in data
    group_names = [g["group"] for g in data["groups"]]
    assert group_names == ["high_risk", "active_followup", "stable", "new", "uncategorized"]

    high_risk_group = next(g for g in data["groups"] if g["group"] == "high_risk")
    assert high_risk_group["count"] == 1
    assert high_risk_group["items"][0]["name"] == "高风险患者"

    stable_group = next(g for g in data["groups"] if g["group"] == "stable")
    assert stable_group["count"] == 0
    assert stable_group["items"] == []


async def test_manage_patients_grouped_unknown_category_goes_to_uncategorized():
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    patients = [
        _patient_ns(id=21, name="未知分类患者", primary_category="custom_future_category"),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients_grouped("doc1")

    uncategorized = next(g for g in data["groups"] if g["group"] == "uncategorized")
    assert uncategorized["count"] == 1
    assert uncategorized["items"][0]["name"] == "未知分类患者"


async def test_manage_patients_grouped_risk():
    db = SimpleNamespace()
    patients = [
        _patient_ns(id=11, name="危重", primary_risk_level="critical", risk_score=99),
        _patient_ns(id=12, name="高风险", primary_risk_level="high", risk_score=75),
    ]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients_grouped_risk("doc1")

    assert data["doctor_id"] == "doc1"
    critical = next(g for g in data["groups"] if g["group"] == "critical")
    assert critical["count"] == 1
    assert critical["items"][0]["name"] == "危重"


async def test_manage_patient_timeline_not_found():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.build_patient_timeline", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await ui.manage_patient_timeline(patient_id=99, doctor_id="doc1", limit=50)

    assert exc.value.status_code == 404


async def test_manage_patient_timeline_success():
    db = SimpleNamespace()
    payload = {"patient": {"id": 11, "name": "张三"}, "events": [{"type": "record", "id": 1}]}
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.build_patient_timeline", new=AsyncMock(return_value=payload)):
        data = await ui.manage_patient_timeline(patient_id=11, doctor_id="doc1", limit=50)

    assert data["doctor_id"] == "doc1"
    assert data["patient"]["name"] == "张三"
    assert data["events"][0]["id"] == 1


# ---------------------------------------------------------------------------
# Label endpoints
# ---------------------------------------------------------------------------


async def test_list_labels_returns_items():
    db = SimpleNamespace()
    labels = [_label_ns(id=1, name="转诊候选"), _label_ns(id=2, name="重点随访", color="#4444FF")]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_labels_for_doctor", new=AsyncMock(return_value=labels)):
        data = await ui.list_labels(doctor_id="doc1")
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "转诊候选"
    assert data["items"][1]["color"] == "#4444FF"


async def test_create_label():
    db = SimpleNamespace()
    new_lbl = _label_ns(id=5, name="医保报销中", color="#22BB44")
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.create_label", new=AsyncMock(return_value=new_lbl)):
        data = await ui.create_label_endpoint(ui.LabelCreate(doctor_id="doc1", name="医保报销中", color="#22BB44"))
    assert data["id"] == 5
    assert data["name"] == "医保报销中"
    assert data["color"] == "#22BB44"


async def test_update_label():
    db = SimpleNamespace()
    updated = _label_ns(id=3, name="新名称", color="#000000")
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.update_label", new=AsyncMock(return_value=updated)):
        data = await ui.update_label_endpoint(3, ui.LabelUpdate(doctor_id="doc1", name="新名称"))
    assert data["id"] == 3
    assert data["name"] == "新名称"


async def test_update_label_not_found_raises_404():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.update_label", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await ui.update_label_endpoint(99, ui.LabelUpdate(doctor_id="doc1", name="x"))
    assert exc.value.status_code == 404


async def test_delete_label():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.delete_label", new=AsyncMock(return_value=True)):
        data = await ui.delete_label_endpoint(1, doctor_id="doc1")
    assert data == {"ok": True}


async def test_assign_label_to_patient():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.assign_label", new=AsyncMock(return_value=None)):
        data = await ui.assign_label_endpoint(11, 1, doctor_id="doc1")
    assert data == {"ok": True}


async def test_remove_label_from_patient():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.remove_label", new=AsyncMock(return_value=None)):
        data = await ui.remove_label_endpoint(11, 1, doctor_id="doc1")
    assert data == {"ok": True}


async def test_patients_list_includes_labels_field():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 1)]))
    )
    patients = [_patient_ns(id=11, name="张三", labels=[])]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)
    assert "labels" in data["items"][0]
    assert data["items"][0]["labels"] == []


async def test_patients_list_labels_populated():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 2)]))
    )
    lbl = SimpleNamespace(id=7, name="转诊候选", color="#FF4444")
    patients = [_patient_ns(id=11, name="张三", labels=[lbl])]
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)
    assert data["items"][0]["labels"] == [{"id": 7, "name": "转诊候选", "color": "#FF4444"}]
