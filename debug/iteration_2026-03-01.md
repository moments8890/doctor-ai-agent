# Debug Iteration Log — 2026-03-01

## Training Run: cardiology_v1 (llama3.2)

**Result:** 17/20 passed

---

### Failed Cases

| Case | Patient | Field | Error |
|------|---------|-------|-------|
| 013 | 唐明 (间断心前区不适半年，轻度心肌缺血) | `auxiliary_examinations` | Input should be a valid string |
| 018 | 顾建军 (慢性心衰复诊，体重增加2kg) | `follow_up_plan` | Input should be a valid string |
| 020 | 孟凡 (血脂升高多年，间断胸闷) | `treatment_plan` | Input should be a valid string |

---

### Root Cause

`llama3.2` (and occasionally other models) returns multi-item fields as **JSON arrays or nested objects** instead of flat strings. For example:

```json
"treatment_plan": ["调整降脂药", "复查血脂", "建议饮食控制"]
```

instead of the expected:

```json
"treatment_plan": "调整降脂药；复查血脂；建议饮食控制"
```

This violates the system prompt instruction ("字段值为字符串或 null，不使用数组或嵌套对象") but smaller models do not reliably follow it. Fields most prone to this are those that naturally enumerate multiple items: `treatment_plan`, `follow_up_plan`, `auxiliary_examinations`.

---

### Fix Applied

**File:** `services/structuring.py`

Added a post-parse coercion step before Pydantic validation. After `json.loads()`, iterate over all optional string fields and coerce non-string values:

- `list` → join with `；`
- `dict` → join as `key：value` pairs with `；`
- other → `str(val)`

```python
_STR_FIELDS = [
    "history_of_present_illness", "past_medical_history", "physical_examination",
    "auxiliary_examinations", "diagnosis", "treatment_plan", "follow_up_plan",
]
for field in _STR_FIELDS:
    val = data.get(field)
    if val is None or isinstance(val, str):
        continue
    if isinstance(val, list):
        data[field] = "；".join(str(item) for item in val if item)
    elif isinstance(val, dict):
        data[field] = "；".join(f"{k}：{v}" for k, v in val.items())
    else:
        data[field] = str(val)
```

This is model-agnostic: the coercion runs for all providers and models, so future model switches remain safe.

---

### Status

- [x] Fix implemented
- [ ] Re-run training to verify 20/20

---

## Training Run: cardiology_v2 (llama3.2) — DB Verification Added

**Result:** Testing revealed additional data quality issues once DB verification was enabled.

### Additional Issues Found

| Issue | Root cause | Fix |
|-------|-----------|-----|
| `这位患者叫什么名字` stored as patient name | llama3.2 extracts the agent's own question from history as the patient name | Server-side `_is_valid_patient_name()` guard in `records.py` — rejects names containing question phrases |
| `王张会` stored instead of `方建国` | llama3.2 hallucinates/garbles Chinese patient names | Model quality issue; use qwen2.5:7b which handles Chinese names reliably |
| `chief_complaint = 章丽萍` (name in wrong field) | Structuring LLM put patient name in chief_complaint | Prompt already says not to; model quality issue |
| `treatment_plan` as raw dict/list string | Old records from before the coercion fix | Coercion fix already applied; old data manually cleaned |
| Anonymous patient (`未报姓名`) always fails | LLM correctly ignores `"未报姓名"` as not a real name, so pipeline loops | Training script now provides `"匿名患者"` placeholder for anonymous cases |

### Fixes Applied

1. **`routers/records.py`**: `_is_valid_patient_name()` — rejects names containing `叫什么名字`, `这位患者`, `请问` or longer than 20 chars; applied before patient create/record save
2. **`tools/train.py`**: `--clean` flag — deletes all `train_*` patients, records, and doctor_contexts before a run
3. **`tools/train.py`**: `verify_db()` — now queries patient by name AND verifies stored name matches expected; catches hallucinated names
4. **`tools/train.py`**: Anonymous patient scenario — uses `"匿名患者"` placeholder instead of `"未报姓名"` when agent asks for name

### Recommendation

Switch `OLLAMA_MODEL` from `llama3.2` to `qwen2.5:7b` for production use. `llama3.2` hallucinated Chinese patient names on ~2/37 cases. `qwen2.5:7b` passed all 37/37 in earlier testing.

### Status

- [x] Fixes implemented
- [ ] Re-run v1 + v2 with qwen2.5:7b to confirm 0 DB-FAILs

---

## Postmerge CI Fix: text pipeline name follow-up

### Issue

`tests/integration/test_text_pipeline.py::test_missing_name_asks_then_saves` failed in CI: second turn (`陈明`) sometimes returned no record.

### Fix

1. **`routers/records.py`**: deterministic fallback for name-followup flow
2. If prior assistant turn asks patient name and current input is a name-only message, force `add_record` with extracted name
3. Exclude the name-only turn from structuring context to avoid polluting clinical text
4. **`tests/test_records_chat.py`**: added unit tests covering `create_patient`/`unknown`/missing-name routing variance

### Status

- [x] Fix implemented
- [x] Unit tests passed locally

---

## CI Automation: enable auto-merge on every PR

### Change

- Added workflow `.github/workflows/auto-enable-pr-automerge.yml`
- Trigger: `pull_request_target` on `opened`, `reopened`, `ready_for_review`
- Action: call `enablePullRequestAutoMerge` GraphQL mutation with `SQUASH`

### Result

- [x] Repository setting `allow_auto_merge` confirmed enabled
- [x] Workflow added so PRs get auto-merge enabled automatically when eligible

## Patient Schema Rename: `age` → `year_of_birth`

### Scope

- Renamed `Patient.age` column to `Patient.year_of_birth` in ORM and added startup migration to rename existing DB column in place.
- Updated patient creation flow to convert extracted `age` into `year_of_birth` at DB write time.
- Updated records/wechat/UI displays to compute age from `current_year - year_of_birth`.
- Updated admin view and CRUD tests accordingly.

### Status

- [x] Rename implemented across backend + UI
- [x] Unit tests green (`.venv/bin/python -m pytest tests/ -v`)

---

## 2026-03-03 Update: LAN Ollama + Shared Env Defaults

### Changes

- Added `OLLAMA_BASE_URL` support across routing/structuring/intent/neuro/vision providers.
- Added `OLLAMA_VISION_BASE_URL` support for image extraction path.
- Integration dependency check now uses `OLLAMA_BASE_URL` to probe `/api/tags`.
- Added DeepSeek/Gemini scenario datasets + template integration tests + batch runners.
- Set repository default env file to shared symlink target:
  - `/Users/jingwuxu/Documents/code/doctor-ai-agent-1/.env` -> `/Users/jingwuxu/Documents/code/shared-db/.env`
- Updated shared env defaults:
  - `OLLAMA_BASE_URL=http://192.168.0.123:11434/v1`
  - `OLLAMA_VISION_BASE_URL=http://192.168.0.123:11434/v1`

### Validation

- [x] Unit tests passed: `.venv/bin/python -m pytest tests/ -v` (`388 passed`)
- [x] DeepSeek integration template passed against LAN Ollama base URL (`5 passed`)

---
## Frontend Unification + Dev Admin Viewer

### Scope

- Removed legacy backend-rendered UI pages; frontend React app remains the single UI implementation.
- Added internal `/admin` route with separate backend endpoints for DB table browsing.
- Expanded admin viewer to cover all core tables with left-nav layout and dense dev-mode table utilities (CSV/JSON export, copy row).

### Status

- [x] Backend UI routes removed (`/chat`, `/manage`)
- [x] Admin APIs added for table list/counts and per-table rows
- [x] Admin page updated to dev-focused dense table mode
- [x] Unit tests green (`.venv/bin/python -m pytest tests/ -v`)

---

## Structured Logging for Task Workflows

### Scope

- Replaced legacy print-based logging helper with standard logging integration and rotating file handlers.
- Added configurable logging env vars (`LOG_LEVEL`, `LOG_TO_FILE`, `LOG_DIR`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`).
- Added task-specific structured events in `services/tasks.py` for creation, notification, scheduler tick, and failures.
- Added tests covering logger utility branches and task logging event emission paths.

### Status

- [x] Structured logger utility implemented
- [x] Rotating file output enabled and `logs/` ignored in git
- [x] Task workflow structured events implemented
- [x] Unit tests green (`.venv/bin/python -m pytest tests/ -v`)

---

## Startup Env Config + Console Noise Control

### Scope

- Added centralized app env config loader with shared `.env` priority:
  - `/Users/jingwuxu/Documents/code/shared-db/.env` first, fallback to local `.env`.
- Added startup environment logging with masked secrets and multi-line pretty output.
- Added startup Ollama connectivity check (retry + fail fast) when routing/structuring provider is `ollama`.
- Reduced terminal noise:
  - `tasks` logger hidden from terminal by default, routed to `logs/tasks.log`.
  - `apscheduler` logger hidden from terminal by default, routed to `logs/scheduler.log`.
  - Added opt-in env toggles: `TASK_LOG_TO_CONSOLE`, `SCHEDULER_LOG_TO_CONSOLE`.
- Added/updated unit tests for config parsing/masking, pretty log output, and logger routing toggles.

### Status

- [x] Shared `.env` loading + startup config struct implemented
- [x] Startup LLM connectivity check implemented
- [x] Task/scheduler terminal log suppression implemented
- [x] Unit tests green (`.venv/bin/python -m pytest tests/ -q`)

---

## Notification Pipeline Reliability + Dev Trigger

### Scope

- Hardened WeChat sender error semantics:
  - Raise on missing credentials, HTTP errors, and non-zero WeChat `errcode`.
  - No silent swallow in notification send path.
- Added retry semantics for task notifications:
  - `TASK_NOTIFY_RETRY_COUNT`
  - `TASK_NOTIFY_RETRY_DELAY_SECONDS`
  - Mark `notified_at` only after successful send.
- Added provider-based notification transport:
  - `NOTIFICATION_PROVIDER=log` (default, local/dev safe)
  - `NOTIFICATION_PROVIDER=wechat` (real channel)
- Added dev-only manual trigger endpoint:
  - `POST /api/tasks/dev/run-notifier`
  - gated by `TASK_DEV_ENDPOINT_ENABLED=true`
- Reduced scheduler noise:
  - heartbeat `scheduler_tick_start` and zero-count cycles now log at `DEBUG`.

### Status

- [x] Notification reliability fixes implemented
- [x] Provider abstraction implemented (`log` default)
- [x] Dev trigger endpoint implemented
- [x] Tests green (`.venv/bin/python -m pytest tests/ -q`)

---

## 2026-03-02 — Train-data integration manual runner + ollama hardening

### Done
- [x] Added manual train-data integration runner script: `tools/test_train_data_integration.sh`
- [x] Made train-data template tests runnable with ollama provider
- [x] Added `INTEGRATION_SERVER_URL` support for integration test targeting
- [x] Fixed ollama warmup to respect `OLLAMA_BASE_URL`
- [x] Added ollama dispatch timeout + local fallback to avoid blocking on tool-call timeouts
- [x] Unit tests passed: `.venv/bin/python -m pytest tests/ -v` (`404 passed`)
- [x] Train-data integration templates passed with current env (`7 passed, 1 skipped`)
