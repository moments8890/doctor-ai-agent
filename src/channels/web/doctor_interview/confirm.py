"""Doctor interview — confirm and cancel endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from utils.log import log

from .shared import (
    InterviewConfirmResponse,
    _resolve_doctor_id,
    _verify_session,
    _build_clinical_text,
)

router = APIRouter()


# ── POST /confirm ────────────────────────────────────────────────

@router.post("/confirm", response_model=InterviewConfirmResponse)
async def interview_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    patient_name: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Confirm interview and save to medical_records.

    Runs batch extraction from the full conversation transcript using
    doctor-extract.md, then saves the result. Per-turn collected fields
    (used for progress UI during the interview) are replaced by the
    batch extraction output for better field routing accuracy.
    """
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)

    if session.status not in ("interviewing",):
        raise HTTPException(400, f"Session status is '{session.status}', cannot confirm")

    from domain.patients.interview_session import save_session
    from db.models.interview_session import InterviewStatus

    collected = session.collected or {}
    if not any(v for k, v in collected.items() if not k.startswith("_")):
        raise HTTPException(400, "No collected data to confirm")

    # Batch re-extraction from full transcript (replaces per-turn draft)
    if session.conversation:
        from domain.patients.interview_summary import batch_extract_from_transcript
        patient_info = {
            "name": collected.get("_patient_name", ""),
            "gender": collected.get("_patient_gender", ""),
            "age": collected.get("_patient_age", ""),
        }
        extracted = await batch_extract_from_transcript(
            session.conversation, patient_info, mode="doctor",
        )
        if extracted:
            # Preserve metadata fields (underscore-prefixed) from per-turn collected
            for k, v in collected.items():
                if k.startswith("_") and k not in extracted:
                    extracted[k] = v
            collected = extracted
            log(f"[interview-confirm] batch extraction replaced per-turn draft: {len(extracted)} fields")

    # Deferred patient creation — if patient_id is still None, create now
    if session.patient_id is None:
        from agent.tools.resolve import resolve

        # Allow frontend to override name (e.g. when LLM didn't extract one)
        if patient_name and patient_name.strip():
            collected["_patient_name"] = patient_name.strip()

        patient_name = collected.get("_patient_name")
        patient_gender = collected.get("_patient_gender")
        patient_age_str = collected.get("_patient_age")
        patient_age = None
        if patient_age_str:
            try:
                patient_age = int(patient_age_str.rstrip("岁"))
            except (ValueError, AttributeError):
                pass

        if not patient_name:
            raise HTTPException(422, "无法确认：未检测到患者姓名，请在对话中提供")

        resolved = await resolve(
            patient_name, resolved_doctor, auto_create=True,
            gender=patient_gender, age=patient_age,
        )
        if "status" in resolved:
            raise HTTPException(422, resolved.get("message", "Patient creation failed"))

        session.patient_id = resolved["patient_id"]
        await save_session(session)
        log(f"[interview-confirm] deferred patient created id={session.patient_id} name={patient_name}")

    # Save directly to medical_records with clinical columns
    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB, RecordStatus
    from db.crud.doctor import _ensure_doctor_exists

    # Build content summary from collected fields (exclude underscore-prefixed metadata)
    clinical_text = _build_clinical_text(collected)

    # Determine status based on completeness
    has_diagnosis = bool(collected.get("diagnosis", "").strip())
    has_treatment = bool(collected.get("treatment_plan", "").strip())
    has_followup = bool(collected.get("orders_followup", "").strip())
    status = RecordStatus.completed if (has_diagnosis and has_treatment and has_followup) else RecordStatus.pending_review

    await _ensure_doctor_exists(db, resolved_doctor)
    record = MedicalRecordDB(
        doctor_id=resolved_doctor,
        patient_id=session.patient_id,
        record_type="interview_summary",
        status=status.value,
        content=clinical_text,
        # clinical record fields from collected
        chief_complaint=collected.get("chief_complaint"),
        present_illness=collected.get("present_illness"),
        past_history=collected.get("past_history"),
        allergy_history=collected.get("allergy_history"),
        personal_history=collected.get("personal_history"),
        marital_reproductive=collected.get("marital_reproductive"),
        family_history=collected.get("family_history"),
        physical_exam=collected.get("physical_exam"),
        specialist_exam=collected.get("specialist_exam"),
        auxiliary_exam=collected.get("auxiliary_exam"),
        diagnosis=collected.get("diagnosis"),
        treatment_plan=collected.get("treatment_plan"),
        orders_followup=collected.get("orders_followup"),
    )
    db.add(record)
    await db.commit()
    record_id = record.id

    log(f"[interview-confirm] record saved id={record_id} doctor={resolved_doctor} patient={session.patient_id} status={status.value}")

    # Update last_activity_at for the patient
    if session.patient_id:
        try:
            from db.crud.patient import touch_patient_activity
            await touch_patient_activity(db, session.patient_id)
        except Exception:
            pass

    # Update session status
    session.status = InterviewStatus.confirmed
    await save_session(session)

    from domain.patients.interview_turn import release_session_lock
    release_session_lock(session_id)

    # Auto-generate follow-up tasks from orders/treatment (best-effort)
    try:
        from domain.tasks.from_record import generate_tasks_from_record
        from db.crud.patient import get_patient_for_doctor
        async with AsyncSessionLocal() as db:
            patient = await get_patient_for_doctor(db, resolved_doctor, session.patient_id)
        patient_name = patient.name if patient else ""
        task_ids = await generate_tasks_from_record(
            doctor_id=resolved_doctor,
            patient_id=session.patient_id,
            record_id=record_id,
            orders_followup=collected.get("orders_followup"),
            treatment_plan=collected.get("treatment_plan"),
            patient_name=patient_name,
        )
        if task_ids:
            log(f"[interview-confirm] auto-created {len(task_ids)} follow-up tasks: {task_ids}")
    except Exception as exc:
        log(f"[interview-confirm] task generation failed (non-blocking): {exc}", level="warning")

    return InterviewConfirmResponse(
        status=status.value,
        preview=clinical_text[:200] if clinical_text else None,
        pending_id=str(record_id),
    )


# ── POST /cancel ─────────────────────────────────────────────────

@router.post("/cancel")
async def interview_cancel_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)

    from domain.patients.interview_session import save_session
    from db.models.interview_session import InterviewStatus

    session.status = InterviewStatus.abandoned
    await save_session(session)

    from domain.patients.interview_turn import release_session_lock
    release_session_lock(session_id)

    return {"status": "abandoned"}
