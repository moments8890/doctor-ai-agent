"""Unit tests for services.domain.intent_handlers._add_record."""
from __future__ import annotations

import json
import pytest
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult
from db.models.medical_record import MedicalRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intent(
    name: Optional[str] = "张三",
    gender: Optional[str] = None,
    age: Optional[int] = None,
    is_emergency: bool = False,
    structured_fields: Optional[dict] = None,
    extra_data: Optional[dict] = None,
    chat_reply: Optional[str] = None,
) -> IntentResult:
    return IntentResult(
        intent=Intent.add_record,
        patient_name=name,
        gender=gender,
        age=age,
        is_emergency=is_emergency,
        structured_fields=structured_fields,
        extra_data=extra_data or {},
        chat_reply=chat_reply,
    )


def _patient(pid: int = 1, name: str = "张三", gender: Optional[str] = None, year_of_birth: Optional[int] = None):
    return SimpleNamespace(id=pid, name=name, gender=gender, year_of_birth=year_of_birth)


def _session(
    current_patient_name: Optional[str] = None,
    current_patient_id: Optional[int] = None,
    candidate_patient_name: Optional[str] = None,
    patient_not_found_name: Optional[str] = None,
    visit_scenario: Optional[str] = None,
    note_style: Optional[str] = None,
):
    return SimpleNamespace(
        current_patient_name=current_patient_name,
        current_patient_id=current_patient_id,
        candidate_patient_name=candidate_patient_name,
        candidate_patient_gender=None,
        candidate_patient_age=None,
        patient_not_found_name=patient_not_found_name,
        visit_scenario=visit_scenario,
        note_style=note_style,
    )


def _record(content: str = "头痛三天", tags: Optional[list] = None) -> MedicalRecord:
    return MedicalRecord(content=content, tags=tags or [])


_MOD = "services.domain.intent_handlers._add_record"


@contextmanager
def _noop_trace(*args, **kwargs):
    yield


# ============================================================================
# _resolve_patient_name
# ============================================================================

class TestResolvePatientName:
    """Test _resolve_patient_name — all 4 resolution paths + weak attribution + block."""

    @pytest.mark.asyncio
    async def test_already_resolved(self):
        """Intent already has a valid patient_name → returns None (no block)."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name="张三")
        with patch(f"{_MOD}.is_valid_patient_name", return_value=True):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert result is None

    @pytest.mark.asyncio
    async def test_history_fallback(self):
        """No intent name → resolve from conversation history."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        with patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value="李四"):
            result = await _resolve_patient_name("头痛", "doc1", [{"role": "user", "content": "李四头痛"}], ir)
        assert result is None
        assert ir.patient_name == "李四"

    @pytest.mark.asyncio
    async def test_session_fallback(self):
        """No history match → resolve from session current_patient."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        sess = _session(current_patient_name="王五")
        with patch(f"{_MOD}.is_valid_patient_name", side_effect=lambda n: n == "王五"), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None), \
             patch("services.session.get_session", return_value=sess):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert result is None
        assert ir.patient_name == "王五"

    @pytest.mark.asyncio
    async def test_single_patient_auto_bind(self):
        """Only one patient in DB → auto-bind."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        sess = _session()
        only_patient = _patient(pid=42, name="赵六")

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None), \
             patch("services.session.get_session", return_value=sess), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch("db.crud.get_all_patients", new_callable=AsyncMock, return_value=[only_patient]), \
             patch(f"{_MOD}.set_current_patient"):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert result is None
        assert ir.patient_name == "赵六"

    @pytest.mark.asyncio
    async def test_weak_attribution_candidate(self):
        """candidate_patient_name in session → use with needs_review."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        sess = _session(candidate_patient_name="候选人")
        sess.candidate_patient_gender = "男"
        sess.candidate_patient_age = 55

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.is_valid_patient_name", side_effect=lambda n: n == "候选人"), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None), \
             patch("services.session.get_session", return_value=sess), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch("db.crud.get_all_patients", new_callable=AsyncMock, return_value=[_patient(), _patient(pid=2, name="李四")]), \
             patch(f"{_MOD}.clear_candidate_patient"), \
             patch(f"{_MOD}.has_clinical_location_context", return_value=False):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert result is None
        assert ir.patient_name == "候选人"
        assert ir.extra_data.get("needs_review") is True
        assert ir.extra_data.get("attribution_source") == "candidate"

    @pytest.mark.asyncio
    async def test_weak_attribution_not_found_blocked(self):
        """patient_not_found_name WITHOUT location context → block."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        sess = _session(patient_not_found_name="钱七")

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.is_valid_patient_name", side_effect=lambda n: n == "钱七"), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None), \
             patch("services.session.get_session", return_value=sess), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch("db.crud.get_all_patients", new_callable=AsyncMock, return_value=[_patient(), _patient(pid=2)]), \
             patch(f"{_MOD}.clear_patient_not_found"), \
             patch(f"{_MOD}.has_clinical_location_context", return_value=False):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert isinstance(result, HandlerResult)
        assert "钱七" in result.reply

    @pytest.mark.asyncio
    async def test_no_resolution_asks_name(self):
        """No resolution at all → ask for patient name."""
        from services.domain.intent_handlers._add_record import _resolve_patient_name
        ir = _intent(name=None)
        sess = _session()

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.is_valid_patient_name", return_value=False), \
             patch(f"{_MOD}.patient_name_from_history", return_value=None), \
             patch("services.session.get_session", return_value=sess), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch("db.crud.get_all_patients", new_callable=AsyncMock, return_value=[_patient(), _patient(pid=2)]), \
             patch(f"{_MOD}.has_clinical_location_context", return_value=False):
            result = await _resolve_patient_name("头痛", "doc1", [], ir)
        assert isinstance(result, HandlerResult)
        assert "叫什么名字" in result.reply


# ============================================================================
# _build_record
# ============================================================================

class TestBuildRecord:
    """Test _build_record — structured_fields shortcut vs LLM structuring."""

    @pytest.mark.asyncio
    async def test_structured_fields_shortcut(self):
        """When intent has structured_fields, skip LLM and return dictation record."""
        from services.domain.intent_handlers._add_record import _build_record
        ir = _intent(structured_fields={"content": "血压140/90mmHg"})
        result = await _build_record("测试", [], ir, "张三", "doc1", None)
        assert isinstance(result, MedicalRecord)
        assert result.content == "血压140/90mmHg"
        assert result.record_type == "dictation"

    @pytest.mark.asyncio
    async def test_assemble_record_success(self):
        """Normal path → calls assemble_record."""
        from services.domain.intent_handlers._add_record import _build_record
        ir = _intent()
        expected = _record("整理后的病历内容")
        with patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, return_value=expected), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await _build_record("头痛三天", [], ir, "张三", "doc1", None)
        assert isinstance(result, MedicalRecord)
        assert result.content == "整理后的病历内容"

    @pytest.mark.asyncio
    async def test_assemble_record_value_error(self):
        """assemble_record raises ValueError → returns HandlerResult with error."""
        from services.domain.intent_handlers._add_record import _build_record
        ir = _intent()
        with patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, side_effect=ValueError("bad")), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await _build_record("头痛", [], ir, "张三", "doc1", None)
        assert isinstance(result, HandlerResult)
        assert "没能识别" in result.reply

    @pytest.mark.asyncio
    async def test_followup_name_skips_text(self):
        """When text == followup_name, effective_text is None → assemble_record gets ''."""
        from services.domain.intent_handlers._add_record import _build_record
        ir = _intent()
        expected = _record("结果")
        with patch(f"{_MOD}.assemble_record", new_callable=AsyncMock, return_value=expected) as mock_ar, \
             patch(f"{_MOD}.trace_block", _noop_trace):
            await _build_record("张三", [], ir, "张三", "doc1", "张三")
        # effective_text should be "" (from None or "")
        call_args = mock_ar.call_args
        assert call_args[0][1] == ""  # second positional arg is effective_text or ""


# ============================================================================
# _create_draft
# ============================================================================

class TestCreateDraft:
    """Test _create_draft — pending record creation with TTL."""

    @pytest.mark.asyncio
    async def test_creates_pending_record(self):
        """Creates a pending record and returns HandlerResult with pending_id."""
        from services.domain.intent_handlers._add_record import _create_draft
        ir = _intent()
        record = _record("头痛三天")

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock) as mock_cpr, \
             patch(f"{_MOD}.set_pending_record_id") as mock_spri, \
             patch(f"{_MOD}._load_rc", return_value={"PENDING_RECORD_TTL_MINUTES": 30}), \
             patch.dict("os.environ", {}, clear=False):
            result = await _create_draft("doc1", record, 1, "张三", ir)

        assert isinstance(result, HandlerResult)
        assert result.pending_id is not None
        assert result.pending_patient_name == "张三"
        assert "草稿" in result.reply
        mock_cpr.assert_awaited_once()
        mock_spri.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_chat_reply_if_set(self):
        """If intent_result.chat_reply is set, use it in the HandlerResult."""
        from services.domain.intent_handlers._add_record import _create_draft
        ir = _intent(chat_reply="自定义回复")
        record = _record("content")

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.create_pending_record", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_pending_record_id"), \
             patch(f"{_MOD}._load_rc", return_value={}), \
             patch.dict("os.environ", {}, clear=False):
            result = await _create_draft("doc1", record, 1, "张三", ir)

        assert result.reply == "自定义回复"


# ============================================================================
# _save_emergency
# ============================================================================

class TestSaveEmergency:
    """Test _save_emergency — immediate save + emergency task creation."""

    @pytest.mark.asyncio
    async def test_saves_and_creates_emergency_task(self):
        """Emergency record: save immediately, create emergency task, audit."""
        from services.domain.intent_handlers._add_record import _save_emergency
        ir = _intent(is_emergency=True)
        record = _record("急性心梗")

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        saved = SimpleNamespace(id=99)

        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.save_record", new_callable=AsyncMock, return_value=saved), \
             patch(f"{_MOD}.create_emergency_task", new_callable=AsyncMock), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch("services.domain.intent_handlers._confirm_pending._bg_auto_learn", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="trace-123"):
            result = await _save_emergency("doc1", "急性心梗", record, 1, "张三", ir)

        assert isinstance(result, HandlerResult)
        assert "紧急" in result.reply
        assert result.record is record


# ============================================================================
# handle_add_record (integration of all above)
# ============================================================================

class TestHandleAddRecord:
    """Test handle_add_record — full flow integration."""

    @pytest.mark.asyncio
    async def test_normal_flow_creates_draft(self):
        """Normal flow: resolve patient → build record → create draft."""
        from services.domain.intent_handlers._add_record import handle_add_record
        ir = _intent(name="张三")
        record = _record("头痛三天，伴呕吐")
        patient = _patient()

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.hydrate_session_state", new_callable=AsyncMock), \
             patch(f"{_MOD}._resolve_patient_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.db_create_patient", new_callable=AsyncMock), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch(f"{_MOD}._build_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.detect_score_keywords", return_value=False), \
             patch(f"{_MOD}._create_draft", new_callable=AsyncMock, return_value=HandlerResult(reply="草稿已创建")), \
             patch("services.session.get_session", return_value=_session()):
            result = await handle_add_record("头痛三天", "doc1", [], ir)

        assert isinstance(result, HandlerResult)
        assert result.reply == "草稿已创建"

    @pytest.mark.asyncio
    async def test_resolution_blocked(self):
        """When _resolve_patient_name returns a block → return it."""
        from services.domain.intent_handlers._add_record import handle_add_record
        ir = _intent(name=None)
        block = HandlerResult(reply="请问这位患者叫什么名字？")

        with patch(f"{_MOD}.hydrate_session_state", new_callable=AsyncMock), \
             patch(f"{_MOD}._resolve_patient_name", new_callable=AsyncMock, return_value=block):
            result = await handle_add_record("头痛", "doc1", [], ir)

        assert result is block

    @pytest.mark.asyncio
    async def test_emergency_path(self):
        """Emergency intent → calls _save_emergency."""
        from services.domain.intent_handlers._add_record import handle_add_record
        ir = _intent(name="张三", is_emergency=True)
        record = _record("急性心梗")
        patient = _patient()

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.hydrate_session_state", new_callable=AsyncMock), \
             patch(f"{_MOD}._resolve_patient_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch(f"{_MOD}._build_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.detect_score_keywords", return_value=False), \
             patch(f"{_MOD}._save_emergency", new_callable=AsyncMock, return_value=HandlerResult(reply="紧急已保存")) as mock_se, \
             patch("services.session.get_session", return_value=_session()):
            result = await handle_add_record("急性心梗", "doc1", [], ir)

        assert result.reply == "紧急已保存"
        mock_se.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_patient_switch_notification(self):
        """When set_current_patient returns a previous name → switch_notification set."""
        from services.domain.intent_handlers._add_record import handle_add_record
        ir = _intent(name="张三")
        record = _record("内容")
        patient = _patient()

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        draft_result = HandlerResult(reply="草稿已创建")

        with patch(f"{_MOD}.hydrate_session_state", new_callable=AsyncMock), \
             patch(f"{_MOD}._resolve_patient_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value="李四"), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch(f"{_MOD}._build_record", new_callable=AsyncMock, return_value=record), \
             patch(f"{_MOD}.detect_score_keywords", return_value=False), \
             patch(f"{_MOD}._create_draft", new_callable=AsyncMock, return_value=draft_result), \
             patch("services.session.get_session", return_value=_session()):
            result = await handle_add_record("头痛", "doc1", [], ir)

        assert result.switch_notification is not None
        assert "李四" in result.switch_notification
        assert "张三" in result.switch_notification

    @pytest.mark.asyncio
    async def test_build_record_error_returns_handler_result(self):
        """When _build_record returns HandlerResult → propagate it."""
        from services.domain.intent_handlers._add_record import handle_add_record
        ir = _intent(name="张三")
        patient = _patient()
        err = HandlerResult(reply="没能识别病历内容")

        mock_db = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.hydrate_session_state", new_callable=AsyncMock), \
             patch(f"{_MOD}._resolve_patient_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace), \
             patch(f"{_MOD}._build_record", new_callable=AsyncMock, return_value=err), \
             patch("services.session.get_session", return_value=_session()):
            result = await handle_add_record("头痛", "doc1", [], ir)

        assert result is err
