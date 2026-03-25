# ReAct Agent Architecture Design (LangChain) ✅ DONE

> **Status: ✅ DONE** — spec implemented and shipped.

> Date: 2026-03-18 | Status: Draft

## Summary

Replace the Understand-Execute-Compose (UEC) pipeline with a
LangChain-powered ReAct agent. Unify doctor and patient interactions
under a single agent parameterized by role. Eliminate persistent context
(ctx). Use LangChain for the agent loop, tool decorator, and prompt
management. Keep our own routing, resolve layer, history persistence,
and interview pipeline.

## Motivation

The current UEC pipeline (ADR 0012/0013) works well for single-action
turns but has a ceiling for:

- **Multi-action sequencing** — compound intents require adaptation to
  intermediate results
- **Diagnostic reasoning (Phase 2)** — chaining tool calls across turns
- **Patient interview** — adaptive multi-turn clinical interview
- **Future extensibility** — new capabilities should be new tools, not
  pipeline changes

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | LangChain (`AgentExecutor` + `@tool`) | Battle-tested ReAct loop, tool decorator, prompt templates. Avoid rebuilding ~500 lines of orchestration |
| Agent pattern | ReAct (bounded, max 10 iterations) | Standard tool-use pattern; constrained tool set + resolve addresses safety. Implementation uses LangChain's `create_tool_calling_agent` (native JSON tool calls), not the text-based `create_react_agent` |
| Context (ctx) | Eliminated | No WorkflowState, no DoctorCtx. Patient binding from LLM + conversation. Pending state from DB |
| DB keys | Name-based for LLM interface, ID-based internally | LLM passes patient_name in tool calls. Resolve translates name to (doctor_id, patient_id) for CRUD. DB uses `doctor_id: str` + `patient_id: int` as actual keys |
| History | We manage, pass to LangChain | Load from our archive DB as `chat_history`. LangChain manages within-turn `agent_scratchpad` |
| Patient history | LLM auto-fetches | When patient in scope, LLM always calls `query_records` first |
| Clinical collection | Prompt-driven accumulation | LLM collects across messages, creates record when enough fields. Max 2 follow-ups |
| Write confirmation | Pending preview for all medical record writes | `create_record` and `update_record` both return preview via `pending_records`. Doctor confirms before permanent save. `create_task` commits immediately (lightweight, editable) |
| Interview | LangChain tool (`advance_interview`) | Same agent pipeline for both roles. Agent decides when to call interview tool vs reply directly |
| RAG | Deferred | Not part of initial migration |
| Doctor + patient | Same agent, different config | Role determines prompt + tool set |
| Dedup | Channel concern | WeChat deduplicates before calling agent. Not in core |

## Architecture

### Overview

```
Channel (Web / WeChat)
  |
  handle_turn(text, role, identity)
  |
  +-- Deterministic fast path (greeting, confirm/abandon)    (0 LLM)
  |
  +-- LangChain AgentExecutor                                (1-4 LLM)
  |     tools filtered by role
  |     prompt from agent-{role}.md
  |     chat_history from our archive DB
  |
  archive_turn(identity, text, reply)
```

No separate interview routing. Patient interview is a tool
(`advance_interview`) within the patient agent. The agent decides
when to call it vs reply directly to off-topic messages.

### Agent-per-Session Model

Each doctor/patient gets a persistent agent instance that holds its
own conversation history in memory. No DB read per turn for history.

```python
MAX_HISTORY = 100  # keep last 100 turns (200 messages)

class SessionAgent:
    def __init__(self, identity: str, role: str):
        self.identity = identity
        self.role = role
        self.executor = get_agent_executor(role, identity)
        self.history: list = []  # in-memory conversation

    async def handle(self, text: str) -> str:
        result = await self.executor.ainvoke({
            "input": text,
            "chat_history": self.history,
        })
        reply = result["output"]
        self._add_turn(text, reply)
        await archive_turn(self.identity, text, reply)  # durability
        return reply

    def _add_turn(self, text: str, reply: str):
        self.history.append(HumanMessage(content=text))
        self.history.append(AIMessage(content=reply))
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]

# One agent per session, kept in memory
_agents: Dict[str, SessionAgent] = {}

def get_or_create_agent(identity: str, role: str) -> SessionAgent:
    if identity not in _agents:
        _agents[identity] = SessionAgent(identity, role)
        # Bootstrap from DB on first access (server restart recovery)
        # _agents[identity].history = load_from_archive(identity)
    return _agents[identity]
```

### Entry Point

```python
async def handle_turn(text: str, role: str, identity: str) -> str:
    """One turn. Channels call this directly."""
    agent = get_or_create_agent(identity, role)

    # Set identity for tools (ContextVar — async-safe, per-task)
    set_current_doctor(identity)

    # Fast path (0 LLM)
    fast = await try_fast_path(text, identity)
    if fast:
        agent._add_turn(text, fast)
        await archive_turn(identity, text, fast)
        return fast

    # LangChain agent (1-4 LLM)
    return await agent.handle(text)
```

Three lines of routing. The agent holds conversation state.
DB archive is for durability — if the server restarts, bootstrap
the agent's history from the archive on first access.

### Channel Integration

Each channel handles its own concerns (auth, dedup, format) and calls
`handle_turn`:

```python
# Web channel
@app.post("/chat")
async def web_chat(req: ChatInput):
    reply = await handle_turn(req.text, "doctor", req.doctor_name)
    return {"reply": reply}

# WeChat channel
async def wechat_handler(msg):
    if dedup.is_duplicate(msg.msg_id):  # WeChat-specific
        return
    reply = await handle_turn(msg.text, "doctor", msg.doctor_name)
    await wechat_send(msg.from_user, reply)
```

## LangChain Agent Setup

### Agent Construction

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

def get_agent_executor(role: str, identity: str) -> AgentExecutor:
    llm = get_llm()  # uses our provider registry
    tools = get_tools_for_role(role, identity)
    prompt = build_prompt(role)

    # create_tool_calling_agent: uses LLM's native JSON tool calls
    # (not text-based create_react_agent). Works with DeepSeek, GPT-4, Claude.
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=10,
        handle_parsing_errors=True,
    )
```

### Prompt Template

```python
def build_prompt(role: str) -> ChatPromptTemplate:
    system_text = load_prompt(f"prompts/agent-{role}.md")
    system_text = system_text.replace("{current_date}", today())
    system_text = system_text.replace("{timezone}", timezone())

    return ChatPromptTemplate.from_messages([
        ("system", system_text),
        MessagesPlaceholder("chat_history"),      # our archived turns
        ("human", "{input}"),                      # current message
        MessagesPlaceholder("agent_scratchpad"),   # LangChain manages this
    ])
```

LangChain injects two types of history:
- `chat_history` — our archived (user, assistant) pairs. We load and
  pass these in.
- `agent_scratchpad` — within-turn tool calls and results. LangChain
  manages this automatically. Ephemeral — discarded after the turn.

### LLM Provider

```python
from langchain_openai import ChatOpenAI

def get_llm() -> ChatOpenAI:
    provider = resolve_provider()  # our existing provider registry
    return ChatOpenAI(
        model=provider["model"],
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        temperature=0.1,
        max_retries=1,
    )
```

We reuse our existing provider registry to configure LangChain's LLM.
Supports DeepSeek, OpenAI, Claude, Ollama, etc.

## Tools

### Tool Definition (LangChain `@tool`)

Use LangChain's built-in `@tool` decorator. Description from docstring,
args from type hints.

```python
from langchain_core.tools import tool

@tool
async def create_record(
    patient_name: str,
    gender: str | None = None,
    age: int | None = None,
) -> dict:
    """为患者创建病历。收集对话中的临床信息，结构化后生成病历预览。
    医生确认后才会永久保存。"""
    doctor_name = get_current_doctor()  # from context var
    resolved = await resolve(patient_name, doctor_name)
    if resolved.is_clarification:
        return {"status": "clarification", "message": resolved.message}
    result = await commit_engine.create(resolved, doctor_name)
    return truncate_result(result)


@tool
async def query_records(
    patient_name: str | None = None,
    limit: int = 5,
) -> dict:
    """查询患者的既往病历记录。"""
    doctor_name = get_current_doctor()
    resolved = await resolve(patient_name, doctor_name)
    if resolved.is_clarification:
        return {"status": "clarification", "message": resolved.message}
    result = await read_engine.query(resolved, doctor_name, limit=limit)
    return truncate_result(result)


@tool
async def list_patients() -> dict:
    """列出医生的患者名单。"""
    doctor_name = get_current_doctor()
    return truncate_result(await read_engine.list_patients(doctor_name))


@tool
async def list_tasks(status: str | None = None) -> dict:
    """查询任务列表。可按状态筛选。"""
    doctor_name = get_current_doctor()
    return truncate_result(await read_engine.list_tasks(doctor_name, status))


@tool
async def update_record(instruction: str, patient_name: str | None = None) -> dict:
    """按医生指示修改现有病历。返回修改预览，医生确认后才会保存。"""
    doctor_name = get_current_doctor()
    resolved = await resolve(patient_name, doctor_name)
    if resolved.is_clarification:
        return {"status": "clarification", "message": resolved.message}
    result = await commit_engine.update_preview(resolved, doctor_name, instruction)
    return truncate_result(result)  # status: "pending_confirmation", diff preview


@tool
async def create_task(
    patient_name: str,
    title: str,
    scheduled_for: str | None = None,
    remind_at: str | None = None,
    notes: str | None = None,
) -> dict:
    """为患者创建任务或预约。scheduled_for 和 remind_at 为 ISO-8601 格式。"""
    doctor_name = get_current_doctor()
    resolved = await resolve(patient_name, doctor_name)
    if resolved.is_clarification:
        return {"status": "clarification", "message": resolved.message}
    result = await commit_engine.create_task(resolved, doctor_name,
                                              title=title,
                                              scheduled_for=scheduled_for,
                                              remind_at=remind_at,
                                              notes=notes)
    return result
```

### Doctor tools (initial migration)

| Tool | Engine | Description |
|------|--------|-------------|
| `query_records` | read engine | Fetch patient records |
| `list_patients` | read engine | List doctor's patient panel |
| `list_tasks` | read engine | List scheduled tasks |
| `create_record` | commit engine | Structure + create medical record |
| `update_record` | commit engine | Modify existing record |
| `create_task` | commit engine | Schedule task/appointment |

1:1 mapping of current capabilities. No new tools.

### Patient tools

| Tool | Engine | Description |
|------|--------|-------------|
| `advance_interview` | interview engine | Advance pre-consultation interview: extract fields, progress state machine, return next question |
| `upload_document` | record import | Submit photo/PDF/file (future) |
| `view_my_records` | read engine (scoped) | View own records (future) |
| `send_message` | message engine | Send message to doctor (future) |

### Role-based filtering

```python
DOCTOR_TOOLS = [query_records, list_patients, list_tasks,
                create_record, update_record, create_task]
PATIENT_TOOLS = [advance_interview]  # + future: upload_document, view_my_records, send_message

def get_tools_for_role(role: str, identity: str):
    # Set identity for tool context
    set_current_identity(identity)
    if role == "doctor":
        return DOCTOR_TOOLS
    return PATIENT_TOOLS
```

### Identity Injection

Tools need `doctor_name` for DB scoping but it shouldn't be a tool
parameter (the LLM doesn't decide the doctor). Use a context variable:

```python
from contextvars import ContextVar

_current_doctor: ContextVar[str] = ContextVar("current_doctor")

def set_current_doctor(name: str):
    _current_doctor.set(name)

def get_current_doctor() -> str:
    return _current_doctor.get()
```

Set once in `handle_turn` before calling the agent. All tools read it.

### Name-Based LLM Interface, ID-Based DB

The LLM passes `patient_name` in tool calls — names are the LLM-facing
interface. Internally, the DB uses `doctor_id: str` + `patient_id: int`
as actual keys. Resolve translates names to IDs.

```
Actual DB schema:
  doctors:   PRIMARY KEY (doctor_id: str)
  patients:  PRIMARY KEY (id: int), FOREIGN KEY (doctor_id), UNIQUE (doctor_id, name)
  records:   FOREIGN KEY (doctor_id, patient_id)
  tasks:     FOREIGN KEY (doctor_id, patient_id)

Tool call:
  create_record(patient_name="张三")
  → resolve("张三", doctor_id) → find_patient_by_name → Patient(id=42)
  → CRUD: get_records_for_patient(session, doctor_id, patient_id=42)
```

Resolve handles the name-to-ID translation:

```python
async def resolve(patient_name: str, doctor_id: str) -> dict:
    patient = await _find_patient(doctor_id, patient_name)
    if patient is None:
        return {"status": "not_found", "message": f"未找到患者{patient_name}"}
    return {"doctor_id": doctor_id, "patient_id": patient.id, "patient_name": patient.name}
```

This keeps the LLM interface simple (names only) while preserving the
existing ID-based DB schema.

### Tool Execution (Resolve Layer)

Every tool call goes through resolve before engine execution:

```
LLM calls tool(patient_name="张三", ...)
  |
  resolve(patient_name, doctor_id)
  |  - find_patient_by_name(session, doctor_id, name) → Patient or None
  |  - validate args
  |  - return {doctor_id, patient_id, patient_name} or clarification
  |
  if clarification → return structured error to LLM
  |
  engine(resolved["doctor_id"], resolved["patient_id"], ...) → result
  |
  truncate_result(result) → return to LLM
```

### Tool Result Size Management

```python
MAX_TOOL_RESULT_CHARS = 4000  # ~1000 tokens

def truncate_result(result: dict) -> dict:
    serialized = json.dumps(result, ensure_ascii=False)
    if len(serialized) <= MAX_TOOL_RESULT_CHARS:
        return result
    if "data" in result and isinstance(result["data"], list):
        original_count = len(result["data"])
        result["data"] = result["data"][:5]
        result["truncated"] = True
        result["total_count"] = original_count
    return result
```

### Error Handling

Tool errors are returned as structured results. LangChain feeds them
back to the LLM, which decides how to respond:

```python
# Inside a tool
try:
    result = await engine.execute(...)
    return result
except Exception as e:
    return {"status": "error", "error": str(e)}
```

The LLM sees the error and can inform the doctor naturally.
`AgentExecutor(handle_parsing_errors=True)` catches LLM output
formatting issues.

## Context Management

### No ctx — context-free architecture

`DoctorCtx` / `WorkflowState` eliminated. All state derived from
conversation history or queried from DB.

| Old (ctx-based) | New (context-free) | Source of truth |
|-----------------|-------------------|-----------------|
| `ctx.workflow.patient_id` | Resolve translates name to ID per-call | LLM passes `patient_name`, resolve returns `patient_id` |
| `ctx.workflow.patient_name` | Same | Same |
| `ctx.workflow.pending_draft_id` | Query `pending_records` table | DB (`WHERE doctor_id = ? AND status = 'awaiting'`) |
| `ctx.interview_state` | Query `interview_sessions` table | DB (`WHERE id = session_id`) |
| `load_context()` / `save_context()` | Eliminated | — |

### Turn Lifecycle

```
Turn starts:
  agent = get_or_create_agent(identity)       # in-memory (0 DB)
  (agent already holds full conversation history)

LangChain agent runs:
  chat_history = agent.history (in-memory)
  agent_scratchpad = within-turn tool calls (LangChain manages, ephemeral)

Turn ends:
  agent._add_turn(text, reply)                # in-memory append
  archive_turn(identity, text, reply)         # 1 DB write (durability)
```

One DB write per turn (archive for durability). Zero DB reads for
history — agent holds it in memory.

### Between Turns

- `agent.history` — carries forward in-memory. Capped at 100 turns.
- `agent_scratchpad` — ephemeral, discarded after each `ainvoke`.
- DB archive — durability backup. Used to bootstrap agent on restart.

### Patient History Auto-Fetch

Prompt-driven. When a patient is in scope, the LLM always calls
`query_records` first:

```
Turn 1: "张三来复诊了"
  Agent: calls query_records("张三") → sees history → replies with summary

Turn 2: "血压140/90"
  Agent: sees history summary in chat_history → no refetch → collects info
```

### Pending State

Tracked in `pending_records` table, not ctx:

```python
# In handle_turn, before agent
pending = await db.get_pending_record(identity)
if pending and CONFIRM_RE.match(text):
    await db.commit_record(pending.id)
    return "已保存"
```

## Patient Interview

The interview is a LangChain tool (`advance_interview`), not a separate
pipeline. The patient agent decides when to call it.

```python
@tool
async def advance_interview(answer: str) -> dict:
    """推进患者预问诊流程。提取临床信息，推进状态机，返回下一个问题。
    当患者提供症状、病史等临床信息时调用此工具。"""
    patient_id = get_current_identity()
    session = await db.get_or_create_interview(patient_id)
    result = await interview_engine.process(session, answer)
    return {
        "stage": result.stage,
        "next_question": result.next_question,
        "collected": result.collected,
        "complete": result.complete,
    }
```

### How it works

```
Patient: "我头疼三天了"
  Agent → calls advance_interview(answer="我头疼三天了")
  Tool → extracts chief complaint, returns next question
  Agent → "收到，头疼三天。疼痛的位置在哪里？"

Patient: "这个检查在哪里做？"
  Agent → off-topic, no tool → replies directly
  "CT检查一般在放射科。我们继续——疼痛的位置在哪里？"

Patient: "左边太阳穴"
  Agent → calls advance_interview(answer="左边太阳穴")
  Tool → extracts location, checks completeness → returns next question
```

### Benefits over separate pipeline

- One pipeline for all patient interactions
- Agent handles off-topic messages naturally (no blocked state)
- Patient can upload documents mid-interview
- No separate routing check before every turn
- Same monitoring, same error handling

### Interview state

Stored in `interview_sessions` table. The `advance_interview` tool
loads and updates the session per call. State machine tracks stages
and collected fields internally.

## Prompt Architecture

### Agent prompt (`prompts/agent.md`)

System prompt for the LangChain agent. ~150 lines of domain rules.
See `src/prompts/agent.md` for full content.

Key sections:
- Patient history auto-fetch rule
- Clinical collection rules (accumulate, max 2 follow-ups, auto-trigger)
- Field priority (必要/重要/自动填充)
- Write confirmation (preview before save)
- Safety rules (never fabricate, never guess patient names)
- Examples

What is NOT in the prompt:
- Tool schemas (LangChain injects via tool-use protocol)
- ReAct mechanics (LangChain manages agent_scratchpad)
- Chat history (LangChain injects via chat_history placeholder)

### Specialized prompts (inside tools)

| Tool | Internal LLM call | Prompt |
|------|-------------------|--------|
| `create_record` | Yes — structuring | `prompts/structuring.md` (unchanged) |
| `update_record` | Yes — re-structuring | `prompts/structuring.md` (unchanged) |
| `query_records` | No — agent LLM summarizes | — |
| Others | No | — |

### LLM Cost

- Chitchat (no tool): 1 LLM call
- Single tool: 2 calls (reason + reply)
- With history fetch: 3 calls
- Multi-action: 3-4 calls

Deterministic fast path (0 calls) and interview (1 call) unchanged.

## Dependencies

### New

| Package | Purpose |
|---------|---------|
| `langchain` | Agent framework, tool decorator |
| `langchain-openai` | ChatOpenAI LLM wrapper |
| `langchain-core` | Prompt templates, message types |

### Unchanged

- `openai` (AsyncOpenAI — used by provider registry and structuring LLM)
- `sqlalchemy` (DB)
- `fastapi` (Web channel)
- `wechatpy` (WeChat channel)

## Migration from UEC

| UEC component | New location | Notes |
|---------------|-------------|-------|
| `turn.py` | `handle_turn` + LangChain `AgentExecutor` | Routing in handle_turn; ReAct loop delegated to LangChain |
| `understand.py` | Removed | LLM reasoning handled by LangChain agent |
| `resolve.py` | Inside each `@tool` function | Same validation logic, called per tool |
| `read_engine.py` | Called by `@tool` functions | `query_records`, `list_patients`, `list_tasks` |
| `commit_engine.py` | Called by `@tool` functions | `create_record`, `update_record`, `create_task` |
| `compose.py` | Removed | Agent LLM composes replies naturally |
| `types.py` | Removed | ActionType enum replaced by LangChain tool definitions |
| `models.py` | Simplified | `DoctorCtx` / `WorkflowState` eliminated |
| `context.py` | Mostly removed | Only `archive_turns` and `get_recent_turns` remain |
| `dedup.py` | Moved to channel layer | WeChat channel deduplicates before handle_turn |

## What This Eliminates

- `DoctorCtx` / `WorkflowState` — no persistent context
- `load_context()` / `save_context()` — no ctx lifecycle
- `compose.py` — agent LLM handles replies
- `understand.py` — agent LLM handles reasoning
- `types.py` — LangChain tool schemas replace ActionType enum
- Custom ReAct loop — LangChain's `AgentExecutor` handles this
- Patient binding tracking — LLM derives from conversation

## What This Does NOT Change

- Database schema
- Patient lookup logic in resolve
- Medical record structuring (`prompts/structuring.md`)
- Channel adapters (Web, WeChat)
- Provider registry (configures LangChain's LLM)
- Audit logging
- Interview engine (now a LangChain tool, but internal logic unchanged)
- Archive persistence

## Cleanup & Simplification

### Delete entirely

| Module | Why redundant |
|--------|--------------|
| `services/runtime/understand.py` | LangChain agent handles reasoning |
| `services/runtime/compose.py` | Agent LLM composes replies naturally |
| `services/runtime/types.py` | `ActionType` enum → LangChain `@tool` definitions |
| `services/runtime/models.py` | `DoctorCtx`, `WorkflowState`, `MemoryState` eliminated |
| `prompts/understand.md` | Replaced by `prompts/agent.md` |
| `services/domain/intent_handlers/` | Intent classification → agent decides which tool |
| `services/hooks.py` | 6 hook stages mapped to UEC pipeline stages that no longer exist |

### Simplify heavily

| Module | Before | After |
|--------|--------|-------|
| `turn.py` (323 lines) | UEC orchestrator | `handle_turn` ~50 lines: fast paths + agent + archive |
| `context.py` | load/save ctx + archive | Keep only `archive_turns`, `get_recent_turns` |
| `resolve.py` | ActionIntent binding, name→ID lookup, read/write asymmetry | Simplified: check `patient_name` exists in DB (name is the key). ~10 lines. Inside each tool |
| `dedup.py` | Pipeline-level LRU dedup | Move to WeChat channel only |
| `messages.py` (~150 lines) | 40+ template messages | Keep ~5 for fast paths (greeting, confirm, error). Agent generates the rest |

### Delete when RAG arrives (future)

| Module | Replaced by |
|--------|------------|
| `services/knowledge/doctor_knowledge.py` | RAG vector search |
| `services/knowledge/skill_loader.py` | RAG-retrievable specialty knowledge |
| `skills/` directory (SKILL.md files) | RAG knowledge base |

### Architectural concepts that disappear

| Concept | Replacement |
|---------|------------|
| 5-layer intent pipeline (classify→extract→bind→plan→gate) | Agent decides in one loop |
| `ActionType` enum | `@tool` definitions |
| `RESPONSE_MODE_TABLE` (direct_reply, llm_compose, template) | Agent always generates reply |
| Read/write binding asymmetry | No binding state. LLM passes patient_name per call |
| `compose_llm` (separate LLM for read summarization) | Agent sees tool result, summarizes naturally |
| `UnderstandResult` / `ActionIntent` / `ResolvedAction` dataclasses | Tool args + tool results |
| `Clarification` model (7 kinds, composition rules) | Agent generates clarifications from tool error results |
| `ChannelAdapter` protocol + adapter classes | `handle_turn(text, role, identity)` is the interface |
| `Message` dataclass | Not needed — `handle_turn` takes `text` |
| Draft guard / pending guard | DB query in fast path |
| `memory_patch` / `MemoryState` | Already dead, confirmed delete |

### Estimated line count impact

| | Before | After | Delta |
|--|--------|-------|-------|
| `turn.py` | 323 | ~50 | -270 |
| `understand.py` | 215 | 0 | -215 |
| `compose.py` | ~200 | 0 | -200 |
| `types.py` | 161 | 0 | -161 |
| `models.py` | ~80 | ~20 | -60 |
| `context.py` | ~180 | ~60 | -120 |
| `resolve.py` | ~300 | ~150 | -150 |
| `messages.py` | ~150 | ~30 | -120 |
| `hooks.py` | ~100 | 0 | -100 |
| Tools (new) | 0 | ~200 | +200 |
| **Total** | **~1700** | **~510** | **~-1200** |

~1200 lines deleted, replaced by ~200 lines of tool definitions +
LangChain configuration. Domain logic (resolve, engines) stays but
simplifies.

## Future Extensions

New capability = new `@tool` function. No framework changes:

- `search_knowledge` — RAG (deferred)
- `generate_differential` — diagnostic reasoning (Phase 2)
- `suggest_workup`, `suggest_treatment` — clinical decision support
- Patient tools: `upload_document`, `view_my_records`, `send_message`
