"""Doctor interview endpoints — structured record collection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from domain.patients.interview_turn import FIELD_LABELS
from utils.log import log

router = APIRouter(prefix="/api/records/interview", tags=["doctor-interview"])


# ── Pydantic models ──────────────────────────────────────────────

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str
    collected: Dict[str, str] = {}
    progress: Dict[str, Any] = {}
    missing: List[str] = []
    missing_required: List[str] = []
    status: str = "interviewing"
    patient_id: Optional[int] = None
    pending_id: Optional[str] = None
    suggestions: List[str] = []
    conversation: List[Dict[str, Any]] = []
    carry_forward: List[Dict[str, str]] = []


class InterviewConfirmResponse(BaseModel):
    status: str
    preview: Optional[str] = None
    pending_id: Optional[str] = None


class FieldUpdateRequest(BaseModel):
    session_id: str
    doctor_id: str = ""
    field: str
    value: str


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_doctor_id(doctor_id: str, authorization: Optional[str]) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )


async def _verify_session(session_id: str, doctor_id: str, *, candidate_doctor_id: str = ""):
    """Load and verify session ownership.

    Checks resolved doctor_id (from JWT) first. If that doesn't match but
    candidate_doctor_id (from request body) does, use that instead — handles
    the case where JWT resolution fell back to a default but the body has
    the correct value.
    """
    from domain.patients.interview_session import load_session
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Interview session not found")
    if session.doctor_id == doctor_id:
        return session
    # JWT-resolved ID didn't match — check if the body candidate matches
    if candidate_doctor_id and session.doctor_id == candidate_doctor_id.strip():
        log(f"[interview] session matched via candidate_doctor_id={candidate_doctor_id!r} (JWT resolved to {doctor_id!r})")
        return session
    log(f"[interview] session owner mismatch: session.doctor_id={session.doctor_id!r} != resolved={doctor_id!r} candidate={candidate_doctor_id!r}")
    raise HTTPException(403, "Not your session")


def _build_clinical_text(collected: Dict[str, str]) -> str:
    parts = []
    for key, label in FIELD_LABELS.items():
        value = collected.get(key, "")
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts)


def _compute_progress(collected):
    from domain.patients.completeness import check_completeness
    from domain.patients.interview_turn import _build_progress
    missing = check_completeness(collected, mode="doctor")
    missing_req = [f for f in ("chief_complaint", "present_illness") if not collected.get(f)]
    return {
        "progress": _build_progress(collected, mode="doctor"),
        "missing": missing,
        "missing_required": missing_req,
        "status": "ready_for_confirm" if not missing else "interviewing",
    }


_CARRY_FORWARD_FIELDS = ("allergy_history", "past_history", "family_history", "personal_history")
_SKIP_VALUES = {"无", "不详", ""}


async def _load_carry_forward(doctor_id: str, patient_id: Optional[int]) -> List[Dict[str, str]]:
    """Load stable history fields from the patient's latest record for one-tap confirmation."""
    if patient_id is None:
        return []

    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
            ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

    if row is None or not row.has_structured_data():
        return []

    source_date = row.created_at.strftime("%Y-%m-%d") if row.created_at else ""
    items = []
    for field_key in _CARRY_FORWARD_FIELDS:
        value = (getattr(row, field_key, None) or "").strip()
        if value and value not in _SKIP_VALUES:
            items.append({
                "field": field_key,
                "label": FIELD_LABELS.get(field_key, field_key),
                "value": value,
                "source_date": source_date,
            })
    return items


async def _extract_file_text(file: UploadFile) -> str:
    content_type = (file.content_type or "").split(";")[0].strip()
    raw = await file.read()
    if content_type.startswith("image/"):
        from infra.llm.vision import extract_text_from_image
        result = await extract_text_from_image(raw)
        return result.get("text", "") if isinstance(result, dict) else str(result)
    elif content_type == "application/pdf" or (file.filename or "").endswith(".pdf"):
        from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
        return extract_text_from_pdf_smart(raw)
    return ""


# ── GET /session/{session_id} ────────────────────────────────────

@router.get("/session/{session_id}", response_model=DoctorInterviewResponse)
async def get_session_state(
    session_id: str,
    doctor_id: str = "",
    authorization: Optional[str] = Header(default=None),
):
    """Get current session state — used when resuming from chat."""
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)

    progress_info = _compute_progress(session.collected)
    last_reply = ""
    for turn in reversed(session.conversation or []):
        if turn.get("role") == "assistant":
            last_reply = turn.get("content", "")
            break

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=last_reply or "病历采集中，请继续输入。",
        collected=session.collected,
        patient_id=session.patient_id,
        conversation=session.conversation or [],
        **progress_info,
    )


# ── POST /turn ───────────────────────────────────────────────────

@router.post("/turn", response_model=DoctorInterviewResponse)
async def interview_turn_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(default=None),
    doctor_id: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor, scope="records.interview")

    extra_text = ""
    if file:
        extra_text = await _extract_file_text(file)
    merged_text = f"{text}\n{extra_text}".strip() if extra_text else text

    if not session_id:
        return await _first_turn(resolved_doctor, merged_text)
    else:
        session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)
        return await _continue_turn(session, merged_text)


async def _first_turn(doctor_id, text):
    from agent.tools.resolve import resolve
    from domain.patients.interview_session import create_session, save_session
    from domain.patients.interview_turn import interview_turn

    # Create session with no patient yet — LLM will extract patient info
    session = await create_session(doctor_id, patient_id=None, mode="doctor")
    response = await interview_turn(session.id, text)

    # Try to resolve patient from LLM-extracted name
    patient_id = None
    carry_forward = []
    patient_name = response.patient_name or response.collected.get("_patient_name")
    if patient_name:
        resolved = await resolve(patient_name, doctor_id, auto_create=False)
        if "patient_id" in resolved:
            patient_id = resolved["patient_id"]
            # Reload session to get latest state, then update patient_id
            from domain.patients.interview_session import load_session
            session = await load_session(session.id)
            session.patient_id = patient_id
            await save_session(session)
            carry_forward = await _load_carry_forward(doctor_id, patient_id)

    progress_info = _compute_progress(response.collected)

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        patient_id=patient_id,
        suggestions=response.suggestions or [],
        carry_forward=carry_forward,
        **progress_info,
    )


async def _continue_turn(session, text):
    from domain.patients.interview_turn import interview_turn

    response = await interview_turn(session.id, text)
    progress_info = _compute_progress(response.collected)

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        patient_id=session.patient_id,
        suggestions=response.suggestions or [],
        **progress_info,
    )


# ── PATCH /field ─────────────────────────────────────────────────

@router.patch("/field", response_model=DoctorInterviewResponse)
async def update_interview_field(
    body: FieldUpdateRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Update a single field value in an interview session (for inline-edit)."""
    resolved_doctor = await _resolve_doctor_id(body.doctor_id, authorization)
    session = await _verify_session(body.session_id, resolved_doctor, candidate_doctor_id=body.doctor_id)

    # Validate field name
    if body.field not in FIELD_LABELS:
        raise HTTPException(status_code=422, detail=f"Unknown field: {body.field}")

    # Update the field
    session.collected[body.field] = body.value
    from domain.patients.interview_session import save_session
    await save_session(session)

    # Return updated progress
    progress_info = _compute_progress(session.collected)
    return DoctorInterviewResponse(
        session_id=session.id,
        reply="",
        collected=session.collected,
        patient_id=session.patient_id,
        **progress_info,
    )


# ── POST /carry-forward-confirm ──────────────────────────────────

class CarryForwardConfirmRequest(BaseModel):
    session_id: str
    doctor_id: str = ""
    field: str
    action: str = "confirm"  # "confirm" or "dismiss"


class CarryForwardConfirmResponse(BaseModel):
    status: str
    progress: Dict[str, Any] = {}
    missing: List[str] = []
    missing_required: List[str] = []
    collected: Dict[str, str] = {}


@router.post("/carry-forward-confirm", response_model=CarryForwardConfirmResponse)
async def carry_forward_confirm_endpoint(
    body: CarryForwardConfirmRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Confirm or dismiss a carry-forward field — no LLM round-trip needed."""
    resolved_doctor = await _resolve_doctor_id(body.doctor_id, authorization)
    session = await _verify_session(body.session_id, resolved_doctor, candidate_doctor_id=body.doctor_id)

    if body.field not in _CARRY_FORWARD_FIELDS:
        raise HTTPException(422, f"Field '{body.field}' is not a carry-forward field")

    if body.action == "confirm":
        # Load the value from the patient's latest record
        carry_items = await _load_carry_forward(resolved_doctor, session.patient_id)
        matched = next((item for item in carry_items if item["field"] == body.field), None)
        if matched is None:
            raise HTTPException(404, f"No carry-forward value found for '{body.field}'")

        from domain.patients.interview_session import save_session
        session.collected[body.field] = matched["value"]
        await save_session(session)
        log(f"[carry-forward] confirmed {body.field}='{matched['value'][:30]}' session={body.session_id}")
    else:
        log(f"[carry-forward] dismissed {body.field} session={body.session_id}")

    progress_info = _compute_progress(session.collected)
    return CarryForwardConfirmResponse(
        collected=session.collected,
        **progress_info,
    )


# ── POST /confirm ────────────────────────────────────────────────

@router.post("/confirm", response_model=InterviewConfirmResponse)
async def interview_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
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

    async with AsyncSessionLocal() as db:
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

    # Update session status
    session.status = InterviewStatus.confirmed
    await save_session(session)

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
    return {"status": "abandoned"}
