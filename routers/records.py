from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from db.crud import (
    create_patient as db_create_patient,
    find_patient_by_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    save_record,
)
from db.engine import AsyncSessionLocal
from models.medical_record import MedicalRecord
from services.agent import dispatch as agent_dispatch
from services.intent import Intent
from services.structuring import structure_medical_record
from services.transcription import transcribe_audio
from utils.log import log

router = APIRouter(prefix="/api/records", tags=["records"])

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
}


class HistoryMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatInput(BaseModel):
    text: str
    history: List[HistoryMessage] = []
    doctor_id: str = "test_doctor"


class TextInput(BaseModel):
    text: str


class ChatResponse(BaseModel):
    reply: str
    record: Optional[MedicalRecord] = None


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatInput):
    """General-purpose agent endpoint: dispatches via LLM and executes business logic.

    doctor_id identifies the doctor — defaults to "test_doctor" for local testing.
    Pass history as prior turns so the agent can resolve pronouns and follow-ups.
    """
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")

    history = [{"role": m.role, "content": m.content} for m in body.history]
    doctor_id = body.doctor_id
    try:
        intent_result = await agent_dispatch(body.text, history=history)
    except Exception as e:
        msg = str(e)
        status = 429 if "rate_limit" in msg or "Rate limit" in msg or "429" in msg else 503
        raise HTTPException(status_code=status, detail=msg)

    # ── create_patient ────────────────────────────────────────────────────────
    if intent_result.intent == Intent.create_patient:
        name = intent_result.patient_name
        if not name:
            return ChatResponse(reply="好的，请告诉我患者的姓名。")
        async with AsyncSessionLocal() as db:
            patient = await db_create_patient(
                db, doctor_id, name, intent_result.gender, intent_result.age
            )
        parts = "、".join(filter(None, [
            intent_result.gender,
            f"{intent_result.age}岁" if intent_result.age else None,
        ]))
        reply = f"✅ 已为患者【{patient.name}】建档" + (f"（{parts}）" if parts else "") + "。"
        log(f"[Chat] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
        return ChatResponse(reply=reply)

    # ── add_medical_record ────────────────────────────────────────────────────
    if intent_result.intent == Intent.add_record:
        if not intent_result.patient_name:
            return ChatResponse(reply="请问这位患者叫什么名字？")
        doctor_ctx = [m["content"] for m in history[-10:] if m["role"] == "user"]
        doctor_ctx.append(body.text)
        try:
            record = await structure_medical_record("\n".join(doctor_ctx))
        except Exception as e:
            return ChatResponse(reply=f"病历生成失败：{e}")

        patient_id = None
        patient_name = intent_result.patient_name
        patient_created = False
        async with AsyncSessionLocal() as db:
            if patient_name:
                patient = await find_patient_by_name(db, doctor_id, patient_name)
                if not patient:
                    patient = await db_create_patient(
                        db, doctor_id, patient_name,
                        intent_result.gender, intent_result.age,
                    )
                    patient_created = True
                patient_id = patient.id
            await save_record(db, doctor_id, record, patient_id)

        if patient_name:
            prefix = "✅ 已为【" + patient_name + "】" + ("新建档并" if patient_created else "") + "保存病历。"
        else:
            prefix = "✅ 病历已保存。"
        log(f"[Chat] saved record patient={patient_name} doctor={doctor_id}")
        return ChatResponse(reply=prefix, record=record)

    # ── query_records ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.query_records:
        name = intent_result.patient_name
        async with AsyncSessionLocal() as db:
            if name:
                patient = await find_patient_by_name(db, doctor_id, name)
                if not patient:
                    return ChatResponse(reply=f"未找到患者【{name}】。")
                records = await get_records_for_patient(db, doctor_id, patient.id)
                if not records:
                    return ChatResponse(reply=f"📂 患者【{name}】暂无历史记录。")
                lines = [f"📂 患者【{name}】最近 {len(records)} 条记录："]
                for i, r in enumerate(records, 1):
                    date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                    lines.append(f"{i}. [{date}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
            else:
                records = await get_all_records_for_doctor(db, doctor_id)
                if not records:
                    return ChatResponse(reply="📂 暂无任何病历记录。")
                lines = [f"📂 最近 {len(records)} 条记录："]
                for r in records:
                    pname = r.patient.name if r.patient else "未关联"
                    date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                    lines.append(f"【{pname}】[{date}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
        return ChatResponse(reply="\n".join(lines))

    # ── list_patients ─────────────────────────────────────────────────────────
    if intent_result.intent == Intent.list_patients:
        async with AsyncSessionLocal() as db:
            patients = await get_all_patients(db, doctor_id)
        if not patients:
            return ChatResponse(reply="📂 暂无患者记录。")
        lines = [f"👥 共 {len(patients)} 位患者："]
        for i, p in enumerate(patients, 1):
            info = "、".join(filter(None, [p.gender, f"{p.age}岁" if p.age else None]))
            lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
        return ChatResponse(reply="\n".join(lines))

    # ── unknown / conversational ──────────────────────────────────────────────
    return ChatResponse(reply=intent_result.chat_reply or "您好！有什么可以帮您？")


@router.post("/from-text", response_model=MedicalRecord)
async def create_record_from_text(body: TextInput):
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    try:
        return await structure_medical_record(body.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-audio", response_model=MedicalRecord)
async def create_record_from_audio(audio: UploadFile = File(...)):
    if audio.content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {audio.content_type}. Supported: mp3, mp4, wav, webm, ogg, flac, m4a.",
        )
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.wav")
        return await structure_medical_record(transcript)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
