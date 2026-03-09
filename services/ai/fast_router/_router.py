"""
Core routing logic for fast_router.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from services.ai.intent import Intent, IntentResult

from ._keywords import (
    _IMPORT_KEYWORDS, _LIST_PATIENTS_EXACT, _LIST_PATIENTS_SHORT,
    _LIST_TASKS_EXACT, _LIST_TASKS_SHORT, _NON_NAME_KEYWORDS,
    _TIER3_BAD_NAME, _EMERGENCY_KW,
)
from . import _mined_rules
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
    _CORRECT_RECORD_RE,
    _CORRECT_NAME_RE,
    _TIER3_NAME_RE,
    _parse_task_num,
    _time_unit_to_days,
    _extract_demographics,
)
from ._tier3 import _is_clinical_tier3, _extract_tier3_demographics
from ._session import _apply_session_context

if TYPE_CHECKING:
    from services.session import DoctorSession


def _fast_route_core(text: str, specialty: Optional[str] = None) -> Optional[IntentResult]:
    """Internal routing logic — no session context applied here."""
    stripped = text.strip()
    if not stripped:
        return None

    # Normalised form used for Tier 1 set lookups (strips polite particles etc.)
    normed = _normalise(stripped)

    # ── Tier 0: import_history — bulk/PDF/Word/Image imports bypass LLM entirely ─
    if stripped.startswith("[PDF:") or stripped.startswith("[Word:"):
        source = "pdf" if stripped.startswith("[PDF:") else "word"
        return IntentResult(intent=Intent.import_history, extra_data={"source": source})
    if stripped.startswith("[Image:"):
        return IntentResult(intent=Intent.import_history, extra_data={"source": "image"})
    if any(kw in stripped for kw in _IMPORT_KEYWORDS):
        date_count = len(_IMPORT_DATE_RE.findall(stripped))
        if date_count >= 2:
            return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})
    if len(stripped) > 800 and len(_IMPORT_DATE_RE.findall(stripped)) >= 2:
        return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})

    # ── Tier 1: list_patients ──────────────────────────────────────────────────
    if normed in _LIST_PATIENTS_EXACT or stripped in _LIST_PATIENTS_EXACT:
        return IntentResult(intent=Intent.list_patients)
    if normed in _LIST_PATIENTS_SHORT or stripped in _LIST_PATIENTS_SHORT:
        return IntentResult(intent=Intent.list_patients)
    if _LIST_PATIENTS_FLEX_RE.match(normed) or _LIST_PATIENTS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_patients)

    # ── Tier 1: list_tasks ────────────────────────────────────────────────────
    if normed in _LIST_TASKS_EXACT or stripped in _LIST_TASKS_EXACT:
        return IntentResult(intent=Intent.list_tasks)
    if normed in _LIST_TASKS_SHORT or stripped in _LIST_TASKS_SHORT:
        return IntentResult(intent=Intent.list_tasks)
    if _LIST_TASKS_FLEX_RE.match(normed) or _LIST_TASKS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_tasks)

    # ── Tier 2: complete_task (fully deterministic — no LLM needed) ───────────
    for _pat in (_COMPLETE_TASK_A_RE, _COMPLETE_TASK_B_RE, _COMPLETE_TASK_C_RE, _COMPLETE_TASK_D_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            return IntentResult(
                intent=Intent.complete_task,
                extra_data={"task_id": task_id},
            )

    # ── Tier 2: cancel_task ──────────────────────────────────────────────────
    for _pat in (_CANCEL_TASK_A_RE, _CANCEL_TASK_B_RE, _CANCEL_TASK_C_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            return IntentResult(intent=Intent.cancel_task, extra_data={"task_id": task_id})

    # ── Tier 2: postpone_task ────────────────────────────────────────────────
    for _pat in (_POSTPONE_TASK_RE, _POSTPONE_TASK_B_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            delta_days = _time_unit_to_days(m.group(2), m.group(3))
            return IntentResult(
                intent=Intent.postpone_task,
                extra_data={"task_id": task_id, "delta_days": delta_days},
            )

    # ── Tier 2: schedule_follow_up (standalone, no record needed) ────────────
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

    # ── Tier 2: schedule_appointment ─────────────────────────────────────────────
    for target in (normed, stripped):
        for pat in (_APPOINTMENT_RE, _APPOINTMENT_VERB_FIRST_RE):
            m = pat.match(target)
            if m:
                appt_name = m.group(1)
                if appt_name and appt_name not in _NON_NAME_KEYWORDS:
                    return IntentResult(intent=Intent.schedule_appointment, patient_name=appt_name)

    # ── Tier 2: export_outpatient_report (卫生部 2010 标准门诊病历) ───────────
    for target in (normed, stripped):
        m = _OUTPATIENT_REPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_outpatient_report, patient_name=name or None)
    if _OUTPATIENT_REPORT_NONAME_RE.match(normed) or _OUTPATIENT_REPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_outpatient_report)

    # ── Tier 2: export_records ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _EXPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_records, patient_name=name or None)
    if _EXPORT_NONAME_RE.match(normed) or _EXPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_records)

    # ── Tier 2: supplement / record continuation → add_record ─────────────────
    # "补充：…", "补一句：…", "加上…" are unambiguously appending to a record.
    if _SUPPLEMENT_RE.match(stripped):
        return IntentResult(intent=Intent.add_record)

    # ── Tier 2: query_records ─────────────────────────────────────────────────
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

    # ── Tier 2: create_patient ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _CREATE_DUPLICATE_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

        m = _CREATE_LEAD_RE.search(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

        m = _CREATE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

        m = _CREATE_TERSE_END_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

    # ── Tier 2: delete_patient ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _DELETE_LEAD_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

        m = _DELETE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

        m = _DELETE_OCCINDEX_RE.match(target)
        if m and m.group(2) not in _NON_NAME_KEYWORDS:
            occurrence = _parse_task_num(m.group(1))
            return IntentResult(
                intent=Intent.delete_patient,
                patient_name=m.group(2),
                extra_data={"occurrence_index": occurrence},
            )

    # ── Tier 2: update_patient_info (demographic correction) ─────────────────
    for target in (normed, stripped):
        m = _UPDATE_PATIENT_DEMO_RE.search(target)
        if m:
            name = m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            if name and name not in _NON_NAME_KEYWORDS:
                gender, age = _extract_demographics(stripped)
                return IntentResult(
                    intent=Intent.update_patient,
                    patient_name=name,
                    gender=gender,
                    age=age,
                )

    # ── Tier 2.5: update_record — MUST come before Tier 3 ────────────────────
    # Correction messages often contain clinical keywords (e.g. "胸痛", "STEMI")
    # which would otherwise be caught by Tier 3 and mis-routed as add_record.
    # Detecting correction intent first ensures the update_record handler runs.
    # Field extraction is deliberately left to the LLM (no structured_fields here)
    # so the update_medical_record tool can parse correction phrasing accurately.
    if _CORRECT_RECORD_RE.search(stripped):
        name = None
        # Try correction-specific pattern first: "刚才[NAME]的..." / "上一条[NAME]的..."
        cm = _CORRECT_NAME_RE.search(stripped)
        if cm:
            name = cm.group(1) or (cm.group(2) if cm.lastindex and cm.lastindex >= 2 else None)
            if name in _TIER3_BAD_NAME or name in _NON_NAME_KEYWORDS:
                name = None
        # Fallback: name at message start (less common in correction phrasing)
        if name is None:
            m = _TIER3_NAME_RE.match(stripped)
            if m and m.group(1) not in _TIER3_BAD_NAME:
                name = m.group(1)
        return IntentResult(intent=Intent.update_record, patient_name=name)

    # ── Mined rules (loaded from data/mined_rules.json) ──────────────────────
    for rule in _mined_rules._MINED_RULES:
        if not rule["enabled"]:
            continue
        if len(stripped) < rule.get("min_length", 0):
            continue
        matched_obj = None
        for p in rule["patterns"]:
            matched_obj = p.search(stripped)
            if matched_obj:
                break
        if matched_obj is None and rule.get("keywords_any"):
            if any(k in stripped for k in rule["keywords_any"]):
                matched_obj = True  # sentinel — no group extraction possible via keywords
        if matched_obj:
            # Extract patient_name from regex group if configured
            patient_name: Optional[str] = None
            grp = rule.get("patient_name_group")
            if grp is not None and matched_obj is not True:
                try:
                    candidate = matched_obj.group(grp)
                    if candidate and candidate not in _NON_NAME_KEYWORDS and candidate not in _TIER3_BAD_NAME:
                        patient_name = candidate
                except (IndexError, AttributeError):
                    pass
            return IntentResult(
                intent=Intent[rule["intent"]],
                patient_name=patient_name,
                extra_data=dict(rule.get("extra_data") or {}),
                confidence=float(rule.get("confidence", 1.0)),
            )

    # ── Tier 3: high-confidence clinical content → add_record ────────────────
    # Skips the routing LLM call entirely; structuring LLM still runs.
    # Conservative: only fires for messages long enough and containing at least
    # one term that is almost exclusively used in clinical contexts.
    if len(stripped) >= 6 and _is_clinical_tier3(stripped, specialty=specialty):
        name, gender, age = _extract_tier3_demographics(stripped)
        is_emergency = any(kw in stripped for kw in _EMERGENCY_KW)
        return IntentResult(
            intent=Intent.add_record,
            patient_name=name,
            gender=gender,
            age=age,
            is_emergency=is_emergency,
            confidence=0.8,
        )

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
