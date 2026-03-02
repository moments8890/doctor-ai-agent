from __future__ import annotations
import asyncio
import io
import os
import wave
from utils.log import log

# Medical terminology prompt — biases Whisper toward correct medical vocabulary
_MEDICAL_PROMPT = (
    "心血管内科、肿瘤科门诊病历录入。"
    "替格瑞洛，氯吡格雷，阿司匹林，利伐沙班，华法林，达比加群，"
    "阿托伐他汀，瑞舒伐他汀，氨氯地平，美托洛尔，呋塞米，螺内酯，硝酸甘油，"
    "肌钙蛋白，TnI，BNP，NT-proBNP，D-二聚体，LDL-C，"
    "射血分数，EF，LVEF，心电图，Holter，超声心动图，"
    "STEMI，NSTEMI，ACS，PCI，CABG，房颤，室颤，心衰，NYHA，"
    "奥希替尼，曲妥珠单抗，吉非替尼，贝伐珠单抗，"
    "CEA，CA199，CA125，AFP，EGFR，HER2，ALK，T790M，"
    "ANC，G-CSF，化疗，靶向治疗，液体活检。"
)

_model = None
_model_lock = asyncio.Lock()


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.environ.get("WHISPER_MODEL", "large-v3")
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        log(f"[Whisper] loading model={model_size} device={device} compute={compute_type}")
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        log("[Whisper] model loaded")
    return _model


def _transcribe_sync(audio_bytes: bytes) -> str:
    model = _get_model()

    # faster-whisper accepts a file-like object or file path
    audio_file = io.BytesIO(audio_bytes)

    segments, info = model.transcribe(
        audio_file,
        language="zh",
        initial_prompt=_MEDICAL_PROMPT,
        beam_size=5,
        vad_filter=True,           # skip silence
        vad_parameters={"min_silence_duration_ms": 300},
    )
    text = "".join(seg.text for seg in segments).strip()
    log(f"[Whisper] detected_language={info.language} prob={info.language_probability:.2f} text={text[:80]}")
    return text


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Transcribe audio bytes to text using local faster-whisper model.

    Falls back to OpenAI Whisper API if faster_whisper is not installed.
    """
    try:
        async with _model_lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _transcribe_sync, audio_bytes)
    except ImportError:
        log("[Whisper] faster_whisper not installed, falling back to OpenAI API")
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_bytes),
            language="zh",
        )
        return response.text
