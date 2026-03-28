"""Generate AI draft replies for patient follow-up messages."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from utils.log import log


@dataclass
class DraftReplyResult:
    text: str
    cited_knowledge_ids: List[int] = field(default_factory=list)
    confidence: float = 0.9
    is_red_flag: bool = False


RED_FLAG_KEYWORDS = [
    "发热", "发烧", "头痛加剧", "头疼加重", "恶心", "呕吐",
    "无力", "麻木", "感觉异常", "言语障碍", "说不出话",
    "胸痛", "胸闷", "呼吸困难", "喘不上气",
    "出血", "流血", "伤口", "红肿",
    "加重", "恶化", "突然",
]


def detect_red_flags(message: str) -> bool:
    """Check if patient message contains red-flag symptoms."""
    return any(kw in message for kw in RED_FLAG_KEYWORDS)


async def generate_draft_reply(
    doctor_id: str,
    patient_id: str,
    message_id: int,
    patient_message_text: str,
    patient_context: str = "",
) -> Optional[DraftReplyResult]:
    """Generate a draft reply using doctor's personal knowledge.

    Returns None if generation fails.
    """
    from agent.prompt_composer import compose_messages
    from agent.prompt_config import LayerConfig
    from agent.llm import llm_call
    from domain.knowledge.citation_parser import extract_citations, validate_citations
    from domain.knowledge.usage_tracking import log_citations
    from db.engine import AsyncSessionLocal
    from db.crud.doctor import list_doctor_knowledge_items

    is_red_flag = detect_red_flags(patient_message_text)

    # Build the prompt
    config = LayerConfig(
        system=True,
        domain=True,
        intent="followup_reply",
        load_knowledge=True,
        patient_context=True,
    )

    user_message = f"患者消息：{patient_message_text}"
    if is_red_flag:
        user_message += "\n\n⚠️ 注意：患者消息中包含红旗征象，请使用就医建议模板回复。"

    try:
        messages = await compose_messages(
            config,
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message=user_message,
        )

        response = await llm_call(messages=messages, op_name="draft_reply")
        if not response:
            log("[draft_reply] LLM returned empty response", level="warning")
            return None

        # Extract and validate citations
        citation_result = extract_citations(response)
        valid_kb_ids: set[int] = set()
        async with AsyncSessionLocal() as session:
            items = await list_doctor_knowledge_items(session, doctor_id, limit=200)
            valid_kb_ids = {item.id for item in items}

        validation = validate_citations(citation_result.cited_ids, valid_kb_ids)

        # Log valid citations to knowledge_usage_log (non-fatal)
        if validation.valid_ids:
            try:
                async with AsyncSessionLocal() as cite_session:
                    await log_citations(
                        cite_session, doctor_id, validation.valid_ids,
                        "followup", patient_id=patient_id,
                    )
            except Exception as cite_exc:
                log(f"[draft_reply] citation logging failed (non-fatal): {cite_exc}", level="warning")

        confidence = 0.7 if is_red_flag else 0.9

        result = DraftReplyResult(
            text=response,
            cited_knowledge_ids=validation.valid_ids,
            confidence=confidence,
            is_red_flag=is_red_flag,
        )

        # Persist draft to MessageDraft table (non-fatal)
        try:
            from db.models.message_draft import MessageDraft, DraftStatus

            async with AsyncSessionLocal() as draft_session:
                draft = MessageDraft(
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    source_message_id=message_id,
                    draft_text=result.text,
                    cited_knowledge_ids=json.dumps(result.cited_knowledge_ids),
                    confidence=result.confidence,
                    status=DraftStatus.generated.value,
                )
                draft_session.add(draft)
                await draft_session.commit()
        except Exception as draft_exc:
            log(f"[draft_reply] draft persistence failed (non-fatal): {draft_exc}", level="warning")

        return result

    except Exception as exc:
        log(f"[draft_reply] generation failed: {exc}", level="error")
        return None
