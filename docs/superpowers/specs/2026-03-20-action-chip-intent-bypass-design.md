# Action Chip & Intent Bypass Design

> **Status: ✅ DONE** — spec implemented and shipped.

> Date: 2026-03-20

## Problem

The doctor chat page has quick command buttons that insert text into the chat
input. The message is then sent through the full LLM ReAct agent pipeline,
which wastes LLM calls on intent classification and multi-tool reasoning when
the intent is already known from the button click.

## Solution

1. **Action chips** — quick command buttons insert a visual chip tag into the
   input field instead of raw text. The chip represents a known intent.
2. **Intent bypass** — when a chip is active, the frontend sends an
   `action_hint` field with the message. The backend uses a fast path that
   calls tool functions directly, bypassing the ReAct agent loop.
3. **Token deletion** — the chip behaves as an atomic unit: backspace at the
   chip boundary deletes the entire chip, not character by character.

## Chip Set

Four commands, ordered by daily usage frequency:

| # | Label    | `action_hint`   | Type          | Tool Function        |
|---|----------|-----------------|---------------|----------------------|
| 1 | 今日摘要 | `daily_summary` | zero-param    | `_fetch_tasks` + recent records query + LLM compose |
| 2 | 新增病历 | `create_record` | parameterized | ReAct agent (narrowed to `create_record` tool) |
| 3 | 查询患者 | `query_patient` | parameterized | `list_patients` / `search_patients` |
| 4 | 诊断建议 | `diagnosis`     | parameterized | (Phase 2, disabled) |

**Rationale for this set:**

- 今日摘要 is #1 — the doctor's operational dashboard (morning, between
  patients, end of day). Subsumes the old 今日任务 chip.
- 新增病历 — core documentation workflow, every consultation.
- 查询患者 — patient lookup before every consult. Empty text = list all.
- 诊断建议 — reserved for Phase 2 (ADR 0018). Shown disabled with "即将上线".

**Removed from current set:**

- 患者列表 — merged into 查询患者 (empty query = list all).
- 新建患者 — removed; QR onboarding (F1.2) replaces manual creation. Still
  accessible via free-text chat.
- 补充记录 — renamed/replaced by 新增病历 (new record, clearer action).
- 修正上条 — removed; corrections work fine through normal chat.
- 导出PDF — moved to patient detail page, not a chat action.
- 今日任务 — merged into 今日摘要 (summary includes pending tasks).

## Visual Design

WeChat-style, matching the platform doctors use daily:

- **Monochrome palette** — white buttons with subtle shadow, grey chip tags.
- **Single accent: WeChat green (#07C160)** — active button background and
  send button only.
- **Square corners (4px radius)** — matches WeChat's aesthetic.
- **No emoji/icons on buttons** — clean text labels only.
- **Chat bubbles** — WeChat green (#95ec69) for user, white for assistant.

### Input States

1. **Idle** — 4 command buttons above the input bar. Input shows placeholder.
2. **Chip active** — Grey tag inside input field (`#f0f0f0` bg, `1px #ddd`
   border). Active button turns green. Send button appears (green).
3. **Chip swap** — Clicking a different button swaps the chip; typed text
   is preserved. Active button highlight moves.
4. **Chip removed** — Backspace at position 0 or ✕ click removes the chip.
   Typed text stays. Input reverts to normal chat mode (no `action_hint`).
5. **Zero-param auto-send** — Clicking 今日摘要 inserts chip and immediately
   sends. Chat shows the tag in the user bubble.

## API Contract

### Request — extended `ChatInput`

```
POST /api/records/chat
{
  "text": "张三，男，45岁，头痛三天",
  "action_hint": "create_record",
  "doctor_id": "dr_123",
  "history": [...]
}
```

- `action_hint` is optional. When absent, normal ReAct agent pipeline runs.
- `text` may be empty for zero-param actions (`daily_summary`). For zero-param
  actions, the frontend sends the chip label as text (e.g. `"今日摘要"`), so
  the existing empty-text validation at `chat.py:130` does not need to change.
- For `query_patient` with empty text, frontend sends `"查询患者"` as text.

### Response — unchanged `ChatResponse`

```json
{
  "reply": "...",
  "record": null,
  "record_id": null,
  "view_payload": null,
  "switch_notification": null
}
```

No response schema changes needed.

### `Action` enum

The system has a single `Action` enum representing all possible doctor
intents. Action chips expose a **subset** of these actions as UI shortcuts.
The ReAct agent, when running without a chip, performs the same intent
classification via LLM — the chip just short-circuits that step.

**Backend** (`src/agent/actions.py`):

```python
from enum import Enum

class Action(str, Enum):
    """All doctor-facing intents. Chips expose a subset."""
    daily_summary    = "daily_summary"
    create_record    = "create_record"
    query_patient    = "query_patient"
    query_records    = "query_records"
    update_record    = "update_record"
    create_task      = "create_task"
    export_pdf       = "export_pdf"
    search_knowledge = "search_knowledge"
    diagnosis        = "diagnosis"
    general          = "general"           # free-text, no specific action

# Actions exposed as chips in the frontend
CHIP_ACTIONS: set[Action] = {
    Action.daily_summary,
    Action.create_record,
    Action.query_patient,
    Action.diagnosis,
}
```

**Frontend** (`constants.jsx`):

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
```

**`ChatInput` model** uses `Action` directly:

```python
class ChatInput(BaseModel):
    text: str = Field(..., max_length=8000)
    history: List[HistoryMessage] = Field(default_factory=list)
    doctor_id: str = ""
    action_hint: Optional[Action] = None
```

Pydantic rejects unknown values with HTTP 422. The `action_hint` field
accepts any `Action` value — not just chip actions — so other callers
(WeChat, API integrations) can send hints too. Adding a new action means
adding one enum value in `actions.py` and `constants.jsx`. Adding a new
chip means also adding to `CHIP_ACTIONS` and `QUICK_COMMANDS`.

**Why `Action` not `Tool`?** Actions and tools don't map 1:1.
`daily_summary` is multi-tool, `diagnosis` has no tool yet, `general` uses
no tool at all. `Action` represents what the doctor wants to do; tools are
how the system fulfills it.

## Backend Architecture

### Current Architecture (no `action_hint`)

```
chat.py → handle_turn()
  ├── _try_fast_path() — regex for greetings, confirm, abandon (0 LLM)
  └── SessionAgent.handle() — LangGraph ReAct agent (1-4 LLM calls)
        └── LLM decides: which tool? → extract params → call tool → format reply
```

The ReAct agent spends LLM calls on: (1) intent classification, (2) param
extraction, (3) tool execution, (4) reply formatting. When `action_hint` is
present, we know (1) already.

### New Architecture (with `action_hint`)

```
chat.py → handle_turn(text, role, identity, action_hint)
  ├── _try_fast_path() — unchanged
  ├── _dispatch_action_hint() — NEW: direct tool dispatch (0-1 LLM calls)
  │     ├── daily_summary → _fetch_tasks + recent records DB query + LLM compose
  │     ├── query_patient (empty) → _fetch_patients() direct call (0 LLM)
  │     ├── query_patient (with text) → _fetch_patients() + name filter (0 LLM)
  │     └── create_record → agent.handle() with narrowed prompt (1-2 LLM)
  └── SessionAgent.handle() — fallback for unknown hints or no hint
```

### Per-action bypass strategy

All bypass functions call **raw helper functions** (`_fetch_tasks`,
`_fetch_patients`, etc.) from `doctor.py` — NOT the `@tool`-decorated
wrappers. The `@tool` wrappers use `get_current_identity()` and return
tool-formatted output; the raw helpers accept explicit `doctor_id` and
return plain Python data structures.

**`daily_summary`** — No user text needed. Call `_fetch_tasks(doctor_id)`
for today's tasks and add a new `_fetch_recent_records(doctor_id, limit=10)`
helper that queries records across all patients (unlike `_fetch_records`
which requires a `patient_id`). Then use a single LLM call to compose a
natural-language summary from the combined data. Alternatively, use a
template-based compose (no LLM) for v1.

**`query_patient`** — Two sub-cases:
- Empty text (or just "查询患者"): call `_fetch_patients(doctor_id)` directly.
  Format the patient list into a readable reply. Zero LLM.
- With text (e.g. "张三"): call `_fetch_patients(doctor_id)` and filter by
  name substring match. Simple string matching, no LLM needed. The existing
  `extract_criteria()` in `nl_search.py` has a field-name mismatch bug
  (`name` vs `surname`) — bypass avoids it entirely by using direct name
  matching.

**`create_record`** — Still needs LLM for param extraction (patient name, age,
gender, clinical text from free-form input). Route through the ReAct agent but
with a narrowed system prompt: "The doctor wants to create a new medical
record. Extract the patient info and clinical details from their message.
Use the create_record tool." This constrains the agent to one tool, reducing
LLM calls from 2-4 to 1-2.

**`diagnosis`** — Phase 2. Backend ignores this hint for now (falls through
to normal agent, which can't diagnose either).

### Reply formatting

All bypass paths must return a `str` (human-readable reply), since
`handle_turn` returns `str` and `chat.py` wraps it in `ChatResponse`.

- `daily_summary` → LLM-composed or template string
- `query_patient` → Format patient list as text (e.g. "共3位患者：\n1. 张三...")
- `create_record` → Agent returns natural language (unchanged)

### Implementation in `handle_turn.py`

```python
from agent.actions import Action

async def handle_turn(
    text: str, role: str, identity: str,
    action_hint: Action | None = None,
) -> str:
    agent = await get_or_create_agent(identity, role)
    set_current_identity(identity)

    # 1. Existing fast paths (greetings, confirm, abandon)
    fast = await _try_fast_path(text, identity) if role == "doctor" else None
    if fast:
        agent._add_turn(text, fast)
        await archive_turns(identity, text, fast)
        return fast

    # 2. NEW: action hint fast paths
    if action_hint:
        try:
            reply = await _dispatch_action_hint(action_hint, text, identity, agent)
        except Exception as exc:
            log(f"[handle_turn] action_hint={action_hint} error: {exc}", level="error")
            reply = None
        if reply:
            agent._add_turn(text, reply)
            await archive_turns(identity, text, reply)
            return reply
        # Fall through to normal agent if dispatch returned None

    # 3. Normal ReAct agent
    try:
        reply = await agent.handle(text)
    except Exception as exc:
        log(f"[handle_turn] agent error: {exc}", level="error")
        reply = M.service_unavailable
    await archive_turns(identity, text, reply)
    return reply
```

Note: `_dispatch_action_hint` receives the `agent` instance so
`create_record` can route through `agent.handle()` with a modified prompt.
On error or `None` return, falls through to the normal agent path.

## Frontend Component Design

### Component structure

```
ChatSection.jsx
├── QuickCommandBar          // replaces existing QuickCommandsPanel
│   └── handles: click → set activeChip, or auto-send if zero-param
├── ChipInput                // new: input field with optional chip tag
│   └── handles:
│       - render chip + text in one input row
│       - backspace at position 0 → remove chip
│       - ✕ click → remove chip
│       - Enter → send with action_hint if chip present
└── performSend()            // existing, extended with actionHint param
```

The existing `QuickCommandsPanel` component (ChatSection.jsx ~line 163) is
replaced entirely by `QuickCommandBar` — different layout (row not grid),
different behavior (chip insertion not text insertion), different data source
(new `QUICK_COMMANDS` constant).

### State

```js
const [activeChip, setActiveChip] = useState(null);
// null → normal chat mode
// { key: "create_record", label: "新增病历" } → chip active
```

### Interactions

| Event                                    | Handler                                          |
|------------------------------------------|--------------------------------------------------|
| Click parameterized button               | `setActiveChip({ key, label })`, focus input     |
| Click zero-param button                  | `setActiveChip(...)`, immediately `performSend`  |
| Click same active button (toggle off)    | `setActiveChip(null)`                            |
| Click different button (swap)            | `setActiveChip(newChip)`, text preserved         |
| Backspace at cursor position 0           | `setActiveChip(null)`                            |
| Click ✕ on chip tag                      | `setActiveChip(null)`                            |
| Enter / send                             | `performSend(text, activeChip?.key)`, clear both |

### `constants.jsx` update

```js
export const QUICK_COMMANDS = [
  { key: Action.DAILY_SUMMARY, label: "今日摘要",  autoSend: true },
  { key: Action.CREATE_RECORD, label: "新增病历",  autoSend: false },
  { key: Action.QUERY_PATIENT, label: "查询患者",  autoSend: false },
  { key: Action.DIAGNOSIS,     label: "诊断建议",  autoSend: false, disabled: true },
];
```

### `performSend` change

The existing `performSend` function accepts a destructured object with
`text`, `loading`, `doctorId`, `history`, etc. Add `actionHint` to that
object:

```js
// In performSend:
const payload = { text, doctor_id: doctorId, history };
if (actionHint) payload.action_hint = actionHint;
const data = await sendChat(payload);
```

The call site in `sendText()` (~line 495) threads `activeChip?.key` through.

### `sendText` signature update

The existing `sendText(text)` function (~line 359) accepts a single string
argument. Extend it to accept an optional `actionHint`:

```js
// Before:
function sendText(text) { performSend({ text, ... }); }

// After:
function sendText(text, actionHint = null) { performSend({ text, actionHint, ... }); }
```

### `useDailySummary` hook update

The existing hook (ChatSection.jsx ~line 432) auto-sends `"今日工作摘要"` as
plain text on first daily load. Update to send with `action_hint`:

```js
// Before:
sendText("今日工作摘要")

// After:
sendText("今日摘要", Action.DAILY_SUMMARY)
```

This gives the auto-summary the same bypass benefit as the manual chip click.

### Chat history display

Messages sent with a chip show the tag label in the user bubble (grey inline
tag matching the chip style), so the doctor can see which action they invoked
in the conversation trail.

## Edge Cases

| Scenario                                      | Behavior                                              |
|-----------------------------------------------|-------------------------------------------------------|
| Parameterized chip + empty text + send         | Show toast "请输入内容", don't send                    |
| Plain text (no chip) + send                    | Normal flow, `action_hint` omitted                    |
| Backend receives unknown `action_hint`         | Pydantic rejects with HTTP 422 (enum validation)      |
| 诊断建议 clicked (disabled)                     | No-op, tooltip "即将上线"                              |
| Network error during chip send                 | Same error handling as normal send                    |
| 查询患者 + empty text                           | Frontend sends text="查询患者", backend lists all      |
| Zero-param button clicked while input has text | Text is cleared, chip auto-sends. Deliberate: the     |
|                                                | zero-param action overrides partial input. If user    |
|                                                | wanted to keep that text, they'd send it first.       |

## Files to Modify

### Frontend

- `frontend/web/src/pages/doctor/constants.jsx` — replace `QUICK_COMMANDS`
  array with new 4-item definition, add `Action` enum object
- `frontend/web/src/pages/doctor/ChatSection.jsx` — replace
  `QuickCommandsPanel` with `QuickCommandBar`, add `ChipInput` component,
  extend `performSend` with `actionHint`, update `useDailySummary` hook,
  update `MsgBubble` to render chip tags in user messages
- `frontend/web/src/api.js` — no change needed (`sendChat` already passes
  through the payload object)

### Backend

- `src/agent/actions.py` — **NEW file**: `Action(str, Enum)` + `CHIP_ACTIONS` set
- `src/channels/web/chat.py` — add `action_hint: Optional[Action] = None`
  field to `ChatInput` model, pass to `handle_turn`
- `src/agent/handle_turn.py` — add `action_hint` parameter to `handle_turn`,
  add `_dispatch_action_hint()` function with per-action fast paths
- `src/agent/tools/doctor.py` — add `_fetch_recent_records(doctor_id, limit)`
  helper that queries records across all patients (existing `_fetch_records`
  requires a `patient_id`). No changes to `@tool` functions.

### WeChat channel

The WeChat channel (`channels/wechat/router.py`) also calls `handle_turn`.
It will not send `action_hint` — the new parameter defaults to `None`, so
WeChat is unaffected.

### Other `sendText` callers

`sendText` is also called from `MsgBubble.onQuickSend`, `PatientPickerDialog`,
and `ImportChoiceDialog`. These callers intentionally do not use chips and
should NOT pass `actionHint` — they continue to use the normal agent path.

## Test Plan

- **Backend unit**: test `_dispatch_action_hint` with each valid hint value;
  verify unknown hints return `None` (fallback to agent)
- **Backend integration**: verify `daily_summary` and `query_patient` bypass
  the ReAct agent (mock `agent.handle` and assert it is NOT called)
- **Frontend unit**: chip insertion, swap, removal, backspace behavior
- **Frontend integration**: verify `action_hint` is included in API payload
  when chip is active and omitted when not
