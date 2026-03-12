"""Unit tests for services.domain.intent_handlers._simple_intents."""
from __future__ import annotations

import pytest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD = "services.domain.intent_handlers._simple_intents"


@contextmanager
def _noop_trace(*args, **kwargs):
    yield


def _intent(
    intent: Intent = Intent.unknown,
    name: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    extra_data: Optional[dict] = None,
    chat_reply: Optional[str] = None,
    structured_fields: Optional[dict] = None,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        patient_name=name,
        gender=gender,
        age=age,
        extra_data=extra_data or {},
        chat_reply=chat_reply,
        structured_fields=structured_fields,
    )


def _patient(pid: int = 1, name: str = "张三", gender: Optional[str] = None, year_of_birth: Optional[int] = None):
    return SimpleNamespace(id=pid, name=name, gender=gender, year_of_birth=year_of_birth)


def _task(tid: int = 1, title: str = "随访", task_type: str = "follow_up", due_at: Optional[datetime] = None, status: str = "pending"):
    return SimpleNamespace(id=tid, title=title, task_type=task_type, due_at=due_at, status=status)


def _mock_db_ctx():
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


# ============================================================================
# handle_delete_patient
# ============================================================================

class TestHandleDeletePatient:
    """Test handle_delete_patient — not found, single, multiple with occurrence_index."""

    @pytest.mark.asyncio
    async def test_no_name(self):
        """No patient_name → ask for name."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient)
        result = await handle_delete_patient("doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Patient not in DB → not found message."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="不存在")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_single_match_deleted(self):
        """Single match → delete successfully."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三")
        patient = _patient()
        deleted = _patient()

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[patient]), \
             patch(f"{_MOD}.delete_patient_for_doctor", new_callable=AsyncMock, return_value=deleted), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "已删除" in result.reply

    @pytest.mark.asyncio
    async def test_multiple_matches_no_index(self):
        """Multiple same-name patients without occurrence_index → ask for index."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三")
        patients = [_patient(pid=1), _patient(pid=2)]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "同名" in result.reply
        assert "2 位" in result.reply

    @pytest.mark.asyncio
    async def test_occurrence_index_valid(self):
        """Multiple matches with valid occurrence_index → delete the right one."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三", extra_data={"occurrence_index": 2})
        patients = [_patient(pid=1), _patient(pid=2)]
        deleted = _patient(pid=2)

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.delete_patient_for_doctor", new_callable=AsyncMock, return_value=deleted), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "已删除" in result.reply

    @pytest.mark.asyncio
    async def test_occurrence_index_out_of_range(self):
        """occurrence_index out of range → error."""
        from services.domain.intent_handlers._simple_intents import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三", extra_data={"occurrence_index": 5})
        patients = [_patient(pid=1), _patient(pid=2)]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "序号超出范围" in result.reply


# ============================================================================
# handle_list_patients
# ============================================================================

class TestHandleListPatients:
    """Test handle_list_patients — empty and with patients."""

    @pytest.mark.asyncio
    async def test_empty(self):
        """No patients → empty message."""
        from services.domain.intent_handlers._simple_intents import handle_list_patients
        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_patients", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_patients("doc1")
        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_with_patients(self):
        """Has patients → list them."""
        from services.domain.intent_handlers._simple_intents import handle_list_patients
        patients = [
            _patient(pid=1, name="张三", gender="男", year_of_birth=1990),
            _patient(pid=2, name="李四"),
        ]
        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_patients", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_patients("doc1")
        assert "2 位" in result.reply
        assert "张三" in result.reply
        assert "李四" in result.reply
        assert len(result.patients_list) == 2


# ============================================================================
# handle_list_tasks
# ============================================================================

class TestHandleListTasks:
    """Test handle_list_tasks — empty and with tasks."""

    @pytest.mark.asyncio
    async def test_empty(self):
        """No tasks → empty message."""
        from services.domain.intent_handlers._simple_intents import handle_list_tasks
        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_tasks("doc1")
        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_with_tasks(self):
        """Has pending tasks → list them."""
        from services.domain.intent_handlers._simple_intents import handle_list_tasks
        tasks = [
            _task(tid=1, title="随访张三", due_at=datetime(2026, 4, 1)),
            _task(tid=2, title="复查血常规"),
        ]
        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=tasks), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_tasks("doc1")
        assert "2 条" in result.reply
        assert "完成 编号" in result.reply

    @pytest.mark.asyncio
    async def test_candidate_capture(self):
        """Intent with candidate_name in extra_data → captured via set_candidate_patient."""
        from services.domain.intent_handlers._simple_intents import handle_list_tasks
        ir = _intent(
            intent=Intent.list_tasks,
            extra_data={"candidate_name": "候选人", "candidate_gender": "女"},
        )
        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.set_candidate_patient") as mock_scp, \
             patch(f"{_MOD}.trace_block", _noop_trace):
            await handle_list_tasks("doc1", ir)
        mock_scp.assert_called_once()


# ============================================================================
# handle_complete_task
# ============================================================================

class TestHandleCompleteTask:
    """Test handle_complete_task — not found, success."""

    @pytest.mark.asyncio
    async def test_no_task_id(self):
        """No task_id identified → error message."""
        from services.domain.intent_handlers._simple_intents import handle_complete_task
        ir = _intent(intent=Intent.complete_task)
        result = await handle_complete_task("doc1", ir, text="完成")
        assert "未能识别" in result.reply

    @pytest.mark.asyncio
    async def test_task_not_found(self):
        """task_id given but not in DB → not found."""
        from services.domain.intent_handlers._simple_intents import handle_complete_task
        ir = _intent(intent=Intent.complete_task, extra_data={"task_id": 99})

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid task_id → mark completed."""
        from services.domain.intent_handlers._simple_intents import handle_complete_task
        ir = _intent(intent=Intent.complete_task, extra_data={"task_id": 5})
        task = _task(tid=5, title="随访张三")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("doc1", ir)
        assert "已标记完成" in result.reply
        assert "随访张三" in result.reply

    @pytest.mark.asyncio
    async def test_task_id_from_text(self):
        """task_id extracted from text '完成 5' when not in extra_data."""
        from services.domain.intent_handlers._simple_intents import handle_complete_task
        ir = _intent(intent=Intent.complete_task)
        task = _task(tid=5, title="复查")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("doc1", ir, text="完成 5")
        assert "已标记完成" in result.reply


# ============================================================================
# handle_schedule_appointment
# ============================================================================

class TestHandleScheduleAppointment:
    """Test handle_schedule_appointment — no name, success."""

    @pytest.mark.asyncio
    async def test_no_name(self):
        """No patient_name → error message."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_appointment
        ir = _intent(intent=Intent.schedule_appointment)
        result = await handle_schedule_appointment("doc1", ir)
        assert "未能识别患者" in result.reply

    @pytest.mark.asyncio
    async def test_no_time(self):
        """No appointment_time → error message."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_appointment
        ir = _intent(intent=Intent.schedule_appointment, name="张三")
        result = await handle_schedule_appointment("doc1", ir)
        assert "未能识别预约时间" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid name and time → appointment created."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="张三",
            extra_data={"appointment_time": "2026-03-15T14:00:00"},
        )
        patient = _patient()
        task = _task(tid=10, title="预约张三")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.create_appointment_task", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_schedule_appointment("doc1", ir)
        assert "已为患者" in result.reply
        assert "2026-03-15" in result.reply

    @pytest.mark.asyncio
    async def test_invalid_time_format(self):
        """Invalid time format → error message."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="张三",
            extra_data={"appointment_time": "invalid-date"},
        )
        result = await handle_schedule_appointment("doc1", ir)
        assert "时间格式无法识别" in result.reply


# ============================================================================
# handle_update_patient
# ============================================================================

class TestHandleUpdatePatient:
    """Test handle_update_patient — no name, no fields, success."""

    @pytest.mark.asyncio
    async def test_no_name(self):
        """No patient_name → ask for name."""
        from services.domain.intent_handlers._simple_intents import handle_update_patient
        ir = _intent(intent=Intent.update_patient, gender="男")
        result = await handle_update_patient("doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_no_fields_to_update(self):
        """No gender and no age → ask for content."""
        from services.domain.intent_handlers._simple_intents import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="张三")
        result = await handle_update_patient("doc1", ir)
        assert "请告诉我要更新的内容" in result.reply

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        """Patient not in DB → not found."""
        from services.domain.intent_handlers._simple_intents import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="不存在", gender="男")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_patient_demographics", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_patient("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid update → success message with updated fields."""
        from services.domain.intent_handlers._simple_intents import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="张三", gender="女", age=45)
        patient = _patient()

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_patient_demographics", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_patient("doc1", ir)
        assert "已更新" in result.reply
        assert "性别" in result.reply
        assert "年龄" in result.reply


# ============================================================================
# handle_update_record
# ============================================================================

class TestHandleUpdateRecord:
    """Test handle_update_record — various paths."""

    @pytest.mark.asyncio
    async def test_no_name_no_session(self):
        """No name in intent and no session patient → ask."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(intent=Intent.update_record)
        sess = SimpleNamespace(current_patient_name=None)

        with patch("services.session.get_session", return_value=sess):
            result = await handle_update_record("doc1", ir, text="主诉改为头痛")
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_structured_fields_path(self):
        """Intent has structured_fields → use them directly."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(
            intent=Intent.update_record,
            name="张三",
            structured_fields={"content": "更正后的内容"},
        )
        patient = _patient()
        updated = SimpleNamespace(id=50)

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=updated), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record("doc1", ir, text="主诉改为头痛")
        assert "已更正" in result.reply

    @pytest.mark.asyncio
    async def test_llm_dispatch_path(self):
        """No structured_fields → LLM dispatch extracts fields."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三")
        llm_result = _intent(structured_fields={"content": "LLM提取的内容"})
        patient = _patient()
        updated = SimpleNamespace(id=51)

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=updated), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.ai.agent.dispatch", new_callable=AsyncMock, return_value=llm_result):
            result = await handle_update_record("doc1", ir, text="主诉改为头痛")
        assert "已更正" in result.reply

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        """Patient name resolves but not found in DB → error."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(intent=Intent.update_record, name="不存在", structured_fields={"content": "x"})

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record("doc1", ir, text="主诉改为x")
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_no_records_to_update(self):
        """Patient found but no records → error."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三", structured_fields={"content": "x"})
        patient = _patient()

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record("doc1", ir, text="x")
        assert "暂无病历" in result.reply

    @pytest.mark.asyncio
    async def test_session_fallback_for_name(self):
        """No name in intent → use session current_patient_name."""
        from services.domain.intent_handlers._simple_intents import handle_update_record
        ir = _intent(intent=Intent.update_record, structured_fields={"content": "更新"})
        sess = SimpleNamespace(current_patient_name="王五")
        patient = _patient(pid=3, name="王五")
        updated = SimpleNamespace(id=52)

        mock_ctx, mock_db = _mock_db_ctx()
        with patch("services.session.get_session", return_value=sess), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=updated), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record("doc1", ir, text="更新")
        assert "已更正" in result.reply


# ============================================================================
# handle_cancel_task
# ============================================================================

class TestHandleCancelTask:
    """Test handle_cancel_task."""

    @pytest.mark.asyncio
    async def test_no_task_id(self):
        """No task_id → error."""
        from services.domain.intent_handlers._simple_intents import handle_cancel_task
        ir = _intent(intent=Intent.cancel_task)
        result = await handle_cancel_task("doc1", ir)
        assert "未能识别" in result.reply

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Task not found → error."""
        from services.domain.intent_handlers._simple_intents import handle_cancel_task
        ir = _intent(intent=Intent.cancel_task, extra_data={"task_id": 99})
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=None):
            result = await handle_cancel_task("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid cancel → success message."""
        from services.domain.intent_handlers._simple_intents import handle_cancel_task
        ir = _intent(intent=Intent.cancel_task, extra_data={"task_id": 5})
        task = _task(tid=5, title="随访")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task):
            result = await handle_cancel_task("doc1", ir)
        assert "已取消" in result.reply


# ============================================================================
# handle_postpone_task
# ============================================================================

class TestHandlePostponeTask:
    """Test handle_postpone_task."""

    @pytest.mark.asyncio
    async def test_no_task_id(self):
        """No task_id → error."""
        from services.domain.intent_handlers._simple_intents import handle_postpone_task
        ir = _intent(extra_data={"delta_days": 7})
        result = await handle_postpone_task("doc1", ir)
        assert "未能识别" in result.reply

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Task not found → error."""
        from services.domain.intent_handlers._simple_intents import handle_postpone_task
        ir = _intent(extra_data={"task_id": 99})
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_task_by_id", new_callable=AsyncMock, return_value=None):
            result = await handle_postpone_task("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid postpone → success with new due date."""
        from services.domain.intent_handlers._simple_intents import handle_postpone_task
        now = datetime.now(timezone.utc)
        ir = _intent(extra_data={"task_id": 5, "delta_days": 3})
        task = _task(tid=5, title="复查", due_at=now + timedelta(days=1))
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_task_by_id", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.update_task_due_at", new_callable=AsyncMock):
            result = await handle_postpone_task("doc1", ir)
        assert "已推迟" in result.reply
        assert "3 天" in result.reply


# ============================================================================
# handle_schedule_follow_up
# ============================================================================

class TestHandleScheduleFollowUp:
    """Test handle_schedule_follow_up."""

    @pytest.mark.asyncio
    async def test_no_name(self):
        """No patient_name → error."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_follow_up
        ir = _intent(intent=Intent.schedule_follow_up)
        result = await handle_schedule_follow_up("doc1", ir)
        assert "未能识别患者" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        """Valid follow-up → success with plan info."""
        from services.domain.intent_handlers._simple_intents import handle_schedule_follow_up
        ir = _intent(
            intent=Intent.schedule_follow_up,
            name="张三",
            extra_data={"follow_up_plan": "3个月后复查MRI"},
        )
        patient = _patient()
        task = _task(tid=20, title="随访", due_at=datetime(2026, 6, 10))

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch("services.notify.tasks.create_follow_up_task", new_callable=AsyncMock, return_value=task), \
             patch("services.notify.tasks.extract_follow_up_days", return_value=90):
            result = await handle_schedule_follow_up("doc1", ir)
        assert "张三" in result.reply
        assert "随访提醒" in result.reply
