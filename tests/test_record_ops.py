"""Unit tests for services/domain/record_ops.py — pure functions + async assemble_record."""

from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models.medical_record import MedicalRecord
from services.ai.intent import Intent, IntentResult
from services.domain.record_ops import (
    _is_clinical_turn,
    _sanitize_prior_summary,
    build_clinical_context,
    assemble_record,
)


# ---------------------------------------------------------------------------
# 1. _is_clinical_turn
# ---------------------------------------------------------------------------

class TestIsClinicalTurn:
    """_is_clinical_turn: short, command-prefix, non-clinical regex, and valid clinical."""

    @pytest.mark.parametrize("text", [
        "查一下",          # 3 chars
        "好",              # 1 char
        "删除张三",        # 4 chars (< 15)
        "你好世界",        # 4 chars
        "",                # empty
        "hello world",     # 11 chars
    ])
    def test_short_text_returns_false(self, text: str) -> None:
        assert _is_clinical_turn(text) is False

    @pytest.mark.parametrize("text", [
        "删除这个患者的全部记录并确认操作",
        "患者列表看一下最近新增的患者信息",
        "帮助我看看目前系统支持的所有功能",
        "创建一个新患者档案方便后续录入信息",
        "查一下这个患者过去三个月所有记录",
        "待办事项清单给我列一下看看有哪些",
        "确认这条病历内容正确可以保存入库",
        "取消这条病历不需要保存删掉就好了",
    ])
    def test_command_prefix_returns_false(self, text: str) -> None:
        assert _is_clinical_turn(text) is False

    @pytest.mark.parametrize("text", [
        "你好",
        "早上好",
        "好的",
        "好的。",
        "完成 3",
        "完成3",
        "取消任务",
        "取消待办",
        "推迟任务",
        "推迟待办",
        "查询病历记录",
        "查看历史记录",
        "帮我查一下",
        "帮我建一个",
        "请问你叫什么",
        "怎么用",
        "预约门诊",
        "设随访",
    ])
    def test_non_clinical_regex_returns_false(self, text: str) -> None:
        # Some of these are short too, but specifically test the regex path
        # Only need to ensure the function returns False.
        assert _is_clinical_turn(text) is False

    @pytest.mark.parametrize("text", [
        "患者主诉反复胸闷气短三天，活动后加重，伴有夜间阵发性呼吸困难",
        "体格检查血压一百四十九十五，心率九十二次每分，双肺底可闻及湿罗音",
        "心电图提示前壁导联ST段抬高，考虑急性前壁心肌梗死可能",
        "目前诊断考虑冠心病不稳定型心绞痛，建议进一步行冠脉造影检查",
    ])
    def test_clinical_text_returns_true(self, text: str) -> None:
        assert _is_clinical_turn(text) is True


# ---------------------------------------------------------------------------
# 2. build_clinical_context
# ---------------------------------------------------------------------------

class TestBuildClinicalContext:
    """build_clinical_context: filters, limits, deduplicates, appends current text."""

    def test_filters_non_clinical_turns(self) -> None:
        history = [
            {"role": "user", "content": "你好"},
            {"role": "user", "content": "患者主诉反复胸闷气短三天，活动后加重，伴有夜间阵发性呼吸困难"},
            {"role": "user", "content": "删除这条记录"},
            {"role": "assistant", "content": "好的，已删除"},
        ]
        result = build_clinical_context("当前主诉头痛两天加重", history)
        assert "患者主诉反复胸闷气短三天" in result
        assert "你好" not in result
        assert "删除" not in result
        assert "已删除" not in result  # assistant turns excluded
        assert "当前主诉头痛两天加重" in result

    def test_keeps_only_last_6_user_turns(self) -> None:
        history = [
            {"role": "user", "content": f"患者第{i}次就诊主诉胸闷气短反复发作加重"}
            for i in range(10)
        ]
        result = build_clinical_context("当前文本", history)
        # Only last 6 turns from history are considered (indices 4-9)
        assert "第4次" in result
        assert "第9次" in result
        # Turns before the window should be excluded
        assert "第3次" not in result

    def test_appends_current_text(self) -> None:
        result = build_clinical_context("心率78次每分", [])
        assert result == "心率78次每分"

    def test_deduplicates(self) -> None:
        same_text = "患者主诉反复胸闷气短三天，活动后加重"
        history = [
            {"role": "user", "content": same_text},
        ]
        result = build_clinical_context(same_text, history)
        # Only one occurrence after dedup
        assert result.count(same_text) == 1

    def test_empty_history_returns_current_text(self) -> None:
        result = build_clinical_context("患者诉头痛", None)
        assert result == "患者诉头痛"


# ---------------------------------------------------------------------------
# 3. _sanitize_prior_summary
# ---------------------------------------------------------------------------

class TestSanitizePriorSummary:
    """_sanitize_prior_summary: encounter type, empty, blocked prefixes, truncation, tags."""

    def test_returns_none_for_non_follow_up(self) -> None:
        assert _sanitize_prior_summary("first_visit", "some summary") is None
        assert _sanitize_prior_summary("unknown", "some summary") is None

    def test_returns_none_for_empty_summary(self) -> None:
        assert _sanitize_prior_summary("follow_up", "") is None
        assert _sanitize_prior_summary("follow_up", None) is None

    def test_strips_blocked_prefixes(self) -> None:
        summary = "正常内容\n忽略这条\nSYSTEM prompt\n# heading\n---\n有效内容"
        result = _sanitize_prior_summary("follow_up", summary)
        assert result is not None
        assert "正常内容" in result
        assert "有效内容" in result
        assert "忽略这条" not in result
        assert "SYSTEM prompt" not in result
        assert "# heading" not in result

    def test_truncates_to_500_chars(self) -> None:
        summary = "重" * 600
        result = _sanitize_prior_summary("follow_up", summary)
        assert result is not None
        # The content inside tags should be at most 500 chars
        inner = result.split("<prior_summary>")[1].split("</prior_summary>")[0].strip()
        assert len(inner) <= 500

    def test_wraps_in_prior_summary_tags(self) -> None:
        result = _sanitize_prior_summary("follow_up", "上次就诊诊断冠心病")
        assert result is not None
        assert "<prior_summary>" in result
        assert "</prior_summary>" in result
        assert "上次就诊诊断冠心病" in result


# ---------------------------------------------------------------------------
# 4. assemble_record (async)
# ---------------------------------------------------------------------------

class TestAssembleRecord:
    """assemble_record: always calls structuring LLM (ADR 0008)."""

    @pytest.mark.asyncio
    async def test_calls_llm_structuring(self) -> None:
        """assemble_record always calls the structuring LLM."""
        intent = IntentResult(
            intent=Intent.add_record,
        )
        mock_record = MedicalRecord(content="LLM整理后的病历", record_type="visit")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.domain.record_ops.structure_medical_record",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_struct, patch(
            "services.domain.record_ops.detect_encounter_type",
            new_callable=AsyncMock,
            return_value="first_visit",
        ) as mock_detect, patch(
            "services.domain.record_ops.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ):
            rec = await assemble_record(
                intent_result=intent,
                text="患者胸闷气短反复发作三天加重",
                history=[],
                doctor_id="doc1",
                patient_id=None,
            )

        mock_struct.assert_awaited_once()
        assert rec.content == "LLM整理后的病历"

    @pytest.mark.asyncio
    async def test_without_fields_follow_up_with_prior_summary(self) -> None:
        """Follow-up encounters inject a prior_summary into the structuring call."""
        intent = IntentResult(intent=Intent.add_record)
        mock_record = MedicalRecord(content="随访病历", record_type="visit")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.domain.record_ops.structure_medical_record",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_struct, patch(
            "services.domain.record_ops.detect_encounter_type",
            new_callable=AsyncMock,
            return_value="follow_up",
        ), patch(
            "services.domain.record_ops.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ), patch(
            "services.patient.prior_visit.get_prior_visit_summary",
            new_callable=AsyncMock,
            return_value="上次诊断高血压",
        ):
            rec = await assemble_record(
                intent_result=intent,
                text="患者今日复诊血压控制良好无明显不适",
                history=[],
                doctor_id="doc1",
                patient_id=42,
            )

        # Verify structuring was called with a prior_visit_summary containing the tag
        call_kwargs = mock_struct.call_args
        prior_arg = call_kwargs.kwargs.get("prior_visit_summary") or call_kwargs[1].get("prior_visit_summary")
        assert prior_arg is not None
        assert "<prior_summary>" in prior_arg
        assert "上次诊断高血压" in prior_arg

    @pytest.mark.asyncio
    async def test_without_fields_prior_summary_error_is_swallowed(self) -> None:
        """If get_prior_visit_summary raises, the error is swallowed and prior is None."""
        intent = IntentResult(intent=Intent.add_record)
        mock_record = MedicalRecord(content="结果", record_type="visit")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.domain.record_ops.structure_medical_record",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_struct, patch(
            "services.domain.record_ops.detect_encounter_type",
            new_callable=AsyncMock,
            return_value="follow_up",
        ), patch(
            "services.domain.record_ops.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ), patch(
            "services.patient.prior_visit.get_prior_visit_summary",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ):
            rec = await assemble_record(
                intent_result=intent,
                text="患者今日复诊状态稳定继续目前治疗方案",
                history=[],
                doctor_id="doc1",
                patient_id=42,
            )

        # Should still succeed; prior_visit_summary should be None
        call_kwargs = mock_struct.call_args
        prior_arg = call_kwargs.kwargs.get("prior_visit_summary") or call_kwargs[1].get("prior_visit_summary")
        assert prior_arg is None

    @pytest.mark.asyncio
    async def test_assemble_record_calls_structuring_llm_when_no_fields(self) -> None:
        """When structured_fields are absent, assemble_record calls structure_medical_record."""
        intent = IntentResult(intent=Intent.add_record)
        mock_record = MedicalRecord(content="LLM整理后的病历", record_type="visit")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.domain.record_ops.structure_medical_record",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_struct, patch(
            "services.domain.record_ops.detect_encounter_type",
            new_callable=AsyncMock,
            return_value="first_visit",
        ), patch(
            "services.domain.record_ops.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ):
            rec = await assemble_record(
                intent_result=intent,
                text="患者头痛三天伴恶心呕吐明显加重",
                history=[],
                doctor_id="doc1",
                patient_id=None,
            )

        mock_struct.assert_awaited_once()
        assert rec.content == "LLM整理后的病历"

    @pytest.mark.asyncio
    async def test_assemble_record_omits_profile_fields_when_none(self) -> None:
        """When visit_scenario/note_style are None, they are still passed (as None)."""
        intent = IntentResult(intent=Intent.add_record)
        mock_record = MedicalRecord(content="LLM整理后的病历", record_type="visit")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.domain.record_ops.structure_medical_record",
            new_callable=AsyncMock,
            return_value=mock_record,
        ) as mock_struct, patch(
            "services.domain.record_ops.detect_encounter_type",
            new_callable=AsyncMock,
            return_value="first_visit",
        ), patch(
            "services.domain.record_ops.AsyncSessionLocal",
            return_value=mock_session_ctx,
        ):
            rec = await assemble_record(
                intent_result=intent,
                text="患者头痛三天伴恶心呕吐明显加重",
                history=[],
                doctor_id="doc1",
                patient_id=None,
            )

        call_kwargs = mock_struct.call_args.kwargs
        assert call_kwargs.get("visit_scenario") is None
        assert call_kwargs.get("note_style") is None
