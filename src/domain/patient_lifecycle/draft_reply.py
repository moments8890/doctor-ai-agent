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


async def generate_draft_reply(
    doctor_id: str,
    patient_id: int,
    message_id: int,
    patient_message_text: str,
    patient_context: str = "",
    force_priority: Optional[str] = None,
) -> Optional[DraftReplyResult]:
    """Generate a draft reply using doctor's personal knowledge.

    ``force_priority`` overrides the defer-to-doctor detector. Set to
    ``"critical"`` from the signal-flag path so urgency does not depend on
    the LLM happening to emit a defer phrase.

    Returns None if generation fails.
    """
    from agent.prompt_composer import compose_messages
    from agent.prompt_config import FOLLOWUP_REPLY_LAYERS
    from agent.style_guard import llm_call_with_guard
    from domain.knowledge.citation_parser import extract_citations, validate_citations
    from domain.knowledge.usage_tracking import log_citations
    from db.engine import AsyncSessionLocal
    from db.crud.doctor import list_doctor_knowledge_items

    config = FOLLOWUP_REPLY_LAYERS

    # Look up patient name for the prompt
    patient_name = ""
    try:
        from db.models.patient import Patient
        async with AsyncSessionLocal() as name_db:
            from sqlalchemy import select
            row = (await name_db.execute(
                select(Patient.name, Patient.gender).where(Patient.id == int(patient_id))
            )).first()
            if row:
                patient_name = row.name or ""
    except Exception:
        pass

    user_message = f"患者姓名：{patient_name}\n患者消息：{patient_message_text}"

    try:
        messages = await compose_messages(
            config,
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message=user_message,
        )

        from agent.llm import compute_prompt_hash
        _prompt_hash = compute_prompt_hash(messages)

        # Style-guard wrapper: 1 regen on hard-block phrase violation, then ship-with-warning
        # (per locked plan latency budget — followup_reply ≤6s)
        response, guard_meta = await llm_call_with_guard(
            messages=messages,
            op_name="draft_reply",
            max_regens=1,
        )
        if guard_meta["initial_violations"]:
            log(f"[draft_reply] style violations detected: initial={guard_meta['initial_violations']} "
                f"final={guard_meta['final_violations']} regens={guard_meta['regens_used']} "
                f"shipped_dirty={guard_meta['shipped_with_violations']}")
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

        confidence = 0.9

        # Strip [KB-*] citation markers from user-facing text
        import re
        clean_response = re.sub(r"\[KB-\d+\]", "", response).strip()
        # Strip [P-xxx] persona citation markers
        from domain.knowledge.persona_citations import strip_persona_citations
        clean_response = strip_persona_citations(clean_response)
        # Collapse any double-spaces left after stripping
        clean_response = re.sub(r"  +", " ", clean_response)

        # Log when draft has no KB grounding (but still generate it)
        if not validation.valid_ids:
            log("[draft_reply] no KB citation — draft generated without grounding", level="info")

        result = DraftReplyResult(
            text=clean_response,
            cited_knowledge_ids=validation.valid_ids,
            confidence=confidence,
        )

        # Detect defer-to-doctor pattern (locked plan rule 19, codex r5 review).
        # When fires, draft is high-priority; the doctor must see it before
        # normal drafts or the defer text is theatre.
        from agent.style_guard import detect_defer_to_doctor
        from domain.patient_lifecycle.priority import resolve_draft_priority

        deferred = detect_defer_to_doctor(result.text)
        priority = force_priority or resolve_draft_priority(deferred_to_doctor=deferred)
        if priority:
            if force_priority:
                log(f"[draft_reply] priority={priority} (forced by caller)")
            else:
                log(f"[draft_reply] priority={priority} (deferred to doctor, "
                    f"{'after-hours' if priority == 'critical' else 'office-hours'})")

        # Persist draft FIRST so we have draft.id for citation logging (non-fatal)
        draft_id: Optional[int] = None
        try:
            from db.models.message_draft import MessageDraft, DraftStatus

            async with AsyncSessionLocal() as draft_session:
                draft = MessageDraft(
                    doctor_id=doctor_id,
                    patient_id=str(patient_id),  # MessageDraft.patient_id is String(64)
                    source_message_id=message_id,
                    draft_text=result.text,
                    cited_knowledge_ids=json.dumps(result.cited_knowledge_ids),
                    confidence=result.confidence,
                    status=DraftStatus.generated.value,
                    prompt_hash=_prompt_hash,
                    priority=priority,
                )
                draft_session.add(draft)
                await draft_session.flush()
                draft_id = draft.id
                await draft_session.commit()
        except Exception as draft_exc:
            log(f"[draft_reply] draft persistence failed (non-fatal): {draft_exc}", level="warning")

        # Log valid citations to knowledge_usage_log with draft_id (non-fatal)
        if validation.valid_ids:
            try:
                async with AsyncSessionLocal() as cite_session:
                    await log_citations(
                        cite_session, doctor_id, validation.valid_ids,
                        "followup", patient_id=patient_id, draft_id=draft_id,
                    )
            except Exception as cite_exc:
                log(f"[draft_reply] citation logging failed (non-fatal): {cite_exc}", level="warning")

        # Log hallucinated citations (non-fatal)
        if validation.hallucinated_ids:
            try:
                from domain.knowledge.citation_parser import log_hallucinations
                async with AsyncSessionLocal() as hal_session:
                    await log_hallucinations(
                        hal_session, doctor_id, "draft_reply", message_id,
                        validation.hallucinated_ids,
                    )
            except Exception as hal_exc:
                log(f"[draft_reply] hallucination logging failed (non-fatal): {hal_exc}", level="warning")

        return result

    except Exception as exc:
        log(f"[draft_reply] generation failed: {exc}", level="error")
        return None
