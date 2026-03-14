"""Deterministic draft confirm/abandon guard (ADR 0011 §6).

When a pending draft exists, this guard intercepts confirm/abandon input and
handles it without an LLM call.  **Read-only intents** (query, list, help,
export, tasks) are allowed to pass through so the doctor is not locked out of
the system while a draft awaits confirmation.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from messages import M
from services.runtime.models import DoctorCtx, TurnResult
from utils.log import log

_LANG = os.environ.get("RUNTIME_LANG", "zh")

# ── Confirm / abandon patterns (language-specific) ─────────────────────────

if _LANG == "en":
    CONFIRM_RE = re.compile(
        r"^(ok|yes|save|confirm|sure|do it)\s*[.?!]*$",
        re.IGNORECASE,
    )
    ABANDON_RE = re.compile(
        r"^(no|cancel|abandon|discard|never\s*mind)\s*[.?!]*$",
        re.IGNORECASE,
    )
    _READONLY_RE = re.compile(
        r"^("
        r"look\s*up|search|find|query|view|show"
        r"|list|patients?|all\s+patients"
        r"|tasks?|to\s*do|done\s+\d+"
        r"|help|menu|commands?\b"
        r"|export|PDF[:：]"
        r"|\?"
        r")",
        re.IGNORECASE,
    )
else:
    CONFIRM_RE = re.compile(
        r"^(确认|确定|保存|是的?|对|好的?|ok|yes|save|confirm)\s*[。？！.?!]*$",
        re.IGNORECASE,
    )
    ABANDON_RE = re.compile(
        r"^(取消|放弃|不要|不保存|不了|算了|cancel|abandon|discard|no)\s*[。？！.?!]*$",
        re.IGNORECASE,
    )
    _READONLY_RE = re.compile(
        r"^("
        # query records / view patient
        r"查(?:询|看|一下)?|搜索?|看看|看下|找"
        r"|查看.{0,4}(?:病历|记录|档案)"
        # list patients / list records
        r"|列出|显示|所有患者|患者列表"
        # tasks
        r"|待办|任务列表?|我的任务|完成\s*\d+"
        # help
        r"|帮助|help|功能|菜单|\?"
        # export
        r"|导出|PDF[:：]"
        r")",
        re.IGNORECASE,
    )


async def check_draft_guard(ctx: DoctorCtx, user_input: str) -> Optional[TurnResult]:
    """If a pending draft exists, handle confirm/abandon/re-prompt.

    Returns TurnResult if handled (model is NOT called).
    Returns None if no pending draft or if the input is a read-only intent
    that should proceed to the model.
    """
    draft_id = ctx.workflow.pending_draft_id
    if not draft_id:
        return None

    text = user_input.strip()

    if CONFIRM_RE.match(text):
        return await _confirm_draft(ctx, draft_id)

    if ABANDON_RE.match(text):
        return await _abandon_draft(ctx, draft_id)

    # Read-only intents pass through — doctor can query/list/help while a
    # draft is pending without being blocked.
    if _READONLY_RE.match(text):
        log(f"[draft_guard] read-only pass-through doctor={ctx.doctor_id} text={text[:40]}")
        return None

    patient = ctx.workflow.patient_name or ""
    return TurnResult(reply=M.draft_pending.format(patient=patient))


async def _confirm_draft(ctx: DoctorCtx, draft_id: str) -> TurnResult:
    """Confirm pending draft -> save to medical_records."""
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
    log(f"[draft_guard] confirmed draft={draft_id} record={record_id} doctor={ctx.doctor_id}")
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
    log(f"[draft_guard] abandoned draft={draft_id} doctor={ctx.doctor_id}")
    return TurnResult(reply=M.draft_abandoned.format(patient=patient))
