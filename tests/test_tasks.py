"""任务系统测试：验证随访天数提取、任务 CRUD、任务服务（创建/通知/重试）、Agent 派发及 REST API 端点的完整流程，所有 I/O 均使用模拟对象。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.notify.tasks as tasks
from services.notify.tasks import (
    extract_follow_up_days,
    create_follow_up_task,
    create_emergency_task,
    create_appointment_task,
    send_task_notification,
    check_and_send_due_tasks,
    run_due_task_cycle,
)
from services.ai.intent import Intent
from services.ai.agent import dispatch
from routers.tasks import TaskOut


# ===========================================================================
# Group A — extract_follow_up_days (pure unit tests, no mocking needed)
# ===========================================================================


def test_extract_two_weeks():
    assert extract_follow_up_days("两周后复查") == 14


def test_extract_invalid_cn_number_falls_back_to_default():
    # "零周" is not in mapping and cannot parse as int => fallback branch.
    assert extract_follow_up_days("零周后复查") == 7


def test_extract_three_days():
    assert extract_follow_up_days("3天后随访") == 3


def test_extract_one_month():
    assert extract_follow_up_days("一个月后复查") == 30


def test_extract_tomorrow():
    assert extract_follow_up_days("明天复查") == 1


def test_extract_next_week():
    assert extract_follow_up_days("下周随访") == 7


def test_extract_one_week():
    assert extract_follow_up_days("一周后") == 7


def test_extract_fallback():
    assert extract_follow_up_days("无随访计划") == 7


def test_extract_five_days():
    assert extract_follow_up_days("5天") == 5


def test_extract_three_months():
    assert extract_follow_up_days("三个月后复查") == 90


def test_extract_empty_string():
    assert extract_follow_up_days("") == 7


def test_extract_next_star_week():
    assert extract_follow_up_days("下星期来复查") == 7


def test_extract_two_months():
    assert extract_follow_up_days("两个月后") == 60


# ===========================================================================
# Group B — CRUD functions (use in-memory SQLite via session_factory fixture)
# ===========================================================================


async def test_create_task_stores_fields(db_session):
    from db.crud import create_task
    task = await create_task(
        db_session,
        doctor_id="doc1",
        task_type="follow_up",
        title="随访提醒：张三",
        content="两周后复查",
        patient_id=None,
        record_id=None,
        due_at=datetime(2026, 4, 1, 9, 0),
    )
    assert task.id is not None
    assert task.doctor_id == "doc1"
    assert task.task_type == "follow_up"
    assert task.title == "随访提醒：张三"
    assert task.status == "pending"
    assert task.due_at == datetime(2026, 4, 1, 9, 0)


async def test_list_tasks_filters_by_status(db_session):
    from db.crud import create_task, list_tasks
    await create_task(db_session, "doc1", "follow_up", "Task A")
    await create_task(db_session, "doc1", "follow_up", "Task B")
    await create_task(db_session, "doc1", "emergency", "Task C")

    all_tasks = await list_tasks(db_session, "doc1")
    assert len(all_tasks) == 3

    pending = await list_tasks(db_session, "doc1", status="pending")
    assert len(pending) == 3  # all default to pending


async def test_list_tasks_status_filter_excludes_completed(db_session):
    from db.crud import create_task, list_tasks, update_task_status
    t = await create_task(db_session, "doc2", "follow_up", "T1")
    await create_task(db_session, "doc2", "follow_up", "T2")
    await update_task_status(db_session, t.id, "doc2", "completed")

    pending = await list_tasks(db_session, "doc2", status="pending")
    assert len(pending) == 1
    assert pending[0].title == "T2"


async def test_get_due_tasks_returns_pending_overdue(db_session):
    from db.crud import create_task, get_due_tasks
    past = datetime(2026, 1, 1)
    t1 = await create_task(db_session, "doc1", "follow_up", "Due task 1", due_at=past)
    t2 = await create_task(db_session, "doc1", "follow_up", "Due task 2", due_at=past)

    now = datetime(2026, 3, 1)
    due = await get_due_tasks(db_session, now)
    ids = [t.id for t in due]
    assert t1.id in ids
    assert t2.id in ids


async def test_update_task_status_wrong_doctor_returns_none(db_session):
    from db.crud import create_task, update_task_status
    t = await create_task(db_session, "doc1", "follow_up", "MyTask")
    result = await update_task_status(db_session, t.id, "wrong_doctor", "completed")
    assert result is None


# ===========================================================================
# Helpers: mock DB session that create_task / mark_task_notified accept
# ===========================================================================


def _make_fake_task(task_id: int = 1, doctor_id: str = "doc1",
                    task_type: str = "follow_up", title: str = "Test Task",
                    due_at: Optional[datetime] = None) -> MagicMock:
    task = MagicMock()
    task.id = task_id
    task.doctor_id = doctor_id
    task.task_type = task_type
    task.title = title
    task.content = None
    task.due_at = due_at
    task.status = "pending"
    return task


class _FakeSessionCtx:
    """Async context manager that yields a fake session."""
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ===========================================================================
# Group C — services/tasks.py behaviour
# ===========================================================================


async def test_create_follow_up_task_sets_correct_due_at():
    """follow_up_plan '两周后复查' → due_at = now + 14 days."""
    fake_task = _make_fake_task(1, due_at=datetime.now(timezone.utc) + timedelta(days=14))
    mock_session = AsyncMock()
    mock_create = AsyncMock(return_value=fake_task)

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.create_task", mock_create):
        task = await create_follow_up_task(
            "doc1", 42, "张三", "两周后复查", patient_id=1
        )

    assert task.id == 1
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["task_type"] == "follow_up"
    assert call_kwargs["record_id"] == 42
    # due_at should be ~14 days from now
    due = call_kwargs["due_at"]
    delta = due - datetime.now(timezone.utc)
    assert 13 <= delta.days <= 14


async def test_create_emergency_task_sends_notification_immediately():
    """Emergency tasks call send_task_notification right after creation."""
    fake_task = _make_fake_task(2, task_type="emergency", title="紧急记录：李明")
    mock_session = AsyncMock()
    mock_create = AsyncMock(return_value=fake_task)
    mock_notify = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.create_task", mock_create), \
         patch("services.notify.tasks.send_task_notification", mock_notify):
        await create_emergency_task("doc1", 10, "李明", "STEMI", patient_id=None)

    mock_notify.assert_awaited_once_with("doc1", fake_task)


async def test_create_follow_up_task_emits_structured_task_log():
    fake_task = _make_fake_task(11, due_at=datetime.now(timezone.utc) + timedelta(days=7))
    mock_session = AsyncMock()
    mock_create = AsyncMock(return_value=fake_task)
    mock_task_log = MagicMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.create_task", mock_create), \
         patch("services.notify.tasks.task_log", mock_task_log):
        await create_follow_up_task("docA", 77, "李雷", "一周后复查", patient_id=5)

    mock_task_log.assert_called_once()
    assert mock_task_log.call_args.args[0] == "task_created"
    assert mock_task_log.call_args.kwargs["task_type"] == "follow_up"
    assert mock_task_log.call_args.kwargs["task_id"] == 11


async def test_create_appointment_task_sets_due_at_one_hour_before():
    fake_task = _make_fake_task(3, task_type="appointment", title="预约提醒：王五")
    mock_session = AsyncMock()
    mock_create = AsyncMock(return_value=fake_task)
    appt = datetime(2026, 5, 1, 14, 0, 0)

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.create_task", mock_create):
        task = await create_appointment_task(
            "doc1", "王五", appt, notes="复查血压", patient_id=9
        )

    assert task.id == 3
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["task_type"] == "appointment"
    assert call_kwargs["patient_id"] == 9
    assert call_kwargs["record_id"] is None
    assert call_kwargs["due_at"] == datetime(2026, 5, 1, 13, 0, 0)


async def test_check_and_send_due_tasks_sends_for_each():
    """Scheduler job sends notification for every due task."""
    task1 = _make_fake_task(1, doctor_id="doc1")
    task2 = _make_fake_task(2, doctor_id="doc2")
    mock_session = AsyncMock()
    mock_get_due = AsyncMock(return_value=[task1, task2])
    mock_notify = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", mock_get_due), \
         patch("services.notify.tasks.send_task_notification", mock_notify), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=None)), \
         patch("services.notify.tasks._scheduler_lease_enabled", return_value=False), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()):
        await check_and_send_due_tasks()

    assert mock_notify.await_count == 2


async def test_check_and_send_due_tasks_continues_on_error():
    """Scheduler job swallows per-task errors and continues."""
    task1 = _make_fake_task(1, doctor_id="doc1")
    task2 = _make_fake_task(2, doctor_id="doc2")
    mock_session = AsyncMock()
    mock_get_due = AsyncMock(return_value=[task1, task2])

    notify_calls = []
    async def _notify(doctor_id, task):
        notify_calls.append(task.id)
        if task.id == 1:
            raise RuntimeError("WeChat push failed")

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", mock_get_due), \
         patch("services.notify.tasks.send_task_notification", side_effect=_notify), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=None)), \
         patch("services.notify.tasks._scheduler_lease_enabled", return_value=False), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()):
        await check_and_send_due_tasks()

    assert 1 in notify_calls
    assert 2 in notify_calls  # continues despite task1 error


async def test_send_task_notification_formats_message_and_marks_notified():
    """Notification message contains task title and 'complete' hint."""
    fake_task = _make_fake_task(5, task_type="follow_up", title="随访提醒：张三",
                                due_at=datetime(2026, 4, 1, 9, 0))
    fake_task.content = "两周后复查"
    mock_session = AsyncMock()
    mock_send = AsyncMock()
    mock_mark = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.send_doctor_notification", mock_send), \
         patch("services.notify.tasks.mark_task_notified", mock_mark):
        await send_task_notification("doc1", fake_task)

    mock_send.assert_awaited_once()
    message = mock_send.call_args.args[1]
    assert "随访提醒：张三" in message
    assert "完成 5" in message

    mock_mark.assert_awaited_once()


async def test_send_task_notification_without_content_or_due_time():
    fake_task = _make_fake_task(8, task_type="emergency", title="紧急记录：李明", due_at=None)
    fake_task.content = None
    mock_session = AsyncMock()
    mock_send = AsyncMock()
    mock_mark = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.send_doctor_notification", mock_send), \
         patch("services.notify.tasks.mark_task_notified", mock_mark):
        await send_task_notification("doc1", fake_task)

    message = mock_send.call_args.args[1]
    assert "紧急记录：李明" in message
    assert "预定时间" not in message


async def test_send_task_notification_emits_structured_task_log():
    fake_task = _make_fake_task(13, task_type="follow_up", title="随访提醒：王强")
    mock_session = AsyncMock()
    mock_send = AsyncMock()
    mock_mark = AsyncMock()
    mock_task_log = MagicMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.send_doctor_notification", mock_send), \
         patch("services.notify.tasks.mark_task_notified", mock_mark), \
         patch("services.notify.tasks.task_log", mock_task_log):
        await send_task_notification("doc9", fake_task)

    mock_task_log.assert_called_once()
    assert mock_task_log.call_args.args[0] == "task_notified"
    assert mock_task_log.call_args.kwargs["task_id"] == 13


async def test_send_task_notification_retries_then_succeeds():
    fake_task = _make_fake_task(31, task_type="follow_up", title="随访提醒：赵敏")
    mock_session = AsyncMock()
    mock_send = AsyncMock(side_effect=[RuntimeError("net"), None])
    mock_mark = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.send_doctor_notification", mock_send), \
         patch("services.notify.tasks.mark_task_notified", mock_mark), \
         patch("services.notify.tasks._notify_retry_count", return_value=2), \
         patch("services.notify.tasks._notify_retry_delay_seconds", return_value=0):
        await send_task_notification("doc-retry", fake_task)

    assert mock_send.await_count == 2
    mock_mark.assert_awaited_once()


async def test_send_task_notification_retry_exhausted_does_not_mark_notified():
    fake_task = _make_fake_task(32, task_type="follow_up", title="随访提醒：王敏")
    mock_session = AsyncMock()
    mock_send = AsyncMock(side_effect=RuntimeError("net"))
    mock_mark = AsyncMock()

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.send_doctor_notification", mock_send), \
         patch("services.notify.tasks.mark_task_notified", mock_mark), \
         patch("services.notify.tasks._notify_retry_count", return_value=2), \
         patch("services.notify.tasks._notify_retry_delay_seconds", return_value=0):
        with pytest.raises(RuntimeError):
            await send_task_notification("doc-fail", fake_task)

    assert mock_send.await_count == 2
    mock_mark.assert_not_called()


async def test_check_and_send_due_tasks_logs_failure_event():
    bad_task = _make_fake_task(21, doctor_id="doc-x", task_type="follow_up")
    mock_session = AsyncMock()
    mock_get_due = AsyncMock(return_value=[bad_task])
    mock_task_log = MagicMock()

    async def _notify(_doctor_id, _task):
        raise RuntimeError("notify failed")

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", mock_get_due), \
         patch("services.notify.tasks.send_task_notification", side_effect=_notify), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=None)), \
         patch("services.notify.tasks._scheduler_lease_enabled", return_value=False), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()), \
         patch("services.notify.tasks.task_log", mock_task_log):
        await check_and_send_due_tasks()

    events = [call.args[0] for call in mock_task_log.call_args_list]
    assert "scheduler_tick_start" in events
    assert "scheduler_due_tasks" in events
    assert "task_notify_failed" in events


async def test_run_due_task_cycle_returns_counts():
    task1 = _make_fake_task(1, doctor_id="doc1")
    task2 = _make_fake_task(2, doctor_id="doc2")
    mock_session = AsyncMock()

    async def _notify(doctor_id, task):
        if task.id == 2:
            raise RuntimeError("notify failed")

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", new=AsyncMock(return_value=[task1, task2])), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=None)), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()), \
         patch("services.notify.tasks.send_task_notification", side_effect=_notify):
        out = await run_due_task_cycle(use_scheduler_lease=False)

    assert out["due_count"] == 2
    assert out["eligible_count"] == 2
    assert out["sent_count"] == 1
    assert out["failed_count"] == 1


async def test_run_due_task_cycle_skips_manual_doctor_when_not_including_manual():
    task1 = _make_fake_task(1, doctor_id="doc_manual")
    mock_session = AsyncMock()

    pref = SimpleNamespace(
        doctor_id="doc_manual",
        notify_mode="manual",
        schedule_type="immediate",
        interval_minutes=1,
        cron_expr=None,
        last_auto_run_at=None,
    )

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", new=AsyncMock(return_value=[task1])), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=pref)), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()), \
         patch("services.notify.tasks.send_task_notification", new=AsyncMock()) as mock_send:
        out = await run_due_task_cycle(include_manual=False, force=False, use_scheduler_lease=False)

    assert out["due_count"] == 1
    assert out["eligible_count"] == 0
    assert out["sent_count"] == 0
    mock_send.assert_not_awaited()


async def test_run_due_task_cycle_force_true_bypasses_manual_and_filter_by_doctor():
    task1 = _make_fake_task(1, doctor_id="doc_manual")
    task2 = _make_fake_task(2, doctor_id="doc_other")
    mock_session = AsyncMock()

    pref = SimpleNamespace(
        doctor_id="doc_manual",
        notify_mode="manual",
        schedule_type="interval",
        interval_minutes=60,
        cron_expr=None,
        last_auto_run_at=datetime.now(),
    )

    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", new=AsyncMock(return_value=[task1, task2])), \
         patch("services.notify.tasks.get_doctor_notify_preference", new=AsyncMock(return_value=pref)), \
         patch("services.notify.tasks.upsert_doctor_notify_preference", new=AsyncMock()), \
         patch("services.notify.tasks.send_task_notification", new=AsyncMock()) as mock_send:
        out = await run_due_task_cycle(
            doctor_id="doc_manual",
            include_manual=True,
            force=True,
        )

    assert out["due_count"] == 1
    assert out["eligible_count"] == 1
    assert out["sent_count"] == 1
    mock_send.assert_awaited_once()


async def test_emit_task_log_awaits_asyncmock():
    mock_task_log = AsyncMock()
    with patch("services.notify.tasks.task_log", mock_task_log):
        await tasks._emit_task_log("evt", x=1)

    mock_task_log.assert_called_once_with("evt", x=1)
    assert mock_task_log.await_count == 1


async def test_run_due_task_cycle_skips_when_lease_not_acquired():
    mock_session = AsyncMock()
    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks._scheduler_lease_enabled", return_value=True), \
         patch("services.notify.tasks.try_acquire_scheduler_lease", new=AsyncMock(return_value=False)), \
         patch("services.notify.tasks.task_log", MagicMock()):
        out = await run_due_task_cycle(use_scheduler_lease=True)

    assert out["skipped_by_lease"] is True
    assert out["due_count"] == 0
    assert out["eligible_count"] == 0


async def test_run_due_task_cycle_logs_debug_when_no_due_tasks():
    mock_session = AsyncMock()
    mock_task_log = MagicMock()
    with patch("services.notify.tasks.AsyncSessionLocal", return_value=_FakeSessionCtx(mock_session)), \
         patch("services.notify.tasks.get_due_tasks", new=AsyncMock(return_value=[])), \
         patch("services.notify.tasks.task_log", mock_task_log):
        out = await run_due_task_cycle(use_scheduler_lease=False)

    assert out["due_count"] == 0
    assert out["eligible_count"] == 0
    assert out["sent_count"] == 0
    assert out["failed_count"] == 0
    assert any(
        c.args and c.args[0] == "scheduler_due_tasks" and c.kwargs.get("level") == "debug" and c.kwargs.get("count") == 0
        for c in mock_task_log.call_args_list
    )


def test_taskout_from_orm_serializes_datetime_fields():
    obj = MagicMock()
    obj.id = 1
    obj.doctor_id = "doc1"
    obj.task_type = "follow_up"
    obj.title = "随访提醒：张三"
    obj.content = "两周后复查"
    obj.status = "pending"
    obj.due_at = datetime(2026, 3, 10, 9, 0, 0)
    obj.created_at = datetime(2026, 3, 2, 8, 0, 0)
    obj.patient_id = 11
    obj.record_id = 22

    out = TaskOut.from_orm(obj)
    assert out.id == 1
    assert out.due_at.startswith("2026-03-10T09:00:00")
    assert out.created_at.startswith("2026-03-02T08:00:00")


# ===========================================================================
# Group D — Agent dispatch: new intents + extra_data (mock LLM)
# ===========================================================================


def _make_tool_call(fn_name: str, args: dict):
    tc = MagicMock()
    tc.function.name = fn_name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)
    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    mock_client = AsyncMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create
    with patch("services.ai.agent.AsyncOpenAI", return_value=mock_client):
        yield mock_create


async def test_dispatch_list_tasks_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("list_tasks", {})
    result = await dispatch("我的待办任务")
    assert result.intent == Intent.list_tasks


async def test_dispatch_complete_task_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("manage_task", {"task_id": 7, "action": "complete"})
    result = await dispatch("完成任务7")
    assert result.intent == Intent.complete_task


async def test_dispatch_complete_task_extra_data(mock_llm):
    mock_llm.return_value = _make_tool_call("manage_task", {"task_id": 42, "action": "complete"})
    result = await dispatch("完成任务42")
    assert result.extra_data.get("task_id") == 42


async def test_dispatch_schedule_appointment_intent(mock_llm):
    mock_llm.return_value = _make_tool_call(
        "schedule_appointment",
        {"patient_name": "王五", "appointment_time": "2026-03-15T14:00:00"},
    )
    result = await dispatch("给王五安排下周二下午2点复诊")
    assert result.intent == Intent.schedule_appointment


async def test_dispatch_schedule_appointment_extra_data(mock_llm):
    mock_llm.return_value = _make_tool_call(
        "schedule_appointment",
        {
            "patient_name": "赵六",
            "appointment_time": "2026-04-01T09:00:00",
            "notes": "检查血压",
        },
    )
    result = await dispatch("给赵六约下个月初9点复查血压")
    assert result.extra_data.get("appointment_time") == "2026-04-01T09:00:00"
    assert result.extra_data.get("notes") == "检查血压"
    assert result.patient_name == "赵六"


async def test_dispatch_complete_task_missing_id_gives_none(mock_llm):
    """If LLM omits task_id, extra_data["task_id"] is None."""
    mock_llm.return_value = _make_tool_call("complete_task", {})
    result = await dispatch("完成任务")
    assert result.extra_data.get("task_id") is None


# ===========================================================================
# Group E — routers/tasks.py REST API
# ===========================================================================


async def test_api_get_tasks_returns_list(session_factory):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router
    from db.crud import create_task

    app = FastAPI()
    app.include_router(tasks_router)

    async with session_factory() as s:
        await create_task(s, "doc1", "follow_up", "Task X")
        await create_task(s, "doc1", "emergency", "Task Y")

    with patch("routers.tasks.AsyncSessionLocal", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tasks", params={"doctor_id": "doc1"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["doctor_id"] == "doc1"


async def test_api_get_tasks_filter_by_status(session_factory):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router
    from db.crud import create_task, update_task_status

    app = FastAPI()
    app.include_router(tasks_router)

    async with session_factory() as s:
        t1 = await create_task(s, "doc2", "follow_up", "Pending Task")
        t2 = await create_task(s, "doc2", "follow_up", "Completed Task")
        await update_task_status(s, t2.id, "doc2", "completed")

    with patch("routers.tasks.AsyncSessionLocal", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tasks", params={"doctor_id": "doc2", "status": "pending"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"


async def test_api_patch_task_marks_completed(session_factory):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router
    from db.crud import create_task

    app = FastAPI()
    app.include_router(tasks_router)

    async with session_factory() as s:
        task = await create_task(s, "doc3", "follow_up", "Patch Me")
        task_id = task.id

    with patch("routers.tasks.AsyncSessionLocal", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/tasks/{task_id}",
                params={"doctor_id": "doc3"},
                json={"status": "completed"},
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_api_patch_task_invalid_status_returns_422(session_factory):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router

    app = FastAPI()
    app.include_router(tasks_router)

    with patch("routers.tasks.AsyncSessionLocal", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/tasks/99",
                params={"doctor_id": "doc3"},
                json={"status": "invalid_status"},
            )

    assert resp.status_code == 422


async def test_api_patch_task_not_found_returns_404(session_factory):
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router

    app = FastAPI()
    app.include_router(tasks_router)

    with patch("routers.tasks.AsyncSessionLocal", session_factory):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/tasks/99999",
                params={"doctor_id": "no_such_doctor"},
                json={"status": "completed"},
            )

    assert resp.status_code == 404


async def test_api_dev_run_notifier_disabled_returns_404():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router

    app = FastAPI()
    app.include_router(tasks_router)

    with patch.dict("os.environ", {"TASK_DEV_ENDPOINT_ENABLED": "false"}, clear=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tasks/dev/run-notifier")

    assert resp.status_code == 404


async def test_api_dev_run_notifier_enabled_returns_summary():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routers.tasks import router as tasks_router

    app = FastAPI()
    app.include_router(tasks_router)

    summary = {"due_count": 3, "sent_count": 2, "failed_count": 1}
    with patch.dict("os.environ", {"TASK_DEV_ENDPOINT_ENABLED": "true"}, clear=False), \
         patch("routers.tasks.run_due_task_cycle", new=AsyncMock(return_value=summary)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tasks/dev/run-notifier")

    assert resp.status_code == 200
    assert resp.json() == summary
