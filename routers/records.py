from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from models.medical_record import MedicalRecord
from services.structuring import structure_medical_record
from services.transcription import transcribe_audio

router = APIRouter(prefix="/api/records", tags=["records"])

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
}


class TextInput(BaseModel):
    text: str


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
