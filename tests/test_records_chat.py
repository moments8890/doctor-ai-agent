"""病历对话接口测试：验证 /api/records/chat 的意图路由、患者姓名补全、任务管理及预约创建逻辑，LLM 和数据库均使用模拟对象。"""

import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from db.models.medical_record import MedicalRecord
from db.crud import create_task
from routers.records import ChatInput, HistoryMessage, chat
from services.ai.intent import Intent, IntentResult


DOCTOR = "unit_doc_records_chat"


def _record() -> MedicalRecord:
    return MedicalRecord(
        content="突发剧烈胸痛两小时，伴大汗淋漓，急性冠脉综合征待排，急性冠脉综合征待排",
        tags=["急性冠脉综合征待排"],
    )


@pytest.mark.asyncio
async def test_name_followup_overrides_create_patient_and_saves_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发剧烈胸痛两小时，伴大汗淋漓，急性冠脉综合征待排"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.intent_handlers._add_record.AsyncSessionLocal", session_factory), \
         patch(
             "services.ai.agent.dispatch",
             new=AsyncMock(
                 return_value=IntentResult(
                     intent=Intent.create_patient,
                     patient_name="陈明",
                 )
             ),
         ), \
         patch(
             "services.domain.record_ops.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ) as mock_structure:
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert "陈明" in response.reply
    # The follow-up name turn must not be used as clinical content.
    assert mock_structure.await_args.args[0] == "突发剧烈胸痛两小时，伴大汗淋漓，急性冠脉综合征待排"


@pytest.mark.asyncio
async def test_name_followup_overrides_unknown_and_saves_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发剧烈胸痛两小时，伴大汗淋漓，急性冠脉综合征待排"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.intent_handlers._add_record.AsyncSessionLocal", session_factory), \
         patch(
             "services.ai.agent.dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply="好的")),
         ), \
         patch(
             "services.domain.record_ops.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ):
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert response.reply  # reply is non-empty (natural or template)


@pytest.mark.asyncio
async def test_name_followup_fills_missing_name_when_intent_is_add_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发剧烈胸痛两小时，伴大汗淋漓，急性冠脉综合征待排"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.intent_handlers._add_record.AsyncSessionLocal", session_factory), \
         patch(
             "services.ai.agent.dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
         ), \
         patch(
             "services.domain.record_ops.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ):
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert "陈明" in response.reply


@pytest.mark.asyncio
async def test_list_tasks_intent_returns_pending_tasks(session_factory):
    async with session_factory() as db:
        await create_task(
            db,
            doctor_id=DOCTOR,
            task_type="follow_up",
            title="随访提醒：张三",
            due_at=datetime(2026, 3, 20, 9, 0, 0),
        )

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.intent_handlers._simple_intents.AsyncSessionLocal", session_factory), \
         patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.list_tasks)),
    ):
        response = await chat(ChatInput(text="查看待办", history=[], doctor_id=DOCTOR))

    assert "待办任务" in response.reply
    assert "随访提醒：张三" in response.reply


@pytest.mark.asyncio
async def test_complete_task_fastpath_marks_task_done(session_factory):
    async with session_factory() as db:
        task = await create_task(
            db,
            doctor_id=DOCTOR,
            task_type="follow_up",
            title="随访提醒：李四",
        )

    agent_mock = AsyncMock()
    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.chat_handlers.AsyncSessionLocal", session_factory), \
         patch("services.ai.agent.dispatch", new=agent_mock):
        response = await chat(ChatInput(text=f"完成 {task.id}", history=[], doctor_id=DOCTOR))

    agent_mock.assert_not_awaited()
    assert "已标记完成" in response.reply

    async with session_factory() as db:
        from db.crud import list_tasks

        pending = await list_tasks(db, DOCTOR, status="pending")
        assert len(pending) == 0


@pytest.mark.asyncio
async def test_complete_task_intent_requires_task_id(session_factory):
    with patch("routers.records.AsyncSessionLocal", session_factory), patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(
            return_value=IntentResult(intent=Intent.complete_task, extra_data={}),
        ),
    ):
        response = await chat(ChatInput(text="完成任务", history=[], doctor_id=DOCTOR))

    assert "未能识别任务编号" in response.reply


@pytest.mark.asyncio
async def test_schedule_appointment_intent_creates_task(session_factory):
    fake_task = SimpleNamespace(id=99)

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("services.domain.intent_handlers._simple_intents.AsyncSessionLocal", session_factory), \
         patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(
            return_value=IntentResult(
                intent=Intent.schedule_appointment,
                patient_name="王五",
                extra_data={
                    "appointment_time": "2026-03-15T14:00:00",
                    "notes": "复查血压",
                },
            ),
        ),
    ), patch(
        "services.domain.intent_handlers._simple_intents.create_appointment_task",
        new=AsyncMock(return_value=fake_task),
    ) as create_appt_mock:
        response = await chat(ChatInput(text="帮王五预约复诊", history=[], doctor_id=DOCTOR))

    create_appt_mock.assert_awaited_once()
    assert "已为患者【王五】安排预约" in response.reply
    assert "任务编号：99" in response.reply
