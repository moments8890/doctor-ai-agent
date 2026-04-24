"""InterviewEngine — template-agnostic orchestrator.

Spec §5c (next_turn), §5d (confirm). Phase 2.5 inlines the full turn loop
using the template's extractor protocol methods.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, List

from pydantic import Field, create_model

from agent.llm import structured_call
from domain.interview.contract import build_response_schema
from domain.interview.protocols import (
    CompletenessState, PersistRef, SessionState, Template, TurnResult,
)
from domain.interview.templates import get_template
from domain.patients.interview_turn import (
    get_session_lock as _get_session_lock,
    release_session_lock as _release_session_lock,
)
from domain.patients.interview_session import (
    load_session as _load_session,
    save_session as _save_session,
)
from db.models.interview_session import InterviewStatus
from utils.log import log


def _build_turn_llm_response_schema(template: Template):
    """Build the per-turn LLM response schema: reply + extracted + suggestions.

    Extracted is build_response_schema(template.extractor.fields()) so each
    template gets its own contract. The wrapper class is created fresh per
    call.
    """
    inner = build_response_schema(template.extractor.fields())
    return create_model(
        "TurnLLMResponse",
        reply=(
            str,
            Field(default="请继续描述您的情况。", description="自然语言回复"),
        ),
        extracted=(
            inner,
            Field(
                default_factory=inner,
                description="本轮新提取的字段（只填有新信息的字段）",
            ),
        ),
        suggestions=(
            List[str],
            Field(default_factory=list, description="快捷回复选项"),
        ),
    )


async def _load_session_state(session_id: str) -> SessionState:
    raw = await _load_session(session_id)
    if raw is None:
        raise LookupError(f"session {session_id} not found")
    return SessionState(
        id=raw.id,
        doctor_id=raw.doctor_id,
        patient_id=raw.patient_id,
        mode=raw.mode,
        status=raw.status,
        template_id=raw.template_id,
        collected=raw.collected,
        conversation=raw.conversation,
        turn_count=raw.turn_count,
    )


async def _save_session_state(sess: SessionState) -> None:
    raw = await _load_session(sess.id)
    if raw is None:
        return
    raw.status = sess.status
    raw.collected = sess.collected
    raw.conversation = sess.conversation
    raw.turn_count = sess.turn_count
    raw.patient_id = sess.patient_id
    await _save_session(raw)


class InterviewEngine:
    """Generic engine. One instance serves every template."""

    async def next_turn(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResult:
        """Execute one turn — template-agnostic orchestration.

        Engine owns: session lock, load/save, turn accounting, safety cap,
        retry/backoff, status transitions. Template owns: prompt shape,
        field semantics, reply post-processing, metadata extraction.
        """
        async with _get_session_lock(session_id):
            return await self._next_turn_inner(session_id, user_input)

    async def _next_turn_inner(
        self, session_id: str, user_input: str,
    ) -> TurnResult:
        raw = await _load_session(session_id)
        if raw is None:
            empty_state = CompletenessState(
                can_complete=False, required_missing=[],
                recommended_missing=[], optional_missing=[], next_focus=None,
            )
            return TurnResult(
                reply="问诊会话不存在。", suggestions=[], state=empty_state,
            )

        mode = getattr(raw, "mode", "patient")
        resumed_from_review = raw.status == InterviewStatus.reviewing

        # Guard: terminal statuses are read-only
        if raw.status not in (InterviewStatus.interviewing, InterviewStatus.reviewing):
            state = CompletenessState(
                can_complete=False, required_missing=[],
                recommended_missing=[], optional_missing=[], next_focus=None,
            )
            return TurnResult(
                reply="该问诊已结束。", suggestions=[], state=state,
            )

        if raw.status == InterviewStatus.reviewing:
            raw.status = InterviewStatus.interviewing

        template = get_template(raw.template_id)

        # Append user message, increment turn count
        raw.conversation.append({
            "role": "user", "content": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raw.turn_count += 1

        # Safety cap
        if raw.turn_count >= template.config.max_turns:
            reply = "我们已经聊了很久了，让我整理一下已有的信息。"
            raw.conversation.append({"role": "assistant", "content": reply})
            raw.status = InterviewStatus.reviewing
            await _save_session(raw)
            state = template.extractor.completeness(raw.collected, mode)
            return TurnResult(
                reply=reply, suggestions=[], state=state, metadata={},
            )

        # Build structured state for the extractor
        session_state = SessionState(
            id=raw.id, doctor_id=raw.doctor_id, patient_id=raw.patient_id,
            mode=mode, status=raw.status, template_id=raw.template_id,
            collected=dict(raw.collected), conversation=list(raw.conversation),
            turn_count=raw.turn_count,
        )
        state = template.extractor.completeness(raw.collected, mode)
        phase = template.extractor.next_phase(
            session_state, template.config.phases[mode],
        )

        # Build prompt via extractor (template-specific)
        messages = await template.extractor.prompt_partial(
            session_state=session_state,
            completeness_state=state,
            phase=phase,
            mode=mode,
        )

        # Build the per-turn LLM response schema from template fields
        response_schema = _build_turn_llm_response_schema(template)

        env_var = (
            "CONVERSATION_LLM"
            if os.environ.get("CONVERSATION_LLM")
            else "ROUTING_LLM"
        )

        # LLM call with 3-attempt retry (infra errors only; parse errors are non-retryable)
        llm_response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                llm_response = await structured_call(
                    response_model=response_schema,
                    messages=messages,
                    op_name=f"interview.{mode}",
                    env_var=env_var,
                    temperature=0.1,
                    max_tokens=2048,
                )
                break
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                log(
                    f"[interview] LLM parse error (attempt {attempt+1}): {e}",
                    level="warning",
                )
                last_error = e
                break  # parse errors won't fix with retry
            except Exception as e:
                log(
                    f"[interview] LLM call failed (attempt {attempt+1}/3): {e}",
                    level="warning",
                )
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))

        if llm_response is None:
            if isinstance(last_error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
                reply = "抱歉，我没有理解，请再说一次。"
            else:
                log(
                    f"[interview] LLM call failed after 3 attempts: {last_error}",
                    level="error",
                )
                reply = "系统暂时繁忙，请重新发送您的回答。"
            raw.conversation.append({"role": "assistant", "content": reply})
            await _save_session(raw)
            state = template.extractor.completeness(raw.collected, mode)
            return TurnResult(
                reply=reply, suggestions=[], state=state, metadata={},
            )

        # Extract the parsed dict from the LLM response
        extracted_raw = llm_response.extracted.model_dump()
        # Drop None / empty-string values before merge
        extracted_dict = {
            k: v for k, v in extracted_raw.items()
            if v is not None and (not isinstance(v, str) or v.strip())
        }

        # Split: template-specific metadata vs. clinical fields
        metadata = template.extractor.extract_metadata(extracted_dict)
        # Remove metadata keys from extracted_dict before merge
        clinical_extracted = {
            k: v for k, v in extracted_dict.items() if k not in metadata
        }

        # Merge clinical fields
        template.extractor.merge(raw.collected, clinical_extracted)

        # Write metadata as underscore-prefixed keys (always overwrite)
        for meta_key, meta_value in metadata.items():
            if meta_value:
                raw.collected[f"_{meta_key}"] = meta_value

        # Build reply, apply template-specific post-processing
        reply = llm_response.reply or (
            "请继续描述您的情况。" if mode == "patient" else "收到，已记录。"
        )
        reply = template.extractor.post_process_reply(reply, raw.collected, mode)

        # Status transition if ready to review
        state = template.extractor.completeness(raw.collected, mode)
        # Patient-mode special: if ready, transition status
        if mode == "patient" and state.can_complete and template.requires_doctor_review:
            raw.status = InterviewStatus.reviewing
            if not resumed_from_review:
                reply = (
                    "我已经整理好主要信息。请确认后提交给医生；"
                    "如果还有补充，也可以继续补充。"
                )

        raw.conversation.append({"role": "assistant", "content": reply})
        await _save_session(raw)

        suggestions = [str(s) for s in (llm_response.suggestions or []) if s][:4]

        return TurnResult(
            reply=reply,
            suggestions=suggestions,
            state=state,
            metadata=metadata,
        )

    async def confirm(
        self,
        session_id: str,
        doctor_edits: dict[str, str] | None = None,
        override_patient_name: str | None = None,
    ) -> PersistRef:
        """Confirm the session. Runs batch re-extract, persist, then
        best-effort hooks. Marks the session confirmed.

        Doctor-mode callers may pass `override_patient_name` to force the
        patient name into `_patient_name` before batch extract (preserves
        the current behavior at confirm.py:76-77).
        """
        sess = await _load_session_state(session_id)
        template = get_template(sess.template_id)

        collected = dict(sess.collected)

        if override_patient_name:
            collected["_patient_name"] = override_patient_name.strip()

        if doctor_edits:
            collected = template.extractor.merge(collected, doctor_edits)

        if template.batch_extractor is not None:
            ctx = {
                "name": collected.get("_patient_name", ""),
                "gender": collected.get("_patient_gender", ""),
                "age": collected.get("_patient_age", ""),
            }
            re_extracted = await template.batch_extractor.extract(
                sess.conversation, ctx, sess.mode,
            )
            if re_extracted:
                # Preserve engine-level underscore metadata across re-extract.
                for k, v in collected.items():
                    if k.startswith("_") and k not in re_extracted:
                        re_extracted[k] = v
                collected = re_extracted

        ref = await template.writer.persist(sess, collected)

        # Bug E fix: persist the reconciled `collected` back to the session
        # row BEFORE hook dispatch. Hooks are best-effort and may fail; the
        # reconciled state must survive those failures so the session JSON
        # stays consistent with the persisted record.
        sess = sess.model_copy(update={"collected": collected})
        await _save_session_state(sess)

        for hook in template.post_confirm_hooks[sess.mode]:
            try:
                await hook.run(sess, ref, collected)
            except Exception as e:
                log(
                    f"[engine-confirm] hook {hook.name} failed: {e}",
                    level="warning",
                )

        # Mark confirmed and release lock
        sess_updated = sess.model_copy(update={"status": "confirmed"})
        await _save_session_state(sess_updated)
        _release_session_lock(session_id)

        return ref
