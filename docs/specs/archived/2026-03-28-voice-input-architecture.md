# Voice Input Architecture — China Deployment

> Date: 2026-03-28
> Status: Draft (pending ASR provider decision)
> Depends on: Tencent Cloud deployment

---

## Problem

Browser Web Speech API uses Google's ASR — **blocked in China**. Voice input
is broken for all Chinese users. We need a China-accessible server-side ASR.

## Requirements

1. **Real-time transcription** — doctor sees text appearing while speaking
2. **Chinese medical vocabulary** — "蛛网膜下腔出血", "卡马西平", "NIHSS评分"
3. **Press-to-hold UX** — keep existing interaction pattern
4. **<500ms latency** for streaming first-word display
5. **Works in**: web browser, WeChat mini-program, mobile WebView
6. **Max recording**: 5 minutes (doctor dictation use case)
7. **Compliance**: data stays in China (PIPL)

## Where Voice Input Is Needed

| Surface | Use Case | Priority |
|---------|----------|----------|
| **Chat** (ChatPage) | Dictate patient notes, ask AI questions | High |
| **随访 draft edit** | Voice-edit a draft reply | High |
| **审核 edit** | Voice-dictate diagnosis edits | Medium |
| **Knowledge add** | Voice-dictate a new rule | Medium |
| **Patient interview** | Already has VoiceInput | Exists |

## Architecture

### Option A: Tencent Cloud ASR (Recommended if on Tencent Cloud)

```
┌─────────────┐    WebSocket     ┌──────────────┐    Tencent ASR API    ┌─────────────┐
│  Frontend    │ ──────────────→ │  Backend      │ ──────────────────→  │  腾讯云ASR   │
│  VoiceInput  │                 │  /ws/transcribe│                     │  实时语音识别 │
│  (mic → PCM) │ ←────────────── │               │ ←────────────────── │             │
│              │   partial text  │  relay + cache │   streaming text    │             │
└─────────────┘                  └──────────────┘                      └─────────────┘
```

**Frontend changes:**
- VoiceInput captures raw PCM audio via `MediaRecorder` or `AudioContext`
- Streams audio chunks to backend via WebSocket
- Receives partial transcription results in real-time
- Shows interim text as doctor speaks

**Backend changes:**
- New WebSocket endpoint: `ws://.../ws/transcribe`
- Relays audio to Tencent Cloud ASR real-time API
- Returns streaming partial results to frontend
- Stores final transcript for audit trail

### Option B: Self-hosted Whisper

```
┌─────────────┐    WebSocket     ┌──────────────┐    Local inference    ┌─────────────┐
│  Frontend    │ ──────────────→ │  Backend      │ ──────────────────→  │  Whisper     │
│  VoiceInput  │                 │  /ws/transcribe│                     │  (GPU)       │
│  (mic → PCM) │ ←────────────── │               │ ←────────────────── │             │
└─────────────┘                  └──────────────┘                      └─────────────┘
```

**Pros:** No API costs, full control, data never leaves server
**Cons:** Needs GPU, higher latency (batch not streaming), Chinese medical accuracy uncertain

### Option C: Hybrid (Recommended)

- **Real-time streaming** → Tencent Cloud ASR (low latency, good Chinese)
- **Batch processing** (WeChat voice messages, uploaded audio) → Self-hosted Whisper
- **Fallback** → If Tencent API fails, queue for Whisper batch processing

## Frontend Component Changes

### Updated VoiceInput.jsx

Current: uses `window.SpeechRecognition` (browser API)
New: uses WebSocket to backend ASR relay

```jsx
// Key changes:
// 1. Replace SpeechRecognition with MediaRecorder + WebSocket
// 2. Stream PCM chunks to ws://.../ws/transcribe
// 3. Display interim results in real-time
// 4. Keep same press-to-hold UX

function VoiceInput({ onResult, onCancel }) {
  const [ws, setWs] = useState(null);
  const [interimText, setInterimText] = useState("");
  const mediaRecorderRef = useRef(null);

  function startRecording() {
    // 1. Get mic access
    // 2. Open WebSocket to /ws/transcribe
    // 3. Start MediaRecorder, send chunks via ws
    // 4. Receive partial transcripts, update interimText
  }

  function stopRecording() {
    // 1. Stop MediaRecorder
    // 2. Close WebSocket
    // 3. Final transcript → onResult(finalText)
  }
}
```

### New surfaces to wire VoiceInput:

1. **FollowupPage** — mic icon next to draft edit textarea
2. **ReviewQueuePage** — mic icon in edit mode for diagnosis notes
3. **AddKnowledgeSubpage** — mic icon next to text input
4. **MyAIPage** — AskAIBar could support voice

## Backend: ASR Relay Service

### New file: `src/services/asr/transcribe.py`

```python
"""Server-side ASR relay. Streams audio to cloud ASR, returns partial text."""

class ASRProvider(str, Enum):
    tencent = "tencent"
    whisper = "whisper"

async def create_realtime_session(provider: str = "tencent") -> ASRSession:
    """Create a streaming ASR session."""
    ...

async def transcribe_audio_file(audio_bytes: bytes, format: str = "wav") -> str:
    """Batch transcribe an audio file (for WeChat voice, uploaded audio)."""
    ...
```

### New WebSocket endpoint: `src/channels/web/transcribe_ws.py`

```python
@app.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket):
    await websocket.accept()
    session = await create_realtime_session()

    async def receive_audio():
        while True:
            data = await websocket.receive_bytes()
            await session.send_audio(data)

    async def send_transcripts():
        async for partial in session.stream_results():
            await websocket.send_json({
                "type": "partial" | "final",
                "text": partial.text,
            })

    await asyncio.gather(receive_audio(), send_transcripts())
```

### New REST endpoint for batch transcription

```python
@router.post("/api/transcribe")
async def transcribe_audio(file: UploadFile):
    """Batch transcribe uploaded audio file."""
    audio = await file.read()
    text = await transcribe_audio_file(audio, format=file.filename.split(".")[-1])
    return {"text": text}
```

## Audio Format Handling

| Source | Format | Processing |
|--------|--------|------------|
| Browser mic (real-time) | PCM 16kHz mono | Stream directly to ASR |
| WeChat voice message | AMR/SILK | Convert to WAV via ffmpeg, then batch ASR |
| Uploaded audio file | MP3/WAV/M4A/OGG | Convert to WAV via ffmpeg, then batch ASR |

Need `ffmpeg` on the server for format conversion.

## Data Flow by Use Case

### Doctor dictates in chat
```
Mic → MediaRecorder (PCM 16kHz) → WebSocket → Backend relay → Tencent ASR
                                                                    ↓
Frontend shows interim text ← WebSocket ← Backend ← streaming partial results
                                                                    ↓
Doctor releases mic → final transcript → inserted into chat input
```

### Doctor voice-edits a draft reply
```
Mic → same pipeline → final transcript → appended to draft textarea
```

### WeChat voice message from patient
```
WeChat webhook → download AMR audio → ffmpeg → WAV → Whisper batch → text
→ stored as patient message → triggers draft reply pipeline
```

## Configuration

```bash
# ASR Provider
ASR_PROVIDER=tencent        # tencent | whisper | hybrid
ASR_FALLBACK=whisper        # fallback if primary fails

# Tencent Cloud ASR
TENCENT_ASR_SECRET_ID=xxx
TENCENT_ASR_SECRET_KEY=xxx
TENCENT_ASR_APPID=xxx
TENCENT_ASR_ENGINE=16k_zh_medical  # medical Chinese model if available

# Whisper (self-hosted)
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda          # cuda | cpu
WHISPER_LANGUAGE=zh
```

## Implementation Priority

```
1. Backend ASR relay service (transcribe.py)           ← infrastructure
2. WebSocket endpoint (transcribe_ws.py)               ← real-time streaming
3. Update VoiceInput.jsx (MediaRecorder + WebSocket)   ← frontend
4. Wire VoiceInput to FollowupPage + ReviewQueuePage   ← new surfaces
5. Batch transcribe endpoint for audio files           ← WeChat voice
6. Wire into WeChat media pipeline                     ← WeChat channel
```

## Cost Estimation

(Pending Codex ASR research results — will update with pricing)

## Open Questions

1. Which Tencent ASR engine to use? (`16k_zh` vs medical-specific?)
2. Does Tencent offer a medical vocabulary add-on?
3. Can we use Tencent ASR WebSocket from WeChat mini-program directly?
4. Whisper GPU requirements — what Tencent Cloud GPU instances are available?
5. Audio retention policy — save recordings for audit or delete after transcription?
