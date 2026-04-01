"""Draft reply management endpoints: list, send, edit, dismiss, and confirmation.

Provides the API surface for the doctor draft review workflow where AI-generated
follow-up reply drafts are reviewed, optionally edited, and sent to patients.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.crud.patient_message import save_patient_message
from db.engine import get_db
from db.models.ai_suggestion import AISuggestion
from db.models.doctor_edit import DoctorEdit
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.tasks import DoctorTask, TaskStatus
from domain.knowledge.teaching import (
    create_rule_from_edit,
    log_doctor_edit,
    should_prompt_teaching,
)
from infra.auth.rate_limit import enforce_doctor_rate_limit
from utils.log import log

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Request / Response Models ────────────────────────────────────────────


class EditDraftRequest(BaseModel):
    edited_text: str


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_cited_ids(raw: Optional[str]) -> list[int]:
    """Parse cited_knowledge_ids JSON string to a list of ints."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return []


# ── 1. List pending drafts ───────────────────────────────────────────────


@router.get("/api/manage/drafts")
async def list_pending_drafts(
    doctor_id: str = Query(default="web_doctor"),
    include_sent: bool = Query(default=False),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List drafts for a doctor.

    By default returns pending (generated/edited). With include_sent=true,
    also returns sent drafts for the completed view.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts")

    stmt = (
        select(
            MessageDraft,
            PatientMessage.content.label("patient_message"),
            Patient.name.label("patient_name"),
            PatientMessage.triage_category.label("triage_category"),
        )
        .outerjoin(
            PatientMessage,
            MessageDraft.source_message_id == PatientMessage.id,
        )
        .outerjoin(
            Patient,
            MessageDraft.patient_id == Patient.id,
        )
        .where(
            MessageDraft.doctor_id == resolved,
            MessageDraft.status.in_(
                [DraftStatus.generated.value, DraftStatus.edited.value, DraftStatus.sent.value]
                if include_sent else
                [DraftStatus.generated.value, DraftStatus.edited.value]
            ),
        )
        .order_by(MessageDraft.created_at.desc())
        .limit(50)
    )
    rows = (await db.execute(stmt)).all()

    # Collect all cited KB IDs across drafts and bulk-load titles
    all_cited_ids: set[int] = set()
    drafts_cited: list[tuple] = []
    for draft, patient_message, patient_name, triage_category in rows:
        ids = _parse_cited_ids(draft.cited_knowledge_ids)
        all_cited_ids.update(ids)
        drafts_cited.append((draft, patient_message, patient_name, triage_category, ids))

    kb_map: dict[int, str] = {}
    if all_cited_ids:
        from db.models.doctor import DoctorKnowledgeItem
        kb_stmt = (
            select(DoctorKnowledgeItem.id, DoctorKnowledgeItem.title)
            .where(
                DoctorKnowledgeItem.id.in_(all_cited_ids),
                DoctorKnowledgeItem.doctor_id == resolved,
            )
        )
        kb_rows = (await db.execute(kb_stmt)).all()
        kb_map = {row.id: row.title for row in kb_rows}

    result = [
        {
            "id": draft.id,
            "type": "draft",
            "patient_id": draft.patient_id,
            "patient_name": patient_name or "unknown",
            "patient_message": patient_message or "",
            "draft_text": draft.edited_text or draft.draft_text,
            "original_draft_text": draft.draft_text,
            "cited_knowledge_ids": cited_ids,
            "cited_rules": [
                {"id": kid, "title": kb_map.get(kid, f"规则 #{kid}")}
                for kid in cited_ids
            ],
            "confidence": draft.confidence,
            "status": draft.status,
            "ai_disclosure": draft.ai_disclosure,
            "badge": "urgent" if triage_cat == "urgent" else None,
            "triage_category": triage_cat,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
        }
        for draft, patient_message, patient_name, triage_cat, cited_ids in drafts_cited
    ]

    # Also include escalated patient messages that have NO draft
    # (AI couldn't ground reply in doctor's knowledge)
    drafted_msg_ids = {draft.source_message_id for draft, _, _, _, _ in drafts_cited if draft.source_message_id}
    undrafted_stmt = (
        select(PatientMessage, Patient.name.label("patient_name"))
        .outerjoin(Patient, PatientMessage.patient_id == Patient.id)
        .where(
            PatientMessage.doctor_id == resolved,
            PatientMessage.ai_handled == False,  # noqa: E712
            PatientMessage.direction == "inbound",
        )
        .order_by(PatientMessage.created_at.desc())
        .limit(50)
    )
    undrafted_rows = (await db.execute(undrafted_stmt)).all()

    for msg, patient_name in undrafted_rows:
        if msg.id in drafted_msg_ids:
            continue  # already has a draft
        result.append({
            "id": f"msg_{msg.id}",
            "type": "undrafted",
            "patient_id": msg.patient_id,
            "patient_name": patient_name or "unknown",
            "patient_message": msg.content or "",
            "draft_text": None,
            "original_draft_text": None,
            "cited_knowledge_ids": [],
            "cited_rules": [],
            "confidence": None,
            "status": "no_draft",
            "ai_disclosure": None,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "source_message_id": msg.id,
            "triage_category": msg.triage_category,
        })

    # Sort all items by created_at descending
    result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return result


# ── 2. Summary counts ───────────────────────────────────────────────────


@router.get("/api/manage/drafts/summary")
async def drafts_summary(
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return summary counts: pending drafts, AI-drafted, and tasks due soon."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.summary")

    now_utc = datetime.now(timezone.utc)
    two_days_later = now_utc + timedelta(days=2)

    # Pending drafts (generated + edited)
    pending_count: int = (
        await db.execute(
            select(func.count())
            .select_from(MessageDraft)
            .where(
                MessageDraft.doctor_id == resolved,
                MessageDraft.status.in_([
                    DraftStatus.generated.value,
                    DraftStatus.edited.value,
                ]),
            )
        )
    ).scalar_one()

    # AI-drafted (generated only, not yet touched by doctor)
    ai_drafted_count: int = (
        await db.execute(
            select(func.count())
            .select_from(MessageDraft)
            .where(
                MessageDraft.doctor_id == resolved,
                MessageDraft.status == DraftStatus.generated.value,
            )
        )
    ).scalar_one()

    # Undrafted escalated messages (AI couldn't ground reply in KB)
    drafted_msg_ids_stmt = select(MessageDraft.source_message_id).where(
        MessageDraft.doctor_id == resolved,
        MessageDraft.source_message_id.isnot(None),
    )
    drafted_msg_ids = {r[0] for r in (await db.execute(drafted_msg_ids_stmt)).all()}

    all_escalated: int = (
        await db.execute(
            select(func.count())
            .select_from(PatientMessage)
            .where(
                PatientMessage.doctor_id == resolved,
                PatientMessage.ai_handled == False,  # noqa: E712
                PatientMessage.direction == "inbound",
            )
        )
    ).scalar_one()
    undrafted_count = max(0, all_escalated - len(drafted_msg_ids))
    pending_count += undrafted_count

    # Due soon: pending tasks due within 2 days
    due_soon_count: int = (
        await db.execute(
            select(func.count())
            .select_from(DoctorTask)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == TaskStatus.pending,
                DoctorTask.due_at.isnot(None),
                DoctorTask.due_at <= two_days_later,
            )
        )
    ).scalar_one()

    # Pending AI suggestions (review queue badge count)
    review_pending_count: int = (
        await db.execute(
            select(func.count())
            .select_from(AISuggestion)
            .where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.decision == None,  # noqa: E711
            )
        )
    ).scalar_one()

    return {
        "pending": pending_count,
        "ai_drafted": ai_drafted_count,
        "due_soon": due_soon_count,
        "review_pending_count": review_pending_count,
    }


# ── 3. Send draft as-is ─────────────────────────────────────────────────


@router.post("/api/manage/drafts/{draft_id}/send")
async def send_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Send a draft reply to the patient.

    Creates a new PatientMessage (outbound, source=doctor) with the draft text
    plus the AI disclosure label, and marks the draft as sent.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.send")

    # Validate draft exists and is sendable
    draft = await db.get(MessageDraft, draft_id)
    if draft is None or draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft is not in a sendable state")
    reply_text = draft.edited_text or draft.draft_text
    patient_id = int(draft.patient_id)
    disclosure = draft.ai_disclosure

    # Use unified reply logic
    from domain.patient_lifecycle.reply import send_doctor_reply
    msg_id = await send_doctor_reply(
        doctor_id=resolved,
        patient_id=patient_id,
        text=reply_text,
        draft_id=draft_id,
        ai_disclosure=disclosure,
    )

    return {"status": "ok", "message_id": msg_id}


# ── 4. Edit draft before sending ────────────────────────────────────────


@router.put("/api/manage/drafts/{draft_id}/edit")
async def edit_draft(
    draft_id: int,
    body: EditDraftRequest,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Edit a draft's text and optionally trigger the teaching loop.

    Stores the edited text on the draft and sets status to 'edited'.
    If the edit is significant (per ``should_prompt_teaching``), logs the edit
    and returns ``teach_prompt=True`` so the frontend can prompt the doctor
    to save the edit as a knowledge rule.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.edit")

    edited_text = (body.edited_text or "").strip()
    if not edited_text:
        raise HTTPException(status_code=422, detail="edited_text is required")

    draft = await db.get(MessageDraft, draft_id)
    if draft is None or draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft is not editable")

    original_text = draft.draft_text

    # Store edit
    draft.edited_text = edited_text
    draft.status = DraftStatus.edited.value

    # Teaching loop: check if edit is significant
    teach_prompt = False
    edit_id: Optional[int] = None

    if should_prompt_teaching(original_text, edited_text):
        teach_prompt = True
        edit_id = await log_doctor_edit(
            db,
            doctor_id=resolved,
            entity_type="draft_reply",
            entity_id=draft_id,
            original_text=original_text,
            edited_text=edited_text,
        )

    await db.commit()

    log(f"[draft] edited draft {draft_id} for doctor={resolved} teach={teach_prompt}")

    return {
        "status": "ok",
        "teach_prompt": teach_prompt,
        "edit_id": edit_id,
    }


# ── 5. Dismiss draft ────────────────────────────────────────────────────


@router.post("/api/manage/drafts/{draft_id}/dismiss")
async def dismiss_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a draft (doctor chose not to send it)."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.dismiss")

    draft = await db.get(MessageDraft, draft_id)
    if draft is None or draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
        raise HTTPException(status_code=409, detail="Draft cannot be dismissed")

    draft.status = DraftStatus.dismissed.value
    await db.commit()

    log(f"[draft] dismissed draft {draft_id} for doctor={resolved}")

    return {"status": "ok"}


# ── 6. Send confirmation data ───────────────────────────────────────────


@router.post("/api/manage/drafts/{draft_id}/send-confirmation")
async def send_confirmation(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return confirmation data for the send confirmation sheet UI.

    Includes patient context summary, draft text, cited knowledge rules,
    and the AI disclosure label that will be appended.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.confirm")

    # Load draft with patient info
    stmt = (
        select(
            MessageDraft,
            PatientMessage.content.label("patient_message"),
            Patient.name.label("patient_name"),
        )
        .outerjoin(
            PatientMessage,
            MessageDraft.source_message_id == PatientMessage.id,
        )
        .outerjoin(
            Patient,
            MessageDraft.patient_id == Patient.id,
        )
        .where(MessageDraft.id == draft_id)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft, patient_message, patient_name = row
    if draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Load cited knowledge rules if any
    cited_ids = _parse_cited_ids(draft.cited_knowledge_ids)
    cited_rules: list[dict] = []
    if cited_ids:
        from db.models.doctor import DoctorKnowledgeItem
        kb_stmt = (
            select(DoctorKnowledgeItem)
            .where(
                DoctorKnowledgeItem.id.in_(cited_ids),
                DoctorKnowledgeItem.doctor_id == resolved,
            )
        )
        kb_rows = (await db.execute(kb_stmt)).scalars().all()
        cited_rules = [
            {
                "id": kb.id,
                "title": kb.title,
                "text": kb.content[:200] if kb.content else "",
            }
            for kb in kb_rows
        ]

    reply_text = draft.edited_text or draft.draft_text

    return {
        "draft_id": draft.id,
        "patient_name": patient_name or "unknown",
        "patient_message": patient_message or "",
        "draft_text": reply_text,
        "ai_disclosure": draft.ai_disclosure,
        "full_text_preview": f"{reply_text}\n\n{draft.ai_disclosure}",
        "cited_rules": cited_rules,
        "confidence": draft.confidence,
        "status": draft.status,
    }


# ── 7. Save doctor edit as knowledge rule ──────────────────────────────


@router.post("/api/manage/drafts/{draft_id}/save-as-rule")
async def save_edit_as_rule(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Save a significant doctor edit as a knowledge rule (teaching loop).

    Looks up the DoctorEdit record associated with this draft and calls
    ``create_rule_from_edit`` to persist it as a knowledge rule with
    source='teaching' and category='preference'.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.save_rule")

    # Verify draft exists and belongs to this doctor
    draft = await db.get(MessageDraft, draft_id)
    if draft is None or draft.doctor_id != resolved:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Find the DoctorEdit record for this draft
    stmt = (
        select(DoctorEdit)
        .where(
            DoctorEdit.doctor_id == resolved,
            DoctorEdit.entity_type == "draft_reply",
            DoctorEdit.entity_id == draft_id,
        )
        .order_by(DoctorEdit.created_at.desc())
        .limit(1)
    )
    edit = (await db.execute(stmt)).scalar_one_or_none()
    if edit is None:
        raise HTTPException(status_code=404, detail="未找到编辑记录")

    # Create knowledge rule from the edit
    rule = await create_rule_from_edit(
        session=db,
        doctor_id=resolved,
        edit_id=edit.id,
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="未找到编辑记录")

    # Capture before commit — session expiry after commit makes attribute access fail
    rule_id = rule.id
    rule_preview = (rule.content or "")[:100]

    await db.commit()

    log(f"[draft] saved edit {edit.id} as rule {rule_id} for doctor={resolved}")

    return {
        "status": "ok",
        "id": rule_id,
        "text_preview": rule_preview,
        "source": "teaching",
    }
