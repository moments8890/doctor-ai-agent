from openai import AsyncOpenAI


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    client = AsyncOpenAI()  # reads OPENAI_API_KEY from env at call time
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, audio_bytes),
        language="zh",
    )
    return response.text
