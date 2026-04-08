"""WebSocket endpoint for real-time audio transcription.

Frontend streams audio chunks via WebSocket, backend relays to ASR provider
and streams back partial transcription results.

For dev (ASR_PROVIDER=browser): returns a message telling frontend to use browser API.
For prod (ASR_PROVIDER=tencent/whisper): streams real transcription.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.asr.provider import ASRProvider, get_asr_provider
from utils.log import log

router = APIRouter()


@router.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket):
    await websocket.accept()
    provider = get_asr_provider()

    if provider == ASRProvider.browser:
        # Dev mode -- tell frontend to use browser's built-in speech recognition
        await websocket.send_json({
            "type": "config",
            "provider": "browser",
            "message": "Use browser SpeechRecognition API (dev mode)",
        })
        await websocket.close()
        return

    # Tell frontend to use server-side ASR (whisper or tencent)
    await websocket.send_json({
        "type": "config",
        "provider": "server",
        "message": f"Server-side ASR via {provider.value}",
    })

    log(f"[transcribe_ws] session started, provider={provider.value}")

    try:
        # Both whisper and tencent: accumulate audio chunks, batch-transcribe on stop.
        # True real-time streaming to Tencent ASR can be added later.
        audio_chunks: list[bytes] = []

        while True:
            try:
                data = await websocket.receive()
            except WebSocketDisconnect:
                break

            if "bytes" in data:
                audio_chunks.append(data["bytes"])
                # Accumulate for batch transcription (whisper & tencent)

            elif "text" in data:
                msg = data["text"]
                if msg == "stop":
                    break

        # Batch transcribe accumulated audio
        text = ""
        if audio_chunks:
            from services.asr.provider import transcribe_audio_bytes
            full_audio = b"".join(audio_chunks)
            text = await transcribe_audio_bytes(full_audio, format="webm")

        # Always send final response so client never hangs
        await websocket.send_json({
            "type": "final",
            "text": text,
        })

        log(f"[transcribe_ws] session ended, chunks={len(audio_chunks)}")

    except WebSocketDisconnect:
        log("[transcribe_ws] client disconnected")
    except Exception as e:
        log(f"[transcribe_ws] error: {e}", level="error")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
