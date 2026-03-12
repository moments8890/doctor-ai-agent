"""Classifier layer tests: fast_route, LLM fallback, menu shortcut, and _build_llm_kwargs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ai.intent import Intent, IntentResult
from services.intent_workflow.classifier import _build_llm_kwargs, _decision_from, classify
from services.intent_workflow.models import IntentDecision


# ── helpers ──────────────────────────────────────────────────────────────────


def _intent_result(
    intent: Intent = Intent.add_record,
    patient_name: Optional[str] = "张三",
    confidence: float = 1.0,
    chat_reply: Optional[str] = None,
    structured_fields: Optional[dict] = None,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        patient_name=patient_name,
        confidence=confidence,
        chat_reply=chat_reply,
        structured_fields=structured_fields,
    )


@dataclass
class _FakeSession:
    """Minimal stand-in for DoctorSession used by _build_llm_kwargs."""

    current_patient_id: Optional[int] = None
    current_patient_name: Optional[str] = None
    candidate_patient_name: Optional[str] = None
    candidate_patient_gender: Optional[str] = None
    candidate_patient_age: Optional[int] = None
    patient_not_found_name: Optional[str] = None
    specialty: Optional[str] = None
    doctor_name: Optional[str] = None
    conversation_history: list = field(default_factory=list)


# ── _decision_from ───────────────────────────────────────────────────────────


class TestDecisionFrom:
    def test_basic_conversion(self):
        ir = _intent_result(intent=Intent.query_records, patient_name="李四", confidence=0.9)
        dec = _decision_from(ir, "fast_route")
        assert dec.intent == Intent.query_records
        assert dec.confidence == 0.9
        assert dec.source == "fast_route"
        assert dec.chat_reply is None
        assert dec.structured_fields is None

    def test_with_chat_reply_and_structured_fields(self):
        fields = {"chief_complaint": "胸痛3天"}
        ir = _intent_result(
            intent=Intent.add_record,
            chat_reply="已记录",
            structured_fields=fields,
        )
        dec = _decision_from(ir, "llm")
        assert dec.source == "llm"
        assert dec.chat_reply == "已记录"
        assert dec.structured_fields == fields

    def test_source_string_passthrough(self):
        ir = _intent_result()
        for src in ("menu_shortcut", "fast_route", "llm", "custom_source"):
            dec = _decision_from(ir, src)
            assert dec.source == src


# ── classify: effective_intent shortcut ──────────────────────────────────────


@pytest.mark.asyncio
class TestClassifyMenuShortcut:
    @patch("services.intent_workflow.classifier.fast_route")
    async def test_returns_immediately_with_menu_shortcut(self, mock_fast_route):
        """When effective_intent is provided, classify returns immediately
        without calling fast_route or agent.dispatch."""
        ir = _intent_result(intent=Intent.list_patients)
        dec, raw = await classify(
            "任意文本",
            "doc1",
            [],
            effective_intent=ir,
        )
        assert dec.source == "menu_shortcut"
        assert dec.intent == Intent.list_patients
        assert raw is ir
        mock_fast_route.assert_not_called()

    async def test_shortcut_does_not_call_dispatch(self):
        """Ensure agent.dispatch is never imported/called for shortcut path."""
        ir = _intent_result(intent=Intent.help, chat_reply="帮助信息")
        with patch("services.intent_workflow.classifier.fast_route") as mfr:
            dec, raw = await classify("帮助", "doc1", [], effective_intent=ir)
            mfr.assert_not_called()
        assert dec.chat_reply == "帮助信息"


# ── classify: fast_route hit ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestClassifyFastRoute:
    @patch("services.intent_workflow.classifier.log_turn")
    @patch("services.intent_workflow.classifier.fast_route_label", return_value="greeting")
    @patch("services.intent_workflow.classifier.get_session")
    @patch("services.intent_workflow.classifier.fast_route")
    async def test_fast_route_hit(self, mock_fr, mock_gs, mock_frl, mock_lt):
        """fast_route returning a result → source='fast_route', no LLM call."""
        ir = _intent_result(intent=Intent.help, patient_name=None)
        mock_fr.return_value = ir
        mock_gs.return_value = _FakeSession()

        dec, raw = await classify("你好", "doc1", [])
        assert dec.source == "fast_route"
        assert dec.intent == Intent.help
        assert raw is ir
        mock_lt.assert_called_once()

    @patch("services.intent_workflow.classifier.log_turn")
    @patch("services.intent_workflow.classifier.fast_route_label", return_value="query")
    @patch("services.intent_workflow.classifier.get_session")
    @patch("services.intent_workflow.classifier.fast_route")
    async def test_fast_route_does_not_call_dispatch(self, mock_fr, mock_gs, mock_frl, mock_lt):
        """When fast_route succeeds, agent.dispatch should never be called."""
        mock_fr.return_value = _intent_result(intent=Intent.query_records)
        mock_gs.return_value = _FakeSession()

        with patch("services.ai.agent.dispatch", new_callable=AsyncMock) as mock_dispatch:
            await classify("查看张三的病历", "doc1", [])
            mock_dispatch.assert_not_called()


# ── classify: LLM fallback ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestClassifyLLMFallback:
    @patch("services.intent_workflow.classifier.log_turn")
    @patch("services.intent_workflow.classifier.get_session")
    @patch("services.intent_workflow.classifier.fast_route", return_value=None)
    @patch("services.ai.agent.dispatch", new_callable=AsyncMock)
    async def test_llm_fallback(self, mock_dispatch, mock_fr, mock_gs, mock_lt):
        """fast_route→None triggers agent.dispatch; source='llm'."""
        ir = _intent_result(intent=Intent.add_record, patient_name="王五")
        mock_dispatch.return_value = ir
        mock_gs.return_value = _FakeSession()

        dec, raw = await classify("王五今天头痛发热38.5度", "doc1", [{"role": "user", "content": "hi"}])
        assert dec.source == "llm"
        assert dec.intent == Intent.add_record
        assert raw is ir
        mock_dispatch.assert_awaited_once()
        mock_lt.assert_called_once()

    @patch("services.intent_workflow.classifier.log_turn")
    @patch("services.intent_workflow.classifier.get_session")
    @patch("services.intent_workflow.classifier.fast_route", return_value=None)
    @patch("services.ai.agent.dispatch", new_callable=AsyncMock)
    async def test_llm_receives_history(self, mock_dispatch, mock_fr, mock_gs, mock_lt):
        """Agent dispatch receives history from classify args."""
        mock_dispatch.return_value = _intent_result(intent=Intent.unknown)
        mock_gs.return_value = _FakeSession()
        history = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "您好"}]

        await classify("请帮我查一下", "doc1", history)
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs["history"] == history

    @patch("services.intent_workflow.classifier.log_turn")
    @patch("services.intent_workflow.classifier.get_session")
    @patch("services.intent_workflow.classifier.fast_route", return_value=None)
    @patch("services.ai.agent.dispatch", new_callable=AsyncMock)
    async def test_llm_channel_parameter(self, mock_dispatch, mock_fr, mock_gs, mock_lt):
        """Channel parameter is informational only (logged) and does not affect dispatch."""
        mock_dispatch.return_value = _intent_result(intent=Intent.unknown)
        mock_gs.return_value = _FakeSession()

        dec, _ = await classify("测试", "doc1", [], channel="wechat")
        assert dec.source == "llm"


# ── _build_llm_kwargs ───────────────────────────────────────────────────────


class TestBuildLLMKwargs:
    def test_minimal_session(self):
        """Empty session → only history and doctor_id."""
        sess = _FakeSession()
        kw = _build_llm_kwargs("doc1", [{"role": "user", "content": "hi"}], "", sess)
        assert kw["doctor_id"] == "doc1"
        assert kw["history"] == [{"role": "user", "content": "hi"}]
        assert "knowledge_context" not in kw
        assert "specialty" not in kw
        assert "doctor_name" not in kw
        assert "current_patient_context" not in kw
        assert "candidate_patient_context" not in kw
        assert "patient_not_found_context" not in kw

    def test_knowledge_context(self):
        sess = _FakeSession()
        kw = _build_llm_kwargs("doc1", [], "一些知识背景", sess)
        assert kw["knowledge_context"] == "一些知识背景"

    def test_specialty_and_doctor_name(self):
        sess = _FakeSession(specialty="心内科", doctor_name="张伟")
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["specialty"] == "心内科"
        assert kw["doctor_name"] == "张伟"

    def test_current_patient_name(self):
        sess = _FakeSession(current_patient_name="李四")
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["current_patient_context"] == "李四"

    def test_candidate_patient_name_only(self):
        sess = _FakeSession(candidate_patient_name="赵六")
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["candidate_patient_context"] == "赵六"

    def test_candidate_patient_with_gender_and_age(self):
        sess = _FakeSession(
            candidate_patient_name="赵六",
            candidate_patient_gender="男",
            candidate_patient_age=45,
        )
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["candidate_patient_context"] == "赵六，男，45岁"

    def test_candidate_patient_with_gender_only(self):
        sess = _FakeSession(candidate_patient_name="赵六", candidate_patient_gender="女")
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["candidate_patient_context"] == "赵六，女"

    def test_candidate_patient_with_age_only(self):
        sess = _FakeSession(candidate_patient_name="赵六", candidate_patient_age=70)
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["candidate_patient_context"] == "赵六，70岁"

    def test_patient_not_found_name(self):
        sess = _FakeSession(patient_not_found_name="未知患者")
        kw = _build_llm_kwargs("doc1", [], "", sess)
        assert kw["patient_not_found_context"] == "未知患者"

    def test_all_fields_populated(self):
        """All session fields set → all kwargs present."""
        sess = _FakeSession(
            specialty="骨科",
            doctor_name="王医生",
            current_patient_name="张三",
            candidate_patient_name="李四",
            candidate_patient_gender="男",
            candidate_patient_age=30,
            patient_not_found_name="找不到",
        )
        kw = _build_llm_kwargs("doc1", [], "ctx", sess)
        assert kw["knowledge_context"] == "ctx"
        assert kw["specialty"] == "骨科"
        assert kw["doctor_name"] == "王医生"
        assert kw["current_patient_context"] == "张三"
        assert kw["candidate_patient_context"] == "李四，男，30岁"
        assert kw["patient_not_found_context"] == "找不到"
