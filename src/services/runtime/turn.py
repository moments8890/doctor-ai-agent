"""Per-turn runtime orchestrator: Understand → Execute → Compose (ADR 0012).

Pipeline: normalise → dedup → load context → deterministic handler
→ understand → resolve → dispatch (read_engine | commit_engine) → compose
→ persist context → archive → reply.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from messages import M
from services.runtime.context import (
    archive_turns,
    get_recent_turns,
    load_context,
    save_context,
)
from services.runtime.dedup import cache_result, get_cached_result, is_duplicate
from services.runtime.models import (
    ActionPayload,
    DoctorCtx,
    TurnEnvelope,
    TurnResult,
)
from services.runtime.types import (
    READ_ACTIONS,
    RESPONSE_MODE_TABLE,
    WRITE_ACTIONS,
    ActionType,
    Clarification,
    ResolvedAction,
    ResponseMode,
    UnderstandError,
)
from utils.log import log


# ── Confirm / abandon patterns (deterministic handler) ──────────────────────

_LANG = os.environ.get("RUNTIME_LANG", "zh")

if _LANG == "en":
    CONFIRM_RE = re.compile(
        r"^(ok|yes|save|confirm|sure|do it)\s*[.?!]*$",
        re.IGNORECASE,
    )
    ABANDON_RE = re.compile(
        r"^(no|cancel|abandon|discard|never\s*mind)\s*[.?!]*$",
        re.IGNORECASE,
    )
    _GREETING_RE = re.compile(
        r"^(hi|hello|hey|good\s+(morning|afternoon|evening))\s*[.!?]*$",
        re.IGNORECASE,
    )
    _HELP_RE = re.compile(r"^(help|menu|commands?|\?)\s*[.!?]*$", re.IGNORECASE)
else:
    CONFIRM_RE = re.compile(
        r"^(确认|确定|保存|是的?|对|好的?|ok|yes|save|confirm)\s*[。？！.?!]*$",
        re.IGNORECASE,
    )
    ABANDON_RE = re.compile(
        r"^(取消|放弃|不要|不保存|不了|算了|cancel|abandon|discard|no)\s*[。？！.?!]*$",
        re.IGNORECASE,
    )
    _GREETING_RE = re.compile(
        r"^(你好|您好|hi|hello|hey|嗨|早上好|下午好|晚上好)\s*[。！.!?]*$",
        re.IGNORECASE,
    )
    _HELP_RE = re.compile(
        r"^(帮助|help|功能|菜单|\?|怎么用|使用说明)\s*[。！.!?]*$",
        re.IGNORECASE,
    )


# ── Public API ──────────────────────────────────────────────────────────────


async def process_turn(
    envelope_or_doctor_id,
    text: Optional[str] = None,
    *,
    message_id: Optional[str] = None,
) -> TurnResult:
    """Process one doctor turn through the ADR 0012 UEC pipeline.

    Accepts either a ``TurnEnvelope`` (unified API) or the legacy
    positional ``(doctor_id, text, *, message_id)`` signature for backward
    compatibility.
    """
    # ── Normalise to TurnEnvelope ─────────────────────────────────────
    if isinstance(envelope_or_doctor_id, TurnEnvelope):
        envelope = envelope_or_doctor_id
    else:
        envelope = TurnEnvelope(
            doctor_id=envelope_or_doctor_id,
            text=text,
            channel="unknown",
            modality="text",
            source_turn_key=message_id,
        )

    doctor_id = envelope.doctor_id
    turn_text = (envelope.text or "").strip() if envelope.text else ""
    msg_id = envelope.source_turn_key
    action = envelope.action

    # ── Validate ──────────────────────────────────────────────────────
    if not turn_text and action is None:
        return TurnResult(reply=M.empty_input)

    # ── Dedup ─────────────────────────────────────────────────────────
    if msg_id and is_duplicate(msg_id):
        cached = get_cached_result(msg_id)
        if cached:
            return cached

    try:
        ctx = await load_context(doctor_id)

        # ── Deterministic handler (ADR 0012 §7) ──────────────────────

        # 1. Typed UI actions (button clicks)
        if action is not None:
            result = await _handle_action(ctx, action)
            # Archive action for audit trail (ADR 0012 §13)
            action_text = f"[{action.type}:{action.target_id}]"
            await _persist(doctor_id, ctx, action_text, result.reply,
                           patient_id=ctx.workflow.patient_id)
            if msg_id:
                cache_result(msg_id, result)
            return result

        # 2. Pending draft confirm/cancel (regex)
        if ctx.workflow.pending_draft_id:
            det_result = await _handle_pending_text(ctx, turn_text)
            if det_result is not None:
                await _persist(doctor_id, ctx, turn_text, det_result.reply,
                               patient_id=ctx.workflow.patient_id)
                if msg_id:
                    cache_result(msg_id, det_result)
                return det_result

        # 3. Greeting/help fast path (0 LLM calls)
        if _GREETING_RE.match(turn_text):
            result = TurnResult(reply=M.greeting)
            await _persist(doctor_id, ctx, turn_text, result.reply)
            if msg_id:
                cache_result(msg_id, result)
            return result
        if _HELP_RE.match(turn_text):
            result = TurnResult(reply=M.help)
            await _persist(doctor_id, ctx, turn_text, result.reply)
            if msg_id:
                cache_result(msg_id, result)
            return result

        # ── UEC Pipeline ──────────────────────────────────────────────
        result = await _run_pipeline(ctx, turn_text, doctor_id)

        await _persist(doctor_id, ctx, turn_text, result.reply,
                       patient_id=ctx.workflow.patient_id)
        if msg_id:
            cache_result(msg_id, result)

        return result

    except Exception as exc:
        log.error("[turn] UNHANDLED ERROR doctor=%s: %s", doctor_id, exc, exc_info=True)
        return TurnResult(reply=M.service_unavailable)


# ── UEC Pipeline ────────────────────────────────────────────────────────────


async def _run_pipeline(ctx: DoctorCtx, text: str, doctor_id: str) -> TurnResult:
    """Understand → Resolve → Dispatch → Compose."""
    from services.runtime.compose import (
        compose_clarification,
        compose_llm,
        compose_template,
    )
    from services.runtime.understand import understand

    recent_turns = await get_recent_turns(doctor_id)

    # ── Understand ────────────────────────────────────────────────────
    try:
        ur = await understand(text, recent_turns, ctx)
    except UnderstandError as e:
        log.warning("[turn] understand failed doctor=%s: %s", doctor_id, e)
        return TurnResult(reply=M.understand_error)

    # Clarification from understand → skip execute
    if ur.clarification:
        reply = compose_clarification(ur.clarification)
        return TurnResult(reply=reply)

    # action_type == none → return chat_reply directly
    if ur.action_type == ActionType.none:
        return TurnResult(reply=ur.chat_reply or M.default_reply)

    # ── Resolve ───────────────────────────────────────────────────────
    from services.runtime.resolve import resolve

    resolve_result = await resolve(ur, ctx)

    # Clarification from resolve → skip engine
    if isinstance(resolve_result, Clarification):
        reply = compose_clarification(resolve_result)
        return TurnResult(reply=reply)

    resolved: ResolvedAction = resolve_result

    # ── Dispatch to engine ────────────────────────────────────────────
    response_mode = RESPONSE_MODE_TABLE.get(resolved.action_type, ResponseMode.template)

    if resolved.action_type in READ_ACTIONS:
        from services.runtime.read_engine import read
        read_result = await read(resolved, doctor_id)

        if response_mode == ResponseMode.llm_compose:
            pending_patient = ctx.workflow.patient_name if ctx.workflow.pending_draft_id else None
            reply = await compose_llm(
                read_result,
                text,
                patient_name=resolved.patient_name,
                pending_patient_name=pending_patient,
            )
        else:
            reply = compose_template(read_result, resolved.action_type, resolved.patient_name)

        # Build view_payload for structured channel rendering
        view_payload = None
        if read_result.data:
            if resolved.action_type == ActionType.query_records:
                view_payload = {"type": "records_list", "data": read_result.data}
            elif resolved.action_type == ActionType.list_patients:
                view_payload = {"type": "patients_list", "data": read_result.data}

        return TurnResult(reply=reply, view_payload=view_payload)

    elif resolved.action_type in WRITE_ACTIONS:
        from services.runtime.commit_engine import commit
        commit_result = await commit(resolved, ctx, recent_turns, text)

        # Update context for writes that switch patients
        if not resolved.scoped_only and resolved.patient_id:
            ctx.workflow.patient_id = resolved.patient_id
            ctx.workflow.patient_name = resolved.patient_name

        reply = compose_template(commit_result, resolved.action_type, resolved.patient_name)

        # Build TurnResult with pending info if applicable
        tr = TurnResult(reply=reply)
        if commit_result.pending_id:
            tr.pending_id = commit_result.pending_id
            tr.pending_patient_name = resolved.patient_name
        if commit_result.data and isinstance(commit_result.data, dict):
            if "task_id" in commit_result.data:
                tr.view_payload = {"type": "task_created", "data": commit_result.data}

        return tr

    return TurnResult(reply=M.default_reply)


# ── Deterministic handlers ──────────────────────────────────────────────────


async def _handle_action(ctx: DoctorCtx, action: ActionPayload) -> TurnResult:
    """Deterministic handler for typed UI actions (no LLM call)."""
    if action.type == "draft_confirm":
        return await _confirm_draft(ctx, action.target_id)
    if action.type == "draft_abandon":
        return await _abandon_draft(ctx, action.target_id)
    log.warning("[turn] unknown action type: %s", action.type)
    return TurnResult(reply=M.service_unavailable)


async def _handle_pending_text(ctx: DoctorCtx, text: str) -> Optional[TurnResult]:
    """Handle confirm/cancel text while a pending draft exists.

    Returns TurnResult if handled, None to pass through to pipeline.
    Under ADR 0012 §7, all non-confirm/cancel input flows through the pipeline.
    """
    draft_id = ctx.workflow.pending_draft_id
    if not draft_id:
        return None

    if CONFIRM_RE.match(text):
        return await _confirm_draft(ctx, draft_id)

    if ABANDON_RE.match(text):
        return await _abandon_draft(ctx, draft_id)

    # Everything else passes through to the pipeline.
    # Resolve owns the blocking logic for writes during pending draft.
    return None


async def _confirm_draft(ctx: DoctorCtx, draft_id: str) -> TurnResult:
    """Confirm pending draft → save to medical_records."""
    from db.crud.pending import get_pending_record
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        pending = await get_pending_record(db, draft_id, ctx.doctor_id)

    # TTL expiry race (ADR 0012 §15)
    if pending is None or pending.status != "awaiting":
        ctx.workflow.pending_draft_id = None
        return TurnResult(reply=M.draft_ttl_expired)

    from services.domain.intent_handlers._confirm_pending import save_pending_record

    result = await save_pending_record(ctx.doctor_id, pending)
    ctx.workflow.pending_draft_id = None

    if result is None:
        return TurnResult(reply=M.draft_save_failed)

    patient_name, record_id = result
    log.info("[turn] confirmed draft=%s record=%s doctor=%s", draft_id, record_id, ctx.doctor_id)
    return TurnResult(
        reply=M.draft_confirmed.format(patient=patient_name),
        record_id=record_id,
    )


async def _abandon_draft(ctx: DoctorCtx, draft_id: str) -> TurnResult:
    """Abandon pending draft."""
    from db.crud.pending import abandon_pending_record
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await abandon_pending_record(db, draft_id, ctx.doctor_id)

    ctx.workflow.pending_draft_id = None
    patient = ctx.workflow.patient_name or ""
    log.info("[turn] abandoned draft=%s doctor=%s", draft_id, ctx.doctor_id)
    return TurnResult(reply=M.draft_abandoned.format(patient=patient))


# ── Persistence ─────────────────────────────────────────────────────────────


async def _persist(
    doctor_id: str,
    ctx: DoctorCtx,
    text: Optional[str],
    reply: str,
    patient_id: Optional[int] = None,
) -> None:
    """Best-effort save of context + archive.  Never raises.

    Archive failure is a patient-safety concern: lost turns mean
    create_draft may produce incomplete medical records.  We log at
    ERROR with full traceback so monitoring can alert.
    """
    try:
        await save_context(ctx)
    except Exception as exc:
        log.error("[turn] save_context FAILED doctor=%s: %s", doctor_id, exc, exc_info=True)
    if text:
        try:
            await archive_turns(doctor_id, text, reply, patient_id=patient_id)
        except Exception as exc:
            log.error(
                "[turn] archive_turns FAILED doctor=%s — clinical content may be lost: %s",
                doctor_id, exc, exc_info=True,
            )
            # One retry — archive is critical for draft quality
            try:
                await archive_turns(doctor_id, text, reply, patient_id=patient_id)
                log.info("[turn] archive_turns retry succeeded doctor=%s", doctor_id)
            except Exception:
                log.error("[turn] archive_turns retry also FAILED doctor=%s", doctor_id)
