"""
快速意图路由核心：无 LLM 多层级意图匹配，支持 Tier 1/2/3 路由。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from services.ai.intent import Intent, IntentResult

from ._keywords import (
    _IMPORT_KEYWORDS, _LIST_PATIENTS_EXACT, _LIST_PATIENTS_SHORT,
    _LIST_TASKS_EXACT, _LIST_TASKS_SHORT, _NON_NAME_KEYWORDS,
    _TIER3_BAD_NAME, _HELP_KEYWORDS,
)
from ._patterns import (
    _normalise,
    _IMPORT_DATE_RE,
    _LIST_TASKS_FLEX_RE,
    _LIST_PATIENTS_FLEX_RE,
    _COMPLETE_TASK_A_RE,
    _COMPLETE_TASK_B_RE,
    _COMPLETE_TASK_C_RE,
    _COMPLETE_TASK_D_RE,
    _CANCEL_TASK_A_RE,
    _CANCEL_TASK_B_RE,
    _CANCEL_TASK_C_RE,
    _POSTPONE_TASK_RE,
    _POSTPONE_TASK_B_RE,
    _FOLLOWUP_WITH_NAME_RE,
    _FOLLOWUP_LEAD_TIME_RE,
    _FOLLOWUP_RELATIVE_RE,
    _FOLLOWUP_TIME_FIRST_RE,
    _APPOINTMENT_RE,
    _APPOINTMENT_VERB_FIRST_RE,
    _OUTPATIENT_REPORT_RE,
    _OUTPATIENT_REPORT_NONAME_RE,
    _EXPORT_RE,
    _EXPORT_NONAME_RE,
    _FOLLOWUP_NONAME_RE,
    _FOLLOWUP_NONAME_RELATIVE_RE,
    _SUPPLEMENT_RE,
    _QUERY_PREFIX_RE,
    _QUERY_SUFFIX_RE,
    _QUERY_NAME_QUESTION_RE,
    _CREATE_DUPLICATE_RE,
    _CREATE_LEAD_RE,
    _CREATE_TRAIL_RE,
    _CREATE_TERSE_END_RE,
    _DELETE_LEAD_RE,
    _DELETE_TRAIL_RE,
    _DELETE_OCCINDEX_RE,
    _UPDATE_PATIENT_DEMO_RE,
    _TIER3_NAME_RE,
    _parse_task_num,
    _time_unit_to_days,
    _extract_demographics,
    _PENDING_RECORD_ABORT_RE,
    _TAIL_TASK_RE,
)
from ._session import _apply_session_context

if TYPE_CHECKING:
    from services.session import DoctorSession


# ---------------------------------------------------------------------------
# Tier 0 helpers
# ---------------------------------------------------------------------------

def _route_tier0_help(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 0: capability-list / help intent."""
    if normed in _HELP_KEYWORDS or stripped in _HELP_KEYWORDS:
        return IntentResult(intent=Intent.help)
    return None


def _route_tier0_import(stripped: str) -> Optional[IntentResult]:
    """Tier 0: bulk / PDF / Word / Image import bypasses LLM entirely."""
    if stripped.startswith("[PDF:") or stripped.startswith("[Word:"):
        source = "pdf" if stripped.startswith("[PDF:") else "word"
        return IntentResult(intent=Intent.import_history, extra_data={"source": source})
    if stripped.startswith("[Image:"):
        return IntentResult(intent=Intent.import_history, extra_data={"source": "image"})
    if any(kw in stripped for kw in _IMPORT_KEYWORDS):
        if len(_IMPORT_DATE_RE.findall(stripped)) >= 2:
            return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})
    if len(stripped) > 800 and len(_IMPORT_DATE_RE.findall(stripped)) >= 2:
        return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})
    return None


# ---------------------------------------------------------------------------
# Tier 1 helpers
# ---------------------------------------------------------------------------

def _route_tier1_lists(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 1: list_patients and list_tasks — exact set + flex regex."""
    if normed in _LIST_PATIENTS_EXACT or stripped in _LIST_PATIENTS_EXACT:
        return IntentResult(intent=Intent.list_patients)
    if normed in _LIST_PATIENTS_SHORT or stripped in _LIST_PATIENTS_SHORT:
        return IntentResult(intent=Intent.list_patients)
    if _LIST_PATIENTS_FLEX_RE.match(normed) or _LIST_PATIENTS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_patients)

    if normed in _LIST_TASKS_EXACT or stripped in _LIST_TASKS_EXACT:
        return IntentResult(intent=Intent.list_tasks)
    if normed in _LIST_TASKS_SHORT or stripped in _LIST_TASKS_SHORT:
        return IntentResult(intent=Intent.list_tasks)
    if _LIST_TASKS_FLEX_RE.match(normed) or _LIST_TASKS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_tasks)
    return None


# ---------------------------------------------------------------------------
# Tier 2 helpers
# ---------------------------------------------------------------------------

def _route_tier2_task_actions(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: complete_task, cancel_task, postpone_task — fully deterministic."""
    for _pat in (_COMPLETE_TASK_A_RE, _COMPLETE_TASK_B_RE, _COMPLETE_TASK_C_RE, _COMPLETE_TASK_D_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            return IntentResult(intent=Intent.complete_task, extra_data={"task_id": _parse_task_num(m.group(1))})

    for _pat in (_CANCEL_TASK_A_RE, _CANCEL_TASK_B_RE, _CANCEL_TASK_C_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            return IntentResult(intent=Intent.cancel_task, extra_data={"task_id": _parse_task_num(m.group(1))})

    for _pat in (_POSTPONE_TASK_RE, _POSTPONE_TASK_B_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            return IntentResult(
                intent=Intent.postpone_task,
                extra_data={
                    "task_id": _parse_task_num(m.group(1)),
                    "delta_days": _time_unit_to_days(m.group(2), m.group(3)),
                },
            )
    return None


def _route_followup_with_name(normed: str, stripped: str) -> Optional[IntentResult]:
    """Match follow-up patterns that include a patient name."""
    for _pat in (_FOLLOWUP_WITH_NAME_RE, _FOLLOWUP_LEAD_TIME_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            name = m.group(1)
            if name and name not in _NON_NAME_KEYWORDS:
                follow_up_plan = ""
                if m.lastindex and m.lastindex >= 3:
                    n_raw, unit = m.group(2), m.group(3)
                    if n_raw and unit:
                        follow_up_plan = f"{n_raw}{unit}后随访"
                return IntentResult(
                    intent=Intent.schedule_follow_up,
                    patient_name=name,
                    extra_data={"follow_up_plan": follow_up_plan or "下次随访"},
                )

    m = _FOLLOWUP_RELATIVE_RE.match(normed) or _FOLLOWUP_RELATIVE_RE.match(stripped)
    if m:
        name, rel_time = m.group(1), m.group(2)
        if name and name not in _NON_NAME_KEYWORDS:
            return IntentResult(
                intent=Intent.schedule_follow_up,
                patient_name=name,
                extra_data={"follow_up_plan": f"{rel_time}随访"},
            )

    m = _FOLLOWUP_TIME_FIRST_RE.match(normed) or _FOLLOWUP_TIME_FIRST_RE.match(stripped)
    if m:
        n_raw, unit, name = m.group(1), m.group(2), m.group(3)
        if name and name not in _NON_NAME_KEYWORDS:
            return IntentResult(
                intent=Intent.schedule_follow_up,
                patient_name=name,
                extra_data={"follow_up_plan": f"{n_raw}{unit}后随访"},
            )
    return None


def _route_followup_noname(normed: str, stripped: str) -> Optional[IntentResult]:
    """Match follow-up patterns without a patient name (session provides context)."""
    m = _FOLLOWUP_NONAME_RE.match(normed) or _FOLLOWUP_NONAME_RE.match(stripped)
    if m:
        n_raw = m.group(1) if m.lastindex and m.lastindex >= 1 else None
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        plan = f"{n_raw}{unit}后随访" if (n_raw and unit) else "下次随访"
        return IntentResult(intent=Intent.schedule_follow_up, extra_data={"follow_up_plan": plan})

    m = _FOLLOWUP_NONAME_RELATIVE_RE.match(normed) or _FOLLOWUP_NONAME_RELATIVE_RE.match(stripped)
    if m:
        return IntentResult(
            intent=Intent.schedule_follow_up,
            extra_data={"follow_up_plan": f"{m.group(1)}随访"},
        )
    return None


def _route_tier2_followup(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: schedule_follow_up — with name, relative time, or no name."""
    result = _route_followup_with_name(normed, stripped)
    if result is not None:
        return result
    return _route_followup_noname(normed, stripped)


def _route_tier2_appointment(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: schedule_appointment."""
    for target in (normed, stripped):
        for pat in (_APPOINTMENT_RE, _APPOINTMENT_VERB_FIRST_RE):
            m = pat.match(target)
            if m:
                appt_name = m.group(1)
                if appt_name and appt_name not in _NON_NAME_KEYWORDS:
                    return IntentResult(intent=Intent.schedule_appointment, patient_name=appt_name)
    return None


def _route_tier2_export(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: export_outpatient_report and export_records."""
    for target in (normed, stripped):
        m = _OUTPATIENT_REPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_outpatient_report, patient_name=name)
    if _OUTPATIENT_REPORT_NONAME_RE.match(normed) or _OUTPATIENT_REPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_outpatient_report)

    for target in (normed, stripped):
        m = _EXPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_records, patient_name=name)
    if _EXPORT_NONAME_RE.match(normed) or _EXPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_records)
    return None


def _route_tier2_query(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: query_records and supplement/add_record continuation."""
    if _SUPPLEMENT_RE.match(stripped):
        return IntentResult(intent=Intent.add_record)

    for target in (normed, stripped):
        m = _QUERY_PREFIX_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS and m.group(1) not in _TIER3_BAD_NAME:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))

        m = _QUERY_SUFFIX_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS and m.group(1) not in _TIER3_BAD_NAME:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))

        m = _QUERY_NAME_QUESTION_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS and m.group(1) not in _TIER3_BAD_NAME:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))
    return None


def _route_tier2_create_patient(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: create_patient — lead keyword, duplicate, trailing keyword, terse."""
    for target in (normed, stripped):
        m = _CREATE_DUPLICATE_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            gender, age = _extract_demographics(stripped)
            return IntentResult(intent=Intent.create_patient, patient_name=m.group(1), gender=gender, age=age)

        m = _CREATE_LEAD_RE.search(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS and m.group(1) not in _TIER3_BAD_NAME:
            gender, age = _extract_demographics(stripped)
            return IntentResult(intent=Intent.create_patient, patient_name=m.group(1), gender=gender, age=age)

        m = _CREATE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            gender, age = _extract_demographics(stripped)
            return IntentResult(intent=Intent.create_patient, patient_name=m.group(1), gender=gender, age=age)

        m = _CREATE_TERSE_END_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            gender, age = _extract_demographics(stripped)
            return IntentResult(intent=Intent.create_patient, patient_name=m.group(1), gender=gender, age=age)
    return None


def _route_tier2_delete_patient(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: delete_patient — lead, trailing, and occurrence-index patterns."""
    for target in (normed, stripped):
        m = _DELETE_LEAD_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

        m = _DELETE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

        m = _DELETE_OCCINDEX_RE.match(target)
        if m and m.group(2) not in _NON_NAME_KEYWORDS:
            return IntentResult(
                intent=Intent.delete_patient,
                patient_name=m.group(2),
                extra_data={"occurrence_index": _parse_task_num(m.group(1))},
            )
    return None


def _route_tier2_update_patient(normed: str, stripped: str) -> Optional[IntentResult]:
    """Tier 2: update_patient_info — demographic correction."""
    for target in (normed, stripped):
        m = _UPDATE_PATIENT_DEMO_RE.search(target)
        if m:
            name = m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            if name and name not in _NON_NAME_KEYWORDS:
                gender, age = _extract_demographics(stripped)
                return IntentResult(intent=Intent.update_patient, patient_name=name, gender=gender, age=age)
    return None



# ---------------------------------------------------------------------------
# Main routing entry point
# ---------------------------------------------------------------------------

def _route_tier2_all(normed: str, stripped: str) -> Optional[IntentResult]:
    """Run all Tier 2 sub-matchers in priority order."""
    for _fn in (
        lambda: _route_tier2_task_actions(normed, stripped),
        lambda: _route_tier2_followup(normed, stripped),
        lambda: _route_tier2_appointment(normed, stripped),
        lambda: _route_tier2_export(normed, stripped),
        lambda: _route_tier2_query(normed, stripped),
        lambda: _route_tier2_create_patient(normed, stripped),
        lambda: _route_tier2_delete_patient(normed, stripped),
        lambda: _route_tier2_update_patient(normed, stripped),
    ):
        result = _fn()
        if result is not None:
            return result
    return None


def _fast_route_core(text: str, specialty: Optional[str] = None) -> Optional[IntentResult]:
    """Internal routing logic — no session context applied here."""
    stripped = text.strip()
    if not stripped:
        return None

    # Normalised form used for Tier 1 set lookups (strips polite particles etc.)
    normed = _normalise(stripped)

    result = _route_tier0_help(normed, stripped)
    if result is not None:
        return result

    result = _route_tier0_import(stripped)
    if result is not None:
        return result

    result = _route_tier1_lists(normed, stripped)
    if result is not None:
        return result

    # Tail-command detection (054 fix): in mixed messages like
    # "clinical note，请先把我的待办调出来", the explicit imperative at
    # the END beats any incidental phrasing in the body (including
    # pending-record continuation in fast_route).  Only fires when the
    # message contains at least one comma and the last segment matches.
    _last_sep = max(stripped.rfind("，"), stripped.rfind(","))
    if _last_sep >= 0:
        _tail = stripped[_last_sep + 1:].strip()
        if _tail and (_TAIL_TASK_RE.match(_tail) or _TAIL_TASK_RE.match(_normalise(_tail))):
            # Candidate capture: extract name+demographics from the pre-comma clause.
            # Requires name + at least one demographic anchor (gender/age) to prevent
            # over-capturing from noisy clinical text (e.g. "头痛两小时，查我的待办").
            _pre = stripped[:_last_sep].strip()
            _extra: Optional[dict] = None
            _nm = _TIER3_NAME_RE.match(_pre)
            if _nm:
                _cname = _nm.group(1)
                if _cname not in _NON_NAME_KEYWORDS and _cname not in _TIER3_BAD_NAME:
                    _cg, _ca = _extract_demographics(_pre)
                    if _cg is not None or _ca is not None:
                        _extra = {
                            "candidate_name": _cname,
                            "candidate_gender": _cg,
                            "candidate_age": _ca,
                        }
            return IntentResult(intent=Intent.list_tasks, extra_data=_extra)

    result = _route_tier2_all(normed, stripped)
    if result is not None:
        return result

    # All remaining messages fall through to the LLM for semantic routing.
    # Tier 3 (clinical keyword → add_record) was removed 2026-03-09.
    # Mined rules and confidence threshold removed 2026-03-10 — available in
    # _mined_rules.py / FAST_ROUTE_CONFIDENCE_THRESHOLD if needed in future.
    return None


def fast_route(
    text: str,
    session: Optional["DoctorSession"] = None,
) -> Optional[IntentResult]:
    """
    Attempt to resolve intent without LLM.

    Returns IntentResult on high-confidence match, None if uncertain (LLM fallback).
    All matches are intentionally conservative — a false negative (LLM handles it) is
    always safer than a false positive (wrong intent served without LLM confirmation).

    Args:
        text: The message text to route.
        session: Optional doctor session. When provided and the result has no
            patient_name, the session's ``current_patient_name`` is used as a
            fallback for intents where patient context is meaningful. This lets
            follow-up messages like "补充：…" or "查一下" skip the LLM even when
            the patient name is omitted from the message.
    """
    specialty: Optional[str] = getattr(session, "specialty", None) if session else None
    result = _fast_route_core(text, specialty=specialty)

    # 079 fix: supplement patterns (_SUPPLEMENT_RE) route add_record without a
    # patient name.  When the session has NO active patient and NO pending draft,
    # the record would fail with "patient not found".  Fall through to LLM so it
    # can resolve the patient first.  (When session IS available with a pinned
    # patient, _apply_session_context below backfills the name — keep result.)
    if (
        result is not None
        and result.intent == Intent.add_record
        and result.patient_name is None
        and session is not None
        and not getattr(session, "current_patient_id", None)
        and not getattr(session, "current_patient_name", None)
        and not getattr(session, "pending_record_id", None)
        and not getattr(session, "candidate_patient_name", None)
        and not getattr(session, "patient_not_found_name", None)
    ):
        result = None

    # Fix 3: pending-record continuation — when an explicit draft exists, route
    # pure clinical content as add_record without LLM.  Guard: must not be a
    # confirm/abort token, must not be a question, must be >= 10 chars.
    if result is None and session is not None:
        pending_record_id: Optional[str] = getattr(session, "pending_record_id", None)
        if pending_record_id:
            _stripped = text.strip()
            if (
                len(_stripped) >= 10
                and not _stripped.endswith("？")
                and not _PENDING_RECORD_ABORT_RE.match(_stripped)
            ):
                result = IntentResult(
                    intent=Intent.add_record,
                    extra_data={"pending_record_id": pending_record_id, "continuation": True},
                )

    if result is not None and session is not None:
        result = _apply_session_context(result, session)
    return result


def fast_route_label(text: str) -> str:
    """Return a routing label and record it in routing_metrics."""
    result = fast_route(text)
    label = "llm" if result is None else f"fast:{result.intent.value}"
    from services.observability.routing_metrics import record
    record(label)
    return label
