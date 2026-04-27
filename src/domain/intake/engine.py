"""IntakeEngine — template-agnostic orchestrator.

Spec §5c (next_turn), §5d (confirm). Phase 2.5 inlines the full turn loop
using the template's extractor protocol methods.

Bump CURRENT_INTAKE_PROMPT_VERSION whenever a prompt change should
invalidate in-flight conversations (e.g., safety fix to patient-intake.md
removing "立即去急诊" — old turns mimicking that style would otherwise
poison the LLM's continuation under the new system prompt). Sessions
with a different version reset conversation on the next turn but keep
collected so the patient doesn't lose structured progress.
"""
from __future__ import annotations

# Bump this on substantive patient-intake.md changes. Format:
# YYYY-MM-DD-short-slug. Sessions started under an older version get
# their conversation truncated on the next turn.
CURRENT_INTAKE_PROMPT_VERSION = "2026-04-27-engine-policy"

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, create_model

from agent.llm import structured_call
from domain.intake.contract import build_response_schema
from domain.intake.protocols import (
    CompletenessState, PersistRef, SessionState, Template, TurnResult,
)
from domain.intake.templates import get_template
from domain.patients.intake_turn import (
    get_session_lock as _get_session_lock,
    release_session_lock as _release_session_lock,
)
from domain.patients.intake_session import (
    load_session as _load_session,
    save_session as _save_session,
)
from db.engine import AsyncSessionLocal
from db.models.intake_session import IntakeStatus
from utils.log import log


class ClinicalSignal(BaseModel):
    section: Literal["differential", "workup", "treatment"]
    content: str
    detail: Optional[str] = None
    urgency: Optional[Literal["low", "medium", "high"]] = None
    evidence: List[str] = Field(default_factory=list)
    risk_signals: List[str] = Field(default_factory=list)


# Reply-gate banned patterns — phrases that betray the doctor's persona
# leaking into the patient-facing reply (clinical instructions, ED routing,
# workup orders). When a reply contains any of these, route the underlying
# clinical thought to clinical_signals[] instead and replace reply with a
# defer-and-continue line.
_BANNED_REPLY_PATTERNS = [
    "做完检查", "我帮你看", "建议做", "建议去医院", "建议就医",
    "立即去急诊", "立即打120", "马上去医院", "去做个", "做个B超",
    "做个CT", "做个核磁", "去医院做",
]


_FIELD_QUESTIONS = {
    "past_history": "之前有没有什么慢性病或动过手术？",
    "allergy_history": "有没有药物或食物过敏？",
    "family_history": "家里直系亲属有没有什么遗传病或慢性病？",
    "personal_history": "平时有抽烟喝酒的习惯吗？",
    "marital_reproductive": "婚姻和生育情况方便简单说一下吗？",
}


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
        clinical_signals=(
            List[ClinicalSignal],
            Field(
                default_factory=list,
                description=(
                    "临床信号（鉴别诊断/检查建议/治疗思路）—— 仅给医生，"
                    "不要写入 reply"
                ),
            ),
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


class IntakeEngine:
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
        resumed_from_review = raw.status == IntakeStatus.reviewing

        # Guard: terminal statuses are read-only
        if raw.status not in (IntakeStatus.active, IntakeStatus.reviewing):
            state = CompletenessState(
                can_complete=False, required_missing=[],
                recommended_missing=[], optional_missing=[], next_focus=None,
            )
            return TurnResult(
                reply="该问诊已结束。", suggestions=[], state=state,
            )

        if raw.status == IntakeStatus.reviewing:
            raw.status = IntakeStatus.active

        # Self-heal stale sessions: if the prompt has changed since this
        # session started accumulating turns, the conversation history
        # would mimic the old style. Wipe conversation, keep collected
        # (structured progress survives), bump version. Patient resumes
        # from same field-completeness on the next turn.
        if getattr(raw, "prompt_version", None) != CURRENT_INTAKE_PROMPT_VERSION:
            log(
                f"[intake] resetting stale conversation for session {session_id}: "
                f"prompt version {getattr(raw, 'prompt_version', None)!r} → "
                f"{CURRENT_INTAKE_PROMPT_VERSION!r}"
            )
            raw.conversation = []
            raw.prompt_version = CURRENT_INTAKE_PROMPT_VERSION

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
            raw.status = IntakeStatus.reviewing
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

        # Snapshot the focus question that's about to be sent to the LLM.
        # Reused after the call to mark `_asked_safety_net`. The `state`
        # variable below is reassigned post-merge, so we can't read it
        # back from `state` then.
        focus_question_this_turn = state.next_focus_question

        # Build prompt via extractor (template-specific)
        messages = await template.extractor.prompt_partial(
            session_state=session_state,
            completeness_state=state,
            phase=phase,
            mode=mode,
        )

        # Build the per-turn LLM response schema from template fields
        response_schema = _build_turn_llm_response_schema(template)

        # Stamp on each buffered clinical_signal so we can correlate the row
        # back to the prompt that produced it (matches ai_suggestions.prompt_hash).
        prompt_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]

        env_var = (
            "CONVERSATION_LLM"
            if os.environ.get("CONVERSATION_LLM")
            else "ROUTING_LLM"
        )

        # structured_call now retries transport errors with backoff internally
        # (3 attempts, 0.5s/1s). The previous 3-outer × 1-inner setup gave
        # 9 total attempts on persistent failures. Single attempt here is
        # enough; we still distinguish parse errors (non-retryable) from
        # transport (already retried inside structured_call) for the user-
        # facing fallback message.
        llm_response = None
        last_error: Exception | None = None
        try:
            llm_response = await structured_call(
                response_model=response_schema,
                messages=messages,
                op_name=f"intake.{mode}",
                env_var=env_var,
                temperature=0.1,
                max_tokens=2048,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log(f"[intake] LLM parse error: {e}", level="warning")
            last_error = e
        except Exception as e:
            log(f"[intake] LLM call failed (after retries): {e}", level="error")
            last_error = e

        if llm_response is None:
            if isinstance(last_error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
                reply = "抱歉，我没有理解，请再说一次。"
            else:
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

        # Snapshot patient-confirmed carry-forward values BEFORE merge so we
        # can restore them after — the LLM cannot overwrite a field the
        # patient has already confirmed via update_field /
        # bulk_confirm_carry_forward.
        cf_meta_pre = raw.collected.get("_carry_forward_meta") or {}
        frozen_snapshot: dict[str, Any] = {}
        if isinstance(cf_meta_pre, dict):
            for field_name, entry in cf_meta_pre.items():
                if (
                    isinstance(entry, dict)
                    and entry.get("confirmed_by_patient")
                    and field_name in raw.collected
                ):
                    frozen_snapshot[field_name] = raw.collected[field_name]

        # For unconfirmed carry-forward fields the LLM is now extracting,
        # the carried value is just a hypothesis — patient input replaces it,
        # not appends to it. Clear the carried value before merge so the new
        # extraction starts from empty (avoids "青霉素过敏；无" append bug).
        unconfirmed_overwrites: list[str] = []
        if isinstance(cf_meta_pre, dict):
            for field_name in clinical_extracted:
                entry = cf_meta_pre.get(field_name)
                if (
                    isinstance(entry, dict)
                    and entry.get("confirmed_by_patient") is False
                    and field_name in raw.collected
                ):
                    raw.collected.pop(field_name, None)
                    unconfirmed_overwrites.append(field_name)

        # Merge clinical fields
        template.extractor.merge(raw.collected, clinical_extracted)

        # Restore confirmed carry-forward values that the merge may have
        # mutated (e.g. an appendable field where the LLM tacked on text).
        for field_name, frozen_value in frozen_snapshot.items():
            raw.collected[field_name] = frozen_value

        # Flip confirmed_by_patient → true for any carry-forward field the
        # patient just provided info on this turn. Otherwise completeness
        # treats the field as still unconfirmed and intake never ends.
        if unconfirmed_overwrites:
            cf_meta_post = raw.collected.get("_carry_forward_meta")
            if isinstance(cf_meta_post, dict):
                for field_name in unconfirmed_overwrites:
                    entry = cf_meta_post.get(field_name)
                    if isinstance(entry, dict):
                        entry["confirmed_by_patient"] = True

        # Write metadata as underscore-prefixed keys (always overwrite)
        for meta_key, meta_value in metadata.items():
            if meta_value:
                raw.collected[f"_{meta_key}"] = meta_value

        # Buffer clinical signals on the session. Materialized as
        # ai_suggestions rows on confirm() so the doctor sees them in the
        # review queue. Cap at 3 per turn; dedup against existing buffer by
        # (section, content_lower, urgency).
        raw_signals = list(llm_response.clinical_signals or [])[:3]
        new_clinical_signals: list[dict[str, Any]] = []
        if raw_signals:
            existing_buffer = raw.collected.get("_pending_ai_suggestions")
            if not isinstance(existing_buffer, list):
                existing_buffer = []
            seen_keys: set[tuple[str, str, Optional[str]]] = set()
            for entry in existing_buffer:
                if not isinstance(entry, dict):
                    continue
                section = str(entry.get("section", ""))
                content = str(entry.get("content", "")).strip().lower()
                urgency = entry.get("urgency")
                seen_keys.add((section, content, urgency))

            for sig in raw_signals:
                key = (sig.section, sig.content.strip().lower(), sig.urgency)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                new_clinical_signals.append({
                    "section": sig.section,
                    "content": sig.content.strip(),
                    "detail": sig.detail,
                    "urgency": sig.urgency,
                    "evidence": list(sig.evidence or []),
                    "risk_signals": list(sig.risk_signals or []),
                    "turn_index": raw.turn_count,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "prompt_hash": prompt_hash,
                })
            if new_clinical_signals:
                raw.collected["_pending_ai_suggestions"] = (
                    existing_buffer + new_clinical_signals
                )

        # Build reply, apply template-specific post-processing
        reply = llm_response.reply or (
            "请继续描述您的情况。" if mode == "patient" else "收到，已记录。"
        )
        reply = template.extractor.post_process_reply(reply, raw.collected, mode)

        # Style guard (detect-only, max_regens=0 — latency budget for intake is ≤3s).
        # We log violations but don't regenerate to avoid latency hit.
        # Per locked plan: intake prefers latency over polish.
        try:
            from agent.style_guard import detect_hard_violations, detect_soft_chain
            hard = detect_hard_violations(reply)
            soft = detect_soft_chain(reply)
            if hard:
                log(f"[intake.{mode}] style violations detected (no regen): hard={hard} soft={soft}")
        except Exception as exc:
            log(f"[intake] style guard check failed (non-fatal): {exc}", level="warning")

        # Reply gate: if the LLM emitted clinical thoughts (either as
        # clinical_signals or leaked into reply via banned phrases), force
        # the patient-facing reply to a defer line + the next phase-2
        # question. The clinical signal itself is preserved in the buffer
        # and surfaces to the doctor on confirm.
        # The presence of clinical_signals is NOT itself a leak — that's the
        # whole point of the channel. We only gate when the LLM actually
        # writes a banned advice phrase into the patient-facing reply.
        # Earlier the gate fired on (signals OR banned_hit), which clobbered
        # every clinically-suggestive turn with the same canned defer line.
        state_pre = template.extractor.completeness(raw.collected, mode)
        banned_hit = any(pat in reply for pat in _BANNED_REPLY_PATTERNS)
        if banned_hit:
            next_q = ""
            for field_name in state_pre.required_missing or []:
                if field_name in _FIELD_QUESTIONS:
                    next_q = _FIELD_QUESTIONS[field_name]
                    break
            if next_q:
                gated_reply = "已记录您的情况，医生会尽快查看。" + next_q
            else:
                gated_reply = "已记录您的情况，医生会尽快查看，请稍候。"
            log(
                f"[intake] reply gate fired (banned_hit) original={reply[:80]!r}",
                level="warning",
            )
            reply = gated_reply

        # Status transition if ready to review
        state = template.extractor.completeness(raw.collected, mode)
        # Patient-mode special: if ready, transition status
        if mode == "patient" and state.can_complete and template.requires_doctor_review:
            raw.status = IntakeStatus.reviewing
            if not resumed_from_review:
                reply = (
                    "我已经整理好主要信息。请确认后提交给医生；"
                    "如果还有补充，也可以继续补充。"
                )

        # Engine-driven focus tracking: if the prompt told the LLM to ask a
        # specific safety-net or chronic-drilldown question this turn, mark
        # it asked so the next turn moves to the next question instead of
        # repeating. Optimistic — assumes the LLM is cooperative when given
        # a concrete focus. Cheaper and more reliable than fuzzy-matching
        # the LLM's reply against the canonical question text.
        if focus_question_this_turn:
            asked = raw.collected.get("_asked_safety_net")
            if not isinstance(asked, list):
                asked = []
            if focus_question_this_turn not in asked:
                asked.append(focus_question_this_turn)
                raw.collected["_asked_safety_net"] = asked

        raw.conversation.append({"role": "assistant", "content": reply})
        await _save_session(raw)

        # Engine-side suggestion post-process — chip completeness for binary
        # / uncertainty-plausible questions. Replaces the bare 4-cap so the
        # LLM doesn't have to remember to inject 没有/不清楚 every turn.
        from domain.intake.templates.medical_general import (
            _postprocess_suggestions,
        )
        raw_suggestions = [
            str(s) for s in (llm_response.suggestions or []) if s
        ]
        suggestions = _postprocess_suggestions(reply, raw_suggestions)

        return TurnResult(
            reply=reply,
            suggestions=suggestions,
            state=state,
            metadata=metadata,
        )

    async def update_field(
        self,
        session_id: str,
        field: str,
        new_value: str,
    ) -> None:
        """Patient-driven correction of a single intake field.

        Sets ``collected[field] = new_value``, marks the field as
        patient-confirmed in ``_carry_forward_meta`` (creating the entry
        if absent — a patient may correct a field that wasn't a
        carry-forward in the first place), and appends ``field`` to
        ``_fields_updated_this_visit``.

        After this call, the engine's frozen-field guard ensures the LLM
        cannot overwrite the value on subsequent turns.
        """
        async with _get_session_lock(session_id):
            raw = await _load_session(session_id)
            if raw is None:
                raise LookupError(f"session {session_id} not found")

            # Normalize the new value the same way merge() does so the LLM
            # snapshot/restore logic compares apples to apples.
            if isinstance(new_value, str):
                new_value = new_value.strip()

            raw.collected[field] = new_value

            cf_meta = raw.collected.get("_carry_forward_meta")
            if not isinstance(cf_meta, dict):
                cf_meta = {}
            entry = cf_meta.get(field)
            if not isinstance(entry, dict):
                # Not a carry-forward field originally — still record the
                # patient confirmation so the freeze guard kicks in.
                entry = {
                    "source_record_id": None,
                    "source_date": None,
                    "confirmed_by_patient": True,
                }
            else:
                entry = dict(entry)
                entry["confirmed_by_patient"] = True
            cf_meta[field] = entry
            raw.collected["_carry_forward_meta"] = cf_meta

            updated = raw.collected.get("_fields_updated_this_visit")
            if not isinstance(updated, list):
                updated = []
            if field not in updated:
                updated.append(field)
            raw.collected["_fields_updated_this_visit"] = updated

            await _save_session(raw)

    async def bulk_confirm_carry_forward(self, session_id: str) -> None:
        """Flip every carry-forward field's ``confirmed_by_patient`` to True.

        Backs the "全部仍然准确" chip — patient asserts every carried-forward
        value is still accurate without changing any. Field values are not
        touched; only the meta flag changes. Fields are NOT added to
        ``_fields_updated_this_visit`` because the patient did not update them.
        """
        async with _get_session_lock(session_id):
            raw = await _load_session(session_id)
            if raw is None:
                raise LookupError(f"session {session_id} not found")

            cf_meta = raw.collected.get("_carry_forward_meta")
            if not isinstance(cf_meta, dict) or not cf_meta:
                return

            updated_meta: dict = {}
            for field_name, entry in cf_meta.items():
                if isinstance(entry, dict):
                    new_entry = dict(entry)
                    new_entry["confirmed_by_patient"] = True
                    updated_meta[field_name] = new_entry
                else:
                    updated_meta[field_name] = entry
            raw.collected["_carry_forward_meta"] = updated_meta
            await _save_session(raw)

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

        # Post-write provenance update: stamp carry_forward_meta and
        # fields_updated_this_visit onto the new medical_record row so the
        # doctor-side review surface can show "carried from 2026-04-12, patient
        # confirmed unchanged" / "patient updated this visit" badges.
        # Direct SQL keeps the writer protocol untouched (template-agnostic).
        if ref.kind == "medical_record":
            cf_meta_raw = collected.get("_carry_forward_meta")
            updated_raw = collected.get("_fields_updated_this_visit")
            cf_meta = cf_meta_raw if isinstance(cf_meta_raw, dict) else None
            updated = updated_raw if isinstance(updated_raw, list) else None
            if cf_meta or updated:
                try:
                    from sqlalchemy import update as _sa_update
                    from db.models.records import MedicalRecordDB
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            _sa_update(MedicalRecordDB)
                            .where(MedicalRecordDB.id == ref.id)
                            .values(
                                carry_forward_meta=cf_meta,
                                fields_updated_this_visit=updated,
                            )
                        )
                        await db.commit()
                except Exception as exc:
                    log(
                        f"[engine-confirm] post-write provenance update failed (non-fatal): {exc}",
                        level="warning",
                    )

            # Buffered clinical_signals stay on the session JSON
            # (`_pending_ai_suggestions`). Not materialized as ai_suggestions
            # rows yet — diagnosis pipeline is the sole writer for that table
            # in the current product call. The buffer is retained so we can
            # backfill if/when intake-side suggestions get promoted to
            # first-class review data.

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
