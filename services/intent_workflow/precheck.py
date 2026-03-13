"""Shared stateful precheck pipeline — deterministic layer before LLM routing.

Checks authoritative session state (pending record, pending create, CVD scale,
blocked write) before running the 5-layer intent workflow.  All three channels
(Web, WeChat, Voice) call ``run_stateful_prechecks()`` so the priority order
and cancel/continuation logic is defined once.

This is NOT a semantic rule engine — it handles exact workflow-state transitions
only (ADR 0007).
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import Optional

from services.domain.name_utils import (
    is_blocked_write_cancel,
    name_only_text,
    name_with_supplement,
)
from services.session import (
    clear_blocked_write_context,
    get_blocked_write_context,
)
from utils.log import log


# ── Low-level blocked-write helpers (kept for backward compat) ────────────


@dataclass
class BlockedWriteContinuation:
    """Result of a successful blocked-write precheck resolution."""

    patient_name: str
    clinical_text: str         # original clinical content from the blocked turn
    original_text: str         # raw input from the blocked turn
    supplement: Optional[str]  # additional text appended in the continuation turn


def precheck_blocked_write(
    doctor_id: str,
    text: str,
) -> Optional[BlockedWriteContinuation]:
    """Check if the current message continues a blocked write.

    Returns:
        BlockedWriteContinuation if the message is a name reply to a
        previously blocked add_record.  Returns None otherwise (fall
        through to normal routing).

    Side effects:
        - Clears blocked write context on cancel.
        - Clears blocked write context on successful resolution.
        - Clears stale/unrelated messages (non-name, non-cancel).
    """
    ctx = get_blocked_write_context(doctor_id)
    if ctx is None:
        return None

    stripped = text.strip()

    # Cancel command
    if is_blocked_write_cancel(stripped):
        clear_blocked_write_context(doctor_id)
        log(f"[precheck] blocked write cancelled doctor={doctor_id}")
        return None  # caller checks for cancel separately

    # Bare name: "张三"
    bare_name = name_only_text(stripped)
    if bare_name:
        clear_blocked_write_context(doctor_id)
        log(
            f"[precheck] blocked write resumed with bare name={bare_name} "
            f"doctor={doctor_id}"
        )
        return BlockedWriteContinuation(
            patient_name=bare_name,
            clinical_text=ctx.clinical_text,
            original_text=ctx.original_text,
            supplement=None,
        )

    # Name + supplement: "张三，还有头痛三天"
    ns = name_with_supplement(stripped)
    if ns:
        name, supplement = ns
        # Merge supplement into clinical text
        merged_text = f"{ctx.clinical_text}，{supplement}" if ctx.clinical_text else supplement
        clear_blocked_write_context(doctor_id)
        log(
            f"[precheck] blocked write resumed with name={name} "
            f"supplement={supplement[:30]!r} doctor={doctor_id}"
        )
        return BlockedWriteContinuation(
            patient_name=name,
            clinical_text=merged_text,
            original_text=ctx.original_text,
            supplement=supplement,
        )

    # Not a name reply — the doctor sent something else.
    # Clear stale blocked context and fall through to normal routing.
    clear_blocked_write_context(doctor_id)
    log(
        f"[precheck] blocked write cleared (unrelated message) "
        f"doctor={doctor_id} text={stripped[:40]!r}"
    )
    return None


def is_blocked_write_cancel_reply(doctor_id: str, text: str) -> bool:
    """Return True if text cancels an active blocked write.

    Separate from precheck_blocked_write so callers can generate
    a cancel reply without needing the full continuation dataclass.
    """
    ctx = get_blocked_write_context(doctor_id)
    if ctx is None:
        return False
    return is_blocked_write_cancel(text.strip())


# ── Shared precheck pipeline ─────────────────────────────────────────────

_PENDING_CANCEL_TEXTS = frozenset({
    "撤销", "取消", "cancel", "Cancel", "退出", "不要", "放弃", "no", "No",
})

_PENDING_CONFIRM_TEXTS = frozenset({
    "确认", "确定", "保存", "ok", "OK", "好的", "yes", "Yes",
})


@dataclass
class PrecheckContext:
    """Input to :func:`run_stateful_prechecks`."""

    doctor_id: str
    text: str               # processed text (e.g. transcription prefix stripped)
    original_text: str       # raw doctor input
    history: list            # conversation history
    channel: str             # "web" | "wechat" | "voice"


@dataclass
class PrecheckResult:
    """Output from :func:`run_stateful_prechecks`.

    When ``handled`` is True, the caller should return ``handler_result``
    (converted to channel-specific format) without running the workflow.

    When ``handled`` is False and ``abandon_notice`` is set, the caller
    should prepend the notice to whatever the normal workflow produces.

    ``knowledge_context`` is loaded regardless of whether a precheck fired.
    """

    handled: bool
    handler_result: Optional[object] = None   # HandlerResult
    knowledge_context: str = ""
    abandon_notice: Optional[str] = None


def _hr(reply: str, **kwargs) -> object:
    """Create a HandlerResult with the given reply text."""
    from services.domain.intent_handlers._types import HandlerResult
    return HandlerResult(reply=reply, **kwargs)


# ── Confirm pending record (moved from routers.wechat_flows) ─────────────


async def confirm_pending_record(doctor_id: str, pending_id: str) -> object:
    """Save a pending draft to medical_records, fire tasks, check CVD.

    Returns a HandlerResult.  Previously lived in ``routers.wechat_flows``
    but moved here so the service layer can use it without importing routers.
    """
    from datetime import datetime, timezone as _tz, timedelta as _td

    from db.crud.pending import get_pending_record
    from db.engine import AsyncSessionLocal
    from services.session import clear_pending_record_id, get_session

    async with AsyncSessionLocal() as db:
        pending = await get_pending_record(db, pending_id, doctor_id)
        _now_utc = datetime.now(_tz.utc)
        if pending is not None and pending.expires_at:
            _exp_at = (
                pending.expires_at
                if pending.expires_at.tzinfo is not None
                else pending.expires_at.replace(tzinfo=_tz.utc)
            )
            expired = (_exp_at - _td(seconds=5)) <= _now_utc
        else:
            expired = False
        if pending is None or pending.status != "awaiting" or expired:
            clear_pending_record_id(doctor_id)
            if expired and pending is not None:
                try:
                    import json as _json
                    _draft = _json.loads(pending.draft_json or "{}")
                    _snippet = (_draft.get("content") or "")[:60]
                    _pname = pending.patient_name or "未关联患者"
                    if _snippet:
                        return _hr(f"⚠️ 草稿已过期（{_pname}：{_snippet}…）\n请重新录入病历。")
                except Exception:
                    pass
            return _hr("⚠️ 草稿已过期\n请重新录入病历。")

    from services.domain.intent_handlers import save_pending_record

    result = await save_pending_record(doctor_id, pending)
    clear_pending_record_id(doctor_id)

    from services.observability.audit import audit
    from utils.log import safe_create_task

    safe_create_task(audit(doctor_id, "WRITE", "pending_record", str(pending.id)))

    if result is None:
        return _hr("⚠️ 草稿解析失败\n请重新录入。")

    patient_name, record_id = result
    return _hr(f"✅ 病历已保存！患者：【{patient_name}】")


# ── Draft correction (delegated to shared handler layer) ─────────────────


async def try_draft_correction(
    text: str, doctor_id: str, pending: object,
) -> Optional[object]:
    """Thin wrapper around the shared try_draft_correction.

    Returns a HandlerResult on success, None otherwise.
    """
    from services.domain.intent_handlers._confirm_pending import (
        try_draft_correction as _shared_try_draft_correction,
    )

    result = await _shared_try_draft_correction(text, doctor_id, pending)
    if result is None:
        return None
    reply_text, draft = result

    from db.models.medical_record import MedicalRecord
    try:
        record = MedicalRecord(**{k: v for k, v in draft.items() if k in MedicalRecord.model_fields})
    except Exception:
        record = None

    return _hr(
        reply_text,
        record=record,
        pending_id=str(pending.id),
        pending_patient_name=pending.patient_name,
    )


# ── Sub-prechecks ────────────────────────────────────────────────────────


async def _pending_record_precheck(ctx: PrecheckContext) -> Optional[PrecheckResult]:
    """Handle pending-record state: confirm / cancel / correction / abandon."""
    from db.crud.pending import abandon_pending_record, get_pending_record
    from db.engine import AsyncSessionLocal
    from services.session import clear_pending_record_id, get_session

    sess = get_session(ctx.doctor_id)
    pending_id = sess.pending_record_id
    if not pending_id:
        return None

    # Web manages pending records via REST endpoints (confirm/abandon).
    # Only handle inline draft correction.
    if ctx.channel == "web":
        async with AsyncSessionLocal() as db:
            pending = await get_pending_record(db, pending_id, ctx.doctor_id)
        if pending is None or pending.status != "awaiting":
            return None
        correction = await try_draft_correction(ctx.text, ctx.doctor_id, pending)
        if correction is not None:
            return PrecheckResult(handled=True, handler_result=correction)
        return None

    # WeChat / Voice: full confirm / cancel / correction / abandon flow.
    async with AsyncSessionLocal() as db:
        pending = await get_pending_record(db, pending_id, ctx.doctor_id)
    if pending is None:
        clear_pending_record_id(ctx.doctor_id)
        return PrecheckResult(handled=False)  # stale → fall through

    stripped = ctx.text.strip()

    if stripped in _PENDING_CANCEL_TEXTS:
        async with AsyncSessionLocal() as db:
            await abandon_pending_record(db, pending_id, doctor_id=ctx.doctor_id)
        clear_pending_record_id(ctx.doctor_id)
        from services.observability.audit import audit
        from utils.log import safe_create_task
        safe_create_task(audit(ctx.doctor_id, "DELETE", "pending_record", str(pending_id)))
        return PrecheckResult(handled=True, handler_result=_hr("已撤销。"))

    if stripped in _PENDING_CONFIRM_TEXTS:
        hr = await confirm_pending_record(ctx.doctor_id, pending_id)
        return PrecheckResult(handled=True, handler_result=hr)

    # Draft correction
    correction = await try_draft_correction(ctx.text, ctx.doctor_id, pending)
    if correction is not None:
        return PrecheckResult(handled=True, handler_result=correction)

    # Unrelated message → abandon draft, fall through to normal routing.
    async with AsyncSessionLocal() as db:
        await abandon_pending_record(db, pending_id, doctor_id=ctx.doctor_id)
    clear_pending_record_id(ctx.doctor_id)
    _pname = pending.patient_name or "未关联患者"
    log(f"[precheck] pending record abandoned doctor={ctx.doctor_id} patient={_pname}")
    return PrecheckResult(
        handled=False,
        abandon_notice=f"⚠️ 【{_pname}】的病历草稿已放弃。",
    )


async def _pending_create_precheck(ctx: PrecheckContext) -> Optional[PrecheckResult]:
    """Handle pending-create state: cancel / name / demographics / clinical."""
    from services.session import clear_pending_create, get_session

    sess = get_session(ctx.doctor_id)
    pending_name = sess.pending_create_name
    if not pending_name:
        return None

    stripped = ctx.original_text.strip()

    # Cancel (all channels)
    if is_blocked_write_cancel(stripped) or stripped in _PENDING_CANCEL_TEXTS:
        clear_pending_create(ctx.doctor_id)
        return PrecheckResult(handled=True, handler_result=_hr("好的，已取消。"))

    # __pending__ sentinel (Web / Voice): expect a bare patient name.
    if pending_name == "__pending__":
        bare_name = name_only_text(stripped)
        if bare_name:
            clear_pending_create(ctx.doctor_id)
            from services.ai.intent import Intent, IntentResult
            from services.domain.intent_handlers import handle_create_patient
            _ir = IntentResult(intent=Intent.create_patient, patient_name=bare_name)
            hr = await handle_create_patient(
                ctx.doctor_id, _ir,
                body_text=ctx.original_text, original_text=ctx.original_text,
            )
            return PrecheckResult(handled=True, handler_result=hr)
        # Not a name → clear sentinel, fall through to normal routing.
        clear_pending_create(ctx.doctor_id)
        return PrecheckResult(handled=False)

    # Real name (all channels): demographics or fall-through.
    from services.domain.intent_handlers import handle_pending_create_reply

    hr = await handle_pending_create_reply(ctx.text, ctx.doctor_id, pending_name)
    if hr is None:
        # No demographics — patient auto-created, pending cleared.
        # Fall through so text goes through the full workflow pipeline.
        return PrecheckResult(handled=False)
    return PrecheckResult(handled=True, handler_result=hr)


async def _blocked_write_precheck(ctx: PrecheckContext) -> Optional[PrecheckResult]:
    """Handle blocked-write cancel or continuation → add_record."""
    if is_blocked_write_cancel_reply(ctx.doctor_id, ctx.text):
        clear_blocked_write_context(ctx.doctor_id)
        return PrecheckResult(handled=True, handler_result=_hr("好的，已取消。"))

    continuation = precheck_blocked_write(ctx.doctor_id, ctx.text)
    if continuation is not None:
        from services.ai.intent import Intent, IntentResult
        from services.domain.intent_handlers import handle_add_record
        from services.session import get_session as _get_session

        _ir = IntentResult(
            intent=Intent.add_record,
            patient_name=continuation.patient_name,
        )
        # Use server-side history, never client-supplied or stored snapshots
        _server_history = list(_get_session(ctx.doctor_id).conversation_history)
        hr = await handle_add_record(
            continuation.clinical_text, ctx.doctor_id,
            _server_history, _ir,
        )
        return PrecheckResult(handled=True, handler_result=hr)

    return None


async def _load_knowledge(ctx: PrecheckContext) -> str:
    """Load doctor knowledge context for LLM dispatch."""
    from db.engine import AsyncSessionLocal
    from services.knowledge.doctor_knowledge import load_knowledge_context_for_prompt

    try:
        async with AsyncSessionLocal() as db:
            return await load_knowledge_context_for_prompt(db, ctx.doctor_id, ctx.text)
    except Exception as e:
        log(f"[precheck] knowledge load failed doctor={ctx.doctor_id}: {e}")
        return ""


# ── Orchestrator ─────────────────────────────────────────────────────────


async def run_stateful_prechecks(ctx: PrecheckContext) -> PrecheckResult:
    """Shared stateful precheck pipeline for Web / WeChat / Voice.

    Check order (mirrors the existing priority across all channels):
      1. Pending record  (non-web: confirm/cancel/correction/abandon;
                          web: draft correction only)
      2. Pending create   (all: cancel, name resolution, demographics)
      3. Blocked-write    (all: cancel or continuation → add_record)

    If nothing matched, loads knowledge context for the LLM dispatch phase.
    """
    # 1. Pending record
    pr = await _pending_record_precheck(ctx)
    if pr is not None:
        if pr.handled:
            return pr
        # pr.handled=False → stale/abandoned, continue checks.
        # abandon_notice (if any) is carried to the final return.

    # 2. Pending create
    pc = await _pending_create_precheck(ctx)
    if pc is not None:
        if pc.handled:
            return pc
        # handled=False → sentinel cleared, continue to normal routing.
        # Carry forward abandon_notice from pending-record precheck if present.
        if pr and pr.abandon_notice:
            pc = PrecheckResult(
                handled=False,
                knowledge_context=pc.knowledge_context,
                abandon_notice=pr.abandon_notice,
            )
        return pc

    # 3. Blocked-write
    bw = await _blocked_write_precheck(ctx)
    if bw is not None:
        return bw

    # 5. No precheck fired → load knowledge for downstream LLM dispatch
    knowledge = await _load_knowledge(ctx)

    return PrecheckResult(
        handled=False,
        knowledge_context=knowledge,
        abandon_notice=pr.abandon_notice if pr else None,
    )
