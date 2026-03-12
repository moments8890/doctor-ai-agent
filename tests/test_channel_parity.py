"""E2E parity test: Web and WeChat channels produce equivalent WorkflowResults.

The 5-layer intent workflow should be channel-agnostic — given identical text,
doctor_id, and history, the classification, entities, binding, plan, and gate
results must match regardless of channel="web" vs channel="wechat".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from services.ai.intent import Intent, IntentResult
from services.intent_workflow.models import WorkflowResult
from services.intent_workflow.workflow import run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    """Minimal stand-in for DoctorSession — enough for all five layers."""

    current_patient_id: Optional[int] = None
    current_patient_name: Optional[str] = None
    candidate_patient_name: Optional[str] = None
    candidate_patient_gender: Optional[str] = None
    candidate_patient_age: Optional[int] = None
    patient_not_found_name: Optional[str] = None
    pending_create_name: Optional[str] = None
    pending_record_id: Optional[str] = None
    specialty: Optional[str] = None
    doctor_name: Optional[str] = None
    conversation_history: List[dict] = field(default_factory=list)


def _ir(
    intent: Intent,
    patient_name: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    is_emergency: bool = False,
    chat_reply: Optional[str] = None,
    structured_fields: Optional[dict] = None,
    confidence: float = 1.0,
) -> IntentResult:
    """Shorthand IntentResult factory."""
    return IntentResult(
        intent=intent,
        patient_name=patient_name,
        gender=gender,
        age=age,
        is_emergency=is_emergency,
        chat_reply=chat_reply,
        structured_fields=structured_fields,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test cases: (id, text, llm_return, description)
#
# For inputs that hit fast_route (Tier 1/2 regex), the LLM mock is unused
# but present for safety.  For inputs that fall through to LLM dispatch,
# the mock controls the deterministic output.
# ---------------------------------------------------------------------------

_CASES = [
    pytest.param(
        "greeting_hello",
        "你好",
        _ir(Intent.unknown, chat_reply="你好！"),
        id="greeting_hello",
    ),
    pytest.param(
        "help_keyword",
        "帮助",
        _ir(Intent.help),
        id="help_keyword",
    ),
    pytest.param(
        "list_patients",
        "所有患者",
        _ir(Intent.list_patients),
        id="list_patients",
    ),
    pytest.param(
        "list_tasks",
        "任务列表",
        _ir(Intent.list_tasks),
        id="list_tasks",
    ),
    pytest.param(
        "create_patient_fast",
        "新患者王明 男 45岁",
        _ir(Intent.create_patient, patient_name="王明", gender="男", age=45),
        id="create_patient_fast",
    ),
    pytest.param(
        "add_record_llm",
        "张三今天主诉头痛三天，伴随恶心呕吐",
        _ir(Intent.add_record, patient_name="张三"),
        id="add_record_llm",
    ),
    pytest.param(
        "query_records_llm",
        "查一下李四最近的病历",
        _ir(Intent.query_records, patient_name="李四"),
        id="query_records_llm",
    ),
    pytest.param(
        "delete_patient_fast",
        "删除患者赵六",
        _ir(Intent.delete_patient, patient_name="赵六"),
        id="delete_patient_fast",
    ),
    pytest.param(
        "unknown_chitchat",
        "今天天气真好啊",
        _ir(Intent.unknown, chat_reply="抱歉，我不太理解您的意思。"),
        id="unknown_chitchat",
    ),
    pytest.param(
        "add_record_no_name_llm",
        "患者今天血压偏高需要调整降压药方案",
        _ir(Intent.add_record, patient_name=None),
        id="add_record_no_name",
    ),
    pytest.param(
        "schedule_followup_fast",
        "张三三个月后随访",
        _ir(Intent.schedule_follow_up, patient_name="张三"),
        id="schedule_followup",
    ),
    pytest.param(
        "export_records_fast",
        "导出王芳的病历",
        _ir(Intent.export_records, patient_name="王芳"),
        id="export_records",
    ),
    pytest.param(
        "complete_task",
        "完成任务1",
        _ir(Intent.complete_task),
        id="complete_task",
    ),
    pytest.param(
        "create_patient_with_clinical",
        "新患者陈明 男 60岁 胸痛两天伴呼吸困难",
        _ir(
            Intent.create_patient,
            patient_name="陈明",
            gender="男",
            age=60,
            structured_fields={"chief_complaint": "胸痛两天伴呼吸困难"},
        ),
        id="create_patient_with_clinical",
    ),
]

DOCTOR_ID = "test_parity_doc"
HISTORY: List[dict] = []


# ---------------------------------------------------------------------------
# Core parity test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id, text, llm_return", _CASES)
async def test_channel_parity(case_id: str, text: str, llm_return: IntentResult):
    """Run the workflow with channel='web' and channel='wechat' and assert equivalence."""
    fake_session = _FakeSession()

    mock_dispatch = AsyncMock(return_value=llm_return)
    mock_hydrate = AsyncMock(return_value=fake_session)

    with (
        patch(
            "services.intent_workflow.classifier.get_session",
            return_value=fake_session,
        ),
        patch(
            "services.intent_workflow.entities.get_session",
            return_value=fake_session,
        ),
        patch(
            "services.intent_workflow.binder.get_session",
            return_value=fake_session,
        ),
        patch("services.ai.agent.dispatch", mock_dispatch),
        patch(
            "services.intent_workflow.workflow.hydrate_session_state",
            mock_hydrate,
        ),
        patch(
            "services.intent_workflow.workflow.clear_candidate_patient",
        ),
        patch(
            "services.intent_workflow.workflow.clear_patient_not_found",
        ),
        patch(
            "services.observability.turn_log.log_turn",
        ),
    ):
        result_web: WorkflowResult = await run(
            text,
            DOCTOR_ID,
            list(HISTORY),
            channel="web",
        )

        result_wechat: WorkflowResult = await run(
            text,
            DOCTOR_ID,
            list(HISTORY),
            channel="wechat",
        )

    # -- Layer 1: Classification --
    assert result_web.decision.intent == result_wechat.decision.intent, (
        f"[{case_id}] intent mismatch: web={result_web.decision.intent} "
        f"wechat={result_wechat.decision.intent}"
    )
    assert result_web.decision.source == result_wechat.decision.source, (
        f"[{case_id}] source mismatch: web={result_web.decision.source} "
        f"wechat={result_wechat.decision.source}"
    )
    assert result_web.decision.confidence == result_wechat.decision.confidence

    # -- Layer 2: Entities --
    web_pname = (
        result_web.entities.patient_name.value
        if result_web.entities.patient_name
        else None
    )
    wechat_pname = (
        result_wechat.entities.patient_name.value
        if result_wechat.entities.patient_name
        else None
    )
    assert web_pname == wechat_pname, (
        f"[{case_id}] patient_name mismatch: web={web_pname} wechat={wechat_pname}"
    )
    assert result_web.entities.is_emergency == result_wechat.entities.is_emergency

    # -- Layer 3: Binding --
    assert result_web.binding.status == result_wechat.binding.status, (
        f"[{case_id}] binding.status mismatch: web={result_web.binding.status} "
        f"wechat={result_wechat.binding.status}"
    )
    assert result_web.binding.source == result_wechat.binding.source
    assert result_web.binding.patient_id == result_wechat.binding.patient_id
    assert result_web.binding.patient_name == result_wechat.binding.patient_name

    # -- Layer 4: Plan --
    web_actions = [a.action for a in result_web.plan.actions]
    wechat_actions = [a.action for a in result_wechat.plan.actions]
    assert web_actions == wechat_actions, (
        f"[{case_id}] plan.actions mismatch: web={web_actions} wechat={wechat_actions}"
    )
    assert result_web.plan.is_compound == result_wechat.plan.is_compound

    # -- Layer 5: Gate --
    assert result_web.gate.approved == result_wechat.gate.approved, (
        f"[{case_id}] gate.approved mismatch: web={result_web.gate.approved} "
        f"wechat={result_wechat.gate.approved}"
    )
    assert result_web.gate.reason == result_wechat.gate.reason
    assert result_web.gate.requires_confirmation == result_wechat.gate.requires_confirmation


# ---------------------------------------------------------------------------
# Bonus: full model equality (strictest check)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id, text, llm_return", _CASES)
async def test_channel_parity_full_model_equality(
    case_id: str, text: str, llm_return: IntentResult,
):
    """Assert that the entire WorkflowResult is identical across channels.

    This is the strictest form: if any field at all diverges, the test fails.
    """
    fake_session = _FakeSession()

    mock_dispatch = AsyncMock(return_value=llm_return)
    mock_hydrate = AsyncMock(return_value=fake_session)

    with (
        patch(
            "services.intent_workflow.classifier.get_session",
            return_value=fake_session,
        ),
        patch(
            "services.intent_workflow.entities.get_session",
            return_value=fake_session,
        ),
        patch(
            "services.intent_workflow.binder.get_session",
            return_value=fake_session,
        ),
        patch("services.ai.agent.dispatch", mock_dispatch),
        patch(
            "services.intent_workflow.workflow.hydrate_session_state",
            mock_hydrate,
        ),
        patch(
            "services.intent_workflow.workflow.clear_candidate_patient",
        ),
        patch(
            "services.intent_workflow.workflow.clear_patient_not_found",
        ),
        patch(
            "services.observability.turn_log.log_turn",
        ),
    ):
        result_web = await run(text, DOCTOR_ID, list(HISTORY), channel="web")
        result_wechat = await run(text, DOCTOR_ID, list(HISTORY), channel="wechat")

    assert result_web.model_dump() == result_wechat.model_dump(), (
        f"[{case_id}] WorkflowResult divergence detected between web and wechat"
    )
