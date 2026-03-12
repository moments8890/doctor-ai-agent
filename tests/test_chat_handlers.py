"""Unit tests for services.domain.chat_handlers — fastpath handlers, notify control,
and per-intent handlers used by the web chat endpoint.
"""
from __future__ import annotations

import re
import pytest
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from db.models.medical_record import MedicalRecord
from services.ai.intent import Intent, IntentResult
from services.domain.chat_handlers import ChatResponse

# ---------------------------------------------------------------------------
# Module path constant for patching
# ---------------------------------------------------------------------------
_MOD = "services.domain.chat_handlers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    is_emergency: bool = False,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        patient_name=name,
        gender=gender,
        age=age,
        extra_data=extra_data or {},
        chat_reply=chat_reply,
        structured_fields=structured_fields,
        is_emergency=is_emergency,
    )


def _patient(pid: int = 1, name: str = "张三", gender: Optional[str] = None, year_of_birth: Optional[int] = None):
    return SimpleNamespace(id=pid, name=name, gender=gender, year_of_birth=year_of_birth)


def _task(tid: int = 1, title: str = "随访", task_type: str = "follow_up", due_at: Optional[datetime] = None, status: str = "pending"):
    return SimpleNamespace(id=tid, title=title, task_type=task_type, due_at=due_at, status=status)


def _record_obj(content: str = "胸痛两小时", tags: Optional[list] = None, record_type: str = "门诊"):
    """Create a real MedicalRecord instance."""
    return MedicalRecord(content=content, tags=tags or [], record_type=record_type)


def _mock_db_ctx():
    """Create a mock async context manager for AsyncSessionLocal."""
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


def _body(text: str = "测试输入"):
    return SimpleNamespace(text=text)


# ============================================================================
# _contains_clinical_content
# ============================================================================

class TestContainsClinicalContent:
    def test_with_clinical_hint(self):
        from services.domain.chat_handlers import _contains_clinical_content
        assert _contains_clinical_content("患者胸痛两小时") is True

    def test_without_clinical_hint(self):
        from services.domain.chat_handlers import _contains_clinical_content
        assert _contains_clinical_content("你好") is False

    def test_none_input(self):
        from services.domain.chat_handlers import _contains_clinical_content
        assert _contains_clinical_content(None) is False

    def test_empty_string(self):
        from services.domain.chat_handlers import _contains_clinical_content
        assert _contains_clinical_content("") is False

    def test_with_abbreviation(self):
        from services.domain.chat_handlers import _contains_clinical_content
        assert _contains_clinical_content("PCI术后复查") is True


# ============================================================================
# _select_patient_target
# ============================================================================

class TestSelectPatientTarget:
    def test_no_occurrence_index(self):
        from services.domain.chat_handlers import _select_patient_target
        patients = [_patient(pid=1), _patient(pid=2)]
        result = _select_patient_target(patients, None, "张三")
        assert result.id == 1

    def test_valid_occurrence_index(self):
        from services.domain.chat_handlers import _select_patient_target
        patients = [_patient(pid=1), _patient(pid=2)]
        result = _select_patient_target(patients, 2, "张三")
        assert result.id == 2

    def test_occurrence_index_zero(self):
        from services.domain.chat_handlers import _select_patient_target
        patients = [_patient(pid=1)]
        result = _select_patient_target(patients, 0, "张三")
        assert isinstance(result, ChatResponse)
        assert "序号超出范围" in result.reply

    def test_occurrence_index_exceeds_length(self):
        from services.domain.chat_handlers import _select_patient_target
        patients = [_patient(pid=1), _patient(pid=2)]
        result = _select_patient_target(patients, 5, "张三")
        assert isinstance(result, ChatResponse)
        assert "序号超出范围" in result.reply


# ============================================================================
# fastpath_complete_task
# ============================================================================

class TestFastpathCompleteTask:
    COMPLETE_RE = re.compile(r'^\s*完成\s*(\d+)\s*$')

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        from services.domain.chat_handlers import fastpath_complete_task
        result = await fastpath_complete_task("随便说说", "doc1", self.COMPLETE_RE)
        assert result is None

    @pytest.mark.asyncio
    async def test_match_task_found(self):
        from services.domain.chat_handlers import fastpath_complete_task
        task = _task(tid=5, title="随访张三")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await fastpath_complete_task("完成 5", "doc1", self.COMPLETE_RE)
        assert result is not None
        assert "已标记完成" in result.reply
        assert "随访张三" in result.reply

    @pytest.mark.asyncio
    async def test_match_task_not_found(self):
        from services.domain.chat_handlers import fastpath_complete_task
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await fastpath_complete_task("完成 999", "doc1", self.COMPLETE_RE)
        assert result is not None
        assert "未找到任务" in result.reply


# ============================================================================
# fastpath_delete_patient_by_id
# ============================================================================

class TestFastpathDeletePatientById:

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        from services.domain.chat_handlers import fastpath_delete_patient_by_id
        parse_fn = MagicMock(return_value=(None, None, None))
        result = await fastpath_delete_patient_by_id("doc1", "随便说", parse_fn)
        assert result is None

    @pytest.mark.asyncio
    async def test_match_patient_found(self):
        from services.domain.chat_handlers import fastpath_delete_patient_by_id
        parse_fn = MagicMock(return_value=(42, None, None))
        deleted = _patient(pid=42, name="李四")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.delete_patient_for_doctor", new_callable=AsyncMock, return_value=deleted), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await fastpath_delete_patient_by_id("doc1", "删除患者 42", parse_fn)
        assert result is not None
        assert "已删除" in result.reply
        assert "李四" in result.reply

    @pytest.mark.asyncio
    async def test_match_patient_not_found(self):
        from services.domain.chat_handlers import fastpath_delete_patient_by_id
        parse_fn = MagicMock(return_value=(99, None, None))
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.delete_patient_for_doctor", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await fastpath_delete_patient_by_id("doc1", "删除患者 99", parse_fn)
        assert result is not None
        assert "未找到" in result.reply


# ============================================================================
# fastpath_save_context
# ============================================================================

class TestFastpathSaveContext:
    CONTEXT_SAVE_RE = re.compile(r'^保存上下文\s*(.*)?$')

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        from services.domain.chat_handlers import fastpath_save_context
        upsert_fn = AsyncMock()
        result = await fastpath_save_context("doc1", "随便说", [], self.CONTEXT_SAVE_RE, upsert_fn)
        assert result is None

    @pytest.mark.asyncio
    async def test_explicit_summary(self):
        from services.domain.chat_handlers import fastpath_save_context
        upsert_fn = AsyncMock()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx):
            result = await fastpath_save_context(
                "doc1", "保存上下文 心内科主任", [], self.CONTEXT_SAVE_RE, upsert_fn,
            )
        assert result is not None
        assert "已保存" in result.reply
        assert "心内科主任" in result.reply
        upsert_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_summary_from_history(self):
        from services.domain.chat_handlers import fastpath_save_context
        upsert_fn = AsyncMock()
        history = [
            {"role": "user", "content": "张三胸痛"},
            {"role": "assistant", "content": "记录了"},
            {"role": "user", "content": "李四头痛"},
        ]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx):
            result = await fastpath_save_context(
                "doc1", "保存上下文", history, self.CONTEXT_SAVE_RE, upsert_fn,
            )
        assert result is not None
        assert "已保存" in result.reply
        # Should contain user messages joined by ;
        assert "张三胸痛" in result.reply
        assert "李四头痛" in result.reply

    @pytest.mark.asyncio
    async def test_auto_summary_empty_history(self):
        from services.domain.chat_handlers import fastpath_save_context
        upsert_fn = AsyncMock()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx):
            result = await fastpath_save_context(
                "doc1", "保存上下文", [], self.CONTEXT_SAVE_RE, upsert_fn,
            )
        assert result is not None
        assert "暂无摘要" in result.reply


# ============================================================================
# handle_list_patients
# ============================================================================

class TestHandleListPatients:
    @pytest.mark.asyncio
    async def test_empty(self):
        from services.domain.chat_handlers import handle_list_patients
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_patients", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_patients("doc1")
        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_with_patients(self):
        from services.domain.chat_handlers import handle_list_patients
        patients = [
            _patient(pid=1, name="张三", gender="男", year_of_birth=1990),
            _patient(pid=2, name="李四"),
        ]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_patients", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_patients("doc1")
        assert "2 位" in result.reply
        assert "张三" in result.reply
        assert "李四" in result.reply

    @pytest.mark.asyncio
    async def test_patient_with_no_yob(self):
        """Patient without year_of_birth should not show age."""
        from services.domain.chat_handlers import handle_list_patients
        patients = [_patient(pid=1, name="王五")]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_patients", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_patients("doc1")
        assert "1 位" in result.reply
        assert "王五" in result.reply


# ============================================================================
# handle_list_tasks
# ============================================================================

class TestHandleListTasks:
    @pytest.mark.asyncio
    async def test_empty(self):
        from services.domain.chat_handlers import handle_list_tasks
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_tasks("doc1")
        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_with_tasks(self):
        from services.domain.chat_handlers import handle_list_tasks
        tasks = [
            _task(tid=1, title="随访张三", due_at=datetime(2026, 4, 1)),
            _task(tid=2, title="复查血常规"),
        ]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=tasks), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_tasks("doc1")
        assert "2 条" in result.reply
        assert "完成 编号" in result.reply
        assert "随访张三" in result.reply

    @pytest.mark.asyncio
    async def test_task_without_due_date(self):
        """Task without due_at should not show due date."""
        from services.domain.chat_handlers import handle_list_tasks
        tasks = [_task(tid=3, title="一般任务", due_at=None)]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.list_tasks", new_callable=AsyncMock, return_value=tasks), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_list_tasks("doc1")
        assert "1 条" in result.reply
        assert "一般任务" in result.reply


# ============================================================================
# handle_complete_task
# ============================================================================

class TestHandleCompleteTask:
    @pytest.mark.asyncio
    async def test_no_task_id(self):
        from services.domain.chat_handlers import handle_complete_task
        ir = _intent(intent=Intent.complete_task)
        result = await handle_complete_task("完成任务", "doc1", ir)
        assert "未能识别" in result.reply

    @pytest.mark.asyncio
    async def test_task_not_found(self):
        from services.domain.chat_handlers import handle_complete_task
        ir = _intent(intent=Intent.complete_task, extra_data={"task_id": 99})
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("完成 99", "doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success_with_extra_data(self):
        from services.domain.chat_handlers import handle_complete_task
        ir = _intent(intent=Intent.complete_task, extra_data={"task_id": 5})
        task = _task(tid=5, title="随访张三")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("完成 5", "doc1", ir)
        assert "已标记完成" in result.reply
        assert "随访张三" in result.reply

    @pytest.mark.asyncio
    async def test_task_id_from_text_regex(self):
        """task_id extracted from text when not in extra_data."""
        from services.domain.chat_handlers import handle_complete_task
        ir = _intent(intent=Intent.complete_task)
        task = _task(tid=7, title="复查")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("完成 7", "doc1", ir)
        assert "已标记完成" in result.reply

    @pytest.mark.asyncio
    async def test_chat_reply_override(self):
        from services.domain.chat_handlers import handle_complete_task
        ir = _intent(intent=Intent.complete_task, extra_data={"task_id": 5}, chat_reply="自定义回复")
        task = _task(tid=5, title="随访")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_task_status", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_complete_task("完成 5", "doc1", ir)
        assert result.reply == "自定义回复"


# ============================================================================
# handle_schedule_appointment
# ============================================================================

class TestHandleScheduleAppointment:
    @pytest.mark.asyncio
    async def test_no_name(self):
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(intent=Intent.schedule_appointment)
        result = await handle_schedule_appointment("doc1", ir)
        assert "未能识别患者" in result.reply

    @pytest.mark.asyncio
    async def test_no_time(self):
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(intent=Intent.schedule_appointment, name="张三")
        result = await handle_schedule_appointment("doc1", ir)
        assert "未能识别预约时间" in result.reply

    @pytest.mark.asyncio
    async def test_invalid_time_format(self):
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="张三",
            extra_data={"appointment_time": "not-a-date"},
        )
        result = await handle_schedule_appointment("doc1", ir)
        assert "时间格式无法识别" in result.reply

    @pytest.mark.asyncio
    async def test_success(self):
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="张三",
            extra_data={"appointment_time": "2026-03-15T14:00:00", "notes": "复查血压"},
        )
        patient = _patient()
        task = _task(tid=10, title="预约张三")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.create_appointment_task", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_schedule_appointment("doc1", ir)
        assert "已为患者" in result.reply
        assert "2026-03-15" in result.reply
        assert "10" in result.reply

    @pytest.mark.asyncio
    async def test_success_no_patient_in_db(self):
        """Patient not in DB but name provided -> patient_id=None, still creates task."""
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="新患者",
            extra_data={"appointment_time": "2026-04-01T09:00:00"},
        )
        task = _task(tid=11, title="预约新患者")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.create_appointment_task", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_schedule_appointment("doc1", ir)
        assert "已为患者【新患者】" in result.reply

    @pytest.mark.asyncio
    async def test_time_with_z_suffix(self):
        """Time ending with Z should be normalized."""
        from services.domain.chat_handlers import handle_schedule_appointment
        ir = _intent(
            intent=Intent.schedule_appointment,
            name="张三",
            extra_data={"appointment_time": "2026-03-15T14:00:00Z"},
        )
        task = _task(tid=12, title="预约")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.create_appointment_task", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_schedule_appointment("doc1", ir)
        assert "已为患者" in result.reply


# ============================================================================
# handle_update_patient
# ============================================================================

class TestHandleUpdatePatient:
    @pytest.mark.asyncio
    async def test_no_name(self):
        from services.domain.chat_handlers import handle_update_patient
        ir = _intent(intent=Intent.update_patient, gender="男")
        result = await handle_update_patient("doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_no_fields(self):
        from services.domain.chat_handlers import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="张三")
        result = await handle_update_patient("doc1", ir)
        assert "请告诉我要更新的内容" in result.reply

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        from services.domain.chat_handlers import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="不存在", gender="男")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_patient_demographics", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_patient("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_success_gender_and_age(self):
        from services.domain.chat_handlers import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="张三", gender="女", age=45)
        patient = _patient()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_patient_demographics", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_patient("doc1", ir)
        assert "已更新" in result.reply
        assert "性别" in result.reply
        assert "年龄" in result.reply

    @pytest.mark.asyncio
    async def test_success_gender_only(self):
        from services.domain.chat_handlers import handle_update_patient
        ir = _intent(intent=Intent.update_patient, name="张三", gender="男")
        patient = _patient()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.update_patient_demographics", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_patient("doc1", ir)
        assert "已更新" in result.reply
        assert "性别" in result.reply


# ============================================================================
# handle_update_record
# ============================================================================

class TestHandleUpdateRecord:
    @pytest.mark.asyncio
    async def test_no_name(self):
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record)
        result = await handle_update_record(_body(), "doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record, name="不存在", structured_fields={"content": "x"})
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record(_body(), "doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_no_records_to_update(self):
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三", structured_fields={"content": "x"})
        patient = _patient()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record(_body(), "doc1", ir)
        assert "暂无病历" in result.reply

    @pytest.mark.asyncio
    async def test_success_with_structured_fields(self):
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三", structured_fields={"content": "更正内容"})
        patient = _patient()
        updated = SimpleNamespace(id=50)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=updated), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_update_record(_body(), "doc1", ir)
        assert "已更正" in result.reply

    @pytest.mark.asyncio
    async def test_llm_dispatch_fallback(self):
        """No structured_fields -> dispatches to LLM for extraction."""
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三")
        llm_result = _intent(structured_fields={"content": "LLM提取"})
        patient = _patient()
        updated = SimpleNamespace(id=51)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.update_latest_record_for_patient", new_callable=AsyncMock, return_value=updated), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.ai.agent.dispatch", new_callable=AsyncMock, return_value=llm_result):
            result = await handle_update_record(_body("主诉改为头痛"), "doc1", ir)
        assert "已更正" in result.reply

    @pytest.mark.asyncio
    async def test_llm_dispatch_failure(self):
        """LLM dispatch fails -> returns error."""
        from services.domain.chat_handlers import handle_update_record
        ir = _intent(intent=Intent.update_record, name="张三")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.ai.agent.dispatch", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            result = await handle_update_record(_body(), "doc1", ir)
        assert "更正失败" in result.reply


# ============================================================================
# handle_delete_patient
# ============================================================================

class TestHandleDeletePatient:
    @pytest.mark.asyncio
    async def test_no_name(self):
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient)
        result = await handle_delete_patient("doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_not_found(self):
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="不存在")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_single_match_deleted(self):
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三")
        patient = _patient()
        deleted = _patient()
        mock_ctx, _ = _mock_db_ctx()
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
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三")
        patients = [_patient(pid=1), _patient(pid=2)]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "同名" in result.reply

    @pytest.mark.asyncio
    async def test_occurrence_index_valid(self):
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三", extra_data={"occurrence_index": 2})
        patients = [_patient(pid=1), _patient(pid=2)]
        deleted = _patient(pid=2)
        mock_ctx, _ = _mock_db_ctx()
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
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三", extra_data={"occurrence_index": 10})
        patients = [_patient(pid=1), _patient(pid=2)]
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=patients), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "序号超出范围" in result.reply

    @pytest.mark.asyncio
    async def test_delete_fails(self):
        """delete_patient_for_doctor returns None -> deletion failed."""
        from services.domain.chat_handlers import handle_delete_patient
        ir = _intent(intent=Intent.delete_patient, name="张三")
        patient = _patient()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[patient]), \
             patch(f"{_MOD}.delete_patient_for_doctor", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_delete_patient("doc1", ir)
        assert "删除失败" in result.reply


# ============================================================================
# handle_query_records
# ============================================================================

class TestHandleQueryRecords:
    @pytest.mark.asyncio
    async def test_by_name_patient_found(self):
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records, name="张三")
        patient = _patient()
        rec = SimpleNamespace(
            content="胸痛两小时记录",
            created_at=datetime(2026, 3, 1),
        )
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[rec]), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)
        assert "张三" in result.reply
        assert "1 条" in result.reply

    @pytest.mark.asyncio
    async def test_by_name_patient_not_found(self):
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records, name="不存在")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)
        assert "未找到" in result.reply

    @pytest.mark.asyncio
    async def test_by_name_no_records(self):
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records, name="张三")
        patient = _patient()
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)
        assert "暂无历史记录" in result.reply

    @pytest.mark.asyncio
    async def test_no_name_all_records(self):
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records)
        rec = SimpleNamespace(
            content="全量记录",
            created_at=datetime(2026, 3, 1),
            patient=SimpleNamespace(name="王五"),
        )
        mock_ctx, _ = _mock_db_ctx()
        sess = SimpleNamespace(current_patient_name=None)
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_records_for_doctor", new_callable=AsyncMock, return_value=[rec]), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.session.get_session", return_value=sess):
            result = await handle_query_records("doc1", ir)
        assert "1 条" in result.reply
        assert "王五" in result.reply

    @pytest.mark.asyncio
    async def test_no_name_no_records(self):
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records)
        mock_ctx, _ = _mock_db_ctx()
        sess = SimpleNamespace(current_patient_name=None)
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_all_records_for_doctor", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.session.get_session", return_value=sess):
            result = await handle_query_records("doc1", ir)
        assert "暂无任何病历" in result.reply

    @pytest.mark.asyncio
    async def test_session_fallback_for_name(self):
        """No name in intent -> session current_patient_name used."""
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records)
        patient = _patient(name="会话患者")
        rec = SimpleNamespace(content="会话记录", created_at=datetime(2026, 3, 5))
        sess = SimpleNamespace(current_patient_name="会话患者")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[rec]), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch("services.session.get_session", return_value=sess):
            result = await handle_query_records("doc1", ir)
        assert "会话患者" in result.reply

    @pytest.mark.asyncio
    async def test_record_with_no_created_at(self):
        """Record without created_at should use dash."""
        from services.domain.chat_handlers import handle_query_records
        ir = _intent(intent=Intent.query_records, name="张三")
        patient = _patient()
        rec = SimpleNamespace(content="无日期记录", created_at=None)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[rec]), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)
        # Should show dash for missing date
        assert "\u2014" in result.reply or "—" in result.reply


# ============================================================================
# handle_notify_control_command
# ============================================================================

class TestHandleNotifyControlCommand:
    @pytest.mark.asyncio
    async def test_no_match(self):
        from services.domain.chat_handlers import handle_notify_control_command
        with patch(f"{_MOD}.parse_notify_command", return_value=None):
            result = await handle_notify_control_command("doc1", "你好")
        assert result is None

    @pytest.mark.asyncio
    async def test_show_action(self):
        from services.domain.chat_handlers import handle_notify_control_command
        pref = SimpleNamespace(notify_mode="auto", interval_minutes=30, cron_expr=None)
        with patch(f"{_MOD}.parse_notify_command", return_value=("show", {})), \
             patch(f"{_MOD}.get_notify_pref", new_callable=AsyncMock, return_value=pref), \
             patch(f"{_MOD}.format_notify_pref", return_value="通知偏好: 自动模式"):
            result = await handle_notify_control_command("doc1", "查看通知设置")
        assert result == "通知偏好: 自动模式"

    @pytest.mark.asyncio
    async def test_set_mode_auto(self):
        from services.domain.chat_handlers import handle_notify_control_command
        pref = SimpleNamespace(notify_mode="auto")
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_mode", {"notify_mode": "auto"})), \
             patch(f"{_MOD}.set_notify_mode", new_callable=AsyncMock, return_value=pref):
            result = await handle_notify_control_command("doc1", "通知模式自动")
        assert "自动" in result

    @pytest.mark.asyncio
    async def test_set_mode_manual(self):
        from services.domain.chat_handlers import handle_notify_control_command
        pref = SimpleNamespace(notify_mode="manual")
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_mode", {"notify_mode": "manual"})), \
             patch(f"{_MOD}.set_notify_mode", new_callable=AsyncMock, return_value=pref):
            result = await handle_notify_control_command("doc1", "通知模式手动")
        assert "手动" in result

    @pytest.mark.asyncio
    async def test_set_interval(self):
        from services.domain.chat_handlers import handle_notify_control_command
        pref = SimpleNamespace(interval_minutes=15)
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_interval", {"interval_minutes": "15"})), \
             patch(f"{_MOD}.set_notify_interval", new_callable=AsyncMock, return_value=pref):
            result = await handle_notify_control_command("doc1", "通知频率15分钟")
        assert "15" in result
        assert "分钟" in result

    @pytest.mark.asyncio
    async def test_set_cron_success(self):
        from services.domain.chat_handlers import handle_notify_control_command
        pref = SimpleNamespace(cron_expr="0 9 * * *")
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_cron", {"cron_expr": "0 9 * * *"})), \
             patch(f"{_MOD}.set_notify_cron", new_callable=AsyncMock, return_value=pref):
            result = await handle_notify_control_command("doc1", "通知计划 0 9 * * *")
        assert "已更新" in result
        assert "0 9 * * *" in result

    @pytest.mark.asyncio
    async def test_set_cron_invalid(self):
        from services.domain.chat_handlers import handle_notify_control_command
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_cron", {"cron_expr": "invalid"})), \
             patch(f"{_MOD}.set_notify_cron", new_callable=AsyncMock, side_effect=ValueError("无效cron表达式")):
            result = await handle_notify_control_command("doc1", "通知计划 invalid")
        assert "无效cron" in result

    @pytest.mark.asyncio
    async def test_set_immediate(self):
        from services.domain.chat_handlers import handle_notify_control_command
        with patch(f"{_MOD}.parse_notify_command", return_value=("set_immediate", {})), \
             patch(f"{_MOD}.set_notify_immediate", new_callable=AsyncMock):
            result = await handle_notify_control_command("doc1", "实时通知")
        assert "实时检查" in result

    @pytest.mark.asyncio
    async def test_trigger_now(self):
        from services.domain.chat_handlers import handle_notify_control_command
        cycle_result = {"due_count": 3, "eligible_count": 2, "sent_count": 2, "failed_count": 0}
        with patch(f"{_MOD}.parse_notify_command", return_value=("trigger_now", {})), \
             patch(f"{_MOD}.run_due_task_cycle", new_callable=AsyncMock, return_value=cycle_result):
            result = await handle_notify_control_command("doc1", "立即通知")
        assert "已触发" in result
        assert "due=3" in result
        assert "sent=2" in result

    @pytest.mark.asyncio
    async def test_unknown_action_returns_none(self):
        from services.domain.chat_handlers import handle_notify_control_command
        with patch(f"{_MOD}.parse_notify_command", return_value=("unknown_action", {})):
            result = await handle_notify_control_command("doc1", "未知命令")
        assert result is None


# ============================================================================
# handle_create_patient
# ============================================================================

class TestHandleCreatePatient:
    @pytest.mark.asyncio
    async def test_no_name(self):
        from services.domain.chat_handlers import handle_create_patient
        ir = _intent(intent=Intent.create_patient)
        result = await handle_create_patient("body", "orig", "doc1", ir)
        assert "请告诉我" in result.reply

    @pytest.mark.asyncio
    async def test_reuse_existing_patient(self):
        from services.domain.chat_handlers import handle_create_patient
        ir = _intent(intent=Intent.create_patient, name="张三")
        existing = _patient(pid=5, name="张三", gender="男", year_of_birth=1990)

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[existing]):
            result = await handle_create_patient("body", "orig", "doc1", ir)
        assert "已存在" in result.reply
        assert "已复用" in result.reply

    @pytest.mark.asyncio
    async def test_create_new_patient(self):
        from services.domain.chat_handlers import handle_create_patient
        ir = _intent(intent=Intent.create_patient, name="新患者", gender="女", age=30)
        new_patient = _patient(pid=10, name="新患者")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient("body", "orig", "doc1", ir)
        assert "已为患者" in result.reply or "已创建" in result.reply

    @pytest.mark.asyncio
    async def test_create_with_clinical_content(self):
        """Clinical content in body -> compound record appended."""
        from services.domain.chat_handlers import handle_create_patient
        ir = _intent(intent=Intent.create_patient, name="新患者", gender="男", age=50)
        new_patient = _patient(pid=11, name="新患者")
        record = _record_obj(content="胸痛两小时数据")
        saved = SimpleNamespace(id=100)

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.structure_medical_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient(
                "创建新患者 胸痛两小时", "创建新患者 胸痛两小时", "doc1", ir,
            )
        assert "已录入病历" in result.reply

    @pytest.mark.asyncio
    async def test_create_with_reminder(self):
        """Reminder in original text -> task appended."""
        from services.domain.chat_handlers import handle_create_patient
        ir = _intent(intent=Intent.create_patient, name="新患者")
        new_patient = _patient(pid=12, name="新患者")
        task = _task(tid=20, title="【新患者】复查血常规")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.create_general_task", new_callable=AsyncMock, return_value=task), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient(
                "创建新患者", "创建新患者，提醒我复查血常规", "doc1", ir,
            )
        assert "已创建提醒任务" in result.reply


# ============================================================================
# handle_add_record
# ============================================================================

class TestHandleAddRecord:
    @pytest.mark.asyncio
    async def test_no_patient_name_no_history(self):
        from services.domain.chat_handlers import handle_add_record
        ir = _intent(intent=Intent.add_record)
        result = await handle_add_record(_body(), "doc1", [], ir)
        assert "患者叫什么" in result.reply

    @pytest.mark.asyncio
    async def test_invalid_patient_name_validation_error(self):
        """resolve_patient raises InvalidMedicalRecordError -> error reply."""
        from services.domain.chat_handlers import handle_add_record
        from utils.errors import InvalidMedicalRecordError
        ir = _intent(intent=Intent.add_record, name="AB")  # invalid name

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.is_valid_patient_name", return_value=True), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, side_effect=InvalidMedicalRecordError("bad")), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_add_record(_body("胸痛记录"), "doc1", [], ir)
        assert "姓名格式无效" in result.reply

    @pytest.mark.asyncio
    async def test_structuring_failure(self):
        from services.domain.chat_handlers import handle_add_record
        ir = _intent(intent=Intent.add_record, name="张三")
        patient = _patient()

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.is_valid_patient_name", return_value=True), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, False)), \
             patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, side_effect=Exception("structuring fail")), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_add_record(_body("胸痛两小时记录"), "doc1", [], ir)
        assert "生成失败" in result.reply

    @pytest.mark.asyncio
    async def test_emergency_record(self):
        from services.domain.chat_handlers import handle_add_record
        ir = _intent(intent=Intent.add_record, name="张三", is_emergency=True)
        patient = _patient()
        record = _record_obj(content="紧急病历内容")
        saved = SimpleNamespace(id=200)

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.is_valid_patient_name", return_value=True), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, False)), \
             patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_add_record(_body("紧急胸痛"), "doc1", [], ir)
        assert "紧急保存" in result.reply

    @pytest.mark.asyncio
    async def test_pending_draft(self):
        from services.domain.chat_handlers import handle_add_record
        ir = _intent(intent=Intent.add_record, name="张三")
        patient = _patient()
        record = _record_obj(content="普通病历内容需要确认")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.is_valid_patient_name", return_value=True), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, False)), \
             patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_pending_record_id"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_add_record(_body("胸痛两小时"), "doc1", [], ir)
        assert "草稿" in result.reply
        assert result.pending_id is not None

    @pytest.mark.asyncio
    async def test_patient_name_from_history(self):
        """No name in intent -> resolved from history."""
        from services.domain.chat_handlers import handle_add_record
        ir = _intent(intent=Intent.add_record)
        patient = _patient(name="王五")
        record = _record_obj(content="从历史补全姓名的病历")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value="王五"), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, False)), \
             patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_pending_record_id"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_add_record(_body("胸痛记录"), "doc1", [], ir)
        assert result.pending_id is not None


# ============================================================================
# _maybe_create_followup_task
# ============================================================================

class TestMaybeCreateFollowupTask:
    @pytest.mark.asyncio
    async def test_success(self):
        from services.domain.chat_handlers import _maybe_create_followup_task
        with patch("services.notify.tasks.create_follow_up_task", new_callable=AsyncMock):
            await _maybe_create_followup_task("doc1", "张三", 1, 100, "3个月后复查")

    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        """Should not raise even if create_follow_up_task fails."""
        from services.domain.chat_handlers import _maybe_create_followup_task
        with patch("services.notify.tasks.create_follow_up_task", new_callable=AsyncMock, side_effect=Exception("DB error")):
            # Should not raise
            await _maybe_create_followup_task("doc1", "张三", 1, 100, "3个月后复查")


# ============================================================================
# _lookup_patient_id
# ============================================================================

class TestLookupPatientId:
    @pytest.mark.asyncio
    async def test_patient_found(self):
        from services.domain.chat_handlers import _lookup_patient_id
        patient = _patient(pid=42)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient):
            result = await _lookup_patient_id("doc1", "张三")
        assert result == 42

    @pytest.mark.asyncio
    async def test_patient_not_found(self):
        from services.domain.chat_handlers import _lookup_patient_id
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None):
            result = await _lookup_patient_id("doc1", "不存在")
        assert result is None


# ============================================================================
# _save_emergency_record
# ============================================================================

class TestSaveEmergencyRecord:
    @pytest.mark.asyncio
    async def test_with_patient_name(self):
        from services.domain.chat_handlers import _save_emergency_record
        ir = _intent(is_emergency=True)
        record = _record_obj()
        saved = SimpleNamespace(id=300)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"):
            result = await _save_emergency_record("doc1", record, 1, "张三", ir)
        assert "紧急保存" in result.reply
        assert "张三" in result.reply

    @pytest.mark.asyncio
    async def test_without_patient_name(self):
        from services.domain.chat_handlers import _save_emergency_record
        ir = _intent(is_emergency=True)
        record = _record_obj()
        saved = SimpleNamespace(id=301)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"):
            result = await _save_emergency_record("doc1", record, None, None, ir)
        assert "紧急保存" in result.reply

    @pytest.mark.asyncio
    async def test_with_chat_reply(self):
        from services.domain.chat_handlers import _save_emergency_record
        ir = _intent(is_emergency=True, chat_reply="自定义紧急回复")
        record = _record_obj()
        saved = SimpleNamespace(id=302)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"):
            result = await _save_emergency_record("doc1", record, 1, "张三", ir)
        assert result.reply == "自定义紧急回复"


# ============================================================================
# _create_pending_draft
# ============================================================================

class TestCreatePendingDraft:
    @pytest.mark.asyncio
    async def test_with_patient_name(self):
        from services.domain.chat_handlers import _create_pending_draft
        ir = _intent()
        record = _record_obj(content="待确认内容")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_pending_record_id"):
            result = await _create_pending_draft("doc1", record, 1, "张三", ir)
        assert "张三" in result.reply
        assert "草稿" in result.reply
        assert result.pending_id is not None
        assert result.pending_patient_name == "张三"
        assert result.pending_expires_at is not None

    @pytest.mark.asyncio
    async def test_without_patient_name(self):
        from services.domain.chat_handlers import _create_pending_draft
        ir = _intent()
        record = _record_obj(content="待确认内容无患者")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_pending_record_id"):
            result = await _create_pending_draft("doc1", record, None, None, ir)
        assert "草稿" in result.reply
        assert result.pending_patient_name is None

    @pytest.mark.asyncio
    async def test_with_cvd_context(self):
        from services.domain.chat_handlers import _create_pending_draft
        ir = _intent(extra_data={"cvd_context": {"risk": "high"}})
        record = _record_obj(content="CVD相关内容")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock) as mock_create, \
             patch(f"{_MOD}.set_pending_record_id"):
            result = await _create_pending_draft("doc1", record, 1, "张三", ir)
        assert result.pending_id is not None
        # Verify cvd_context was included in draft_json
        call_kwargs = mock_create.call_args
        import json
        draft_json = call_kwargs.kwargs.get("draft_json") or call_kwargs[1].get("draft_json")
        draft_data = json.loads(draft_json)
        assert "cvd_context" in draft_data


# ============================================================================
# _resolve_add_record_patient
# ============================================================================

class TestResolveAddRecordPatient:
    @pytest.mark.asyncio
    async def test_no_name_no_history(self):
        from services.domain.chat_handlers import _resolve_add_record_patient
        ir = _intent(intent=Intent.add_record)
        with patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None):
            result = await _resolve_add_record_patient("doc1", ir, [])
        assert isinstance(result, ChatResponse)
        assert "患者叫什么" in result.reply

    @pytest.mark.asyncio
    async def test_name_from_history(self):
        from services.domain.chat_handlers import _resolve_add_record_patient
        ir = _intent(intent=Intent.add_record)
        patient = _patient(name="历史患者")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value="历史患者"), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, False)):
            result = await _resolve_add_record_patient("doc1", ir, [])
        assert not isinstance(result, ChatResponse)
        patient_id, patient_name = result
        assert patient_id == 1
        assert patient_name == "历史患者"

    @pytest.mark.asyncio
    async def test_valid_name_patient_created(self):
        from services.domain.chat_handlers import _resolve_add_record_patient
        ir = _intent(intent=Intent.add_record, name="新名字")
        patient = _patient(pid=99, name="新名字")
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.is_valid_patient_name", return_value=True), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.resolve_patient", new_callable=AsyncMock, return_value=(patient, True)), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"):
            result = await _resolve_add_record_patient("doc1", ir, [])
        assert not isinstance(result, ChatResponse)
        patient_id, patient_name = result
        assert patient_id == 99


# ============================================================================
# _append_compound_record
# ============================================================================

class TestAppendCompoundRecord:
    @pytest.mark.asyncio
    async def test_success(self):
        from services.domain.chat_handlers import _append_compound_record
        patient = _patient()
        record = _record_obj(content="复合录入内容较长以确保截断")
        saved = SimpleNamespace(id=400)
        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.structure_medical_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await _append_compound_record("doc1", patient, "胸痛症状", "张三", "初始回复")
        assert "已录入病历" in result

    @pytest.mark.asyncio
    async def test_failure(self):
        from services.domain.chat_handlers import _append_compound_record
        patient = _patient()
        with patch(f"{_MOD}.structure_medical_record", new_callable=AsyncMock, side_effect=Exception("LLM fail")), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await _append_compound_record("doc1", patient, "胸痛", "张三", "初始回复")
        assert "病历录入失败" in result


# ============================================================================
# _append_reminder_task
# ============================================================================

class TestAppendReminderTask:
    @pytest.mark.asyncio
    async def test_success(self):
        from services.domain.chat_handlers import _append_reminder_task
        import re as _re
        match = _re.search(r"提醒我\s*(.{2,20}?)(?:[。！\s]|$)", "提醒我复查血常规")
        patient = _patient()
        task = _task(tid=30, title="【张三】复查血常规")
        with patch(f"{_MOD}.create_general_task", new_callable=AsyncMock, return_value=task):
            result = await _append_reminder_task("doc1", patient, "张三", match, "初始回复")
        assert "已创建提醒任务" in result

    @pytest.mark.asyncio
    async def test_failure_swallowed(self):
        from services.domain.chat_handlers import _append_reminder_task
        import re as _re
        match = _re.search(r"提醒我\s*(.{2,20}?)(?:[。！\s]|$)", "提醒我做检查项目")
        patient = _patient()
        with patch(f"{_MOD}.create_general_task", new_callable=AsyncMock, side_effect=Exception("fail")):
            result = await _append_reminder_task("doc1", patient, "张三", match, "初始回复")
        # Should not raise, original reply preserved
        assert "初始回复" in result


# ============================================================================
# ChatResponse model
# ============================================================================

class TestChatResponseModel:
    def test_basic_fields(self):
        resp = ChatResponse(reply="测试回复")
        assert resp.reply == "测试回复"
        assert resp.record is None
        assert resp.pending_id is None
        assert resp.pending_patient_name is None
        assert resp.pending_expires_at is None

    def test_with_all_fields(self):
        resp = ChatResponse(
            reply="完整回复",
            pending_id="abc123",
            pending_patient_name="张三",
            pending_expires_at="2026-03-12T10:00:00",
        )
        assert resp.pending_id == "abc123"
        assert resp.pending_patient_name == "张三"


# ============================================================================
# _PatientValidationError
# ============================================================================

class TestPatientValidationError:
    def test_is_exception(self):
        from services.domain.chat_handlers import _PatientValidationError
        err = _PatientValidationError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"
