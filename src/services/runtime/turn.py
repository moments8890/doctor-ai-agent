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
    ActionIntent,
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

        # 2. Greeting/help fast path (0 LLM calls)
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
        log(f"[turn] UNHANDLED ERROR doctor={doctor_id}: {exc}", level="error")
        return TurnResult(reply=M.service_unavailable)


# ── UEC Pipeline ────────────────────────────────────────────────────────────


async def _run_pipeline(ctx: DoctorCtx, text: str, doctor_id: str) -> TurnResult:
    """Understand → [Resolve → Dispatch → Compose]* (multi-action loop)."""
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
        log(f"[turn] understand failed doctor={doctor_id}: {e}", level="warning")
        return TurnResult(reply=M.understand_error)

    # Top-level clarification → skip execute
    if ur.clarification:
        reply = compose_clarification(ur.clarification)
        return TurnResult(reply=reply)

    # Single none action → return chat_reply directly
    if len(ur.actions) == 1 and ur.actions[0].action_type == ActionType.none:
        return TurnResult(reply=ur.chat_reply or M.default_reply)

    # ── Multi-action loop ─────────────────────────────────────────────
    from services.runtime.resolve import resolve

    replies: list = []
    view_payload = None
    switch_notifications: list = []
    record_id = None

    for action_intent in ur.actions:
        # Resolve
        resolve_result = await resolve(action_intent, ctx)

        if isinstance(resolve_result, Clarification):
            replies.append(compose_clarification(resolve_result))
            break

        resolved: ResolvedAction = resolve_result

        # Dispatch to engine
        prev_patient = ctx.workflow.patient_name
        response_mode = RESPONSE_MODE_TABLE.get(resolved.action_type, ResponseMode.template)

        if resolved.action_type in READ_ACTIONS:
            from services.runtime.read_engine import read
            read_result = await read(resolved, doctor_id)

            if response_mode == ResponseMode.llm_compose:
                reply = await compose_llm(
                    read_result,
                    text,
                    patient_name=resolved.patient_name,
                )
            else:
                reply = compose_template(read_result, resolved.action_type, resolved.patient_name)

            if read_result.data:
                if resolved.action_type == ActionType.query_records:
                    view_payload = {"type": "records_list", "data": read_result.data}
                elif resolved.action_type == ActionType.list_patients:
                    view_payload = {"type": "patients_list", "data": read_result.data}

        elif resolved.action_type in WRITE_ACTIONS:
            from services.runtime.commit_engine import commit
            commit_result = await commit(resolved, ctx, recent_turns, text)
            reply = compose_template(commit_result, resolved.action_type, resolved.patient_name)

            if commit_result.data and isinstance(commit_result.data, dict):
                if "record_id" in commit_result.data:
                    record_id = commit_result.data["record_id"]
                if "task_id" in commit_result.data:
                    view_payload = {"type": "task_created", "data": commit_result.data}
        else:
            reply = M.default_reply

        # Track patient switches
        if resolved.patient_id and not resolved.scoped_only:
            if (prev_patient
                    and resolved.patient_name
                    and prev_patient != resolved.patient_name):
                switch_notifications.append(
                    f"已从【{prev_patient}】切换到【{resolved.patient_name}】"
                )
            ctx.workflow.patient_id = resolved.patient_id
            ctx.workflow.patient_name = resolved.patient_name

        replies.append(reply)

    return TurnResult(
        reply="\n\n".join(replies),
        view_payload=view_payload,
        switch_notification="\n".join(switch_notifications) if switch_notifications else None,
        record_id=record_id,
    )


# ── Deterministic handlers ──────────────────────────────────────────────────


async def _handle_action(ctx: DoctorCtx, action: ActionPayload) -> TurnResult:
    """Deterministic handler for typed UI actions (no LLM call).

    draft_confirm / draft_abandon retained for migration; the multi-action
    pipeline no longer uses pending drafts so these are no-ops.
    """
    if action.type in ("draft_confirm", "draft_abandon"):
        log(f"[turn] legacy action {action.type} — no-op (draft flow removed)")
        return TurnResult(reply=M.default_reply)
    log(f"[turn] unknown action type: {action.type}", level="warning")
    return TurnResult(reply=M.service_unavailable)


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
        log(f"[turn] save_context FAILED doctor={doctor_id}: {exc}", level="error")
    if text:
        try:
            await archive_turns(doctor_id, text, reply, patient_id=patient_id)
        except Exception as exc:
            log(
                f"[turn] archive_turns FAILED doctor={doctor_id} — clinical content may be lost: {exc}",
                level="error",
            )
            # One retry — archive is critical for draft quality
            try:
                await archive_turns(doctor_id, text, reply, patient_id=patient_id)
                log(f"[turn] archive_turns retry succeeded doctor={doctor_id}")
            except Exception:
                log(f"[turn] archive_turns retry also FAILED doctor={doctor_id}", level="error")
