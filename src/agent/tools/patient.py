"""Patient-role tools for the LangChain ReAct agent."""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.tools import tool

from agent.identity import get_current_identity


async def _process_interview(session_id: str, answer: str) -> Any:
    """Delegate to existing interview engine.

    interview_turn(session_id, patient_text) -> InterviewResponse
    InterviewResponse fields: reply, collected, progress, status
    """
    from domain.patients.interview_turn import interview_turn
    return await interview_turn(session_id, answer)


@tool
async def advance_interview(answer: str) -> Dict[str, Any]:
    """推进患者预问诊流程。提取临床信息，推进状态机，返回下一个问题。
    当患者提供症状、病史等临床信息时调用此工具。"""
    session_id = get_current_identity()
    result = await _process_interview(session_id, answer)
    return {
        "suggested_reply": result.reply,
        "collected": result.collected,
        "progress": result.progress,
        "status": result.status,
        "complete": result.status == "reviewing",
    }


PATIENT_TOOLS = [advance_interview]
