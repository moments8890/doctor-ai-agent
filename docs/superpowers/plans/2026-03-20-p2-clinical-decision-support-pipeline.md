# P2: Clinical Decision Support Pipeline — Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI diagnosis pipeline that auto-generates differential diagnoses, workup, and treatment suggestions. Results display in the doctor's review workflow. Case history matching integrated into chat.

**Architecture:** `run_diagnosis()` is a single pipeline function shared by APScheduler (auto-run) and chat tool (on-demand). Uses the same AsyncOpenAI + JSON mode + retry pattern as `structuring.py`. Immutable `ai_output` + separate `doctor_decisions` in the DB. Frontend adds DiagnosisSection to ReviewDetail.

**Tech Stack:** Python 3.9 / FastAPI / SQLAlchemy async / AsyncOpenAI / React 19 / MUI 7

**Spec:** `docs/superpowers/specs/2026-03-20-p2-clinical-decision-support-pipeline-design.md`

**Testing policy (per AGENTS.md):** Integration tests required for diagnosis pipeline (safety-critical). No unit tests for non-critical modules unless asked.

---

## File Map

### New files (6)
| File | Responsibility |
|------|---------------|
| `src/db/models/diagnosis_result.py` | DiagnosisResult ORM model + DiagnosisStatus enum + dataclasses |
| `src/db/crud/diagnosis.py` | CRUD: create pending, save completed, get by record, update decisions, compute agreement |
| `src/domain/diagnosis.py` | Pipeline: run_diagnosis(), prompt builder, LLM call, response parser, validation |
| `src/agent/tools/diagnosis.py` | `diagnose()` agent tool + `_build_case_context()` cached injection |
| `src/channels/web/ui/diagnosis_handlers.py` | API endpoints: GET diagnosis by record, PATCH decide on items |
| `frontend/web/src/pages/doctor/DiagnosisSection.jsx` | Diagnosis display: similar cases, red flags, differentials, workup, treatment, confirm/reject |

### Modified files (10)
| File | Change |
|------|--------|
| `src/db/models/__init__.py` | Import DiagnosisResult |
| `src/utils/runtime_config.py` | Add `DIAGNOSIS_LLM` default |
| `src/utils/runtime_config_meta.py` | Add `DIAGNOSIS_LLM` to config categories |
| `src/startup/scheduler.py` | Add `run_pending_diagnoses` job with lease |
| `src/agent/setup.py` | Register `diagnose()` tool in extended set |
| `src/agent/handle_turn.py` | Inject cached case context into agent messages |
| `src/db/crud/review.py` | Join diagnosis_results in list_reviews(), return diagnosis_status |
| `src/channels/web/ui/__init__.py` | Include diagnosis router |
| `frontend/web/src/api.js` | Add diagnosis API functions |
| `frontend/web/src/pages/doctor/constants.jsx` | Add DIAGNOSIS_STATUS_LABEL |
| `frontend/web/src/pages/doctor/ReviewDetail.jsx` | Add DiagnosisSection when results exist |
| `frontend/web/src/pages/doctor/TasksSection.jsx` | Render diagnosis status chip from joined data |

---

### Task 1: DiagnosisResult ORM Model + Config

**Files:**
- Create: `src/db/models/diagnosis_result.py`
- Modify: `src/db/models/__init__.py`
- Modify: `src/utils/runtime_config.py`
- Modify: `src/utils/runtime_config_meta.py`

- [ ] **Step 1: Create the DiagnosisResult model**

Create `src/db/models/diagnosis_result.py` with:
- `DiagnosisStatus(str, Enum)`: pending, completed, confirmed, failed
- `DiagnosisResult(Base)` ORM model matching the spec's schema:
  - id, record_id (UNIQUE), doctor_id, ai_output (TEXT/JSON), doctor_decisions (TEXT/JSON),
    red_flags (TEXT/JSON), case_references (TEXT/JSON), status, agreement_score (Float),
    error_message, created_at, completed_at, confirmed_at
  - FK to medical_records.id and doctors.doctor_id
  - Index on (doctor_id, status)
- Follow the pattern in `src/db/models/review_queue.py` for column types and imports
- Use `from __future__ import annotations` and `Optional[X]` (Python 3.9)

- [ ] **Step 2: Register in model registry**

In `src/db/models/__init__.py`, add import and `__all__` entry for `DiagnosisResult` and `DiagnosisStatus`.

- [ ] **Step 3: Add DIAGNOSIS_LLM config**

In `src/utils/runtime_config.py`, add to `DEFAULT_RUNTIME_CONFIG`:
```python
"DIAGNOSIS_LLM": "",  # defaults to STRUCTURING_LLM if empty
```

In `src/utils/runtime_config_meta.py`, add to the `"llm"` category keys list and add descriptions.

- [ ] **Step 4: Verify + Commit**

```bash
PYTHONPATH=src .venv/bin/python -c "from db.models.diagnosis_result import DiagnosisResult, DiagnosisStatus; print('OK')"
git add src/db/models/diagnosis_result.py src/db/models/__init__.py src/utils/runtime_config.py src/utils/runtime_config_meta.py
git commit -m "feat(p2): add DiagnosisResult ORM model + DiagnosisStatus enum + config"
```

---

### Task 2: Diagnosis CRUD

**Files:**
- Create: `src/db/crud/diagnosis.py`

- [ ] **Step 1: Create the CRUD module**

Functions needed (follow patterns in `src/db/crud/review.py`):

```python
async def create_pending_diagnosis(session, record_id, doctor_id) -> DiagnosisResult:
    """Create a pending diagnosis_results row (status=pending)."""

async def save_completed_diagnosis(session, diagnosis_id, ai_output_json, red_flags, case_references) -> DiagnosisResult:
    """Update pending → completed with AI results."""

async def save_failed_diagnosis(session, diagnosis_id, error_message) -> DiagnosisResult:
    """Update pending → failed with error."""

async def get_diagnosis_by_record(session, record_id, doctor_id) -> Optional[DiagnosisResult]:
    """Get diagnosis for a record (scoped by doctor_id)."""

async def update_item_decision(session, diagnosis_id, doctor_id, item_type, index, decision) -> Optional[DiagnosisResult]:
    """Update doctor_decisions JSON for a specific item. ai_output never touched."""

async def confirm_diagnosis(session, diagnosis_id, doctor_id) -> Optional[DiagnosisResult]:
    """Set status=confirmed, compute agreement_score from doctor_decisions vs ai_output."""
```

The `confirm_diagnosis` function computes `agreement_score`:
```python
total = len(differentials) + len(workup) + len(treatment)
rejected = count of items with decision="rejected"
agreement_score = (total - rejected) / total if total > 0 else 1.0
```

- [ ] **Step 2: Verify + Commit**

```bash
PYTHONPATH=src .venv/bin/python -c "from db.crud.diagnosis import create_pending_diagnosis, confirm_diagnosis; print('OK')"
git add src/db/crud/diagnosis.py
git commit -m "feat(p2): add diagnosis CRUD — create, save, get, decide, confirm"
```

---

### Task 3: Diagnosis Pipeline

**Files:**
- Create: `src/domain/diagnosis.py`

This is the core module (~200 lines). Follow the `structuring.py` pattern exactly.

- [ ] **Step 1: Create the pipeline module**

Key function: `async def run_diagnosis(doctor_id, record_id=None, clinical_text=None) -> dict`

Steps inside:
1. **Load clinical context:** If `record_id` → load `medical_records.structured` from DB, parse JSON.
   If `clinical_text` → call `structure_medical_record(clinical_text, doctor_id)` to extract structured fields.
2. **Match cases:** `await match_cases(session, doctor_id, chief_complaint, limit=5)`
3. **Load skill:** `get_diagnosis_skill("neurology")` (hardcoded for MVP, extensible later)
4. **Load knowledge:** `await load_knowledge_context_for_prompt(session, doctor_id, chief_complaint)`
5. **Build prompt:** System = skill + matched cases + knowledge. User = structured record fields.
6. **Call LLM:** Same pattern as `structuring.py`:
   - Resolve provider from `DIAGNOSIS_LLM` env var (fall back to `STRUCTURING_LLM`)
   - `_get_structuring_client()` equivalent for diagnosis (or reuse the same client cache)
   - `response_format={"type": "json_object"}`, `temperature=0`, `max_tokens=3000`
   - `call_with_retry_and_fallback()` with cloud fallback
7. **Parse + validate:** Extract JSON, validate fields, coerce confidence values, cap array sizes
8. **Save:** If `record_id` provided → create/update `diagnosis_results`. If chat-only → return without saving.
9. **Return:** Parsed result dict

Key imports to reference:
```python
from domain.records.structuring import structure_medical_record  # for chat path
from db.crud.case_history import match_cases
from domain.knowledge.skill_loader import get_diagnosis_skill
from domain.knowledge.doctor_knowledge import load_knowledge_context_for_prompt
from infra.llm.resilience import call_with_retry_and_fallback
```

**Provider resolution:** There is no shared `resolve_provider()` function.
Replicate the `_resolve_provider()` pattern from `structuring.py` locally
in `diagnosis.py`, reading from `DIAGNOSIS_LLM` env var (falling back to
`STRUCTURING_LLM` if empty). See `structuring.py` lines 40-85 for the
exact pattern: read env var → look up in `_PROVIDERS` dict from
`infra.llm.client` → get base_url + api_key + model.

**Return type:** Return a plain `dict` matching the `DiagnosisOutput`
structure (not the dataclass itself). Consumers (CRUD, chat tool) work
with dicts for JSON serialization simplicity. The dataclass definitions
in the spec serve as documentation of the expected shape.

Error handling per spec: LLM timeout → failed, invalid JSON → partial parse attempt, schema validation → drop malformed items, empty differentials → failed.

- [ ] **Step 2: Verify + Commit**

```bash
PYTHONPATH=src .venv/bin/python -c "from domain.diagnosis import run_diagnosis; print('OK')"
git add src/domain/diagnosis.py
git commit -m "feat(p2): add diagnosis pipeline — prompt builder, LLM call, parser, validation"
```

---

### Task 4: APScheduler Job

**Files:**
- Modify: `src/startup/scheduler.py`

- [ ] **Step 1: Add the diagnosis scheduler job**

Add a new function `run_pending_diagnoses()` and register it in `configure_scheduler()`.

Follow the lease pattern from `src/domain/tasks/task_crud.py` lines 308-325
(NOT from `scheduler.py` which has no lease usage):
- Acquire a lease via `SchedulerLease` before processing to prevent duplicate runs in multi-instance deployments
- Query: `select(ReviewQueue).outerjoin(DiagnosisResult, ...).where(status=pending_review, DiagnosisResult.id.is_(None)).limit(5)`
- For each result: call `await run_diagnosis(doctor_id=rq.doctor_id, record_id=rq.record_id)`
- Wrap in try/except per record (one failure doesn't block others)
- Register as interval job: 1 minute

Add imports: `from db.models.review_queue import ReviewQueue`, `from db.models.diagnosis_result import DiagnosisResult`, `from domain.diagnosis import run_diagnosis`

- [ ] **Step 2: Commit**

```bash
git add src/startup/scheduler.py
git commit -m "feat(p2): add run_pending_diagnoses scheduler job (1-min interval, lease-based)"
```

---

### Task 5: Chat Integration — Case Context Injection

**Files:**
- Create: `src/agent/tools/diagnosis.py` (partial — case context function)
- Modify: `src/agent/handle_turn.py`

- [ ] **Step 1: Create `_build_case_context()` with cache**

In `src/agent/tools/diagnosis.py`, add the cached case context builder:

```python
_case_context_cache: Dict[str, Tuple[str, float]] = {}

async def _build_case_context(doctor_id: str, chief_complaint: str) -> str:
    """Build case context string with 5-min TTL cache."""
    cache_key = f"{doctor_id}:{chief_complaint[:50]}"
    now = time.time()
    if cache_key in _case_context_cache:
        cached, ts = _case_context_cache[cache_key]
        if now - ts < 300:
            return cached
    async with AsyncSessionLocal() as session:
        matched = await match_cases(session, doctor_id, chief_complaint, limit=2)
    if not matched:
        return ""
    lines = [f"- {m['chief_complaint'][:30]} → {m['final_diagnosis']} ({m['similarity']:.0%})"
             for m in matched]
    context = "【类似病例参考】\n" + "\n".join(lines)
    _case_context_cache[cache_key] = (context, now)
    return context
```

- [ ] **Step 2: Inject in handle_turn.py**

In `src/agent/handle_turn.py`, find where the agent is called. Before the agent call, if a patient is in working context, build case context and prepend to the user message or inject as a system message.

Read `handle_turn.py` first to find the exact injection point. Look for where `SessionAgent.handle()` is called and where the working context (current patient) is available.

- [ ] **Step 3: Commit**

```bash
git add src/agent/tools/diagnosis.py src/agent/handle_turn.py
git commit -m "feat(p2): inject cached case context into agent messages when patient active"
```

---

### Task 6: Chat Integration — diagnose() Tool

**Files:**
- Modify: `src/agent/tools/diagnosis.py` (add the tool)
- Modify: `src/agent/setup.py`

- [ ] **Step 1: Add the diagnose() tool**

In `src/agent/tools/diagnosis.py`, add:

```python
@tool
async def diagnose() -> Dict[str, Any]:
    """为当前患者生成AI鉴别诊断建议。"""
    doctor_id = get_current_identity()
    # 1. Get current patient from working context
    # 2. Try: find latest medical record for patient
    #    → run_diagnosis(doctor_id=doctor_id, record_id=record.id)
    # 3. Fallback: scan chat history (same pattern as _create_pending_record)
    #    from agent import session as _session_mod
    #    history = _session_mod.get_agent_history(doctor_id)
    #    → extract relevant messages
    #    → run_diagnosis(doctor_id=doctor_id, clinical_text=joined_text)
    # 4. Format result conversationally and return
```

Follow the `_create_pending_record` pattern in `src/agent/tools/doctor.py` lines 160-190 for the history scanning fallback.

- [ ] **Step 2: Register in setup.py**

In `src/agent/setup.py`, add `diagnose` to the extended tool set (gated behind `Action.diagnosis`).

- [ ] **Step 3: Commit**

```bash
git add src/agent/tools/diagnosis.py src/agent/setup.py
git commit -m "feat(p2): add diagnose() chat tool with dual-mode input (record + history)"
```

---

### Task 7: API Endpoints

**Files:**
- Create: `src/channels/web/ui/diagnosis_handlers.py`
- Modify: `src/channels/web/ui/__init__.py`
- Modify: `src/db/crud/review.py`

- [ ] **Step 1: Create diagnosis endpoints**

Three endpoints following existing handler patterns (`review_handlers.py`):

```python
@router.get("/api/manage/diagnosis/{record_id}")
async def get_diagnosis(record_id, doctor_id, authorization):
    """Get diagnosis results for a record. Returns ai_output + doctor_decisions + status."""

@router.patch("/api/manage/diagnosis/{diagnosis_id}/decide")
async def decide_item(diagnosis_id, body: ItemDecision, doctor_id, authorization):
    """Update doctor decision on a specific item. Body: {type, index, decision}"""

@router.post("/api/manage/diagnosis/{diagnosis_id}/confirm")
async def confirm_diagnosis_endpoint(diagnosis_id, doctor_id, authorization):
    """Confirm diagnosis: status→confirmed, compute agreement_score.
    Called when doctor taps '确认审核' in ReviewDetail (alongside review confirm)."""
```

**Integration note:** The existing `confirm_review_endpoint` in
`review_handlers.py` should also call the diagnosis confirm endpoint
(or the CRUD function directly) when a diagnosis_results row exists.
Add this to Task 7 as a modification to `review_handlers.py`.

Both use `_resolve_ui_doctor_id()`, `enforce_doctor_rate_limit()`, `safe_create_task(audit(...))`.

- [ ] **Step 2: Update list_reviews() to join diagnosis status**

In `src/db/crud/review.py`, modify `list_reviews()` to LEFT JOIN `diagnosis_results` on `record_id` and return `diagnosis_status` per item. This way the frontend queue list can show "诊断中" / "诊断完成" chips without a separate API call.

- [ ] **Step 3: Include router + Commit**

In `src/channels/web/ui/__init__.py`, add the diagnosis router.

```bash
git add src/channels/web/ui/diagnosis_handlers.py src/channels/web/ui/__init__.py src/db/crud/review.py
git commit -m "feat(p2): add diagnosis API endpoints + join diagnosis status in review list"
```

---

### Task 8: Frontend API + Constants

**Files:**
- Modify: `frontend/web/src/api.js`
- Modify: `frontend/web/src/pages/doctor/constants.jsx`

- [ ] **Step 1: Add API functions**

```javascript
// Diagnosis
export async function getDiagnosis(recordId, doctorId) {
  return request(`/api/manage/diagnosis/${recordId}?doctor_id=${doctorId}`);
}

export async function decideDiagnosisItem(diagnosisId, doctorId, type, index, decision) {
  return request(`/api/manage/diagnosis/${diagnosisId}/decide?doctor_id=${doctorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, index, decision }),
  });
}
```

- [ ] **Step 2: Add constants**

```javascript
export const DIAGNOSIS_STATUS_LABEL = {
  pending: "诊断中",
  completed: "诊断完成",
  confirmed: "已确认",
  failed: "诊断失败",
};

export const DIAGNOSIS_STATUS_COLOR = {
  pending: "#1890ff",      // blue
  completed: "#07C160",    // green
  confirmed: "#999",       // grey
  failed: "#FA5151",       // red
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/api.js frontend/web/src/pages/doctor/constants.jsx
git commit -m "feat(p2): add diagnosis API client + status label constants"
```

---

### Task 9: DiagnosisSection Component

**Files:**
- Create: `frontend/web/src/pages/doctor/DiagnosisSection.jsx`

- [ ] **Step 1: Create DiagnosisSection**

A React component that renders the diagnosis results. Receives props: `diagnosis` (the API response), `doctorId`, `onDecide` callback.

Sections in order (per spec):
1. **📋 您的类似病例** — `case_references` array, show similarity + chief complaint + diagnosis + treatment
2. **⚠️ 危险信号** — `red_flags` array, warning styling (red/orange banner)
3. **鉴别诊断** — `ai_output.differentials` array, each with ✓ ✗ buttons, overlay `doctor_decisions`
4. **检查建议** — `ai_output.workup` array, each with ✓ ✗ buttons
5. **治疗方向** — `ai_output.treatment` array, each with ✓ ✗ buttons
6. **免责** — static "AI建议仅供参考，最终诊断由医生决定"

Follow the existing card styling from `ReviewDetail.jsx`: white cards on `#f7f7f7` background, `#07C160` accent, 13-14px text.

Each item shows the AI suggestion text + confirm/reject buttons. The `doctor_decisions` overlay determines the visual state (confirmed = green check, rejected = red strike-through, unreviewed = default).

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/DiagnosisSection.jsx
git commit -m "feat(p2): add DiagnosisSection — similar cases, red flags, differentials, confirm/reject"
```

---

### Task 10: ReviewDetail + TasksSection Integration

**Files:**
- Modify: `frontend/web/src/pages/doctor/ReviewDetail.jsx`
- Modify: `frontend/web/src/pages/doctor/TasksSection.jsx`

- [ ] **Step 1: Add DiagnosisSection to ReviewDetail**

In `ReviewDetail.jsx`, after the structured fields card and before `ConversationHistory`:
1. Fetch diagnosis data: `getDiagnosis(detail.record_id, doctorId)` on component mount
2. If diagnosis exists and status is `completed` or `confirmed`, render `<DiagnosisSection />`
3. If status is `pending`, show a "诊断中..." spinner
4. If status is `failed` or no diagnosis, show nothing (graceful degradation)
5. Wire the `onDecide` callback to call `decideDiagnosisItem()` API

Update the "确认审核" button behavior: when diagnosis exists, confirming the review also confirms the diagnosis (calls `confirm_diagnosis` which computes agreement_score).

- [ ] **Step 2: Update TasksSection status chip**

In `TasksSection.jsx`, update `ReviewQueueItem` to use the `diagnosis_status` field returned by the updated `list_reviews()` API:

```javascript
// Current: binary orange/green chip
// New: infer from diagnosis_status
const chipLabel = item.diagnosis_status === "pending" ? "诊断中"
  : item.diagnosis_status === "completed" ? "诊断完成"
  : reviewed ? "已审核" : "待审核";

const chipColor = item.diagnosis_status === "pending" ? "#1890ff"
  : item.diagnosis_status === "completed" ? "#07C160"
  : reviewed ? "#07C160" : "#ff9500";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/ReviewDetail.jsx frontend/web/src/pages/doctor/TasksSection.jsx
git commit -m "feat(p2): integrate DiagnosisSection in ReviewDetail + diagnosis status in queue"
```

---

### Task 11: Integration Tests

**Files:**
- Create: `tests/core/test_diagnosis_pipeline.py`

- [ ] **Step 1: Create tests**

Test the diagnosis pipeline with mocked LLM + mocked embeddings. 4 tests:

1. `test_run_diagnosis_with_record` — create a medical record, run `run_diagnosis(record_id=N)`, verify `diagnosis_results` row created with status=completed, ai_output is valid JSON
2. `test_run_diagnosis_with_clinical_text` — run `run_diagnosis(clinical_text="头痛...")`, verify it returns results without saving to DB
3. `test_confirm_with_agreement_score` — create diagnosis, add decisions (confirm 2, reject 1), confirm, verify agreement_score is computed correctly
4. `test_graceful_failure` — mock LLM to raise timeout, verify `diagnosis_results` has status=failed

Mock targets:
- LLM call → return a fixture JSON response
- `match_cases` → return fake matched cases
- `embed` → return fake embedding (reuse P1 test pattern)
- `structure_medical_record` → return structured dict

- [ ] **Step 2: Run + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_diagnosis_pipeline.py -v --tb=short
git add tests/core/test_diagnosis_pipeline.py
git commit -m "test(p2): add diagnosis pipeline integration tests — run, confirm, failure"
```
