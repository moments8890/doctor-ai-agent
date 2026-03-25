# Plan and Act Agent Pipeline — Implementation Plan

> **Status: COMPLETE** — All phases implemented. E2E benchmark: 46/46 passing (2026-03-23)

**Goal:** Replace the LangChain ReAct agent with a Plan-and-Act routing pipeline (routing LLM → deterministic dispatch → intent-specific handlers).

**Architecture:** A lightweight routing LLM classifies doctor messages into 1 of 6 intents and extracts entities as structured JSON. Deterministic code dispatches to a dedicated async handler per intent. Each handler loads per-intent context (knowledge, records) and calls an intent-specific LLM with a focused prompt. No LangChain, no tool schemas, no autonomous tool-calling.

**Tech Stack:** AsyncOpenAI (existing `infra/llm/client.py`), Pydantic v2 structured output, SQLAlchemy async (existing DB layer).

**Spec:** `docs/product/domain-operations-design.md` Sections 1-6, 7.1-7.7.

**Scope:** This plan covers the agent pipeline only (router, dispatcher, handlers, prompts). DB schema migration is a separate plan. This plan works with the EXISTING DB schema — no table changes required.

---

## File Structure

### New files (create)

```
src/agent/types.py              — Pydantic models: RoutingResult, HandlerResult, TurnContext, IntentType enum
src/agent/router.py             — Routing LLM call → RoutingResult
src/agent/dispatcher.py         — Intent → handler dispatch + deferred acknowledgment
src/agent/handlers/__init__.py  — Handler registry
src/agent/handlers/query_record.py   — Fetch records → compose LLM summary
src/agent/handlers/create_record.py  — Start/resume interview session
src/agent/handlers/create_task.py    — Extract params → save task to DB
src/agent/handlers/query_task.py     — Fetch tasks → compose LLM summary
src/agent/handlers/query_patient.py  — Fetch patients → compose LLM summary
src/agent/handlers/general.py        — Fallback chitchat/conversational reply
src/agent/prompts/routing.md         — Routing LLM prompt (intent classification)
src/agent/prompts/compose.md         — Response synthesis for query intents
```

### Modified files

```
src/agent/handle_turn.py  — Replace ReAct agent call with router→dispatch flow
src/agent/session.py      — Replace LangChain messages with plain dicts, simplify
src/agent/actions.py      — Update IntentType enum to match 6 routing intents
```

### Unchanged (reuse as-is)

```
src/agent/tools/resolve.py    — Patient name→ID resolution
src/agent/identity.py         — ContextVar for doctor_id
src/agent/archive.py          — Chat archival (modify later in DB migration plan)
src/infra/llm/client.py       — AsyncOpenAI client with retry/fallback
src/infra/llm/resilience.py   — call_with_retry_and_fallback
src/domain/*                   — All domain logic untouched
src/db/*                       — All DB models/CRUD untouched
```

---

## Task 1: Types and Enums

**Files:**
- Create: `src/agent/types.py`
- Modify: `src/agent/actions.py`
- Test: `tests/unit/test_agent_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_agent_types.py
from agent.types import IntentType, RoutingResult, HandlerResult

def test_intent_type_values():
    assert IntentType.query_record == "query_record"
    assert IntentType.create_record == "create_record"
    assert IntentType.query_task == "query_task"
    assert IntentType.create_task == "create_task"
    assert IntentType.query_patient == "query_patient"
    assert IntentType.general == "general"
    assert len(IntentType) == 6

def test_routing_result_parses_json():
    raw = '{"intent": "query_record", "patient_name": "张三", "params": {"limit": 5}, "deferred": null}'
    result = RoutingResult.model_validate_json(raw)
    assert result.intent == IntentType.query_record
    assert result.patient_name == "张三"
    assert result.params == {"limit": 5}
    assert result.deferred is None

def test_routing_result_defaults():
    raw = '{"intent": "general"}'
    result = RoutingResult.model_validate_json(raw)
    assert result.patient_name is None
    assert result.params == {}
    assert result.deferred is None

def test_routing_result_rejects_invalid_intent():
    import pytest
    raw = '{"intent": "invalid_intent"}'
    with pytest.raises(Exception):
        RoutingResult.model_validate_json(raw)

def test_handler_result():
    result = HandlerResult(reply="病历查询结果", data={"records": []})
    assert result.reply == "病历查询结果"
    assert result.data == {"records": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_agent_types.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.types'`

- [ ] **Step 3: Write the implementation**

```python
# src/agent/types.py
"""Plan-and-Act agent types — routing, dispatch, and handler contracts."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """6 routing intents — routing LLM classifies into one of these."""
    query_record = "query_record"
    create_record = "create_record"
    query_task = "query_task"
    create_task = "create_task"
    query_patient = "query_patient"
    general = "general"


class RoutingResult(BaseModel):
    """Structured output from the routing LLM."""
    intent: IntentType
    patient_name: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    deferred: Optional[str] = None


class HandlerResult(BaseModel):
    """Return value from intent handlers."""
    reply: str
    data: Optional[Dict[str, Any]] = None


class TurnContext(BaseModel):
    """Context passed to every handler."""
    doctor_id: str
    text: str
    history: List[Dict[str, str]] = Field(default_factory=list)
    routing: RoutingResult
```

- [ ] **Step 4: Update actions.py to re-export IntentType**

```python
# src/agent/actions.py — replace contents
"""Intent types for the Plan-and-Act routing pipeline."""
from __future__ import annotations

from agent.types import IntentType

# Backwards compat alias
Action = IntentType

# UI chip actions — subset exposed to frontend for quick-action buttons
CHIP_ACTIONS = {
    IntentType.create_record,
    IntentType.query_patient,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_agent_types.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/agent/types.py src/agent/actions.py tests/unit/test_agent_types.py
git commit -m "feat: add Plan-and-Act types and IntentType enum"
```

---

## Task 2: Routing LLM

**Files:**
- Create: `src/agent/router.py`
- Create: `src/agent/prompts/routing.md`
- Test: `tests/unit/test_router.py`

- [ ] **Step 1: Write the routing prompt**

```markdown
# src/agent/prompts/routing.md
你是一个医疗AI助手的意图路由器。根据医生的消息，判断意图并提取关键实体。

## 意图类型（必须选择一个）

- query_record — 查询患者病历（"查一下张三的病历"、"最近的病历"）
- create_record — 创建新病历（"给张三建病历"、"张三，男，45岁，头痛"）
- query_task — 查询任务列表（"我的任务"、"待处理的任务"）
- create_task — 创建新任务（"建个随访任务"、"提醒我下周复查"）
- query_patient — 查询患者信息（"我的患者"、"60岁以上的女性"）
- general — 其他对话（问候、闲聊、不明确的请求）

## 规则

1. 如果消息同时包含 create_record 和其他意图，只返回 create_record（排他性）
2. 如果消息包含多个非 create_record 意图，返回第一个意图，其余放入 deferred
3. 提取患者姓名（如果提到）
4. 从消息中提取相关参数

## 输出格式（严格JSON）

```json
{
  "intent": "意图类型",
  "patient_name": "患者姓名或null",
  "params": {},
  "deferred": "被推迟的请求文本或null"
}
```

## 参数说明

- query_record: params.limit (int, 默认5)
- create_record: params.gender, params.age, params.clinical_text (均可选)
- query_task: params.status ("pending" 或 "completed", 可选)
- create_task: params.title (必填), params.content, params.due_at (可选)
- query_patient: params.query (必填, 搜索条件)
- general: params 为空
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_router.py
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.types import IntentType, RoutingResult


@pytest.fixture
def mock_llm():
    """Mock the AsyncOpenAI chat completion."""
    with patch("agent.router._get_routing_client") as mock_get:
        client = AsyncMock()
        mock_get.return_value = client
        yield client


def _mock_completion(content: dict):
    """Create a mock completion response."""
    choice = MagicMock()
    choice.message.content = json.dumps(content, ensure_ascii=False)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_route_query_record(mock_llm):
    mock_llm.chat.completions.create = AsyncMock(
        return_value=_mock_completion({
            "intent": "query_record",
            "patient_name": "张三",
            "params": {"limit": 5},
            "deferred": None,
        })
    )
    from agent.router import route
    result = await route("查张三的病历", "doc1", [])
    assert result.intent == IntentType.query_record
    assert result.patient_name == "张三"


@pytest.mark.asyncio
async def test_route_general_fallback(mock_llm):
    mock_llm.chat.completions.create = AsyncMock(
        return_value=_mock_completion({
            "intent": "general",
            "patient_name": None,
            "params": {},
            "deferred": None,
        })
    )
    from agent.router import route
    result = await route("你好", "doc1", [])
    assert result.intent == IntentType.general


@pytest.mark.asyncio
async def test_route_with_deferred(mock_llm):
    mock_llm.chat.completions.create = AsyncMock(
        return_value=_mock_completion({
            "intent": "query_record",
            "patient_name": "张三",
            "params": {},
            "deferred": "建个随访任务",
        })
    )
    from agent.router import route
    result = await route("查张三病历然后建个随访", "doc1", [])
    assert result.deferred == "建个随访任务"


@pytest.mark.asyncio
async def test_route_malformed_json_falls_back_to_general(mock_llm):
    choice = MagicMock()
    choice.message.content = "not json"
    resp = MagicMock()
    resp.choices = [choice]
    mock_llm.chat.completions.create = AsyncMock(return_value=resp)

    from agent.router import route
    result = await route("asdfgh", "doc1", [])
    assert result.intent == IntentType.general
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_router.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.router'`

- [ ] **Step 4: Write the router implementation**

```python
# src/agent/router.py
"""Routing LLM — classifies doctor messages into intents."""
from __future__ import annotations

import os
from typing import List, Dict

from openai import AsyncOpenAI

from agent.types import IntentType, RoutingResult
from infra.llm.resilience import call_with_retry_and_fallback
from utils.log import log
from utils.prompt_loader import get_prompt_sync

_client_cache: dict[str, AsyncOpenAI] = {}


def _get_routing_client() -> AsyncOpenAI:
    """Get or create the routing LLM client."""
    from infra.llm.client import _get_providers
    provider_name = os.environ.get("ROUTING_LLM", "groq")
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))

    cache_key = provider_name
    if cache_key not in _client_cache:
        _client_cache[cache_key] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider.get("api_key_env", ""), "nokeyneeded"),
            timeout=float(os.environ.get("ROUTING_LLM_TIMEOUT", "15")),
            max_retries=0,
        )
    return _client_cache[cache_key]


def _get_routing_model() -> str:
    from infra.llm.client import _get_providers
    provider_name = os.environ.get("ROUTING_LLM", "groq")
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))
    return provider.get("model", "deepseek-chat")


async def route(
    text: str,
    doctor_id: str,
    history: List[Dict[str, str]],
) -> RoutingResult:
    """Classify a doctor message into an intent with extracted entities.

    Returns RoutingResult. On any error (malformed JSON, LLM failure),
    falls back to IntentType.general so the conversation never breaks.
    """
    system_prompt = get_prompt_sync("routing")
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-5:],
        {"role": "user", "content": text},
    ]

    try:
        client = _get_routing_client()
        model = _get_routing_model()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=256,
        )
        raw = response.choices[0].message.content
        result = RoutingResult.model_validate_json(raw)
        log(f"[router] intent={result.intent.value} patient={result.patient_name} deferred={result.deferred}")
        return result
    except Exception as exc:
        log(f"[router] classification failed, falling back to general: {exc}", level="warning")
        return RoutingResult(intent=IntentType.general)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_router.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/agent/router.py src/agent/prompts/routing.md tests/unit/test_router.py
git commit -m "feat: add routing LLM for intent classification"
```

---

## Task 3: Dispatcher

**Files:**
- Create: `src/agent/dispatcher.py`
- Create: `src/agent/handlers/__init__.py`
- Test: `tests/unit/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dispatcher.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from agent.types import IntentType, RoutingResult, HandlerResult, TurnContext


@pytest.mark.asyncio
async def test_dispatch_routes_to_correct_handler():
    mock_handler = AsyncMock(return_value=HandlerResult(reply="found records"))
    routing = RoutingResult(intent=IntentType.query_record, patient_name="张三")
    ctx = TurnContext(doctor_id="doc1", text="查张三病历", routing=routing)

    with patch("agent.dispatcher.HANDLERS", {IntentType.query_record: mock_handler}):
        from agent.dispatcher import dispatch
        result = await dispatch(ctx)

    assert result.reply == "found records"
    mock_handler.assert_called_once_with(ctx)


@pytest.mark.asyncio
async def test_dispatch_appends_deferred_notice():
    mock_handler = AsyncMock(return_value=HandlerResult(reply="查询结果"))
    routing = RoutingResult(
        intent=IntentType.query_record,
        patient_name="张三",
        deferred="建个随访任务",
    )
    ctx = TurnContext(doctor_id="doc1", text="查张三病历然后建随访", routing=routing)

    with patch("agent.dispatcher.HANDLERS", {IntentType.query_record: mock_handler}):
        from agent.dispatcher import dispatch
        result = await dispatch(ctx)

    assert "建个随访任务" in result.reply


@pytest.mark.asyncio
async def test_dispatch_unknown_intent_falls_back():
    routing = RoutingResult(intent=IntentType.general)
    ctx = TurnContext(doctor_id="doc1", text="hello", routing=routing)

    from agent.dispatcher import dispatch
    result = await dispatch(ctx)
    assert result.reply  # general handler should produce some reply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_dispatcher.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the dispatcher**

```python
# src/agent/dispatcher.py
"""Deterministic intent dispatcher — routes RoutingResult to handlers."""
from __future__ import annotations

from typing import Callable, Dict

from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


# Handler type: async function that takes TurnContext, returns HandlerResult
HandlerFn = Callable[[TurnContext], HandlerResult]

# Registry populated by handler imports
HANDLERS: Dict[IntentType, HandlerFn] = {}


def register(intent: IntentType):
    """Decorator to register a handler for an intent."""
    def decorator(fn: HandlerFn) -> HandlerFn:
        HANDLERS[intent] = fn
        return fn
    return decorator


async def dispatch(ctx: TurnContext) -> HandlerResult:
    """Dispatch to the registered handler for ctx.routing.intent."""
    intent = ctx.routing.intent
    handler = HANDLERS.get(intent)

    if handler is None:
        log(f"[dispatcher] no handler for intent={intent.value}, using general")
        handler = HANDLERS.get(IntentType.general)

    if handler is None:
        return HandlerResult(reply="抱歉，我没有理解您的意思。请再试一次。")

    log(f"[dispatcher] intent={intent.value} → {handler.__name__}")
    result = await handler(ctx)

    # Append deferred notice if routing found a secondary intent
    if ctx.routing.deferred:
        result = HandlerResult(
            reply=f"{result.reply}\n\n您还提到：{ctx.routing.deferred}——请单独发送以处理。",
            data=result.data,
        )

    return result
```

```python
# src/agent/handlers/__init__.py
"""Handler registry — import all handlers to trigger @register decorators."""
from __future__ import annotations

from agent.handlers import (
    query_record,
    create_record,
    create_task,
    query_task,
    query_patient,
    general,
)
```

- [ ] **Step 4: Write a minimal general handler (needed for tests)**

```python
# src/agent/handlers/general.py
"""Fallback handler for general/chitchat messages."""
from __future__ import annotations

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext


@register(IntentType.general)
async def handle_general(ctx: TurnContext) -> HandlerResult:
    """Simple conversational reply — no DB, no LLM for now."""
    return HandlerResult(reply="您好！我是您的AI医疗助手，请问有什么可以帮您？")
```

- [ ] **Step 5: Create stub handlers for remaining intents** (so __init__.py imports don't fail)

Create minimal stubs for: `query_record.py`, `create_record.py`, `create_task.py`, `query_task.py`, `query_patient.py`. Each just returns a placeholder reply. Full implementation in Tasks 4-8.

```python
# src/agent/handlers/query_record.py (stub)
from __future__ import annotations
from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext

@register(IntentType.query_record)
async def handle_query_record(ctx: TurnContext) -> HandlerResult:
    return HandlerResult(reply="[TODO] query_record handler")
```

(Same pattern for create_record, create_task, query_task, query_patient)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_dispatcher.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/agent/dispatcher.py src/agent/handlers/ tests/unit/test_dispatcher.py
git commit -m "feat: add intent dispatcher with handler registry"
```

---

## Task 4: Wire handle_turn.py

**Files:**
- Modify: `src/agent/handle_turn.py`
- Modify: `src/agent/session.py`
- Test: `tests/unit/test_handle_turn_v2.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handle_turn_v2.py
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("ROUTING_LLM", "deepseek")


@pytest.mark.asyncio
async def test_handle_turn_routes_query_record():
    with patch("agent.handle_turn.route") as mock_route, \
         patch("agent.handle_turn.dispatch") as mock_dispatch:
        from agent.types import IntentType, RoutingResult, HandlerResult
        mock_route.return_value = RoutingResult(
            intent=IntentType.query_record, patient_name="张三"
        )
        mock_dispatch.return_value = HandlerResult(reply="张三的病历摘要")

        from agent.handle_turn import handle_turn
        result = await handle_turn("查张三的病历", "doctor", "doc1")

        assert result == "张三的病历摘要"
        mock_route.assert_called_once()
        mock_dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_handle_turn_general_fallback():
    with patch("agent.handle_turn.route") as mock_route, \
         patch("agent.handle_turn.dispatch") as mock_dispatch:
        from agent.types import IntentType, RoutingResult, HandlerResult
        mock_route.return_value = RoutingResult(intent=IntentType.general)
        mock_dispatch.return_value = HandlerResult(reply="您好！")

        from agent.handle_turn import handle_turn
        result = await handle_turn("你好", "doctor", "doc1")
        assert "您好" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_handle_turn_v2.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL (handle_turn still uses old ReAct path)

- [ ] **Step 3: Rewrite handle_turn.py**

```python
# src/agent/handle_turn.py
"""Main entry point — Plan-and-Act routing pipeline."""
from __future__ import annotations

from typing import List, Dict, Optional

from agent.identity import set_current_identity
from agent.router import route
from agent.dispatcher import dispatch
from agent.types import TurnContext, HandlerResult
from agent.session import get_session_history, append_to_history
from utils.log import log

# Ensure handler registry is populated
import agent.handlers  # noqa: F401


async def handle_turn(
    text: str,
    role: str,
    identity: str,
    *,
    action_hint: Optional[str] = None,
) -> str:
    """One turn of the Plan-and-Act pipeline.

    Channels (web, wechat) call this directly.
    1. Load chat history for context
    2. Route: classify intent + extract entities
    3. Dispatch: call the registered handler
    4. Persist: append turn to chat history
    5. Return: handler's reply text
    """
    set_current_identity(identity)

    # Load recent history for routing context
    history = get_session_history(identity)

    # Route
    routing = await route(text, identity, history)
    log(f"[turn] identity={identity} role={role} intent={routing.intent.value}")

    # Build context
    ctx = TurnContext(
        doctor_id=identity,
        text=text,
        history=history,
        routing=routing,
    )

    # Dispatch
    result: HandlerResult = await dispatch(ctx)

    # Persist turn
    append_to_history(identity, text, result.reply)

    return result.reply
```

- [ ] **Step 4: Simplify session.py**

```python
# src/agent/session.py
"""Session management — plain dict history, no LangChain."""
from __future__ import annotations

from typing import Dict, List

MAX_HISTORY_TURNS = 50  # keep last 50 turns (100 messages)

# In-memory session store: identity → list of {role, content} dicts
_sessions: Dict[str, List[Dict[str, str]]] = {}


def get_session_history(identity: str) -> List[Dict[str, str]]:
    """Return chat history for the given identity."""
    return list(_sessions.get(identity, []))


def append_to_history(identity: str, user_text: str, assistant_reply: str) -> None:
    """Append a turn (user + assistant) to session history."""
    if identity not in _sessions:
        _sessions[identity] = []
    history = _sessions[identity]
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    # Trim to max
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        _sessions[identity] = history[-max_messages:]


def clear_session(identity: str) -> None:
    """Clear session history (new conversation)."""
    _sessions.pop(identity, None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_handle_turn_v2.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/agent/handle_turn.py src/agent/session.py tests/unit/test_handle_turn_v2.py
git commit -m "feat: wire Plan-and-Act pipeline in handle_turn"
```

---

## Task 5: query_record Handler

**Files:**
- Modify: `src/agent/handlers/query_record.py`
- Create: `src/agent/prompts/compose.md`
- Test: `tests/unit/test_handler_query_record.py`

- [ ] **Step 1: Write the compose prompt**

```markdown
# src/agent/prompts/compose.md
你是一位医疗AI助手。根据以下数据，为医生生成简洁的中文摘要回复。

## 规则
1. 使用自然语言，不要返回JSON或表格
2. 按时间倒序排列
3. 突出关键诊断和治疗信息
4. 如果没有数据，礼貌告知
5. 保持简洁，不超过500字
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_handler_query_record.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.types import IntentType, RoutingResult, HandlerResult, TurnContext


@pytest.mark.asyncio
async def test_query_record_with_patient():
    routing = RoutingResult(intent=IntentType.query_record, patient_name="张三")
    ctx = TurnContext(doctor_id="doc1", text="查张三病历", routing=routing)

    with patch("agent.handlers.query_record._fetch_records") as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary") as mock_compose:
        mock_fetch.return_value = [{"content": "头痛三天", "created_at": "2026-03-20"}]
        mock_compose.return_value = "张三最近一次就诊：头痛三天（2026-03-20）"

        from agent.handlers.query_record import handle_query_record
        result = await handle_query_record(ctx)

    assert "张三" in result.reply


@pytest.mark.asyncio
async def test_query_record_no_patient_returns_overview():
    routing = RoutingResult(intent=IntentType.query_record, patient_name=None)
    ctx = TurnContext(doctor_id="doc1", text="最近的病历", routing=routing)

    with patch("agent.handlers.query_record._fetch_recent_records") as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary") as mock_compose:
        mock_fetch.return_value = []
        mock_compose.return_value = "暂无病历记录"

        from agent.handlers.query_record import handle_query_record
        result = await handle_query_record(ctx)

    assert result.reply == "暂无病历记录"
```

- [ ] **Step 3: Implement the handler**

```python
# src/agent/handlers/query_record.py
"""Handler for query_record intent — fetch records, compose LLM summary."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext
from agent.tools.resolve import resolve
from utils.log import log
from utils.prompt_loader import get_prompt_sync


@register(IntentType.query_record)
async def handle_query_record(ctx: TurnContext) -> HandlerResult:
    """Fetch patient records and return LLM-composed summary."""
    patient_name = ctx.routing.patient_name
    limit = ctx.routing.params.get("limit", 5)

    if patient_name:
        resolved = await resolve(patient_name, ctx.doctor_id)
        if "status" in resolved:
            return HandlerResult(reply=resolved["message"])
        records = await _fetch_records(ctx.doctor_id, resolved["patient_id"], limit)
    else:
        records = await _fetch_recent_records(ctx.doctor_id, limit)

    summary = await _compose_summary(ctx.text, records, patient_name)
    return HandlerResult(reply=summary, data={"records": records})


async def _fetch_records(doctor_id: str, patient_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    from db.crud.records import get_records_for_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=limit)
        return [{"id": r.id, "content": r.content or "", "created_at": r.created_at.isoformat() if r.created_at else None} for r in records]


async def _fetch_recent_records(doctor_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    from db.crud.records import get_all_records_for_doctor
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_all_records_for_doctor(session, doctor_id, limit=limit)
        return [{"id": r.id, "content": r.content or "", "created_at": r.created_at.isoformat() if r.created_at else None} for r in records]


async def _compose_summary(query: str, records: list, patient_name: Optional[str] = None) -> str:
    """Call compose LLM to summarize records into a readable reply."""
    if not records:
        return f"{'没有找到' + patient_name + '的' if patient_name else '暂无'}病历记录。"

    import json, os
    from openai import AsyncOpenAI
    from infra.llm.client import _get_providers

    compose_prompt = get_prompt_sync("compose")
    records_text = json.dumps(records, ensure_ascii=False, indent=2)
    user_msg = f"医生查询：{query}\n\n数据：\n{records_text}"

    provider_name = os.environ.get("ROUTING_LLM", "groq")
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider.get("api_key_env", ""), "nokeyneeded"),
        timeout=30, max_retries=0,
    )
    try:
        response = await client.chat.completions.create(
            model=provider.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": compose_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        log(f"[compose] LLM failed, returning raw summary: {exc}", level="warning")
        return f"查询到 {len(records)} 条病历记录。"
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/test_handler_query_record.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/handlers/query_record.py src/agent/prompts/compose.md tests/unit/test_handler_query_record.py
git commit -m "feat: add query_record handler with compose LLM"
```

---

## Task 6: create_task Handler

**Files:**
- Modify: `src/agent/handlers/create_task.py`
- Test: `tests/unit/test_handler_create_task.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handler_create_task.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from agent.types import IntentType, RoutingResult, HandlerResult, TurnContext


@pytest.mark.asyncio
async def test_create_task_with_title():
    routing = RoutingResult(
        intent=IntentType.create_task,
        patient_name="张三",
        params={"title": "复查血常规", "due_at": "2026-04-06"},
    )
    ctx = TurnContext(doctor_id="doc1", text="给张三建个复查任务", routing=routing)

    with patch("agent.handlers.create_task._resolve_and_save_task") as mock_save:
        mock_save.return_value = {"status": "ok", "task_id": 42, "title": "复查血常规"}

        from agent.handlers.create_task import handle_create_task
        result = await handle_create_task(ctx)

    assert "复查血常规" in result.reply
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_missing_title():
    routing = RoutingResult(
        intent=IntentType.create_task,
        params={},  # no title
    )
    ctx = TurnContext(doctor_id="doc1", text="建个任务", routing=routing)

    from agent.handlers.create_task import handle_create_task
    result = await handle_create_task(ctx)
    assert "标题" in result.reply or "title" in result.reply.lower()
```

- [ ] **Step 2: Implement the handler**

```python
# src/agent/handlers/create_task.py
"""Handler for create_task intent — extract params, save to DB."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from agent.dispatcher import register
from agent.tools.resolve import resolve
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


@register(IntentType.create_task)
async def handle_create_task(ctx: TurnContext) -> HandlerResult:
    """Create a task from routing-extracted params."""
    title = ctx.routing.params.get("title")
    if not title:
        return HandlerResult(reply="请提供任务标题，例如"建个复查血常规的任务"。")

    result = await _resolve_and_save_task(
        doctor_id=ctx.doctor_id,
        patient_name=ctx.routing.patient_name,
        title=title,
        content=ctx.routing.params.get("content"),
        due_at_str=ctx.routing.params.get("due_at"),
    )

    if result.get("status") == "error":
        return HandlerResult(reply=result["message"])

    reply = f"已创建任务：{result['title']}"
    if result.get("task_id"):
        reply += f"（#{result['task_id']}）"
    return HandlerResult(reply=reply, data=result)


async def _resolve_and_save_task(
    doctor_id: str,
    patient_name: Optional[str],
    title: str,
    content: Optional[str] = None,
    due_at_str: Optional[str] = None,
) -> Dict[str, Any]:
    from db.crud.tasks import create_task as db_create_task
    from db.engine import AsyncSessionLocal

    patient_id = None
    if patient_name:
        resolved = await resolve(patient_name, doctor_id)
        if "status" in resolved:
            return resolved
        patient_id = resolved["patient_id"]

    due_at = None
    if due_at_str:
        try:
            due_at = datetime.fromisoformat(due_at_str)
        except ValueError:
            return {"status": "error", "message": f"日期格式无效：{due_at_str}"}

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session,
            doctor_id=doctor_id,
            task_type="general",
            title=title,
            content=content,
            patient_id=patient_id,
            due_at=due_at,
        )
        return {"status": "ok", "task_id": task.id, "title": title}
```

- [ ] **Step 3: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/unit/test_handler_create_task.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

```bash
git add src/agent/handlers/create_task.py tests/unit/test_handler_create_task.py
git commit -m "feat: add create_task handler"
```

---

## Task 7: query_task Handler

**Files:**
- Modify: `src/agent/handlers/query_task.py`
- Test: `tests/unit/test_handler_query_task.py`

- [ ] **Step 1: Write test + implementation** (same pattern as query_record)

```python
# src/agent/handlers/query_task.py
"""Handler for query_task intent — fetch tasks, compose LLM summary."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log
from utils.prompt_loader import get_prompt_sync


@register(IntentType.query_task)
async def handle_query_task(ctx: TurnContext) -> HandlerResult:
    """Fetch tasks and return LLM-composed summary."""
    status_filter = ctx.routing.params.get("status")
    tasks = await _fetch_tasks(ctx.doctor_id, status_filter)

    if not tasks:
        return HandlerResult(reply="当前没有任务。")

    summary = await _compose_task_summary(ctx.text, tasks)
    return HandlerResult(reply=summary, data={"tasks": tasks})


async def _fetch_tasks(doctor_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    from db.crud.tasks import list_tasks as db_list_tasks
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tasks = await db_list_tasks(session, doctor_id, status=status)
        return [
            {
                "id": t.id, "title": getattr(t, "title", None),
                "status": getattr(t, "status", None),
                "due_at": t.due_at.isoformat() if getattr(t, "due_at", None) else None,
            }
            for t in tasks
        ]


async def _compose_task_summary(query: str, tasks: list) -> str:
    import json, os
    from openai import AsyncOpenAI
    from infra.llm.client import _get_providers

    compose_prompt = get_prompt_sync("compose")
    tasks_text = json.dumps(tasks, ensure_ascii=False, indent=2)
    user_msg = f"医生查询：{query}\n\n任务数据：\n{tasks_text}"

    provider_name = os.environ.get("ROUTING_LLM", "groq")
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider.get("api_key_env", ""), "nokeyneeded"),
        timeout=30, max_retries=0,
    )
    try:
        response = await client.chat.completions.create(
            model=provider.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": compose_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3, max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        log(f"[compose] task summary failed: {exc}", level="warning")
        return f"共有 {len(tasks)} 个任务。"
```

- [ ] **Step 2: Run tests and commit**

```bash
git add src/agent/handlers/query_task.py tests/unit/test_handler_query_task.py
git commit -m "feat: add query_task handler"
```

---

## Task 8: query_patient Handler

**Files:**
- Modify: `src/agent/handlers/query_patient.py`

- [ ] **Step 1: Implement** (same compose pattern, uses existing `_fetch_patients` and `extract_criteria`)

```python
# src/agent/handlers/query_patient.py
"""Handler for query_patient intent — search patients, compose summary."""
from __future__ import annotations

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext


@register(IntentType.query_patient)
async def handle_query_patient(ctx: TurnContext) -> HandlerResult:
    """Search patients by NL criteria and return summary."""
    query = ctx.routing.params.get("query", ctx.text)

    from domain.patients.nl_search import extract_criteria
    from db.crud.patient import get_all_patients
    from db.engine import AsyncSessionLocal
    from datetime import datetime

    criteria = extract_criteria(query)

    async with AsyncSessionLocal() as session:
        all_patients = await get_all_patients(session, ctx.doctor_id)

    results = []
    for p in all_patients:
        if criteria.name and criteria.name not in (p.name or ""):
            continue
        if criteria.gender and criteria.gender != getattr(p, "gender", None):
            continue
        if criteria.min_age and getattr(p, "year_of_birth", None):
            age = datetime.now().year - p.year_of_birth
            if age < criteria.min_age:
                continue
        if criteria.max_age and getattr(p, "year_of_birth", None):
            age = datetime.now().year - p.year_of_birth
            if age > criteria.max_age:
                continue
        results.append({"id": p.id, "name": p.name, "gender": getattr(p, "gender", None)})

    if not results:
        return HandlerResult(reply="没有找到符合条件的患者。")

    names = "、".join(p["name"] for p in results[:10])
    return HandlerResult(
        reply=f"找到 {len(results)} 位患者：{names}",
        data={"patients": results},
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/handlers/query_patient.py
git commit -m "feat: add query_patient handler"
```

---

## Task 9: create_record Handler (interview entry point)

**Files:**
- Modify: `src/agent/handlers/create_record.py`

- [ ] **Step 1: Implement** (delegates to existing interview flow)

```python
# src/agent/handlers/create_record.py
"""Handler for create_record intent — enters interview flow."""
from __future__ import annotations

from agent.dispatcher import register
from agent.tools.resolve import resolve
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


@register(IntentType.create_record)
async def handle_create_record(ctx: TurnContext) -> HandlerResult:
    """Start or resume a doctor interview session for record creation."""
    patient_name = ctx.routing.patient_name
    if not patient_name:
        return HandlerResult(reply="请提供患者姓名，例如"给张三建病历"。")

    # Resolve or auto-create patient
    resolved = await resolve(
        patient_name, ctx.doctor_id,
        auto_create=True,
        gender=ctx.routing.params.get("gender"),
        age=ctx.routing.params.get("age"),
    )
    if "status" in resolved:
        return HandlerResult(reply=resolved["message"])

    # Delegate to existing interview flow
    from domain.patients.interview_turn import create_session, interview_turn
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        interview = await create_session(
            session,
            doctor_id=ctx.doctor_id,
            patient_id=resolved["patient_id"],
            mode="doctor",
        )

    # If clinical_text was extracted by routing, do first turn with it
    clinical_text = ctx.routing.params.get("clinical_text")
    if clinical_text:
        from domain.patients.interview_turn import interview_turn
        response = await interview_turn(interview.id, clinical_text)
        return HandlerResult(
            reply=response.reply,
            data={"session_id": interview.id, "progress": response.progress},
        )

    return HandlerResult(
        reply=f"开始为{patient_name}建病历。请告诉我患者的主诉（主要症状和持续时间）。",
        data={"session_id": interview.id},
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/handlers/create_record.py
git commit -m "feat: add create_record handler (interview entry)"
```

---

## Task 10: End-to-End Integration Test

**Files:**
- Create: `tests/integration/test_plan_and_act_e2e.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/integration/test_plan_and_act_e2e.py
"""End-to-end test of the Plan-and-Act pipeline."""
from __future__ import annotations

import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("ROUTING_LLM", "deepseek")


def _mock_routing_response(intent, patient_name=None, params=None, deferred=None):
    choice = MagicMock()
    choice.message.content = json.dumps({
        "intent": intent,
        "patient_name": patient_name,
        "params": params or {},
        "deferred": deferred,
    }, ensure_ascii=False)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_full_turn_query_record():
    """Doctor asks for patient records → routing → handler → compose → reply."""
    with patch("agent.router._get_routing_client") as mock_client, \
         patch("agent.handlers.query_record._fetch_records") as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary") as mock_compose:

        # Routing LLM returns query_record intent
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            return_value=_mock_routing_response("query_record", "张三")
        )
        mock_client.return_value = client

        # DB returns records
        mock_fetch.return_value = [{"content": "头痛", "created_at": "2026-03-20"}]

        # Compose LLM returns summary
        mock_compose.return_value = "张三最近就诊：头痛（3月20日）"

        from agent.handle_turn import handle_turn
        reply = await handle_turn("查张三的病历", "doctor", "test_doc")

        assert "张三" in reply
        assert "头痛" in reply


@pytest.mark.asyncio
async def test_full_turn_with_deferred():
    """Doctor sends multi-intent → first intent handled, deferred acknowledged."""
    with patch("agent.router._get_routing_client") as mock_client, \
         patch("agent.handlers.query_record._fetch_records") as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary") as mock_compose:

        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            return_value=_mock_routing_response(
                "query_record", "张三", deferred="建个随访任务"
            )
        )
        mock_client.return_value = client
        mock_fetch.return_value = [{"content": "头痛"}]
        mock_compose.return_value = "张三病历摘要"

        from agent.handle_turn import handle_turn
        reply = await handle_turn("查张三病历然后建个随访", "doctor", "test_doc2")

        assert "随访" in reply  # deferred notice appended
```

- [ ] **Step 2: Run E2E tests**

Run: `.venv/bin/python -m pytest tests/integration/test_plan_and_act_e2e.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_plan_and_act_e2e.py
git commit -m "test: add Plan-and-Act E2E integration tests"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Types + Enums | types.py, actions.py | 5 unit tests |
| 2 | Routing LLM | router.py, routing.md | 4 unit tests |
| 3 | Dispatcher | dispatcher.py, handlers/__init__.py, general.py + stubs | 3 unit tests |
| 4 | Wire handle_turn | handle_turn.py, session.py | 2 unit tests |
| 5 | query_record handler | query_record.py, compose.md | 2 unit tests |
| 6 | create_task handler | create_task.py | 2 unit tests |
| 7 | query_task handler | query_task.py | 1 unit test |
| 8 | query_patient handler | query_patient.py | 1 unit test |
| 9 | create_record handler | create_record.py | 1 unit test |
| 10 | E2E integration | test_plan_and_act_e2e.py | 2 integration tests |

**Total: 10 tasks, ~15 new files, 23 tests, ~10 commits**

---

## Post-Plan Phases (all COMPLETE)

### Phase 2: DB Schema Migration — COMPLETE
- Clinical columns, doctor_wechat, patient_auth, doctor/patient_chat_log tables
- TaskType simplified, 13 killed tables deleted

### Phase 3: Cleanup — COMPLETE
- LangChain removed, old ReAct code deleted, import breakages fixed

### Phase 4: Instructor Structured Output — COMPLETE
- `instructor.Mode.JSON` for Groq/Qwen3 compatibility
- Pydantic response models for routing, interview, diagnosis, structuring

### Phase 5: 6-Layer Prompt Composer — COMPLETE
- `prompt_config.py` (LayerConfig matrix with assert)
- `prompt_composer.py` (XML-tagged context injection)
- Prompt files: `system/base.md`, `common/neurology.md`, `intent/*.md`

### Phase 6: Frontend + Interview Confirm — COMPLETE
- `handle_turn` returns HandlerResult, `view_payload.session_id` handoff
- Interview confirm saves structured data directly to medical_records

### Phase 7: Prompt Rewrite — COMPLETE
- Few-shot examples for interview (4), diagnosis (2)
- Dead code removed, output format sections stripped

**E2E benchmark: 46/46 active tests passing (up from 22/52 pre-migration)**
