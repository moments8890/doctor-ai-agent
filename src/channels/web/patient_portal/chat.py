"""
Patient portal chat routes: polling + agent-style triage endpoint.

Provides:
  GET  /chat/messages — poll for new messages (patient/ai/doctor)
  POST /chat          — send a message through AI triage pipeline
"""
from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import _authenticate_patient
from db.engine import AsyncSessionLocal, get_db
from db.models.patient_message import PatientMessage
from db.models.records import FieldEntryDB, MedicalRecordDB
from domain.patient_lifecycle.chat_state import (
    ChatSessionState,
    evaluate_entry,
)
from domain.patient_lifecycle.chat_state_store import load_state, serialize_state
from domain.patient_lifecycle.dedup import (
    EpisodeSignals,
    create_supplement,
    detect_same_episode,
    merge_into_existing,
)
from domain.patient_lifecycle.extraction_confidence import (
    REQUIRED_FIELDS as _CONFIDENCE_REQUIRED_FIELDS,
)
from domain.patient_lifecycle.extraction_confidence import calculate as calc_confidence
from domain.patient_lifecycle.red_flag import detect as red_flag_detect
from domain.patient_lifecycle.retraction import retract_recent_whitelist_replies
from domain.patient_lifecycle.triage import (
    TriageCategory,
    classify,
    handle_escalation,
    handle_informational,
    handle_urgent,
    load_patient_context,
)
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import safe_create_task

logger = logging.getLogger(__name__)

chat_router = APIRouter(tags=["patient-portal"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    text: str = Field(..., max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    triage_category: str
    ai_handled: bool


class ChatMessageOut(BaseModel):
    id: int
    content: str
    source: str  # patient / ai / doctor
    sender_id: Optional[str] = None
    triage_category: Optional[str] = None
    ai_handled: Optional[bool] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_source(msg: PatientMessage) -> str:
    """Return the message source, inferring from direction for old rows."""
    if msg.source:
        return msg.source
    # Pre-migration rows: infer from direction column
    return "patient" if msg.direction == "inbound" else "ai"


def _msg_to_out(msg: PatientMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        content=msg.content,
        source=_infer_source(msg),
        sender_id=msg.sender_id,
        triage_category=msg.triage_category,
        ai_handled=msg.ai_handled,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# Categories that the AI handles directly (no doctor escalation).
# ---------------------------------------------------------------------------

_AI_HANDLED_CATEGORIES = {TriageCategory.informational}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@chat_router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Save patient message and generate a draft reply for doctor review.

    Thin wrapper. Currently always delegates to ``_legacy_triage_dispatch``.
    Section F will add a feature-flag check that routes flag-on doctors to
    the new ``_intake_dispatch`` (state-machine path) instead.
    """
    return await _legacy_triage_dispatch(body, x_patient_token, authorization, db)


async def _legacy_triage_dispatch(
    body: ChatRequest,
    x_patient_token: Optional[str],
    authorization: Optional[str],
    db: AsyncSession,
) -> ChatResponse:
    """Original chat handler — saves inbound, generates draft via background task.

    Kill-switch fallback path: when the PATIENT_CHAT_INTAKE_ENABLED flag is
    off (or for any doctor explicitly opted out), incoming messages route
    here and behave exactly as they did pre-Task-1.7. Behavior verbatim.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    enforce_doctor_rate_limit(
        str(patient.id), scope="patient_portal.chat", max_requests=10,
    )

    doctor_id = patient.doctor_id

    try:
        # Save inbound message
        from db.crud.patient_message import save_patient_message
        saved_msg = await save_patient_message(
            db, patient_id=patient.id, doctor_id=doctor_id,
            content=text, direction="inbound", source="patient",
            ai_handled=False,
        )

        # Load patient context for draft generation
        patient_context = await load_patient_context(patient.id, doctor_id, db)
        context_str = json.dumps(patient_context, ensure_ascii=False) if patient_context else ""

        # Generate draft reply for doctor (fire-and-forget)
        from domain.patient_lifecycle.triage_handlers import _generate_draft_for_escalated
        safe_create_task(
            _generate_draft_for_escalated(
                doctor_id, patient.id, saved_msg.id, text, context_str,
            ),
            name=f"draft-reply-{saved_msg.id}",
        )

        # Update last_activity_at
        try:
            from db.crud.patient import touch_patient_activity
            async with AsyncSessionLocal() as _act_db:
                await touch_patient_activity(_act_db, patient.id)
        except Exception:
            pass

        logger.info("[PatientChat] message saved, draft scheduled | patient_id=%s", patient.id)

    except Exception:
        logger.exception("[PatientChat] failed | patient_id=%s", patient.id)
        from db.crud.patient_message import save_patient_message
        async with AsyncSessionLocal() as fallback_db:
            await save_patient_message(
                fallback_db, patient_id=patient.id, doctor_id=doctor_id,
                content=text, direction="inbound", source="patient",
            )
            await fallback_db.commit()

    safe_create_task(audit(
        doctor_id, "WRITE",
        resource_type="patient_chat", resource_id=str(patient.id),
    ))

    return ChatResponse(
        reply="",
        triage_category="pending",
        ai_handled=False,
    )


# ---------------------------------------------------------------------------
# New intake dispatch (Task 1.7) — feature-flagged path
# ---------------------------------------------------------------------------

# 2-field minimum for v0 confirm-gate threshold. Spec §threshold mentions a
# (duration OR severity) signal too — deferred until we have a richer
# per-turn extractor. See _intake_threshold_met for the contract.
_MIN_FIELDS_FOR_THRESHOLD = ("chief_complaint", "present_illness")

# Window for considering another record as a dedup candidate. Past this
# gap, dedup never fires — see EpisodeSignals.hours_since_last.
_DEDUP_LOOKBACK_HOURS = 24


async def _intake_dispatch(
    body: ChatRequest,
    x_patient_token: Optional[str],
    authorization: Optional[str],
    db: AsyncSession,
) -> ChatResponse:
    """State-machine path. Routes by ChatSessionState.state.

    Replaces _legacy_triage_dispatch when PATIENT_CHAT_INTAKE_ENABLED is on.
    Always-on red-flag pass runs first and short-circuits.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    enforce_doctor_rate_limit(
        str(patient.id), scope="patient_portal.chat", max_requests=10,
    )

    doctor_id = patient.doctor_id
    patient_id = patient.id

    # 1. Load state (and apply idle decay for stale intake/qa_window)
    state = await load_state(db, patient_id)
    state = state.apply_idle_decay(now_iso=datetime.now(timezone.utc).isoformat())

    # 2. Save the patient's message FIRST (snapshot patched after dispatch)
    patient_msg = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content=text, direction="inbound", source="patient",
        ai_handled=False,
        intake_segment_id=state.intake_segment_id,
        is_whitelist_reply=False, retracted=False,
    )
    db.add(patient_msg)
    await db.flush()

    # 3. Always-on red-flag pass (Codex round 2: must run on every turn)
    try:
        red_flag_fired = await red_flag_detect(
            message=text, patient_context={"patient_id": patient_id},
        )
    except Exception:
        logger.exception("[PatientChat:intake] red_flag_detect failed | patient_id=%s", patient_id)
        red_flag_fired = False

    if red_flag_fired:
        if state.intake_segment_id:
            try:
                await retract_recent_whitelist_replies(
                    db, intake_segment_id=state.intake_segment_id,
                )
            except Exception:
                logger.exception("[PatientChat:intake] retract failed | seg=%s", state.intake_segment_id)
        if state.record_id:
            rec = await db.get(MedicalRecordDB, state.record_id)
            if rec:
                rec.red_flag = True
        ai_reply_text = "请立即联系您的医生，或评估是否需要急诊就医。"
        ai_msg = PatientMessage(
            patient_id=patient_id, doctor_id=doctor_id,
            content=ai_reply_text, direction="outbound", source="ai",
            ai_handled=True,
            intake_segment_id=state.intake_segment_id,
            is_whitelist_reply=False, retracted=False,
        )
        db.add(ai_msg)
        # Snapshot stays on patient_msg as-is (state didn't transition)
        patient_msg.chat_state_snapshot = serialize_state(state)
        await db.commit()
        safe_create_task(audit(
            doctor_id, "WRITE",
            resource_type="patient_chat", resource_id=str(patient_id),
        ))
        return ChatResponse(reply=ai_reply_text, triage_category="urgent", ai_handled=True)

    # 4. Triage classify (used by entry rule + qa_window handling)
    try:
        patient_context = await load_patient_context(patient_id, doctor_id, db)
        triage = await classify(message=text, patient_context=patient_context or {}, doctor_id=doctor_id)
    except Exception:
        logger.exception("[PatientChat:intake] classify failed | patient_id=%s", patient_id)
        # Safe fallback: stay in current state, no transitions; degrade to legacy.
        patient_msg.chat_state_snapshot = serialize_state(state)
        await db.commit()
        return ChatResponse(reply="", triage_category="pending", ai_handled=False)

    # 5. State-machine dispatch
    if state.state == "idle":
        decision = evaluate_entry(triage, text)
        if decision.entered:
            seg_id = str(uuid.uuid4())
            rec = MedicalRecordDB(
                patient_id=patient_id, doctor_id=doctor_id,
                status="interview_active", seed_source="chat_detected",
                intake_segment_id=seg_id, red_flag=False,
                record_type="visit",
            )
            db.add(rec)
            await db.flush()
            new_state = ChatSessionState(
                state="intake", record_id=rec.id, intake_segment_id=seg_id,
                last_intake_turn_at_iso=datetime.now(timezone.utc).isoformat(),
            )
            patient_msg.intake_segment_id = seg_id
            patient_msg.chat_state_snapshot = serialize_state(new_state)
            # Best-effort field extraction for this first turn
            await _extract_and_append_fields(db, rec.id, text, seg_id)
            await db.commit()
            safe_create_task(audit(
                doctor_id, "WRITE",
                resource_type="patient_chat", resource_id=str(patient_id),
            ))
            return ChatResponse(reply="", triage_category="symptom_report", ai_handled=False)
        # Not entering intake → legacy idle reply path. Snapshot first so the
        # state transition log is anchored to this message even when the
        # message also has whitelist KB-downgrade replies attached.
        patient_msg.chat_state_snapshot = serialize_state(state)
        await db.commit()
        return await _legacy_triage_dispatch(body, x_patient_token, authorization, db)

    if state.state == "intake":
        # Append fields, refresh last_intake_turn_at_iso
        if state.record_id is not None:
            await _extract_and_append_fields(
                db, state.record_id, text, state.intake_segment_id,
            )
        new_state = dataclasses.replace(
            state,
            last_intake_turn_at_iso=datetime.now(timezone.utc).isoformat(),
        )
        patient_msg.chat_state_snapshot = serialize_state(new_state)

        # Threshold check → maybe insert a confirm/dedup gate marker message.
        if state.record_id is not None and await _intake_threshold_met(db, state.record_id):
            dedup_decision = await _maybe_dedup(db, patient_id, state.record_id)
            await _emit_gate_message(
                db,
                patient_id=patient_id,
                doctor_id=doctor_id,
                draft_record_id=state.record_id,
                intake_segment_id=state.intake_segment_id,
                dedup_decision=dedup_decision,
            )
        await db.commit()
        safe_create_task(audit(
            doctor_id, "WRITE",
            resource_type="patient_chat", resource_id=str(patient_id),
        ))
        return ChatResponse(reply="", triage_category="symptom_report", ai_handled=False)

    if state.state == "qa_window":
        new_state = state.handle_message(triage, text)
        patient_msg.chat_state_snapshot = serialize_state(new_state)
        await db.commit()
        safe_create_task(audit(
            doctor_id, "WRITE",
            resource_type="patient_chat", resource_id=str(patient_id),
        ))
        return ChatResponse(reply="", triage_category=triage.category.value, ai_handled=False)

    # Defensive fallback for unknown states.
    patient_msg.chat_state_snapshot = serialize_state(state)
    await db.commit()
    return ChatResponse(reply="", triage_category="pending", ai_handled=False)


# ---------------------------------------------------------------------------
# Intake helpers
# ---------------------------------------------------------------------------

async def _extract_and_append_fields(
    db: AsyncSession,
    record_id: int,
    text: str,
    segment_id: Optional[str],
) -> None:
    """Best-effort field extraction from a single patient turn.

    v0 minimal heuristic: append the raw turn as ``present_illness`` every
    time, and seed ``chief_complaint`` from the first turn that lands on
    this record. The full medical_general extractor is too heavy to call
    per turn; v1+ can swap in a richer extractor.
    """
    existing_fields = (await db.execute(
        select(FieldEntryDB.field_name).where(FieldEntryDB.record_id == record_id)
    )).scalars().all()
    now = datetime.utcnow()
    if "chief_complaint" not in existing_fields:
        db.add(FieldEntryDB(
            record_id=record_id, field_name="chief_complaint",
            text=text, intake_segment_id=segment_id, created_at=now,
        ))
    db.add(FieldEntryDB(
        record_id=record_id, field_name="present_illness",
        text=text, intake_segment_id=segment_id, created_at=now,
    ))
    await db.flush()


async def _intake_threshold_met(db: AsyncSession, record_id: int) -> bool:
    """Returns True iff the record has chief_complaint AND present_illness.

    The (duration OR severity) signal is deferred — v0 uses a 2-field minimum.
    """
    fields = set((await db.execute(
        select(FieldEntryDB.field_name).where(FieldEntryDB.record_id == record_id)
    )).scalars().all())
    return all(f in fields for f in _MIN_FIELDS_FOR_THRESHOLD)


async def _maybe_dedup(db: AsyncSession, patient_id: int, draft_record_id: int):
    """Look for a same-day candidate from this patient and run dedup.

    Returns a DedupDecision augmented with ``target_record_id`` and
    ``target_reviewed`` attrs (added dynamically), or None when no
    candidate exists or the texts are not similar.

    TODO: episode signals are simplified for v0 — `treatment_event_since_last`
    isn't wired (would query AISuggestion existence between target.created_at
    and now). Add when we ship Phase 1 dedup polish.
    """
    cutoff = datetime.utcnow() - timedelta(hours=_DEDUP_LOOKBACK_HOURS)
    candidates = (await db.execute(
        select(MedicalRecordDB)
        .where(
            MedicalRecordDB.patient_id == patient_id,
            MedicalRecordDB.id != draft_record_id,
            MedicalRecordDB.created_at >= cutoff,
        )
        .order_by(desc(MedicalRecordDB.created_at))
        .limit(1)
    )).scalars().all()
    if not candidates:
        return None
    target = candidates[0]

    # Compare latest chief_complaint texts.
    target_chief = (await db.execute(
        select(FieldEntryDB.text).where(
            FieldEntryDB.record_id == target.id,
            FieldEntryDB.field_name == "chief_complaint",
        ).order_by(desc(FieldEntryDB.created_at)).limit(1)
    )).scalar_one_or_none()
    if not target_chief:
        return None
    draft_chief = (await db.execute(
        select(FieldEntryDB.text).where(
            FieldEntryDB.record_id == draft_record_id,
            FieldEntryDB.field_name == "chief_complaint",
        ).order_by(desc(FieldEntryDB.created_at)).limit(1)
    )).scalar_one_or_none()
    if not draft_chief:
        return None

    hours_since = (datetime.utcnow() - target.created_at).total_seconds() / 3600
    signals = EpisodeSignals(
        hours_since_last=hours_since,
        treatment_event_since_last=False,  # TODO v1: query AISuggestion since target.created_at
        status_change_since_last=(target.status != "interview_active"),
    )
    decision = await detect_same_episode(draft_chief, target_chief, signals)
    if not decision.same_episode:
        return None
    # Augment with target metadata (callers need both id + reviewed-state)
    decision.target_record_id = target.id  # type: ignore[attr-defined]
    decision.target_reviewed = target.status != "interview_active"  # type: ignore[attr-defined]
    return decision


async def _emit_gate_message(
    db: AsyncSession,
    *,
    patient_id: int,
    doctor_id: str,
    draft_record_id: int,
    intake_segment_id: Optional[str],
    dedup_decision,
) -> None:
    """Insert a system message that the patient UI renders as a gate prompt.

    Three flavors:
      - dedup ``auto_merge``    → confirm_gate (continuity=True, target id present)
      - dedup ``patient_prompt``→ dedup_prompt (asks patient merge vs new)
      - no dedup                → confirm_gate (continuity=False)
    """
    if dedup_decision is not None and dedup_decision.band == "auto_merge":
        payload = {
            "kind": "confirm_gate",
            "draft_id": draft_record_id,
            "continuity": True,
            "merge_target_record_id": getattr(dedup_decision, "target_record_id", None),
        }
    elif dedup_decision is not None and dedup_decision.band == "patient_prompt":
        payload = {
            "kind": "dedup_prompt",
            "draft_id": draft_record_id,
            "target_record_id": getattr(dedup_decision, "target_record_id", None),
            "target_reviewed": bool(getattr(dedup_decision, "target_reviewed", False)),
        }
    else:
        payload = {
            "kind": "confirm_gate",
            "draft_id": draft_record_id,
            "continuity": False,
        }
    db.add(PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content=json.dumps(payload, ensure_ascii=False),
        direction="outbound", source="system",
        ai_handled=True,
        intake_segment_id=intake_segment_id,
        is_whitelist_reply=False, retracted=False,
    ))
    await db.flush()


@chat_router.get("/chat/messages")
async def get_chat_messages(
    since: Optional[int] = Query(default=None, description="Last message ID for polling"),
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Poll for chat messages (patient/ai/doctor).

    If *since* is provided, only messages with ``id > since`` are returned
    (long-polling pattern).  Otherwise returns the full conversation.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)

    stmt = (
        select(PatientMessage)
        .where(
            PatientMessage.patient_id == patient.id,
            PatientMessage.doctor_id == patient.doctor_id,
        )
    )
    if since is not None:
        stmt = stmt.where(PatientMessage.id > since)
    # Exclude AI drafts awaiting doctor review (source=ai + ai_handled=False)
    from sqlalchemy import or_, and_
    stmt = stmt.where(
        or_(
            PatientMessage.source != "ai",
            and_(PatientMessage.source == "ai", PatientMessage.ai_handled == True),
        )
    )
    stmt = stmt.order_by(PatientMessage.created_at.asc()).limit(200)

    result = await db.execute(stmt)
    messages = result.scalars().all()

    safe_create_task(audit(
        "patient", "READ",
        resource_type="chat_messages", resource_id=str(patient.id),
    ))
    return [_msg_to_out(m) for m in messages]


# ---------------------------------------------------------------------------
# Confirm-gate / dedup-decision endpoints (Task 1.7 Section E)
# ---------------------------------------------------------------------------


class ConfirmDraftRequest(BaseModel):
    draft_id: int
    action: str  # "confirm" | "continue"


class DedupDecisionRequest(BaseModel):
    draft_id: int
    action: str  # "merge" | "new" | "neither"


@chat_router.post("/chat/confirm_draft")
async def confirm_draft(
    body: ConfirmDraftRequest,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Patient response to the confirm_gate system message.

    - ``confirm``  → promote draft to pending_review, compute extraction_confidence,
      reset session state to idle.
    - ``continue`` → no server-side change; the draft stays in interview_active.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    rec = await db.get(MedicalRecordDB, body.draft_id)
    if rec is None or rec.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Draft not found")

    if body.action == "confirm":
        rec.status = "pending_review"
        rec.patient_confirmed_at = datetime.utcnow()
        fields_dict = await _build_fields_dict(db, rec.id)
        rec.extraction_confidence = calc_confidence(fields_dict)
        # Reset state to idle, anchored on a system marker message.
        marker = PatientMessage(
            patient_id=patient.id, doctor_id=rec.doctor_id,
            content="confirm",
            direction="outbound", source="system",
            ai_handled=True,
            chat_state_snapshot=serialize_state(ChatSessionState()),
        )
        db.add(marker)
        await db.commit()
        return {
            "status": "promoted",
            "record_id": rec.id,
            "extraction_confidence": rec.extraction_confidence,
        }
    if body.action == "continue":
        # Draft stays in interview_active. State is already intake.
        return {"status": "continuing"}
    raise HTTPException(status_code=400, detail="invalid action")


@chat_router.post("/chat/dedup_decision")
async def dedup_decision(
    body: DedupDecisionRequest,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Patient response to the dedup_prompt system message.

    Three actions:
      - ``merge``   → merge into target (append-only for active drafts; create
        a supplement for doctor-reviewed targets). Cancel the draft.
      - ``new``     → keep the draft as a new record, mark dedup_skipped_by_patient.
      - ``neither`` → cancel the draft.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    draft = await db.get(MedicalRecordDB, body.draft_id)
    if draft is None or draft.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Draft not found")

    target_record_id, target_reviewed = await _latest_dedup_target(
        db, patient.id, body.draft_id,
    )
    if target_record_id is None:
        raise HTTPException(status_code=409, detail="no pending dedup decision")

    if body.action == "merge":
        new_fields = await _build_fields_dict(db, draft.id)
        if target_reviewed:
            await create_supplement(
                db, target_record_id=target_record_id,
                new_fields=new_fields, intake_segment_id=draft.intake_segment_id,
            )
            draft.status = "diagnosis_failed"
            draft.cancellation_reason = "merged_into_existing"
        else:
            await merge_into_existing(
                db, target_record_id=target_record_id,
                new_fields=new_fields, intake_segment_id=draft.intake_segment_id,
            )
            target = await db.get(MedicalRecordDB, target_record_id)
            if target is not None:
                target.status = "pending_review"
                target.patient_confirmed_at = datetime.utcnow()
            draft.status = "diagnosis_failed"
            draft.cancellation_reason = "merged_into_existing"
        marker = PatientMessage(
            patient_id=patient.id, doctor_id=draft.doctor_id,
            content="merge",
            direction="outbound", source="system",
            ai_handled=True,
            chat_state_snapshot=serialize_state(ChatSessionState()),
        )
        db.add(marker)
        await db.commit()
        return {"status": "merged"}

    if body.action == "new":
        draft.dedup_skipped_by_patient = True
        draft.status = "pending_review"
        draft.patient_confirmed_at = datetime.utcnow()
        fields_dict = await _build_fields_dict(db, draft.id)
        draft.extraction_confidence = calc_confidence(fields_dict)
        marker = PatientMessage(
            patient_id=patient.id, doctor_id=draft.doctor_id,
            content="new",
            direction="outbound", source="system",
            ai_handled=True,
            chat_state_snapshot=serialize_state(ChatSessionState()),
        )
        db.add(marker)
        await db.commit()
        return {"status": "new", "record_id": draft.id}

    if body.action == "neither":
        draft.status = "diagnosis_failed"
        draft.cancellation_reason = "patient_cancel"
        marker = PatientMessage(
            patient_id=patient.id, doctor_id=draft.doctor_id,
            content="cancel",
            direction="outbound", source="system",
            ai_handled=True,
            chat_state_snapshot=serialize_state(ChatSessionState()),
        )
        db.add(marker)
        await db.commit()
        return {"status": "cancelled"}

    raise HTTPException(status_code=400, detail="invalid action")


async def _build_fields_dict(db: AsyncSession, record_id: int) -> dict:
    """Reduce FieldEntryDB rows to {field_name: latest_text} for the merge/confidence calls."""
    rows = (await db.execute(
        select(FieldEntryDB)
        .where(FieldEntryDB.record_id == record_id)
        .order_by(FieldEntryDB.created_at)
    )).scalars().all()
    out: dict = {}
    for r in rows:
        out[r.field_name] = r.text  # latest wins (rows are time-ordered)
    return out


async def _latest_dedup_target(
    db: AsyncSession, patient_id: int, draft_id: int,
) -> tuple[Optional[int], bool]:
    """Find the most recent dedup_prompt system message for this draft.

    Returns (target_record_id, target_reviewed) or (None, False) if no
    pending dedup prompt exists for the given draft.
    """
    rows = (await db.execute(
        select(PatientMessage)
        .where(
            PatientMessage.patient_id == patient_id,
            PatientMessage.source == "system",
        )
        .order_by(desc(PatientMessage.created_at))
        .limit(20)
    )).scalars().all()
    for m in rows:
        try:
            payload = json.loads(m.content)
        except Exception:
            continue
        if payload.get("kind") == "dedup_prompt" and payload.get("draft_id") == draft_id:
            return payload.get("target_record_id"), bool(payload.get("target_reviewed"))
    return None, False


@chat_router.post("/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as read by setting read_at = utcnow().

    Only messages belonging to the authenticated patient can be marked.
    Idempotent: if already read, returns ok without updating.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)

    # Verify the message belongs to this patient
    msg = (
        await db.execute(
            select(PatientMessage).where(
                PatientMessage.id == message_id,
                PatientMessage.patient_id == patient.id,
            )
        )
    ).scalar_one_or_none()

    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.read_at is None:
        msg.read_at = datetime.now(timezone.utc)
        await db.commit()

    return {"status": "ok"}
