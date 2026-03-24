"""Handler for create_record intent — enters interview flow."""
from __future__ import annotations

from agent.dispatcher import register
from agent.tools.resolve import resolve
from agent.types import IntentType, HandlerResult, TurnContext
from domain.patients.interview_session import create_session
from domain.patients.interview_turn import interview_turn
from utils.log import log


@register(IntentType.create_record)
async def handle_create_record(ctx: TurnContext) -> HandlerResult:
    """Start or resume a doctor interview session for record creation."""
    patient_name = ctx.routing.patient_name
    if not patient_name:
        return HandlerResult(reply='请提供患者姓名，例如\u201c给张三建病历\u201d。')

    # Resolve or auto-create patient
    resolved = await resolve(
        patient_name, ctx.doctor_id,
        auto_create=True,
        gender=ctx.routing.params.get("gender"),
        age=ctx.routing.params.get("age"),
    )
    if "status" in resolved:
        return HandlerResult(reply=resolved["message"])

    # Delegate to existing interview flow
    # create_session manages its own DB session internally
    interview = await create_session(
        doctor_id=ctx.doctor_id,
        patient_id=resolved["patient_id"],
        mode="doctor",
    )

    # Use the full original message as clinical context for the first
    # interview turn. The routing LLM no longer extracts clinical_text
    # into params (to keep output short and avoid truncation).
    clinical_text = ctx.text
    if clinical_text and patient_name in clinical_text:
        response = await interview_turn(interview.id, clinical_text)
        return HandlerResult(
            reply=response.reply,
            data={"session_id": interview.id, "progress": response.progress},
        )

    return HandlerResult(
        reply=f"开始为{patient_name}建病历。请告诉我患者的主诉（主要症状和持续时间）。",
        data={"session_id": interview.id},
    )
