# Action Chip & Intent Bypass Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text-insertion quick commands with action chips that bypass LLM intent classification, reducing latency and cost for known-intent actions.

**Architecture:** Frontend chips send `action_hint` (from the `Action` enum) with chat messages. Backend dispatches to fast paths that call tool helpers directly, falling back to the normal ReAct agent when no hint is present. Two independent workstreams: backend (Tasks 1-4) and frontend (Tasks 5-8).

**Tech Stack:** Python/FastAPI + Pydantic (backend), React + MUI (frontend), existing LangChain ReAct agent

**Spec:** `docs/specs/archived/2026-03-20-action-chip-intent-bypass-design.md`

---

### Task 1: Create `Action` enum

**Files:**
- Create: `src/agent/actions.py`
- Test: `tests/core/test_actions.py`

- [ ] **Step 1: Write the test**

```python
# tests/core/test_actions.py
"""Action enum — value stability and chip subset."""
from agent.actions import Action, CHIP_ACTIONS


def test_action_values_are_stable():
    """Enum string values must not drift — frontend sends these over the wire."""
    assert Action.daily_summary.value == "daily_summary"
    assert Action.create_record.value == "create_record"
    assert Action.query_patient.value == "query_patient"
    assert Action.diagnosis.value == "diagnosis"
    assert Action.general.value == "general"


def test_action_is_str_enum():
    assert isinstance(Action.daily_summary, str)
    assert Action.daily_summary == "daily_summary"


def test_chip_actions_subset():
    assert CHIP_ACTIONS == {
        Action.daily_summary,
        Action.create_record,
        Action.query_patient,
        Action.diagnosis,
    }
    assert CHIP_ACTIONS.issubset(set(Action))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_actions.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.actions'`

- [ ] **Step 3: Write the implementation**

```python
# src/agent/actions.py
"""Action enum — all doctor-facing intents.

Chips expose CHIP_ACTIONS subset. The ReAct agent classifies into these same
values via LLM; chips short-circuit that classification step.
"""
from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    daily_summary    = "daily_summary"
    create_record    = "create_record"
    query_patient    = "query_patient"
    query_records    = "query_records"
    update_record    = "update_record"
    create_task      = "create_task"
    export_pdf       = "export_pdf"
    search_knowledge = "search_knowledge"
    diagnosis        = "diagnosis"
    general          = "general"


CHIP_ACTIONS: set[Action] = {
    Action.daily_summary,
    Action.create_record,
    Action.query_patient,
    Action.diagnosis,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_actions.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/agent/actions.py tests/core/test_actions.py
git commit -m "feat: add Action enum and CHIP_ACTIONS subset"
```

---

### Task 2: Add `action_hint` to API layer

**Files:**
- Modify: `src/channels/web/chat.py:38-54` (ChatInput model)
- Modify: `src/channels/web/chat.py:118-136` (chat endpoint)
- Test: `tests/core/test_chat_input.py`

- [ ] **Step 1: Write the test**

```python
# tests/core/test_chat_input.py
"""ChatInput model — action_hint validation."""
import pytest
from pydantic import ValidationError


def test_chat_input_accepts_valid_action_hint():
    from channels.web.chat import ChatInput
    body = ChatInput(text="张三", action_hint="create_record")
    assert body.action_hint.value == "create_record"


def test_chat_input_allows_no_hint():
    from channels.web.chat import ChatInput
    body = ChatInput(text="hello")
    assert body.action_hint is None


def test_chat_input_rejects_unknown_hint():
    from channels.web.chat import ChatInput
    with pytest.raises(ValidationError):
        ChatInput(text="hello", action_hint="invalid_action")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_chat_input.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `ChatInput` has no `action_hint` field yet

- [ ] **Step 3: Modify `ChatInput` in `chat.py`**

Add import at top of `src/channels/web/chat.py`:
```python
from agent.actions import Action
```

Add field to `ChatInput` class (after `doctor_id`):
```python
    action_hint: Optional[Action] = None
```

Modify the `chat()` endpoint to pass `action_hint` to `handle_turn`:
```python
    reply = await handle_turn(text, "doctor", doctor_id, action_hint=body.action_hint)
```

Note: `handle_turn` doesn't accept `action_hint` yet — that's Task 3. For now, add `action_hint=None` as a keyword arg with a default so existing calls don't break:

In `src/agent/handle_turn.py`, change function signature only (do not add dispatch logic yet):
```python
async def handle_turn(text: str, role: str, identity: str, *, action_hint=None) -> str:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_chat_input.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: 3 PASSED

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/chat.py src/agent/handle_turn.py tests/core/test_chat_input.py
git commit -m "feat: add action_hint field to ChatInput, thread to handle_turn"
```

---

### Task 3: Add `_fetch_recent_records` helper

**Files:**
- Modify: `src/agent/tools/doctor.py:113-144` (add helper after existing helpers)
- Test: `tests/core/test_fetch_recent_records.py`

The `daily_summary` bypass needs records across all patients. The existing
`_fetch_records` requires `patient_id`, but `get_all_records_for_doctor`
in `db/crud/records.py` already queries cross-patient records via
`RecordRepository.list_for_doctor()`. We just need a tool helper that
calls it.

- [ ] **Step 1: Write the test**

```python
# tests/core/test_fetch_recent_records.py
"""_fetch_recent_records — cross-patient record retrieval."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_fetch_recent_records_returns_serialized_list():
    mock_record = MagicMock()
    mock_record.id = 1
    mock_record.content = "头痛三天"
    mock_record.tags = "[]"
    mock_record.record_type = "visit"
    mock_record.created_at = datetime(2026, 3, 20, 10, 0)

    with patch("db.engine.AsyncSessionLocal") as mock_session_cls, \
         patch("db.crud.records.get_all_records_for_doctor", new_callable=AsyncMock) as mock_query:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_query.return_value = [mock_record]

        from agent.tools.doctor import _fetch_recent_records
        result = await _fetch_recent_records("dr_test", limit=5)

    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["content"] == "头痛三天"
```

Note: Mock targets match the lazy import locations — `db.engine.AsyncSessionLocal`
and `db.crud.records.get_all_records_for_doctor` — not the consumer module.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_fetch_recent_records.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `_fetch_recent_records` does not exist

- [ ] **Step 3: Add tool helper in `doctor.py`**

In `src/agent/tools/doctor.py`, add after `_fetch_tasks` (~line 144):
```python
async def _fetch_recent_records(
    doctor_id: str, limit: int = 10,
) -> List[Dict[str, Any]]:
    from db.crud.records import get_all_records_for_doctor
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_all_records_for_doctor(session, doctor_id, limit=limit)
        return [_serialize_record(r) for r in records]
```

No new CRUD function needed — `get_all_records_for_doctor` already exists
at `db/crud/records.py:163` and calls `repo.list_for_doctor()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_fetch_recent_records.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add src/agent/tools/doctor.py tests/core/test_fetch_recent_records.py
git commit -m "feat: add _fetch_recent_records helper for cross-patient queries"
```

---

### Task 4: Implement `_dispatch_action_hint` in `handle_turn.py`

**Files:**
- Modify: `src/agent/handle_turn.py` (add dispatch logic)
- Test: `tests/core/test_action_dispatch.py`

This is the core bypass logic. Each action hint maps to a fast path.

- [ ] **Step 1: Write the tests**

```python
# tests/core/test_action_dispatch.py
"""Action hint dispatch — bypass ReAct agent for known intents."""
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("ROUTING_LLM", "deepseek")

from agent.actions import Action


@pytest.mark.asyncio
async def test_query_patient_empty_lists_all():
    """query_patient with label text → list all patients."""
    mock_patients = [
        {"id": 1, "name": "张三", "gender": "男", "year_of_birth": 1980},
        {"id": 2, "name": "李四", "gender": "女", "year_of_birth": 1990},
    ]
    with patch("agent.handle_turn._fetch_patients", new_callable=AsyncMock, return_value=mock_patients):
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.query_patient, "查询患者", "dr_test", agent=None)

    assert "张三" in reply
    assert "李四" in reply


@pytest.mark.asyncio
async def test_query_patient_with_name_filters():
    """query_patient with name text → filter by substring."""
    mock_patients = [
        {"id": 1, "name": "张三", "gender": "男", "year_of_birth": 1980},
        {"id": 2, "name": "李四", "gender": "女", "year_of_birth": 1990},
    ]
    with patch("agent.handle_turn._fetch_patients", new_callable=AsyncMock, return_value=mock_patients):
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.query_patient, "张三", "dr_test", agent=None)

    assert "张三" in reply
    assert "李四" not in reply


@pytest.mark.asyncio
async def test_daily_summary_calls_helpers():
    """daily_summary → calls _fetch_tasks + _fetch_recent_records."""
    with patch("agent.handle_turn._fetch_tasks", new_callable=AsyncMock, return_value=[]) as mock_tasks, \
         patch("agent.handle_turn._fetch_recent_records", new_callable=AsyncMock, return_value=[]) as mock_records:
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.daily_summary, "今日摘要", "dr_test", agent=None)

    mock_tasks.assert_called_once_with("dr_test")
    mock_records.assert_called_once()
    assert isinstance(reply, str)


@pytest.mark.asyncio
async def test_create_record_falls_through_to_agent():
    """create_record → routes through agent.handle()."""
    mock_agent = MagicMock()
    mock_agent.handle = AsyncMock(return_value="已为张三创建病历草稿")

    from agent.handle_turn import _dispatch_action_hint
    reply = await _dispatch_action_hint(Action.create_record, "张三，男，45岁", "dr_test", agent=mock_agent)

    mock_agent.handle.assert_called_once()
    assert "张三" in reply


@pytest.mark.asyncio
async def test_diagnosis_returns_none():
    """diagnosis (Phase 2) → returns None, falls through to normal agent."""
    from agent.handle_turn import _dispatch_action_hint
    reply = await _dispatch_action_hint(Action.diagnosis, "test", "dr_test", agent=None)
    assert reply is None


@pytest.mark.asyncio
async def test_handle_turn_uses_dispatch_when_hint_present():
    """handle_turn with action_hint skips agent, uses dispatch."""
    with patch("agent.handle_turn.get_or_create_agent", new_callable=AsyncMock) as mock_get_agent, \
         patch("agent.handle_turn.set_current_identity"), \
         patch("agent.handle_turn._try_fast_path", new_callable=AsyncMock, return_value=None), \
         patch("agent.handle_turn._dispatch_action_hint", new_callable=AsyncMock, return_value="患者列表...") as mock_dispatch, \
         patch("agent.handle_turn.archive_turns", new_callable=AsyncMock):
        mock_agent = MagicMock()
        mock_agent._add_turn = MagicMock()
        mock_get_agent.return_value = mock_agent

        from agent.handle_turn import handle_turn
        reply = await handle_turn("查询患者", "doctor", "dr_test", action_hint=Action.query_patient)

    assert reply == "患者列表..."
    mock_dispatch.assert_called_once()
    mock_agent.handle.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_action_dispatch.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `_dispatch_action_hint` does not exist

- [ ] **Step 3: Implement `_dispatch_action_hint` in `handle_turn.py`**

Add imports at top of `src/agent/handle_turn.py`:
```python
from datetime import datetime
from agent.actions import Action
from agent.tools.doctor import _fetch_tasks, _fetch_patients, _fetch_recent_records
```

Add the dispatch function (after `_try_fast_path`, before `handle_turn`):
```python
_QUERY_LABEL = re.compile(r"^查询患者[：:]?\s*$")


def _format_patient_list(patients: list) -> str:
    if not patients:
        return "暂无患者记录。"
    lines = [f"共{len(patients)}位患者："]
    for i, p in enumerate(patients, 1):
        parts = [p["name"]]
        if p.get("gender"):
            parts.append(p["gender"])
        if p.get("year_of_birth"):
            age = datetime.now().year - p["year_of_birth"]
            parts.append(f"{age}岁")
        lines.append(f"{i}. {'，'.join(parts)}")
    return "\n".join(lines)


def _format_daily_summary(tasks: list, records: list) -> str:
    lines = ["**今日工作摘要**", ""]
    if tasks:
        pending = [t for t in tasks if t.get("status") == "pending"]
        done = [t for t in tasks if t.get("status") == "completed"]
        lines.append(f"**待处理任务** ({len(pending)})")
        for t in pending:
            lines.append(f"- {t.get('title', '未命名')}")
        if done:
            lines.append(f"\n**已完成** ({len(done)})")
            for t in done:
                lines.append(f"- ~~{t.get('title', '未命名')}~~")
    else:
        lines.append("今日暂无任务。")
    lines.append("")
    if records:
        lines.append(f"**最近病历** ({len(records)}条)")
        for r in records:
            date = (r.get("created_at") or "")[:10]
            content_preview = (r.get("content") or "")[:40]
            lines.append(f"- {date} {content_preview}")
    else:
        lines.append("暂无近期病历。")
    return "\n".join(lines)


async def _dispatch_action_hint(
    action: Action, text: str, identity: str, agent,
) -> Optional[str]:
    """Fast path for known intents. Returns reply str or None to fall through."""

    if action == Action.query_patient:
        patients = await _fetch_patients(identity)
        # If text is just the label or empty, list all; otherwise filter by name
        search = text.strip()
        if _QUERY_LABEL.match(search) or not search:
            return _format_patient_list(patients)
        filtered = [p for p in patients if search in p.get("name", "")]
        return _format_patient_list(filtered)

    if action == Action.daily_summary:
        tasks = await _fetch_tasks(identity)
        records = await _fetch_recent_records(identity, limit=10)
        return _format_daily_summary(tasks, records)

    if action == Action.create_record:
        if agent is None:
            return None
        return await agent.handle(text)

    # Unknown or future actions (e.g. diagnosis) → fall through
    return None
```

Update `handle_turn` function to wire in the dispatch:
```python
async def handle_turn(text: str, role: str, identity: str, *, action_hint=None) -> str:
    """One turn. Channels call this directly."""
    agent = await get_or_create_agent(identity, role)
    set_current_identity(identity)

    # Fast path (0 LLM) — doctor only
    fast = await _try_fast_path(text, identity) if role == "doctor" else None
    if fast:
        agent._add_turn(text, fast)
        try:
            await archive_turns(identity, text, fast)
        except Exception as exc:
            log(f"[handle_turn] archive failed: {exc}", level="error")
        return fast

    # Action hint fast paths
    if action_hint:
        try:
            reply = await _dispatch_action_hint(action_hint, text, identity, agent)
        except Exception as exc:
            log(f"[handle_turn] action_hint={action_hint} error: {exc}", level="error")
            reply = None
        if reply:
            agent._add_turn(text, reply)
            try:
                await archive_turns(identity, text, reply)
            except Exception as exc:
                log(f"[handle_turn] archive failed: {exc}", level="error")
            return reply

    # LangChain agent (1-4 LLM calls)
    try:
        reply = await agent.handle(text)
    except Exception as exc:
        log(f"[handle_turn] agent error: {exc}", level="error")
        reply = M.service_unavailable

    try:
        await archive_turns(identity, text, reply)
    except Exception as exc:
        log(f"[handle_turn] archive failed: {exc}", level="error")

    return reply
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_action_dispatch.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: 6 PASSED

- [ ] **Step 5: Run all tests to verify no regression**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/agent/handle_turn.py tests/core/test_action_dispatch.py
git commit -m "feat: implement _dispatch_action_hint — bypass ReAct for known intents"
```

---

### Task 5: Update `constants.jsx` — `Action` enum + new `QUICK_COMMANDS`

**Files:**
- Modify: `frontend/web/src/pages/doctor/constants.jsx:96-105`

- [ ] **Step 1: Replace `QUICK_COMMANDS` and add `Action` enum**

In `frontend/web/src/pages/doctor/constants.jsx`, replace lines 96-105:

```js
export const Action = {
  DAILY_SUMMARY:    "daily_summary",
  CREATE_RECORD:    "create_record",
  QUERY_PATIENT:    "query_patient",
  QUERY_RECORDS:    "query_records",
  UPDATE_RECORD:    "update_record",
  CREATE_TASK:      "create_task",
  EXPORT_PDF:       "export_pdf",
  SEARCH_KNOWLEDGE: "search_knowledge",
  DIAGNOSIS:        "diagnosis",
  GENERAL:          "general",
};

export const QUICK_COMMANDS = [
  { key: Action.DAILY_SUMMARY, label: "今日摘要",  autoSend: true },
  { key: Action.CREATE_RECORD, label: "新增病历",  autoSend: false },
  { key: Action.QUERY_PATIENT, label: "查询患者",  autoSend: false },
  { key: Action.DIAGNOSIS,     label: "诊断建议",  autoSend: false, disabled: true },
];
```

- [ ] **Step 2: Update import in `ChatSection.jsx`**

In `frontend/web/src/pages/doctor/ChatSection.jsx`, line 22, change:
```js
import { QUICK_COMMANDS } from "./constants";
```
to:
```js
import { QUICK_COMMANDS, Action } from "./constants";
```

- [ ] **Step 3: Verify the frontend still compiles**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds (QUICK_COMMANDS shape changed but is still an array of objects)

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/constants.jsx frontend/web/src/pages/doctor/ChatSection.jsx
git commit -m "feat: replace QUICK_COMMANDS with Action enum + chip definitions"
```

---

### Task 6: Build `QuickCommandBar` component

**Files:**
- Modify: `frontend/web/src/pages/doctor/ChatSection.jsx:163-195` (replace `QuickCommandsPanel`)

- [ ] **Step 1: Replace `QuickCommandsPanel` with `QuickCommandBar`**

In `ChatSection.jsx`, replace the `QuickCommandsPanel` function (lines 163-195) with:

```jsx
function QuickCommandBar({ activeChip, onSelect }) {
  return (
    <Box sx={{ px: 1.5, pt: 1, pb: 0.8, borderTop: "0.5px solid #e0e0e0", backgroundColor: "#f7f7f7", display: "flex", gap: 1, flexWrap: "wrap" }}>
      {QUICK_COMMANDS.map((cmd) => {
        const isActive = activeChip?.key === cmd.key;
        const isDisabled = cmd.disabled;
        return (
          <Box key={cmd.key} component="button"
            onClick={() => !isDisabled && onSelect(cmd)}
            disabled={isDisabled}
            title={isDisabled ? "即将上线" : undefined}
            sx={{
              display: "inline-flex", alignItems: "center", px: 1.5, py: 0.6,
              border: "none", borderRadius: "4px", cursor: isDisabled ? "default" : "pointer",
              fontSize: 13, fontFamily: "inherit", whiteSpace: "nowrap",
              backgroundColor: isActive ? "#07C160" : "#fff",
              color: isActive ? "#fff" : "#333",
              opacity: isDisabled ? 0.4 : 1,
              boxShadow: isActive ? "none" : "0 1px 2px rgba(0,0,0,0.08)",
              transition: "background-color 0.15s, color 0.15s",
              "&:active": isDisabled ? {} : { opacity: 0.7 },
            }}>
            {cmd.label}
          </Box>
        );
      })}
    </Box>
  );
}
```

- [ ] **Step 2: Remove unused icon imports and `CMD_ICONS` map**

In `ChatSection.jsx`, remove lines 29-47 (icon imports for old commands and the `CMD_ICONS` object). Keep only the icons still used by other components (`SendOutlinedIcon`, `AttachFileOutlinedIcon`, `DeleteOutlineIcon`, `SmartToyOutlinedIcon`, `LocalHospitalOutlinedIcon`, `AddCircleOutlineIcon`, `MicNoneOutlinedIcon`).

Remove these imports:
```
PersonAddOutlinedIcon, SearchOutlinedIcon, PeopleOutlinedIcon,
NoteAddOutlinedIcon, EditOutlinedIcon, FileDownloadOutlinedIcon,
AssignmentOutlinedIcon, AssessmentOutlinedIcon,
KeyboardArrowDownIcon, KeyboardArrowUpIcon
```

Remove `const CMD_ICONS = { ... };` block.

- [ ] **Step 3: Verify the frontend compiles**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/ChatSection.jsx
git commit -m "feat: replace QuickCommandsPanel with QuickCommandBar"
```

---

### Task 7: Build `ChipInput` and wire up chip state

**Files:**
- Modify: `frontend/web/src/pages/doctor/ChatSection.jsx`

This is the core frontend task: chip state management, chip-aware input field,
`performSend` / `sendText` extension, `useDailySummary` update.

- [ ] **Step 1: Add `activeChip` state to `ChatSection`**

In the `ChatSection` default export function (~line 446), add state:
```js
const [activeChip, setActiveChip] = useState(null);
```

- [ ] **Step 2: Add `ChipInput` component**

Add new component before the `ChatSection` export:

```jsx
function ChipInput({ activeChip, onRemoveChip, input, onInput, onSend, loading, isProcessing }) {
  const inputRef = useRef(null);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
    if (e.key === "Backspace" && activeChip && !input) {
      e.preventDefault();
      onRemoveChip();
    }
  }

  useEffect(() => {
    if (activeChip) inputRef.current?.focus();
  }, [activeChip]);

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 1, borderTop: "0.5px solid #e0e0e0", backgroundColor: "#f6f6f6" }}>
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 0.8, flexWrap: "nowrap",
        backgroundColor: "#fff", borderRadius: "4px", px: 1.2, py: 0.8, minHeight: 36 }}>
        {activeChip && (
          <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.3, backgroundColor: "#f0f0f0",
            color: "#333", px: 1, py: 0.25, borderRadius: "3px", fontSize: 12, whiteSpace: "nowrap",
            border: "1px solid #ddd", flexShrink: 0 }}>
            {activeChip.label}
            <Box component="span" onClick={onRemoveChip}
              sx={{ color: "#999", ml: 0.3, cursor: "pointer", fontSize: 10, lineHeight: 1, "&:hover": { color: "#666" } }}>
              ✕
            </Box>
          </Box>
        )}
        <Box component="input" ref={inputRef} value={input}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={activeChip ? "输入内容..." : "输入消息..."}
          sx={{ flex: 1, border: "none", outline: "none", fontSize: 14, fontFamily: "inherit",
            backgroundColor: "transparent", minWidth: 0, p: 0 }}
        />
      </Box>
      {(activeChip || input.trim()) ? (
        <Box component="button" onClick={onSend}
          disabled={loading || isProcessing}
          sx={{ px: 1.2, py: 0.5, backgroundColor: "#07C160", color: "#fff", border: "none",
            borderRadius: "4px", fontSize: 14, cursor: "pointer", fontFamily: "inherit",
            whiteSpace: "nowrap", "&:disabled": { opacity: 0.5 } }}>
          发送
        </Box>
      ) : (
        <Box sx={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "#666" }}>
          +
        </Box>
      )}
    </Box>
  );
}
```

- [ ] **Step 3: Extend `performSend` and `sendText`**

Modify `performSend` (~line 296) — add `actionHint` parameter:
```js
async function performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated, actionHint }) {
  if (!text || loading) return;
  // ... existing code ...
  try {
    const payload = { text, doctor_id: doctorId, history };
    if (actionHint) payload.action_hint = actionHint;
    const data = await sendChat(payload);
    // ... rest unchanged ...
```

Modify `sendText` in `useChatState` (~line 359):
```js
  function sendText(text, actionHint = null) {
    return performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated, actionHint });
  }
```

Update return of `useChatState` — no change needed (sendText is already returned).

- [ ] **Step 4: Add chip message metadata to user messages**

In `performSend`, update the user message to include the chip label:
```js
  setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs(), actionLabel: actionHint ? QUICK_COMMANDS.find(c => c.key === actionHint)?.label : null }]);
```

Add the import at the top of `performSend` or pass it in. Simpler: just pass the label as a parameter:
```js
async function performSend({ ..., actionHint, actionLabel }) {
  ...
  setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs(), actionLabel }]);
```

- [ ] **Step 5: Render chip tag in user bubble**

In `MsgBubble` (~line 91), update the user message rendering:
```jsx
{isUser ? (
  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: isMobile ? 1.8 : 1.7, color: textColor }}>
    {msg.actionLabel && (
      <Box component="span" sx={{ display: "inline-flex", alignItems: "center", backgroundColor: "rgba(0,0,0,0.06)",
        px: 0.8, py: 0.1, borderRadius: "2px", fontSize: 12, color: "#555", mr: 0.8 }}>
        {msg.actionLabel}
      </Box>
    )}
    {msg.content}
  </Typography>
) : (
  // ... existing assistant rendering ...
```

- [ ] **Step 6: Wire `QuickCommandBar` handler and `ChipInput` into `ChatSection`**

In the `ChatSection` export function, add the handler:
```js
  function handleCommandSelect(cmd) {
    if (cmd.autoSend) {
      setInput("");
      setActiveChip(null);
      sendText(cmd.label, cmd.key);
      return;
    }
    // Toggle if same chip clicked
    if (activeChip?.key === cmd.key) {
      setActiveChip(null);
      return;
    }
    // Set or swap chip, preserve text
    setActiveChip({ key: cmd.key, label: cmd.label });
  }

  function handleChipSend() {
    const text = input.trim();
    if (activeChip && !activeChip.autoSend && !text) return; // parameterized needs text
    sendText(text || activeChip?.label || "", activeChip?.key);
    setInput("");
    setActiveChip(null);
  }
```

Replace the `<QuickCommandsPanel ... />` line (~line 510) with:
```jsx
<QuickCommandBar activeChip={activeChip} onSelect={handleCommandSelect} />
```

Replace the desktop/mobile input bars section with `ChipInput`:
```jsx
<ChipInput
  activeChip={activeChip}
  onRemoveChip={() => setActiveChip(null)}
  input={input}
  onInput={setInput}
  onSend={handleChipSend}
  loading={loading}
  isProcessing={isProcessing}
/>
```

Note: The existing `DesktopInputBar` and `MobileInputBar` components are
replaced by the unified `ChipInput`. If voice input / camera / file attach
buttons are needed, they can be added back to `ChipInput` later. For now,
the file attach button (`fileInputRef`) should be kept accessible — add it
inside `ChipInput` or keep it as a separate row. Keep the hidden file inputs
as they are (lines 511-518).

- [ ] **Step 7: Update `useDailySummary` hook**

In the `useDailySummary` function (~line 432), change:
```js
const t = setTimeout(() => sendText("今日工作摘要"), 1200);
```
to:
```js
const t = setTimeout(() => sendText("今日摘要", "daily_summary"), 1200);
```

- [ ] **Step 8: Remove unused `toggleCommands` state and `commandsShown`**

The old `QuickCommandsPanel` had show/hide toggle. Remove:
- `const [commandsShown, setCommandsShown]` state declaration
- `toggleCommands` function (~line 488-489)

- [ ] **Step 9: Verify the frontend compiles**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 10: Commit**

```bash
git add frontend/web/src/pages/doctor/ChatSection.jsx
git commit -m "feat: chip input UX — action chips, token delete, intent bypass"
```

---

### Task 8: Manual QA and edge case verification

**Files:** None (testing only)

- [ ] **Step 1: Start the dev server**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -m uvicorn main:app --reload --port 8000`

- [ ] **Step 2: Open the frontend and verify each state**

Test these interactions in the browser:

1. **Idle state** — 4 buttons visible (今日摘要, 新增病历, 查询患者, 诊断建议 greyed out)
2. **Click 新增病历** — chip appears in input, button turns green, cursor in input
3. **Type text** — text appears after chip
4. **Click 查询患者** — chip swaps to 查询患者, text preserved, button highlight moves
5. **Backspace when cursor at position 0** — chip removed, text stays
6. **Click 今日摘要** — auto-sends, shows in chat with tag
7. **Click 诊断建议** — no-op (disabled)
8. **Send 新增病历 with text** — API call includes `action_hint: "create_record"`
9. **Send 查询患者 without extra text** — lists all patients
10. **Send plain text (no chip)** — normal agent, no `action_hint` in payload

- [ ] **Step 3: Verify API payloads in browser DevTools**

Open Network tab, filter for `/api/records/chat`:
- With chip: payload includes `"action_hint": "create_record"`
- Without chip: payload has no `action_hint` field

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All tests pass

- [ ] **Step 5: Commit any fixes**

If any issues found during QA, fix and commit each atomically.
