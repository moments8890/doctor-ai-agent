"""Tests for ADR 0007: blocked-write stateful precheck."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from services.domain.name_utils import (
    is_blocked_write_cancel,
    name_only_text,
    name_with_supplement,
)
from services.intent_workflow.precheck import (
    BlockedWriteContinuation,
    is_blocked_write_cancel_reply,
    precheck_blocked_write,
)
from services.session import (
    BlockedWriteContext,
    clear_blocked_write_context,
    get_blocked_write_context,
    get_session,
    set_blocked_write_context,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_session():
    """Ensure each test starts with a clean session."""
    import services.session as _mod
    with _mod._registry_lock:
        _mod._sessions.clear()
        _mod._loaded_from_db.clear()
    yield
    with _mod._registry_lock:
        _mod._sessions.clear()
        _mod._loaded_from_db.clear()


DOCTOR = "test_precheck_doc"
CLINICAL_TEXT = "胸痛两天，血压150/90，心电图ST段改变"
ORIGINAL_TEXT = CLINICAL_TEXT
HISTORY = [
    {"role": "user", "content": CLINICAL_TEXT},
    {"role": "assistant", "content": "请问这位患者叫什么名字？"},
]


def _store_blocked_write():
    """Helper to set up a standard blocked write context."""
    set_blocked_write_context(
        DOCTOR,
        intent="add_record",
        clinical_text=CLINICAL_TEXT,
        original_text=ORIGINAL_TEXT,
        history_snapshot=HISTORY,
    )


# ── Session helpers ───────────────────────────────────────────────────────────


class TestBlockedWriteSessionHelpers:

    def test_set_and_get(self):
        _store_blocked_write()
        ctx = get_blocked_write_context(DOCTOR)
        assert ctx is not None
        assert ctx.intent == "add_record"
        assert ctx.clinical_text == CLINICAL_TEXT
        assert ctx.original_text == ORIGINAL_TEXT
        assert len(ctx.history_snapshot) == 2

    def test_clear(self):
        _store_blocked_write()
        clear_blocked_write_context(DOCTOR)
        assert get_blocked_write_context(DOCTOR) is None

    def test_get_returns_none_when_empty(self):
        assert get_blocked_write_context(DOCTOR) is None

    def test_expiry(self):
        _store_blocked_write()
        # Manually backdate the context
        sess = get_session(DOCTOR)
        sess.blocked_write.created_at = time.monotonic() - 400  # > 300s TTL
        assert get_blocked_write_context(DOCTOR) is None
        # Should also be cleared from session
        assert sess.blocked_write is None


# ── Name parsers ──────────────────────────────────────────────────────────────


class TestNameOnlyText:

    def test_bare_name(self):
        assert name_only_text("张三") == "张三"

    def test_three_char_name(self):
        assert name_only_text("张三丰") == "张三丰"

    def test_four_char_name(self):
        assert name_only_text("欧阳修远") == "欧阳修远"

    def test_too_short(self):
        assert name_only_text("张") is None

    def test_too_long(self):
        assert name_only_text("张三丰风格特殊") is None

    def test_non_name(self):
        # "胸痛两天" is 4 CJK chars so passes the regex; use a longer phrase
        assert name_only_text("胸痛两天了") is None


class TestNameWithSupplement:

    def test_name_comma_supplement(self):
        result = name_with_supplement("张三，还有头痛三天")
        assert result is not None
        name, supplement = result
        assert name == "张三"
        assert supplement == "还有头痛三天"

    def test_name_space_supplement(self):
        result = name_with_supplement("张三 男52岁复查")
        assert result is not None
        name, supplement = result
        assert name == "张三"
        assert supplement == "男52岁复查"

    def test_bare_name_returns_none(self):
        # No supplement → use name_only_text instead
        assert name_with_supplement("张三") is None

    def test_invalid_name_returns_none(self):
        assert name_with_supplement("入院查，血常规") is None


class TestBlockedWriteCancel:

    def test_cancel_keywords(self):
        assert is_blocked_write_cancel("取消") is True
        assert is_blocked_write_cancel("算了") is True
        assert is_blocked_write_cancel("不要了") is True
        assert is_blocked_write_cancel("放弃") is True
        assert is_blocked_write_cancel("不用了") is True
        assert is_blocked_write_cancel("不记了") is True

    def test_non_cancel(self):
        assert is_blocked_write_cancel("张三") is False
        assert is_blocked_write_cancel("胸痛") is False


# ── Precheck logic ────────────────────────────────────────────────────────────


class TestPrecheckBlockedWrite:

    def test_no_blocked_context_returns_none(self):
        result = precheck_blocked_write(DOCTOR, "张三")
        assert result is None

    def test_bare_name_resumes(self):
        _store_blocked_write()
        result = precheck_blocked_write(DOCTOR, "张三")
        assert result is not None
        assert isinstance(result, BlockedWriteContinuation)
        assert result.patient_name == "张三"
        assert result.clinical_text == CLINICAL_TEXT
        assert result.supplement is None
        # Context should be cleared
        assert get_blocked_write_context(DOCTOR) is None

    def test_name_with_supplement_resumes(self):
        _store_blocked_write()
        result = precheck_blocked_write(DOCTOR, "李四，还有头痛")
        assert result is not None
        assert result.patient_name == "李四"
        assert "头痛" in result.clinical_text
        assert CLINICAL_TEXT in result.clinical_text  # original text preserved
        assert result.supplement == "还有头痛"
        assert get_blocked_write_context(DOCTOR) is None

    def test_cancel_clears_context(self):
        _store_blocked_write()
        result = precheck_blocked_write(DOCTOR, "取消")
        # precheck returns None on cancel (caller handles reply)
        assert result is None
        assert get_blocked_write_context(DOCTOR) is None

    def test_unrelated_message_clears_context(self):
        _store_blocked_write()
        result = precheck_blocked_write(DOCTOR, "查询所有患者")
        assert result is None
        # Stale context should be cleared
        assert get_blocked_write_context(DOCTOR) is None

    def test_expired_context_returns_none(self):
        _store_blocked_write()
        sess = get_session(DOCTOR)
        sess.blocked_write.created_at = time.monotonic() - 400
        result = precheck_blocked_write(DOCTOR, "张三")
        assert result is None

    def test_history_snapshot_preserved(self):
        _store_blocked_write()
        result = precheck_blocked_write(DOCTOR, "张三")
        assert result is not None
        assert len(result.history_snapshot) == 2
        assert result.history_snapshot[0]["role"] == "user"


class TestIsBlockedWriteCancelReply:

    def test_cancel_with_context(self):
        _store_blocked_write()
        assert is_blocked_write_cancel_reply(DOCTOR, "取消") is True

    def test_cancel_without_context(self):
        assert is_blocked_write_cancel_reply(DOCTOR, "取消") is False

    def test_non_cancel_with_context(self):
        _store_blocked_write()
        assert is_blocked_write_cancel_reply(DOCTOR, "张三") is False


# ── Integration: records.py wiring ────────────────────────────────────────────


class TestRecordsChatCoreBlockedWrite:
    """Integration tests for the blocked-write precheck wired into chat_core."""

    @pytest.mark.asyncio
    async def test_gate_block_stores_context(self):
        """When gate blocks add_record for no_patient_name, context is stored."""
        from services.intent_workflow.models import (
            ActionPlan, BindingDecision, EntityResolution,
            GateResult, IntentDecision, WorkflowResult,
        )
        from services.ai.intent import Intent

        mock_result = WorkflowResult(
            decision=IntentDecision(intent=Intent.add_record, source="llm"),
            entities=EntityResolution(),
            binding=BindingDecision(status="no_name"),
            plan=ActionPlan(),
            gate=GateResult(
                approved=False,
                reason="no_patient_name",
                clarification_message="请问这位患者叫什么名字？",
            ),
        )

        with patch("routers.records.load_knowledge_context_for_prompt", new_callable=AsyncMock, return_value=""), \
             patch("services.ai.turn_context.assemble_turn_context", new_callable=AsyncMock), \
             patch("services.intent_workflow.run", new_callable=AsyncMock, return_value=mock_result):

            from routers.records import chat_core
            resp = await chat_core(
                "胸痛两天血压高", DOCTOR, [],
                original_text="胸痛两天血压高",
            )

        assert "叫什么名字" in resp.reply
        ctx = get_blocked_write_context(DOCTOR)
        assert ctx is not None
        assert ctx.intent == "add_record"
        assert ctx.clinical_text == "胸痛两天血压高"

    @pytest.mark.asyncio
    async def test_bare_name_resumes_blocked_write(self):
        """A bare name after blocked write resumes without LLM routing."""
        _store_blocked_write()

        with patch(
            "routers.records.shared_handle_add_record",
            new_callable=AsyncMock,
        ) as mock_handler:
            from services.domain.intent_handlers._types import HandlerResult
            mock_handler.return_value = HandlerResult(
                reply="📋 已为【张三】生成病历草稿，请确认后保存。",
                pending_id="draft-123",
            )
            from routers.records import chat_core
            resp = await chat_core("张三", DOCTOR, HISTORY)

        assert "张三" in resp.reply
        # Verify handler was called with stored clinical text, not the bare name
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args
        assert call_args[0][0] == CLINICAL_TEXT  # text arg is clinical text
        assert call_args[1]["followup_name"] == "张三"
        # Context should be cleared
        assert get_blocked_write_context(DOCTOR) is None

    @pytest.mark.asyncio
    async def test_cancel_returns_reply(self):
        """Cancel command returns user-facing reply and clears context."""
        _store_blocked_write()

        from routers.records import chat_core
        resp = await chat_core("取消", DOCTOR, HISTORY)

        assert "已取消" in resp.reply
        assert get_blocked_write_context(DOCTOR) is None
