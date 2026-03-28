"""Draft reply management endpoints: list, send, edit, dismiss, and confirmation.

Provides the API surface for the doctor draft review workflow where AI-generated
follow-up reply drafts are reviewed, optionally edited, and sent to patients.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.crud.patient_message import save_patient_message
from db.engine import AsyncSessionLocal
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.tasks import DoctorTask, TaskStatus
from domain.knowledge.teaching import log_doctor_edit, should_prompt_teaching
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
    authorization: Optional[str] = Header(default=None),
):
    """List pending drafts (generated or edited) for a doctor.

    Joins with PatientMessage to include the original patient message text,
    and with Patient to include the patient name.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts")

    async with AsyncSessionLocal() as db:
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
            .where(
                MessageDraft.doctor_id == resolved,
                MessageDraft.status.in_([
                    DraftStatus.generated.value,
                    DraftStatus.edited.value,
                ]),
            )
            .order_by(MessageDraft.created_at.desc())
            .limit(50)
        )
        rows = (await db.execute(stmt)).all()

    return [
        {
            "id": draft.id,
            "patient_id": draft.patient_id,
            "patient_name": patient_name or "unknown",
            "patient_message": patient_message or "",
            "draft_text": draft.edited_text or draft.draft_text,
            "original_draft_text": draft.draft_text,
            "cited_knowledge_ids": _parse_cited_ids(draft.cited_knowledge_ids),
            "confidence": draft.confidence,
            "status": draft.status,
            "ai_disclosure": draft.ai_disclosure,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
        }
        for draft, patient_message, patient_name in rows
    ]


# ── 2. Summary counts ───────────────────────────────────────────────────


@router.get("/api/manage/drafts/summary")
async def drafts_summary(
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Return summary counts: pending drafts, AI-drafted, and tasks due soon."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.summary")

    now_utc = datetime.now(timezone.utc)
    two_days_later = now_utc + timedelta(days=2)

    async with AsyncSessionLocal() as db:
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

    return {
        "pending": pending_count,
        "ai_drafted": ai_drafted_count,
        "due_soon": due_soon_count,
    }


# ── 3. Send draft as-is ─────────────────────────────────────────────────


@router.post("/api/manage/drafts/{draft_id}/send")
async def send_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Send a draft reply to the patient.

    Creates a new PatientMessage (outbound, source=doctor) with the draft text
    plus the AI disclosure label, and marks the draft as sent.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.send")

    async with AsyncSessionLocal() as db:
        draft = await db.get(MessageDraft, draft_id)
        if draft is None or draft.doctor_id != resolved:
            raise HTTPException(status_code=404, detail="Draft not found")
        if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
            raise HTTPException(status_code=409, detail="Draft is not in a sendable state")

        # Use edited_text if available, otherwise original draft_text
        reply_text = draft.edited_text or draft.draft_text

        # Append AI disclosure label
        full_text = f"{reply_text}\n\n{draft.ai_disclosure}"

        # Create outbound patient message
        msg = await save_patient_message(
            db,
            patient_id=int(draft.patient_id),
            doctor_id=resolved,
            content=full_text,
            direction="outbound",
            source="doctor",
            sender_id=resolved,
        )

        # Mark draft as sent
        draft.status = DraftStatus.sent.value
        await db.commit()

        log(f"[draft] sent draft {draft_id} as message {msg.id} for doctor={resolved}")

    return {"status": "ok", "message_id": msg.id}


# ── 4. Edit draft before sending ────────────────────────────────────────


@router.put("/api/manage/drafts/{draft_id}/edit")
async def edit_draft(
    draft_id: int,
    body: EditDraftRequest,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
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

    async with AsyncSessionLocal() as db:
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
):
    """Dismiss a draft (doctor chose not to send it)."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.dismiss")

    async with AsyncSessionLocal() as db:
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
):
    """Return confirmation data for the send confirmation sheet UI.

    Includes patient context summary, draft text, cited knowledge rules,
    and the AI disclosure label that will be appended.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.drafts.confirm")

    async with AsyncSessionLocal() as db:
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
                    "text": kb.text[:200] if kb.text else "",
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
