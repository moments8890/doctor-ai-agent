"""Unit tests for services.domain.intent_handlers._create_patient."""
from __future__ import annotations

import re
import pytest
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD = "services.domain.intent_handlers._create_patient"


@contextmanager
def _noop_trace(*args, **kwargs):
    yield


def _intent(
    name: Optional[str] = "张三",
    gender: Optional[str] = None,
    age: Optional[int] = None,
    extra_data: Optional[dict] = None,
) -> IntentResult:
    return IntentResult(
        intent=Intent.create_patient,
        patient_name=name,
        gender=gender,
        age=age,
        extra_data=extra_data or {},
    )


def _patient(pid: int = 1, name: str = "张三", gender: Optional[str] = None, year_of_birth: Optional[int] = None):
    return SimpleNamespace(id=pid, name=name, gender=gender, year_of_birth=year_of_birth)


def _mock_db_ctx():
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


# ============================================================================
# handle_create_patient
# ============================================================================

class TestHandleCreatePatient:
    """Test handle_create_patient — no name, existing patient, new patient."""

    @pytest.mark.asyncio
    async def test_no_name_prompts(self):
        """No patient_name → asks for name."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name=None)
        result = await handle_create_patient("doc1", ir)
        assert isinstance(result, HandlerResult)
        assert "姓名" in result.reply

    @pytest.mark.asyncio
    async def test_empty_name_prompts(self):
        """Empty patient_name → asks for name."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="")
        result = await handle_create_patient("doc1", ir)
        assert isinstance(result, HandlerResult)
        assert "姓名" in result.reply

    @pytest.mark.asyncio
    async def test_existing_patient_reuses(self):
        """Patient already exists → reuse existing (reply contains '已存在')."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="张三")
        existing = _patient(pid=5, name="张三", year_of_birth=1990)

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[existing]), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient("doc1", ir)

        assert "已存在" in result.reply
        assert "张三" in result.reply

    @pytest.mark.asyncio
    async def test_new_patient_created(self):
        """No existing patient → creates new one (reply contains '已为患者')."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="李四", gender="男", age=45)
        new_patient = _patient(pid=10, name="李四")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient("doc1", ir)

        assert "已为患者" in result.reply or "创建" in result.reply
        assert "李四" in result.reply

    @pytest.mark.asyncio
    async def test_patient_switch_notification(self):
        """When set_current_patient returns a previous name → switch_notification."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="王五")
        new_patient = _patient(pid=11, name="王五")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.set_current_patient", return_value="旧患者"), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient("doc1", ir)

        assert result.switch_notification is not None
        assert "旧患者" in result.switch_notification


# ============================================================================
# Compound record detection
# ============================================================================

class TestCompoundRecord:
    """Test compound record creation when body_text has clinical content."""

    @pytest.mark.asyncio
    async def test_compound_record_appended(self):
        """body_text with clinical content → record appended to reply."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="张三")
        new_patient = _patient(pid=1, name="张三")
        from db.models.medical_record import MedicalRecord
        record = MedicalRecord(content="头痛三天伴恶心呕吐，血压160/100mmHg")
        saved = SimpleNamespace(id=42)

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock, return_value=new_patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_create_patient(
                "doc1", ir, body_text="头痛三天伴恶心呕吐，血压160/100mmHg"
            )

        # Compound records are now handled by the dispatch layer, not here.
        assert "已录入病历" not in result.reply
        assert "已为患者" in result.reply


# ============================================================================
# Reminder task detection
# ============================================================================

class TestReminderTask:
    """Test reminder task detection via original_text with time patterns."""

    @pytest.mark.asyncio
    async def test_reminder_task_created(self):
        """original_text with time pattern → reminder task created."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="张三")
        existing = _patient(pid=1, name="张三")
        task = SimpleNamespace(id=99)

        mock_ctx, _ = _mock_db_ctx()
        # We need _REMINDER_IN_MSG_RE to match the original_text
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[existing]), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}._REMINDER_IN_MSG_RE") as mock_re:
            # Simulate regex match
            mock_match = MagicMock()
            mock_match.group.return_value = "三天后复查血常规"
            mock_re.search.return_value = mock_match

            with patch(f"{_MOD}.create_general_task", new_callable=AsyncMock, return_value=task):
                result = await handle_create_patient(
                    "doc1", ir, original_text="请提醒三天后复查血常规"
                )

        assert "提醒任务" in result.reply

    @pytest.mark.asyncio
    async def test_no_reminder_without_match(self):
        """original_text without time pattern → no reminder task."""
        from services.domain.intent_handlers._create_patient import handle_create_patient
        ir = _intent(name="张三")
        existing = _patient(pid=1, name="张三")

        mock_ctx, _ = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patients_by_exact_name", new_callable=AsyncMock, return_value=[existing]), \
             patch(f"{_MOD}.set_current_patient", return_value=None):
            result = await handle_create_patient(
                "doc1", ir, original_text="创建患者张三"
            )

        assert "提醒任务" not in result.reply
