# Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 8 targeted backend fixes for production launch — security, concurrency, observability, and a local debug dashboard.

**Architecture:** All changes are additive or mechanical. No schema changes. The debug dashboard is a single backend-served HTML page backed by one new API endpoint. Log format changes make files machine-parseable while keeping console output human-readable.

**Tech Stack:** Python/FastAPI (backend), vanilla HTML/JS (dashboard), structlog (logging), Sentry (error alerting)

**Spec:** `docs/specs/2026-03-29-backend-hardening-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/infra/auth/unified.py` | Modify | Tighten JWT env guard |
| `src/domain/patients/interview_turn.py` | Modify | Add per-session asyncio.Lock |
| `src/domain/patients/interview_summary.py` | Modify | Clean up lock on confirm |
| `src/channels/web/doctor_interview_confirm.py` | Modify | Clean up lock on cancel |
| `src/channels/web/patient_interview_routes.py` | Modify | Clean up lock on patient cancel |
| `src/db/engine.py` | Modify | DB_ECHO env toggle |
| `src/main.py` | Modify | Sentry init |
| `requirements.txt` | Modify | Add sentry-sdk |
| `src/agent/llm.py` | Modify | Correlation fields + tokens + remove .txt files |
| `src/utils/log.py` | Modify | JSON for file handlers |
| `src/domain/diagnosis_pipeline.py` | Modify | Remove duplicate logger |
| `src/channels/web/ui/debug_handlers.py` | Modify | Add /api/debug/llm-calls + /debug page route |
| `src/channels/web/ui/debug.html` | Create | Debug dashboard HTML |
| `cli.py` | Modify | Print debug URL on startup |
| 31 files across `src/` | Modify | utcnow() → now(timezone.utc) |

---

### Task 1: Tighten JWT environment guard

**Files:**
- Modify: `src/infra/auth/unified.py:26`

- [ ] **Step 1: Edit the guard**

In `src/infra/auth/unified.py`, change line 26 in the `_secret()` function:

```python
# Before:
        if env not in ("development", "dev", "test", ""):

# After:
        if env not in ("development", "dev", "test"):
```

- [ ] **Step 2: Verify the app still starts in dev**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src ENVIRONMENT=development .venv/bin/python -c "from infra.auth.unified import _secret; print('OK:', _secret()[:10] + '...')"`

Expected: prints `OK: dev-unifie...`

- [ ] **Step 3: Verify empty env raises**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src ENVIRONMENT="" .venv/bin/python -c "from infra.auth.unified import _secret; _secret()" 2>&1 | head -3`

Expected: `RuntimeError: UNIFIED_AUTH_SECRET must be set in production.`

---

### Task 2: In-memory lock for interview turns

> **Codex review fixes applied:** lock now covers confirm/cancel paths, cleanup uses `try/finally`, doctor confirm path included.

**Files:**
- Modify: `src/domain/patients/interview_turn.py:126`
- Modify: `src/domain/patients/interview_summary.py:205`
- Modify: `src/channels/web/doctor_interview_confirm.py:20,183`
- Modify: `src/channels/web/patient_interview_routes.py:167,221`

- [ ] **Step 1: Add the lock dict, helper, and wrap interview_turn**

In `src/domain/patients/interview_turn.py`, add at module level (after the existing imports around line 15):

```python
import asyncio as _asyncio_lock

# Per-session lock to prevent concurrent interview_turn calls on the same session
# (e.g., double-tap send, browser retry). Single-instance only.
_session_locks: dict[str, "_asyncio_lock.Lock"] = {}


def get_session_lock(session_id: str) -> "_asyncio_lock.Lock":
    """Get or create the per-session asyncio.Lock."""
    return _session_locks.setdefault(session_id, _asyncio_lock.Lock())


def release_session_lock(session_id: str) -> None:
    """Remove the session lock entry when a session is finalized."""
    _session_locks.pop(session_id, None)
```

Then wrap the body of `interview_turn()` at line 126. Change:

```python
async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    session = await load_session(session_id)
```

to:

```python
async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    async with get_session_lock(session_id):
        return await _interview_turn_inner(session_id, patient_text)


async def _interview_turn_inner(session_id: str, patient_text: str) -> InterviewResponse:
    """Inner implementation — always called under the session lock."""
    session = await load_session(session_id)
```

Keep the rest of the function body unchanged, but it's now inside `_interview_turn_inner`.

- [ ] **Step 2: Wrap confirm_interview with lock + finally cleanup**

In `src/domain/patients/interview_summary.py`, wrap the `confirm_interview()` body with the session lock and use `try/finally` for cleanup:

```python
async def confirm_interview(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
    conversation: Optional[list] = None,
) -> Dict[str, int]:
    """Finalize interview: ..."""
    from domain.patients.interview_turn import get_session_lock, release_session_lock

    async with get_session_lock(session_id):
        try:
            # ... existing function body unchanged ...
            return result
        finally:
            release_session_lock(session_id)
```

- [ ] **Step 3: Wrap doctor confirm endpoint with lock cleanup**

In `src/channels/web/doctor_interview_confirm.py`, find the confirm endpoint (around line 20) and add lock cleanup in a `finally` block. Also add cleanup to the cancel endpoint (line 172):

For the **confirm** endpoint, add after the `confirm_interview()` call returns:
```python
    from domain.patients.interview_turn import release_session_lock
    release_session_lock(body.session_id)
```

For the **cancel** endpoint (line 183), after `session.status = InterviewStatus.abandoned`:
```python
    from domain.patients.interview_turn import release_session_lock
    release_session_lock(body.session_id)
```

- [ ] **Step 4: Wrap patient confirm/cancel with lock cleanup**

In `src/channels/web/patient_interview_routes.py`:

For the **confirm** path (around line 167), add after confirm completes:
```python
    from domain.patients.interview_turn import release_session_lock
    release_session_lock(session_id)
```

For the **cancel** path (line 221), after `session.status = InterviewStatus.abandoned`:
```python
    from domain.patients.interview_turn import release_session_lock
    release_session_lock(session_id)
```

---

### Task 3: SQL echo environment toggle

**Files:**
- Modify: `src/db/engine.py:55,61`

- [ ] **Step 1: Make echo configurable**

In `src/db/engine.py`, change both `echo=False` occurrences.

Line 55 (SQLite path):
```python
# Before:
        echo=False,
# After:
        echo=os.environ.get("DB_ECHO", "false").lower() == "true",  # WARNING: logs SQL with params — may contain PHI. Dev/debug only.
```

Line 61 (MySQL path):
```python
# Before:
        echo=False,
# After:
        echo=os.environ.get("DB_ECHO", "false").lower() == "true",  # WARNING: logs SQL with params — may contain PHI. Dev/debug only.
```

> **Codex review note:** DB_ECHO dumps raw SQL with bound parameters into logs. For a medical app this includes patient data. Never enable in production. Comment makes this explicit.

- [ ] **Step 2: Verify default is off**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src .venv/bin/python -c "from db.engine import engine; print('echo:', engine.echo)"`

Expected: `echo: False`

---

### Task 4: Sentry integration

**Files:**
- Modify: `requirements.txt`
- Modify: `src/main.py:92`

- [ ] **Step 1: Add sentry-sdk to requirements**

In `requirements.txt`, add after the `structlog` line:

```
sentry-sdk[fastapi]>=2.0.0     # error alerting (optional, set SENTRY_DSN to enable)
```

- [ ] **Step 2: Install the dependency**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/pip install "sentry-sdk[fastapi]>=2.0.0"`

- [ ] **Step 3: Add _init_sentry to main.py**

In `src/main.py`, add this function before the `lifespan` function (before line 91):

```python
def _init_sentry() -> None:
    """Initialize Sentry error tracking. No-op if SENTRY_DSN is not set."""
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
            environment=os.environ.get("ENVIRONMENT", "development"),
        )
        logging.getLogger("startup").info("[Sentry] initialized (dsn=%s...)", dsn[:20])
    except ImportError:
        logging.getLogger("startup").warning("[Sentry] sentry-sdk not installed, skipping")
```

- [ ] **Step 4: Call it at the top of lifespan**

In `src/main.py`, inside the `lifespan` function, add `_init_sentry()` as the very first line after `_startup_log = ...` (line 94):

```python
    _startup_log = logging.getLogger("startup")
    _init_sentry()  # ← ADD THIS LINE
    # Production guards FIRST ...
```

---

### Task 5: LLM call correlation + token tracking

> **Codex review fix applied:** Uses `get_current_trace_id()` from observability (set by HTTP middleware) instead of `_ctx_trace_id` from log module (only set for WeChat). Adds `bind_log_context()` to web chat handler for doctor_id/intent.

**Files:**
- Modify: `src/agent/llm.py:66-122` (_log_llm_call), `src/agent/llm.py:191-226` (structured_call), `src/agent/llm.py:229-273` (llm_call)
- Modify: `src/channels/web/chat.py:107` (bind log context for web requests)

- [ ] **Step 1: Bind log context in web chat handler**

In `src/channels/web/chat.py`, add the import at the top:
```python
from utils.log import bind_log_context
```

Then in the `chat()` endpoint (line 90), after `doctor_id` is resolved (line 100) and before `handle_turn` (line 107), add:
```python
    bind_log_context(doctor_id=doctor_id)
```

This ensures `_ctx_doctor_id` is set for all web chat requests, not just WeChat.

- [ ] **Step 2: Add correlation fields + usage param to _log_llm_call**

In `src/agent/llm.py`, change the `_log_llm_call` signature and add correlation + usage fields to the entry dict.

Change line 66:
```python
# Before:
def _log_llm_call(op_name: str, model: str, messages: list, output: Any = None) -> None:

# After:
def _log_llm_call(op_name: str, model: str, messages: list, output: Any = None, *, usage: Any = None) -> None:
```

Then after the `entry` dict is built (after line 89 where `entry["output"]` is set), add:

```python
        # Correlation: trace_id from HTTP middleware (observability ContextVar)
        from infra.observability.observability import get_current_trace_id
        # doctor_id and intent from log ContextVars (set by chat handlers)
        from utils.log import _ctx_doctor_id, _ctx_intent
        entry["trace_id"] = get_current_trace_id() or ""
        entry["doctor_id"] = _ctx_doctor_id.get("")
        entry["intent"] = _ctx_intent.get("")

        # Token usage from LLM response
        if usage is not None:
            entry["tokens"] = {
                "prompt": getattr(usage, "prompt_tokens", 0),
                "completion": getattr(usage, "completion_tokens", 0),
                "total": getattr(usage, "total_tokens", 0),
            }
```

- [ ] **Step 2: Capture usage in llm_call**

In `src/agent/llm.py`, inside the `llm_call` function, modify the `_call` closure to capture usage. Change the `_call` function (around line 245):

```python
    _last_usage = None  # captured from the response

    async def _call(model_name: str) -> str:
        nonlocal _last_usage
        client = _get_client(env_var)
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        extra = _extra_body(model_name)
        if extra:
            kwargs["extra_body"] = extra

        response = await client.chat.completions.create(**kwargs)
        _last_usage = getattr(response, "usage", None)
        raw = response.choices[0].message.content or ""
        return clean_llm_output(raw)
```

Then change the `_log_llm_call` call at line 272:

```python
# Before:
    _log_llm_call(op_name, model, messages, result)

# After:
    _log_llm_call(op_name, model, messages, result, usage=_last_usage)
```

- [ ] **Step 3: Pass usage in structured_call**

In `src/agent/llm.py`, inside `structured_call`, instructor returns the Pydantic model directly. To get usage, capture it from the raw response. Modify the `_call` closure (around line 210):

```python
    _last_usage = None

    async def _call(model_name: str) -> T:
        nonlocal _last_usage
        instructor_client = _get_instructor_client(env_var)
        result = await instructor_client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
        # instructor attaches _raw_response on the Pydantic model
        raw_resp = getattr(result, "_raw_response", None)
        if raw_resp:
            _last_usage = getattr(raw_resp, "usage", None)
        return result
```

Then change the `_log_llm_call` call at line 225:

```python
# Before:
    _log_llm_call(op_name, model, messages, result)

# After:
    _log_llm_call(op_name, model, messages, result, usage=_last_usage)
```

- [ ] **Step 4: Verify correlation fields appear**

After restarting the server and sending one chat message, check:

Run: `tail -1 /Volumes/ORICO/Code/doctor-ai-agent/logs/llm_calls.jsonl | python3 -m json.tool | grep -E 'trace_id|doctor_id|intent|tokens'`

Expected: `trace_id`, `doctor_id`, `intent` fields present (possibly empty strings if no request context). `tokens` field present if the provider returns usage data.

---

### Task 6: Log restructuring

**Files:**
- Modify: `src/agent/llm.py:66-122` (remove .txt file generation)
- Modify: `src/domain/diagnosis_pipeline.py:34-54` (remove duplicate logger)
- Modify: `src/utils/log.py:165-183` (JSON for file handlers)

- [ ] **Step 1: Remove per-call .txt file generation from _log_llm_call**

In `src/agent/llm.py`, inside `_log_llm_call()`, delete the entire block that writes per-call .txt files (approximately lines 91-113). Remove everything from `# 1. Per-call human-readable file` through the `per_call.write_text(...)` line. Keep only the `# 2. Append to rotated JSONL file` block.

Also remove the `_LLM_LOG_DIR` constant (line 36) since it's no longer needed:
```python
# DELETE this line:
_LLM_LOG_DIR = _REPO_ROOT / "logs" / "llm_debug"
```

- [ ] **Step 2: Migrate diagnosis logger fields, then remove separate logger**

> **Codex review fix:** `_log_llm_io()` logs `record_id` and `matched_cases_count` which `_log_llm_call()` doesn't capture. Instead of deleting blindly, first check what fields are logged, pass useful ones as metadata through the existing structured_call/llm_call path.

In `src/domain/diagnosis_pipeline.py`:
1. Find all calls to `_log_llm_io(...)` — note what extra fields they log (e.g., `record_id`, `matched_cases_count`)
2. For each call site, replace with a `log()` call that captures the same context:
   ```python
   from utils.log import log
   log("[diagnosis] llm_io", record_id=record_id, matched_cases=len(matched_cases))
   ```
3. Delete the separate logger setup (lines 34-54) and the `_log_llm_io` function
4. Delete `logs/diagnosis_llm.jsonl` — the data now flows through `app.log` (JSON) and `llm_calls.jsonl`

- [ ] **Step 3: JSON format for file handlers, text for console**

In `src/utils/log.py`, modify `init_logging()` (line 165) to use separate formatters:

```python
# Before (line 175):
    formatter = _build_formatter(use_json)
    _configure_structlog(formatter, level)

# After:
    console_formatter = _build_formatter(use_json)
    file_formatter = _build_formatter(use_json=True)  # always JSON for files
    _configure_structlog(console_formatter, level)
```

Then change `_attach_file_handlers` call (line 183):

```python
# Before:
        _attach_file_handlers(formatter, level, root, task_logger, scheduler_logger)

# After:
        _attach_file_handlers(file_formatter, level, root, task_logger, scheduler_logger)
```

- [ ] **Step 4: Update debug logs endpoint for JSON format**

> **Codex review fix:** The existing `/api/debug/logs` endpoint filters by text tags like `[ERROR]`. After switching to JSON file format, those tags won't exist. Update the endpoint to parse JSON.

In `src/channels/web/ui/debug_handlers.py`, rewrite the `debug_logs` endpoint body (around line 44). Replace the text tag filtering with JSON parsing:

```python
@router.get("/api/debug/logs")
async def debug_logs(
    level: str = Query(default="ALL"),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    source: str = Query(default="app"),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    _require_ui_debug_access(x_debug_token)
    log_path = Path(_LOG_SOURCES.get(source, f"{_LOG_ROOT}/app.log"))
    if not log_path.exists():
        return {"lines": [], "source": source, "total": 0}
    level_upper = level.upper()
    level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_priority = level_priority.get(level_upper, -1)  # -1 = ALL
    matching: list[str] = []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.rstrip()
                if not stripped:
                    continue
                if min_priority >= 0:
                    # Try JSON parse first (new format)
                    try:
                        obj = json.loads(stripped)
                        line_level = obj.get("level", "info").upper()
                        if level_priority.get(line_level, 0) >= min_priority:
                            matching.append(stripped)
                        continue
                    except (json.JSONDecodeError, ValueError):
                        pass
                    # Fall back to text tag matching (old format lines still in log)
                    if any(tag in stripped for tag in _LOG_LEVEL_TAGS.get(level_upper, [])):
                        matching.append(stripped)
                else:
                    matching.append(stripped)
    except OSError:
        return {"lines": [], "source": source, "total": 0}
    return {"lines": matching[-limit:], "source": source, "total": len(matching)}
```

Add `import json` to the top of the file if not already present.

- [ ] **Step 5: Verify app.log is now JSON**

Restart the server, then check the last line of app.log:

Run: `tail -1 /Volumes/ORICO/Code/doctor-ai-agent/logs/app.log | python3 -m json.tool | head -5`

Expected: Valid JSON with `"event"`, `"level"`, `"timestamp"` keys.

---

### Task 7: Debug dashboard

**Files:**
- Modify: `src/channels/web/ui/debug_handlers.py`
- Create: `src/channels/web/ui/debug.html`
- Modify: `cli.py:743`

- [ ] **Step 1: Add /api/debug/llm-calls endpoint**

In `src/channels/web/ui/debug_handlers.py`, add the following imports at the top (after existing imports):

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi.responses import FileResponse
```

Then add the endpoint at the end of the file:

```python
_LLM_LOG_FILE = Path(__file__).resolve().parents[4] / "logs" / "llm_calls.jsonl"


@router.get("/api/debug/llm-calls")
async def debug_llm_calls(
    limit: int = Query(default=30, ge=1, le=200),
    op: Optional[str] = Query(default=None),
    doctor_id: Optional[str] = Query(default=None),
    trace_id: Optional[str] = Query(default=None),
    since_minutes: int = Query(default=60, ge=1, le=1440),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Return recent LLM calls with filtering. Reads from llm_calls.jsonl tail."""
    _require_ui_debug_access(x_debug_token)
    if not _LLM_LOG_FILE.exists():
        return {"calls": [], "total": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    cutoff_iso = cutoff.isoformat()

    matching: list[dict] = []
    try:
        with open(_LLM_LOG_FILE, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Time filter
                ts = entry.get("timestamp", "")
                if ts < cutoff_iso:
                    continue
                # Op filter
                if op and entry.get("op") != op:
                    continue
                # Doctor filter
                if doctor_id and entry.get("doctor_id") != doctor_id:
                    continue
                # Trace filter
                if trace_id and entry.get("trace_id") != trace_id:
                    continue
                matching.append(entry)
    except OSError:
        return {"calls": [], "total": 0}

    # Return newest first, up to limit
    matching = matching[-limit:]
    matching.reverse()
    return {"calls": matching, "total": len(matching)}


@router.get("/debug", include_in_schema=False)
async def debug_dashboard_page(token: str = Query(..., description="Debug access token")):
    """Serve the debug dashboard HTML page. Token required."""
    _require_ui_debug_access(token)
    return FileResponse(
        Path(__file__).parent / "debug.html",
        media_type="text/html",
    )
```

- [ ] **Step 2: Create debug.html**

Create the file `src/channels/web/ui/debug.html`. This is a large self-contained HTML file with 4 tabs. The agent implementing this task should build it with:

**Structure:**
- Tab bar: Requests | LLM Calls | Errors | Health
- Global controls: time range dropdown, auto-refresh toggle, token input (persisted to localStorage)
- All API calls include `X-Debug-Token` header from localStorage

**Tab 1 — Requests:**
- Fetch from `/api/debug/observability` (traces + spans)
- List of recent requests: method, path, status badge (green/red), latency, timestamp
- Click to expand: span waterfall (colored bars proportional to latency), linked LLM calls (fetch from `/api/debug/llm-calls?trace_id=X`)
- Filters: status (all/2xx/4xx/5xx), path search text input

**Tab 2 — LLM Calls:**
- Fetch from `/api/debug/llm-calls`
- List of calls: op badge, model, tokens, latency, timestamp
- Click to expand: collapsible sections for SYSTEM prompt, USER message, OUTPUT (JSON pretty-printed)
- Filters: op dropdown (routing/diagnosis/interview/structuring/etc.), model dropdown

**Tab 3 — Errors:**
- Fetch from `/api/debug/logs?level=ERROR&limit=100`
- Parse JSON lines, show: timestamp, event message, trace_id (clickable → switches to Requests tab filtered by that trace)
- Error count badge in tab header

**Tab 4 — Health:**
- Fetch from `/healthz` (system status)
- Fetch from `/api/debug/observability` (latency summary: p50/p95/p99)
- Fetch from `/api/debug/routing-metrics` (fast vs LLM hit rate)
- Display as cards with numbers

**Style guidelines:**
- Dark background (#1a1a2e), light text, monospace for code/JSON
- Status badges: green (200), yellow (4xx), red (5xx)
- Expandable rows: click to toggle, smooth transition
- Mobile-responsive: single column on narrow screens
- Auto-refresh: 30s default, toggle button to pause
- Token: prompt on first visit, save to localStorage, include in all API requests as `X-Debug-Token` header

**Size target:** ~800-1200 lines of self-contained HTML/CSS/JS. No external dependencies.

- [ ] **Step 3: Add debug URL to cli.py**

In `cli.py`, modify `_print_urls` (line 737). Add the debug URL line after the WeChat URL:

```python
# Before:
    print(f"  WeChat URL : http://127.0.0.1:{port}/wechat")
    print(f"  Docs       : http://127.0.0.1:{port}/docs")

# After:
    print(f"  WeChat URL : http://127.0.0.1:{port}/wechat")
    print(f"  Debug      : http://127.0.0.1:{port}/debug")
    print(f"  Docs       : http://127.0.0.1:{port}/docs")
```

- [ ] **Step 4: Verify dashboard loads**

Start the server and open `http://localhost:8000/debug?token=YOUR_DEBUG_TOKEN` in a browser. Verify:
- Page loads without errors
- 4 tabs are visible and clickable
- Requests tab shows recent traces (or empty state if no recent requests)
- LLM Calls tab shows recent calls (or empty state)
- Health tab shows system status from /healthz

---

### Task 8: Bulk datetime.utcnow() migration

**Files:**
- Modify: 31 files across `src/` (40 occurrences)

- [ ] **Step 1: Find all occurrences**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && grep -rn "datetime\.utcnow\(\)\|utcfromtimestamp" src/ --include="*.py" | wc -l`

Note the count for verification after the migration.

- [ ] **Step 2: Replace utcnow() with now(timezone.utc)**

For each file found in step 1, replace:
- `datetime.utcnow()` → `datetime.now(timezone.utc)`
- `_dt.utcnow()` → `_dt.now(timezone.utc)` (the alias used in `llm.py`)
- `datetime.utcfromtimestamp(x)` → `datetime.fromtimestamp(x, tz=timezone.utc)`

Ensure each modified file has the `timezone` import. Common patterns:
- If file has `from datetime import datetime` → change to `from datetime import datetime, timezone`
- If file has `from datetime import datetime as _dt` → also import timezone
- If file has `import datetime` → use `datetime.timezone.utc`

- [ ] **Step 3: Verify zero occurrences remain**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && grep -rn "datetime\.utcnow\(\)\|\.utcfromtimestamp(" src/ --include="*.py" | wc -l`

Expected: `0`

- [ ] **Step 4: Verify app starts cleanly**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && PYTHONPATH=src ENVIRONMENT=development .venv/bin/python -c "from main import app; print('OK')"`

Expected: `OK` (no import errors from timezone changes)

---

## Execution Order

```
Task 1 (JWT guard)           — independent
Task 2 (Interview lock)      — independent
Task 3 (SQL echo)            — independent
Task 4 (Sentry)              — independent
Task 5 (LLM correlation)     — independent, but must complete before 6 and 7
Task 6 (Log restructuring)   — depends on 5
Task 7 (Debug dashboard)     — depends on 5 and 6
Task 8 (utcnow migration)    — independent, do last (touches many files)
```

Tasks 1-4 can all run in parallel. Task 5 next. Then 6. Then 7. Then 8 last.
