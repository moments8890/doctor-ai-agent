"""Per-turn runtime orchestrator (ADR 0011 §5).

Pipeline: normalize → dedup → load context → draft guard → conversation model
→ commit engine → apply memory patch → persist context → archive → reply.
"""
from __future__ import annotations

from typing import Optional

from services.runtime.commit_engine import execute_action
from services.runtime.context import (
    archive_turns,
    get_recent_turns,
    load_context,
    save_context,
)
from services.runtime.conversation import call_conversation_model
from services.runtime.dedup import cache_result, get_cached_result, is_duplicate
from services.runtime.draft_guard import check_draft_guard
from messages import M
from services.runtime.models import (
    MEMORY_FIELDS,
    ActionPayload,
    DoctorCtx,
    TurnEnvelope,
    TurnResult,
)
from utils.log import log


def _apply_memory_patch(ctx: DoctorCtx, patch: Optional[dict]) -> None:
    """Apply validated memory_patch to context.memory (ADR 0011 §9)."""
    if not patch:
        return
    for key, value in patch.items():
        if key not in MEMORY_FIELDS:
            log(f"[turn] dropping invalid memory key: {key}")
            continue
        setattr(ctx.memory, key, value)


async def _persist(doctor_id: str, ctx: DoctorCtx, text: Optional[str], reply: str) -> None:
    """Best-effort save of context + archive.  Never raises."""
    try:
        await save_context(ctx)
    except Exception as exc:
        log(f"[turn] save_context FAILED doctor={doctor_id}: {exc}")
    if text:
        try:
            await archive_turns(doctor_id, text, reply)
        except Exception as exc:
            log(f"[turn] archive_turns FAILED doctor={doctor_id}: {exc}")


async def process_turn(
    envelope_or_doctor_id,
    text: Optional[str] = None,
    *,
    message_id: Optional[str] = None,
) -> TurnResult:
    """Process one doctor turn through the ADR 0011 runtime pipeline.

    Accepts either a ``TurnEnvelope`` (new unified API) or the legacy
    positional ``(doctor_id, text, *, message_id)`` signature for backward
    compatibility.  The legacy form will be removed once all callers migrate.
    """
    # ── Normalize to TurnEnvelope ──────────────────────────────────────
    if isinstance(envelope_or_doctor_id, TurnEnvelope):
        envelope = envelope_or_doctor_id
    else:
        # Legacy call: process_turn(doctor_id, text, *, message_id=...)
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

    # ── Validate: need either text or action ───────────────────────────
    if not turn_text and action is None:
        return TurnResult(reply=M.empty_input)

    # ── Dedup ──────────────────────────────────────────────────────────
    if msg_id and is_duplicate(msg_id):
        cached = get_cached_result(msg_id)
        if cached:
            return cached

    try:
        ctx = await load_context(doctor_id)

        # ── Deterministic guard: typed action takes priority ───────────
        if action is not None:
            guard_result = await _handle_action(ctx, action)
            await _persist(doctor_id, ctx, None, guard_result.reply)
            if msg_id:
                cache_result(msg_id, guard_result)
            return guard_result

        # ── Deterministic guard: text-based draft confirm/abandon ──────
        guard_result = await check_draft_guard(ctx, turn_text)
        if guard_result is not None:
            await _persist(doctor_id, ctx, turn_text, guard_result.reply)
            if msg_id:
                cache_result(msg_id, guard_result)
            return guard_result

        # ── Conversation model (LLM) ──────────────────────────────────
        recent_turns = await get_recent_turns(doctor_id)
        model_output = await call_conversation_model(ctx, turn_text, recent_turns)

        # Apply memory_patch BEFORE execute_action so working_note is available
        # for clinical text collection during draft creation (ADR 0011 §9).
        _apply_memory_patch(ctx, model_output.memory_patch)

        result = await execute_action(ctx, model_output, recent_turns, user_input=turn_text)

        await _persist(doctor_id, ctx, turn_text, result.reply)

        if msg_id:
            cache_result(msg_id, result)

        log(f"[turn] done doctor={doctor_id} action={getattr(model_output.action_request, 'type', 'none')}")
        return result
    except Exception as exc:
        log(f"[turn] UNHANDLED ERROR doctor={doctor_id}: {exc}")
        return TurnResult(reply=M.service_unavailable)


async def _handle_action(ctx: DoctorCtx, action: ActionPayload) -> TurnResult:
    """Deterministic handler for typed UI actions (no LLM call)."""
    if action.type == "draft_confirm":
        return await _action_confirm_draft(ctx, action.target_id)
    if action.type == "draft_abandon":
        return await _action_abandon_draft(ctx, action.target_id)
    log(f"[turn] unknown action type: {action.type}")
    return TurnResult(reply=M.service_unavailable)


async def _action_confirm_draft(ctx: DoctorCtx, draft_id: str) -> TurnResult:
    """Confirm a specific draft by ID (button click path)."""
    from db.crud.pending import get_pending_record
    from db.engine import AsyncSessionLocal
    from services.domain.intent_handlers._confirm_pending import save_pending_record

    async with AsyncSessionLocal() as db:
        pending = await get_pending_record(db, draft_id, ctx.doctor_id)

    if pending is None or pending.status != "awaiting":
        ctx.workflow.pending_draft_id = None
        return TurnResult(reply=M.draft_expired)

    result = await save_pending_record(ctx.doctor_id, pending)
    ctx.workflow.pending_draft_id = None

    if result is None:
        return TurnResult(reply=M.draft_save_failed)

    patient_name, record_id = result
    ctx.memory.working_note = None
    log(f"[turn] action confirmed draft={draft_id} record={record_id} doctor={ctx.doctor_id}")
    return TurnResult(
        reply=M.draft_confirmed.format(patient=patient_name),
        record_id=record_id,
    )


async def _action_abandon_draft(ctx: DoctorCtx, draft_id: str) -> TurnResult:
    """Abandon a specific draft by ID (button click path)."""
    from db.crud.pending import abandon_pending_record
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await abandon_pending_record(db, draft_id, ctx.doctor_id)

    ctx.workflow.pending_draft_id = None
    patient = ctx.workflow.patient_name or ""
    log(f"[turn] action abandoned draft={draft_id} doctor={ctx.doctor_id}")
    return TurnResult(reply=M.draft_abandoned.format(patient=patient))
