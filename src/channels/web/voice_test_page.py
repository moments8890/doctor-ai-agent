"""Hidden voice test page — exercises the ASR pipeline without touching the main UI."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["voice-test"])

_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice ASR Test</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,system-ui,sans-serif;background:#f5f5f5;color:#333;
  display:flex;flex-direction:column;align-items:center;padding:20px;min-height:100vh}
h2{margin-bottom:8px}
.info{color:#888;font-size:13px;margin-bottom:20px}
.card{background:#fff;border-radius:12px;padding:20px;width:100%;max-width:400px;
  box-shadow:0 1px 4px rgba(0,0,0,0.1);margin-bottom:16px}
.card h3{font-size:15px;margin-bottom:12px;color:#07C160}
.btn{display:block;width:100%;padding:14px;border:none;border-radius:8px;font-size:16px;
  cursor:pointer;font-weight:600;margin-bottom:8px;transition:all 0.15s}
.btn-record{background:#07C160;color:#fff}
.btn-record:active{background:#06a050}
.btn-record.recording{background:#e53935;animation:pulse 1s infinite}
.btn-upload{background:#1976d2;color:#fff}
.btn-upload:active{background:#1565c0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.7}}
.result{margin-top:12px;padding:12px;background:#f9f9f9;border-radius:8px;
  font-size:14px;line-height:1.6;min-height:40px;word-break:break-all}
.result.error{color:#e53935;background:#fff5f5}
.result.success{color:#333;background:#f0fff0}
.status{font-size:12px;color:#888;margin-top:8px}
.timer{font-size:24px;font-weight:700;text-align:center;margin:8px 0;font-variant-numeric:tabular-nums}
#fileInput{display:none}
</style>
</head>
<body>
<h2>Voice ASR Test</h2>
<p class="info">Test Tencent ASR without changing the app UI</p>

<!-- Method 1: Microphone recording -->
<div class="card">
  <h3>Method 1: Microphone</h3>
  <button id="recBtn" class="btn btn-record"
    onmousedown="startRec()" onmouseup="stopRec()"
    ontouchstart="startRec()" ontouchend="stopRec()">
    Hold to Record
  </button>
  <div id="timer" class="timer" style="display:none">00:00</div>
  <div id="recResult" class="result" style="display:none"></div>
  <div id="recStatus" class="status"></div>
</div>

<!-- Method 2: File upload -->
<div class="card">
  <h3>Method 2: Upload Audio File</h3>
  <button class="btn btn-upload" onclick="document.getElementById('fileInput').click()">
    Choose Audio File
  </button>
  <input id="fileInput" type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.webm,.amr,.silk,.flac"
    onchange="uploadFile(this)">
  <div id="uploadResult" class="result" style="display:none"></div>
  <div id="uploadStatus" class="status"></div>
</div>

<!-- Diagnostics -->
<div class="card">
  <h3>Diagnostics</h3>
  <div id="diag" class="result" style="display:block;font-size:12px;font-family:monospace"></div>
</div>

<script>
const diag = document.getElementById('diag');
const lines = [];
function log(msg) { lines.push(msg); diag.textContent = lines.slice(-10).join('\\n'); }

// Check capabilities
log('UserAgent: ' + navigator.userAgent.slice(0, 60));
log('MediaRecorder: ' + (typeof MediaRecorder !== 'undefined' ? 'YES' : 'NO'));
log('getUserMedia: ' + (navigator.mediaDevices?.getUserMedia ? 'YES' : 'NO'));
log('SpeechRecognition: ' + (window.SpeechRecognition || window.webkitSpeechRecognition ? 'YES' : 'NO'));
log('wx env: ' + (window.__wxjs_environment || 'none'));

let mediaRecorder, stream, chunks, timerInterval, seconds;

async function startRec() {
  const btn = document.getElementById('recBtn');
  const timer = document.getElementById('timer');
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus' : 'audio/webm';
    mediaRecorder = new MediaRecorder(stream, {mimeType});
    chunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.start(250);
    btn.textContent = 'Recording...';
    btn.classList.add('recording');
    seconds = 0;
    timer.style.display = 'block';
    timer.textContent = '00:00';
    timerInterval = setInterval(() => {
      seconds++;
      const m = String(Math.floor(seconds/60)).padStart(2,'0');
      const s = String(seconds%60).padStart(2,'0');
      timer.textContent = m+':'+s;
    }, 1000);
    log('Recording started (' + mimeType + ')');
  } catch(e) {
    log('Mic error: ' + e.message);
    showResult('recResult', e.message, true);
  }
}

async function stopRec() {
  const btn = document.getElementById('recBtn');
  const timer = document.getElementById('timer');
  clearInterval(timerInterval);
  btn.textContent = 'Hold to Record';
  btn.classList.remove('recording');
  timer.style.display = 'none';
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return;

  mediaRecorder.stop();
  stream.getTracks().forEach(t => t.stop());

  // Wait for final data
  await new Promise(r => { mediaRecorder.onstop = r; });

  if (seconds < 1) { log('Too short, skipped'); return; }

  const blob = new Blob(chunks, {type: mediaRecorder.mimeType});
  log('Recorded ' + seconds + 's, ' + (blob.size/1024).toFixed(1) + 'KB');

  const ext = blob.type.includes('webm') ? 'webm' : 'ogg';
  await sendAudio(blob, 'recording.' + ext, 'recResult', 'recStatus');
}

async function uploadFile(input) {
  const file = input.files[0];
  if (!file) return;
  log('File: ' + file.name + ' (' + (file.size/1024).toFixed(1) + 'KB)');
  await sendAudio(file, file.name, 'uploadResult', 'uploadStatus');
  input.value = '';
}

async function sendAudio(blob, filename, resultId, statusId) {
  const resultEl = document.getElementById(resultId);
  const statusEl = document.getElementById(statusId);
  statusEl.textContent = 'Uploading + transcribing...';
  resultEl.style.display = 'none';

  const form = new FormData();
  form.append('file', blob, filename);

  const t0 = Date.now();
  try {
    const resp = await fetch('/api/transcribe', {method: 'POST', body: form});
    const ms = Date.now() - t0;
    const data = await resp.json();

    if (resp.ok) {
      const text = data.text || '(no speech detected)';
      showResult(resultId, text, !data.text);
      statusEl.textContent = 'Provider: ' + data.provider + ' | ' + ms + 'ms';
      log('ASR: "' + text.slice(0,30) + '" (' + ms + 'ms)');
    } else {
      const err = data.detail || JSON.stringify(data);
      showResult(resultId, 'Error: ' + err, true);
      statusEl.textContent = 'HTTP ' + resp.status + ' | ' + ms + 'ms';
      log('ASR error: ' + err);
    }
  } catch(e) {
    showResult(resultId, 'Network error: ' + e.message, true);
    statusEl.textContent = '';
    log('Network error: ' + e.message);
  }
}

function showResult(id, text, isError) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'result ' + (isError ? 'error' : 'success');
  el.style.display = 'block';
}
</script>
</body>
</html>
"""


@router.get("/test/voice", response_class=HTMLResponse)
async def voice_test_page():
    """Self-contained voice ASR test page. No auth required."""
    return _HTML
