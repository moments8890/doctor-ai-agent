"""UI 路由测试：验证患者列表/分组、病历筛选、Prompt 管理、标签 CRUD、可观测性视图及管理员数据库视图等接口的响应格式与业务逻辑。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.ui as ui
from utils.errors import LabelNotFoundError, PatientNotFoundError


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
        record_type="visit",
        content="患者复诊，胸闷两周，血压偏高，诊断冠心病，两周后随访。",
        tags='["冠心病", "两周后随访"]',
        encounter_type="follow_up",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
        updated_at=datetime(2026, 3, 2, 10, 0, 0),
        patient=SimpleNamespace(name="张三"),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


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
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)

    assert data["doctor_id"] == "doc1"
    assert data["items"][0]["record_count"] == 2
    assert data["items"][0]["created_at"] == "2026-03-01 08:00:00"
    assert data["items"][1]["record_count"] == 1
    assert data["items"][1]["created_at"] is None


async def test_manage_patients_uses_resolved_doctor_id():
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui._resolve_ui_doctor_id", return_value="resolved_doc"), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=[])) as get_patients:
        data = await ui.manage_patients(doctor_id="doc1", authorization="Bearer x")

    assert data["doctor_id"] == "resolved_doc"
    assert get_patients.await_args.args[1] == "resolved_doc"


async def test_manage_patients_invalid_authorization_raises_401():
    with patch(
        "routers.ui._utils.resolve_doctor_id_from_auth_or_fallback",
        side_effect=HTTPException(status_code=401, detail="bad token"),
    ):
        with pytest.raises(HTTPException) as exc:
            await ui.manage_patients(doctor_id="doc1", authorization="Bearer bad")
    assert exc.value.status_code == 401


async def test_manage_records_with_patient_filter():
    db = SimpleNamespace()
    records = [_record(id=21, patient_id=11, patient=None)]
    patients = [SimpleNamespace(id=11, name="张三"), SimpleNamespace(id=12, name="李四")]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_records_for_patient", new=AsyncMock(return_value=records)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
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
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_records_for_doctor", new=AsyncMock(return_value=records)):
        data = await ui.manage_records(doctor_id="doc2", patient_id=None, limit=10)

    assert data["doctor_id"] == "doc2"
    assert data["items"][0]["patient_name"] == "王五"
    assert "content" in data["items"][0]
    assert data["items"][1]["patient_name"] is None
    assert data["items"][1]["created_at"] is None


async def test_manage_records_filter_by_patient_name():
    db = SimpleNamespace()
    records = [
        _record(id=41, patient=SimpleNamespace(name="沈梅")),
        _record(id=42, patient=SimpleNamespace(name="王五")),
    ]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_records_for_doctor", new=AsyncMock(return_value=records)):
        data = await ui.manage_records(doctor_id="doc2", patient_id=None, patient_name="沈", limit=50)

    assert len(data["items"]) == 1
    assert data["items"][0]["patient_name"] == "沈梅"


async def test_manage_records_filter_by_date_range():
    db = SimpleNamespace()
    records = [
        _record(id=51, created_at=datetime(2026, 3, 1, 9, 0, 0), patient=SimpleNamespace(name="张三")),
        _record(id=52, created_at=datetime(2026, 3, 3, 9, 0, 0), patient=SimpleNamespace(name="李四")),
    ]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_records_for_doctor", new=AsyncMock(return_value=records)):
        data = await ui.manage_records(
            doctor_id="doc2",
            patient_id=None,
            date_from="2026-03-02",
            date_to="2026-03-03",
            limit=50,
        )

    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 52


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
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)

    item = data["items"][0]
    assert item["primary_category"] == "new"
    assert item["category_tags"] == ["recent_visit"]


async def test_manage_patients_category_filter():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )
    patients = [
        _patient_ns(id=11, name="高风险患者", primary_category="high_risk"),
        _patient_ns(id=12, name="新患者", primary_category="new"),
    ]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category="high_risk")

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
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
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
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients_grouped("doc1")

    uncategorized = next(g for g in data["groups"] if g["group"] == "uncategorized")
    assert uncategorized["count"] == 1
    assert uncategorized["items"][0]["name"] == "未知分类患者"



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


async def test_admin_get_tunnel_url_log_missing_returns_not_found_payload():
    with patch("routers.ui.admin_config.Path.exists", return_value=False):
        data = await ui.admin_get_tunnel_url()

    assert data["ok"] is False
    assert data["url"] is None
    assert "source" in data
    assert data["detail"] == "log file not found"


async def test_admin_get_tunnel_url_read_failure_is_sanitized():
    with patch("routers.ui.admin_config.Path.exists", return_value=True), \
         patch("routers.ui.admin_config.Path.read_text", side_effect=RuntimeError("permission denied: /etc/passwd")):
        data = await ui.admin_get_tunnel_url()

    assert data["ok"] is False
    assert data["url"] is None
    assert data["detail"] == "read failed"


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


async def test_assign_label_to_patient_not_found_raises_404():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.assign_label", new=AsyncMock(side_effect=PatientNotFoundError())):
        with pytest.raises(HTTPException) as exc:
            await ui.assign_label_endpoint(11, 1, doctor_id="doc1")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Patient not found"


async def test_remove_label_from_patient():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.remove_label", new=AsyncMock(return_value=None)):
        data = await ui.remove_label_endpoint(11, 1, doctor_id="doc1")
    assert data == {"ok": True}


async def test_remove_label_from_patient_not_found_raises_404():
    db = SimpleNamespace()
    with patch("routers.ui.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.remove_label", new=AsyncMock(side_effect=LabelNotFoundError())):
        with pytest.raises(HTTPException) as exc:
            await ui.remove_label_endpoint(11, 1, doctor_id="doc1")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Label not found"


async def test_patients_list_includes_labels_field():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 1)]))
    )
    patients = [_patient_ns(id=11, name="张三", labels=[])]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)
    assert "labels" in data["items"][0]
    assert data["items"][0]["labels"] == []


async def test_patients_list_labels_populated():
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(11, 2)]))
    )
    lbl = SimpleNamespace(id=7, name="转诊候选", color="#FF4444")
    patients = [_patient_ns(id=11, name="张三", labels=[lbl])]
    with patch("routers.ui.record_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)), \
         patch("routers.ui.record_handlers.get_all_patients", new=AsyncMock(return_value=patients)):
        data = await ui.manage_patients("doc1", category=None)
    assert data["items"][0]["labels"] == [{"id": 7, "name": "转诊候选", "color": "#FF4444"}]


async def test_admin_db_view_returns_patients_and_records():
    patient_rows = [
        _patient_ns(id=11, doctor_id="doc1", name="沈梅", created_at=datetime(2026, 3, 2, 8, 0, 0)),
    ]
    record_rows = [
        (
            _record(
                id=28,
                patient_id=11,
                doctor_id="doc1",
                record_type="visit",
                content="活动耐量下降，气短。氨氯地平从5mg加到10mg，加上呋塞米20mg。下周复查BNP和心超。",
                tags='["心衰", "随访1周"]',
                created_at=datetime(2026, 3, 2, 23, 20, 25),
            ),
            "沈梅",
        )
    ]
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: patient_rows)),
                SimpleNamespace(all=lambda: record_rows),
            ]
        )
    )
    with patch("routers.ui.admin_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_db_view(doctor_id="doc1", limit=50)

    assert data["counts"]["patients"] == 1
    assert data["counts"]["records"] == 1
    assert data["patients"][0]["name"] == "沈梅"
    assert "活动耐量下降" in data["records"][0]["content"]
    assert data["records"][0]["created_at"] == "2026-03-02 23:20:25"


async def test_admin_db_view_invalid_date_raises_400():
    with pytest.raises(HTTPException) as exc:
        await ui.admin_db_view(date_from="2026/03/02")
    assert exc.value.status_code == 400


async def test_admin_filter_options_returns_doctors_and_patients_by_doctor():
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _exec_scalars(["doc0"]),          # Doctor.doctor_id
                _exec_scalars(["doc1", "doc2"]),  # Patient.doctor_id
                _exec_scalars(["doc2", "doc3"]),  # MedicalRecordDB.doctor_id
                _exec_scalars(["doc3", None]),    # DoctorTask.doctor_id
                _exec_scalars(["doc_ctx"]),       # DoctorContext.doctor_id
                _exec_scalars(["doc_label"]),     # PatientLabel.doctor_id
                _exec_scalars(["张三", "李四", "张三"]),  # Patient.name filtered by doctor_id
            ]
        )
    )
    with patch("routers.ui.admin_config.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_filter_options(doctor_id="doc2")

    assert data["selected_doctor_id"] == "doc2"
    assert data["doctor_ids"] == ["doc0", "doc1", "doc2", "doc3", "doc_ctx", "doc_label"]
    assert data["patient_names"] == ["张三", "李四"]


async def test_admin_observability_returns_summary_and_traces():
    summary = {"count": 3, "avg_ms": 12.5}
    traces = [{"trace_id": "t1", "path": "/api/manage/patients"}]
    spans = [{"trace_id": "t1", "name": "agent.chat_completion"}]
    slow_spans = [{"trace_id": "t1", "name": "agent.chat_completion", "latency_ms": 320.0}]
    with patch("routers.ui.admin_config.get_latency_summary_scoped", return_value=summary), \
         patch("routers.ui.admin_config.get_recent_traces_scoped", return_value=traces), \
         patch("routers.ui.admin_config.get_recent_spans_scoped", return_value=spans), \
         patch("routers.ui.admin_config.get_slowest_spans_scoped", return_value=slow_spans):
        data = await ui.admin_observability(trace_limit=10, summary_limit=20)

    assert data["scope"] == "all"
    assert data["summary"] == summary
    assert data["recent_traces"] == traces
    assert data["recent_spans"] == spans
    assert data["slow_spans"] == slow_spans


async def test_admin_observability_with_trace_id_returns_timeline():
    with patch("routers.ui.admin_config.get_latency_summary_scoped", return_value={"count": 1}), \
         patch("routers.ui.admin_config.get_recent_traces_scoped", return_value=[]), \
         patch("routers.ui.admin_config.get_recent_spans_scoped", return_value=[]), \
         patch("routers.ui.admin_config.get_slowest_spans_scoped", return_value=[]), \
         patch("routers.ui.admin_config.get_trace_timeline", return_value=[{"trace_id": "abc", "name": "chat"}]) as timeline_mock:
        data = await ui.admin_observability(trace_id="abc")
    timeline_mock.assert_called_once_with(trace_id="abc", limit=200)
    assert data["trace_timeline"] == [{"trace_id": "abc", "name": "chat"}]


async def test_admin_observability_public_scope_passed_through():
    with patch("routers.ui.admin_config.get_latency_summary_scoped", return_value={"count": 2}) as summary_mock, \
         patch("routers.ui.admin_config.get_recent_traces_scoped", return_value=[]), \
         patch("routers.ui.admin_config.get_recent_spans_scoped", return_value=[]), \
         patch("routers.ui.admin_config.get_slowest_spans_scoped", return_value=[]):
        data = await ui.admin_observability(scope="public")
    assert data["scope"] == "public"
    summary_mock.assert_any_call(limit=500, scope="public")


async def test_admin_clear_observability_traces():
    with patch("routers.ui.admin_config.clear_traces") as clear_mock:
        data = await ui.admin_clear_observability_traces()
    clear_mock.assert_called_once()
    assert data == {"ok": True}


async def test_admin_seed_observability_samples():
    with patch("routers.ui.admin_handlers.add_trace") as add_trace_mock, patch("routers.ui.admin_handlers.add_span") as add_span_mock:
        data = await ui.admin_seed_observability_samples(count=2)
    assert data["ok"] is True
    assert data["count"] == 2
    assert len(data["trace_ids"]) == 2
    assert add_trace_mock.call_count == 2
    assert add_span_mock.call_count == 8


async def test_admin_get_runtime_config():
    with patch("routers.ui.admin_config.load_runtime_config_dict", new=AsyncMock(return_value={"TASK_SCHEDULER_MODE": "interval"})), \
         patch("routers.ui.admin_config.runtime_config_source_path", return_value="/tmp/runtime.json"):
        data = await ui.admin_get_runtime_config()
    assert data["source"] == "/tmp/runtime.json"
    assert data["config"]["TASK_SCHEDULER_MODE"] == "interval"


async def test_admin_update_runtime_config():
    body = ui.RuntimeConfigUpdate(config={"TASK_SCHEDULER_MODE": "cron"})
    with patch("routers.ui.admin_config.save_runtime_config_dict", new=AsyncMock(return_value={"TASK_SCHEDULER_MODE": "cron"})) as save_mock, \
         patch("routers.ui.admin_config.runtime_config_source_path", return_value="/tmp/runtime.json"):
        data = await ui.admin_update_runtime_config(body)

    save_mock.assert_awaited_once_with({"TASK_SCHEDULER_MODE": "cron"})
    assert data["ok"] is True
    assert data["applied"] is False
    assert data["source"] == "/tmp/runtime.json"


async def test_admin_verify_runtime_config():
    body = ui.RuntimeConfigUpdate(config={"TASK_SCHEDULER_MODE": "interval"})
    with patch(
        "routers.ui.admin_config.validate_runtime_config",
        return_value={"ok": True, "errors": [], "warnings": [], "sanitized": {"TASK_SCHEDULER_MODE": "interval"}},
    ):
        data = await ui.admin_verify_runtime_config(body)
    assert data["ok"] is True
    assert data["config"]["TASK_SCHEDULER_MODE"] == "interval"


async def test_admin_apply_runtime_config():
    with patch("routers.ui.admin_config.load_runtime_config_dict", new=AsyncMock(return_value={"TASK_SCHEDULER_MODE": "interval"})), \
         patch("routers.ui.admin_config.apply_runtime_config", new=AsyncMock()) as apply_mock, \
         patch("routers.ui.admin_config.runtime_config_source_path", return_value="/tmp/runtime.json"):
        data = await ui.admin_apply_runtime_config()
    apply_mock.assert_awaited_once_with({"TASK_SCHEDULER_MODE": "interval"})
    assert data["ok"] is True
    assert data["applied"] is True


async def test_admin_tables_returns_all_table_counts():
    # One scalar result per DB query in admin_tables execution order.
    side_effects = [SimpleNamespace(scalar=lambda i=i: i) for i in range(1, 25)]
    db = SimpleNamespace(execute=AsyncMock(side_effect=side_effects))
    with patch("routers.ui.admin_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_tables()
    keys = [item["key"] for item in data["items"]]
    assert "doctors" in keys
    assert "patients" in keys
    assert "medical_records" in keys
    assert "system_prompt_versions" in keys
    assert "doctor_contexts" in keys
    assert data["items"][0]["key"] == "doctors"


async def test_admin_table_rows_unknown_table_raises_404():
    db = SimpleNamespace(execute=AsyncMock())
    with patch("routers.ui.admin_table_rows.AsyncSessionLocal", return_value=_SessionCtx(db)):
        with pytest.raises(HTTPException) as exc:
            await ui.admin_table_rows("not_exists")
    assert exc.value.status_code == 404


def _exec_scalars(rows):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


def _exec_all(rows):
    return SimpleNamespace(all=lambda: rows)


def test_normalize_date_blank_returns_none():
    assert ui._normalize_date_yyyy_mm_dd("   ") is None


async def test_admin_db_view_with_all_filters():
    patient_rows = [_patient_ns(id=12, doctor_id="doc1", name="张三", created_at=datetime(2026, 3, 3, 8, 0, 0))]
    record_rows = [(_record(id=61, doctor_id="doc1", patient_id=12, created_at=datetime(2026, 3, 3, 9, 0, 0)), "张三")]
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _exec_scalars(patient_rows),
                _exec_all(record_rows),
            ]
        )
    )
    with patch("routers.ui.admin_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_db_view(
            doctor_id="doc1",
            patient_name="张",
            date_from="2026-03-01",
            date_to="2026-03-03",
            limit=10,
        )
    assert data["filters"]["doctor_id"] == "doc1"
    assert data["filters"]["patient_name"] == "张"
    assert data["counts"] == {"patients": 1, "records": 1}


async def test_admin_tables_with_filters():
    side_effects = [SimpleNamespace(scalar=lambda i=i: i) for i in range(10, -10, -1)]
    db = SimpleNamespace(execute=AsyncMock(side_effect=side_effects))
    with patch("routers.ui.admin_handlers.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_tables(
            doctor_id="doc1",
            patient_name="张",
            date_from="2026-03-01",
            date_to="2026-03-03",
        )
    assert data["items"][0]["key"] == "doctors"
    assert data["items"][0]["count"] == 10


@pytest.mark.parametrize(
    "table_key,exec_result,expected_key",
    [
        (
            "doctors",
            _exec_scalars(
                [
                    SimpleNamespace(
                        doctor_id="doc1",
                        name="张医生",
                        created_at=datetime(2026, 3, 2, 9, 0, 0),
                        updated_at=datetime(2026, 3, 3, 9, 0, 0),
                    )
                ]
            ),
            "doctor_id",
        ),
        (
            "patients",
            _exec_scalars([_patient_ns(id=31, doctor_id="doc1", name="王五", created_at=datetime(2026, 3, 2, 9, 0, 0))]),
            "name",
        ),
        (
            "medical_records",
            _exec_all([(_record(id=71, patient_id=31, doctor_id="doc1"), "王五")]),
            "content",
        ),
        (
            "doctor_tasks",
            _exec_all(
                [
                    (
                        SimpleNamespace(
                            id=81,
                            doctor_id="doc1",
                            patient_id=31,
                            record_id=None,
                            task_type="follow_up",
                            title="复查 BNP",
                            status="pending",
                            due_at=datetime(2026, 3, 5, 10, 0, 0),
                            updated_at=None,
                            created_at=datetime(2026, 3, 3, 8, 0, 0),
                        ),
                        "王五",
                    )
                ]
            ),
            "title",
        ),
        (
            "neuro_cases",
            _exec_scalars(
                [
                    SimpleNamespace(
                        id=91,
                        doctor_id="doc1",
                        patient_id=31,
                        neuro_patient_name="王五",
                        nihss=2,
                        created_at=datetime(2026, 3, 3, 7, 0, 0),
                    )
                ]
            ),
            "nihss",
        ),
        (
            "patient_labels",
            _exec_scalars(
                [
                    SimpleNamespace(
                        id=101,
                        doctor_id="doc1",
                        name="重点随访",
                        color="#ff0000",
                        created_at=datetime(2026, 3, 3, 6, 0, 0),
                    )
                ]
            ),
            "name",
        ),
        (
            "patient_label_assignments",
            _exec_all([(31, 101, "王五", "重点随访", "doc1")]),
            "label_name",
        ),
        (
            "system_prompts",
            _exec_scalars([SimpleNamespace(key="structuring", content="prompt", updated_at=datetime(2026, 3, 3, 5, 0, 0))]),
            "content",
        ),
        (
            "doctor_contexts",
            _exec_scalars([SimpleNamespace(doctor_id="doc1", summary="summary", updated_at=datetime(2026, 3, 3, 4, 0, 0))]),
            "summary",
        ),
    ],
)
async def test_admin_table_rows_each_table(table_key, exec_result, expected_key):
    db = SimpleNamespace(execute=AsyncMock(return_value=exec_result))
    with patch("routers.ui.admin_table_rows.AsyncSessionLocal", return_value=_SessionCtx(db)):
        data = await ui.admin_table_rows(
            table_key,
            doctor_id="doc1",
            patient_name="王",
            date_from="2026-03-01",
            date_to="2026-03-03",
            limit=50,
        )

    assert data["table"] == table_key
    assert len(data["items"]) == 1
    assert expected_key in data["items"][0]
