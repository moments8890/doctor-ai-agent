# ReAct Agent Migration Implementation Plan

> **Status: ✅ DONE** — implementation complete, merged to main.

> **Status: COMPLETE** — All 12 tasks done. Completed 2026-03-19.

**Goal:** Replace the UEC pipeline with a LangChain-powered ReAct agent, eliminating ctx, simplifying resolve, and unifying doctor/patient under one agent.

**Architecture:** LangChain `create_agent` (LangGraph). 6 doctor tools + 1 patient tool. Agent-per-session model with in-memory history. Fast path for greetings/confirmations. DB keys: Name-based for LLM interface, ID-based internally. Resolve translates names to IDs.

**Tech Stack:** LangChain, langchain-openai, langchain-core, LangFuse, existing SQLAlchemy + FastAPI + wechatpy

**Spec:** `docs/specs/archived/2026-03-18-react-mcp-architecture-design.md`

## Completion Summary

| Task | Status | What was built |
|------|--------|---------------|
| 1. LangChain deps | Done | langchain, langchain-openai, langchain-core, langfuse |
| 2. Identity context | Done | `get_current_identity()` / `set_current_identity()` (renamed from doctor-specific) |
| 3. Truncation | Done | `truncate_result()` — 4K char limit |
| 4. Resolve | Done | Name→ID lookup + `auto_create=True` for write tools |
| 5. Read tools | Done | `query_records`, `list_patients`, `list_tasks` |
| 6. Write tools | Done | `create_record`, `update_record`, `create_task` + 5 extended (excluded from default) |
| 7. Agent setup | Done | `langchain.agents.create_agent` + AgentTracer + LangFuse |
| 8. Session + handle_turn | Done | SessionAgent (max 100 turns), history bootstrap from DB, recursion_limit=25 |
| 9. Patient interview tool | Done | `advance_interview` wrapping existing interview engine |
| 10. Wire channels | Done | Web + WeChat → `handle_turn()`, confirm/abandon via `save_pending_record` |
| 11. Cleanup | Done | Entire `services/runtime/` deleted, codebase restructured to `agent/domain/infra` |
| 12. Agent prompt | Done | `agent-doctor.md` with clinical collection, patient history auto-fetch, reply style |

### Beyond original plan

- Codebase restructured: `services/` → `agent/` + `domain/` + `infra/` + `channels/`
- `DoctorContext` table fully removed from DB schema + all code
- `MemoryState` eliminated
- `.dev.sh` with 7 LLM providers (DeepSeek, Groq, SambaNova, Cerebras, SiliconFlow, OpenRouter, Ollama)
- LangFuse cloud observability
- Agent tracing with prompt detection
- LLM provider docs with benchmarks and pricing (`docs/dev/llm-providers.md`)
- Frontend timeout 120s for ReAct agent
- Non-blocking Ollama warmup
- Env var precedence over runtime.json
- Auto-create patient on write tools
- Clear session API (clears agent memory + DB archive)

### Deferred (per spec)

- Unit tests (AGENTS.md: "do not add tests during MVP iteration")
- RAG / `search_knowledge` tool
- Patient-side ReAct tools (beyond `advance_interview`)
- Diagnostic reasoning tools (Phase 2)

---

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `src/services/agent/handle_turn.py` | Entry point: `handle_turn()`, fast path, agent dispatch |
| `src/services/agent/session.py` | `SessionAgent` class, agent-per-session cache, history management |
| `src/services/agent/setup.py` | `get_agent_executor()`, `build_prompt()`, `get_llm()`, LangChain config |
| `src/services/agent/identity.py` | `ContextVar` for doctor_id, `set_current_doctor()`, `get_current_doctor()` |
| `src/services/agent/tools/doctor.py` | 6 doctor tools: query_records, list_patients, list_tasks, create_record, update_record, create_task |
| `src/services/agent/tools/patient.py` | Patient tools: advance_interview |
| `src/services/agent/tools/resolve.py` | Simplified resolve: name-to-ID lookup via `find_patient_by_name` |
| `src/services/agent/tools/truncate.py` | `truncate_result()` for tool output size management |
| `src/services/agent/__init__.py` | Public API: re-export `handle_turn` |
| `src/prompts/agent.md` | Doctor agent system prompt (already drafted) |
| `src/prompts/agent-patient.md` | Patient agent system prompt |
| `tests/test_agent_handle_turn.py` | Integration tests for handle_turn |
| `tests/test_agent_tools.py` | Unit tests for each tool |
| `tests/test_agent_session.py` | Tests for SessionAgent, history management |
| `tests/test_agent_resolve.py` | Tests for simplified resolve |

### Files to modify

| File | Change |
|------|--------|
| `requirements.txt` | Add langchain, langchain-openai, langchain-core |
| `src/channels/web/chat.py` | Replace `process_turn()` calls with `handle_turn()` |
| `src/channels/wechat/router.py` | Replace `process_turn()` calls with `handle_turn()` |

### Files to delete (after migration verified)

| File | Why |
|------|-----|
| `src/services/runtime/understand.py` | LangChain agent handles reasoning |
| `src/services/runtime/compose.py` | Agent LLM composes replies |
| `src/services/runtime/types.py` | LangChain tool definitions replace ActionType |
| `src/services/runtime/models.py` | DoctorCtx/WorkflowState eliminated |
| `src/services/domain/intent_handlers/` | Confirm/abandon handled by fast path in handle_turn |
| `src/prompts/understand.md` | Replaced by agent.md |

### Files to simplify/move

| File | Change |
|------|--------|
| `src/messages.py` | Remove UEC-specific constants, keep agent-used messages |
| `src/services/runtime/dedup.py` | Move to `src/channels/wechat/dedup.py` (WeChat-only concern) |

---

## Task 1: Add LangChain Dependencies

**Files:**
- Modify: `requirements.txt`

- [x] **Step 1: Add LangChain packages to requirements.txt**

Add these lines to `requirements.txt`:
```
langchain>=0.3.0
langchain-openai>=0.3.0
langchain-core>=0.3.0
```

- [x] **Step 2: Install and verify**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/pip install langchain langchain-openai langchain-core`
Expected: Successful install

- [x] **Step 3: Verify import works**

Run: `.venv/bin/python -c "from langchain.agents import create_tool_calling_agent, AgentExecutor; print('OK')"`
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add LangChain dependencies for agent migration"
```

---

## Task 2: Identity Context Variable

**Files:**
- Create: `src/services/agent/__init__.py`
- Create: `src/services/agent/identity.py`
- Test: `tests/test_agent_identity.py`

- [x] **Step 1: Create package init**

```python
# src/services/agent/__init__.py
from __future__ import annotations
```

- [x] **Step 2: Write the failing test**

```python
# tests/test_agent_identity.py
from __future__ import annotations

import asyncio
import pytest
from services.agent.identity import set_current_doctor, get_current_doctor


def test_set_and_get_doctor():
    set_current_doctor("李医生")
    assert get_current_doctor() == "李医生"


def test_async_isolation():
    """Two concurrent tasks get their own ContextVar copies."""
    results = {}

    async def task(name):
        set_current_doctor(name)
        await asyncio.sleep(0.01)  # yield control
        results[name] = get_current_doctor()

    async def main():
        await asyncio.gather(task("李医生"), task("王医生"))

    asyncio.run(main())
    assert results["李医生"] == "李医生"
    assert results["王医生"] == "王医生"
```

- [x] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_identity.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — module not found

- [x] **Step 4: Write implementation**

```python
# src/services/agent/identity.py
from __future__ import annotations

from contextvars import ContextVar

_current_doctor: ContextVar[str] = ContextVar("current_doctor")


def set_current_doctor(name: str) -> None:
    _current_doctor.set(name)


def get_current_doctor() -> str:
    return _current_doctor.get()
```

- [x] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_identity.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add src/services/agent/ tests/test_agent_identity.py
git commit -m "feat: add ContextVar identity injection for agent tools"
```

---

## Task 3: Tool Result Truncation

**Files:**
- Create: `src/services/agent/tools/__init__.py`
- Create: `src/services/agent/tools/truncate.py`
- Test: `tests/test_agent_truncate.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agent_truncate.py
from __future__ import annotations

import json
from services.agent.tools.truncate import truncate_result, MAX_TOOL_RESULT_CHARS


def test_small_result_unchanged():
    result = {"status": "ok", "data": [{"name": "张三"}]}
    assert truncate_result(result) == result


def test_large_result_truncated():
    big_data = [{"name": f"patient_{i}", "records": "x" * 200} for i in range(50)]
    result = {"status": "ok", "data": big_data}
    truncated = truncate_result(result)
    assert len(truncated["data"]) == 5
    assert truncated["truncated"] is True
    assert truncated["total_count"] == 50
    assert len(json.dumps(truncated, ensure_ascii=False)) <= MAX_TOOL_RESULT_CHARS + 500


def test_non_list_data_not_truncated():
    result = {"status": "ok", "data": "a" * 5000}
    truncated = truncate_result(result)
    assert truncated["data"] == "a" * 5000  # string data not truncated by list logic
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_truncate.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write implementation**

```python
# src/services/agent/tools/__init__.py
from __future__ import annotations

# src/services/agent/tools/truncate.py
from __future__ import annotations

import json
from typing import Any, Dict

MAX_TOOL_RESULT_CHARS = 4000  # ~1000 tokens


def truncate_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate large tool results to fit LLM context window."""
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

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_truncate.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/services/agent/tools/ tests/test_agent_truncate.py
git commit -m "feat: add tool result truncation for LLM context management"
```

---

## Task 4: Simplified Resolve

**Files:**
- Create: `src/services/agent/tools/resolve.py`
- Test: `tests/test_agent_resolve.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agent_resolve.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.agent.tools.resolve import resolve


@pytest.mark.asyncio
async def test_resolve_existing_patient():
    mock_patient = MagicMock()
    mock_patient.id = 42
    mock_patient.name = "张三"
    with patch("services.agent.tools.resolve._find_patient", new_callable=AsyncMock, return_value=mock_patient):
        result = await resolve("张三", "doc-123")
    assert result["doctor_id"] == "doc-123"
    assert result["patient_id"] == 42
    assert result["patient_name"] == "张三"
    assert "status" not in result


@pytest.mark.asyncio
async def test_resolve_missing_patient():
    with patch("services.agent.tools.resolve._find_patient", new_callable=AsyncMock, return_value=None):
        result = await resolve("不存在", "doc-123")
    assert result["status"] == "not_found"
    assert "不存在" in result["message"]


@pytest.mark.asyncio
async def test_resolve_none_patient_name():
    result = await resolve(None, "doc-123")
    assert result["status"] == "missing"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_resolve.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write implementation**

```python
# src/services/agent/tools/resolve.py
from __future__ import annotations

from typing import Any, Dict, Optional

from db.models.patient import Patient


async def _find_patient(doctor_id: str, patient_name: str) -> Optional[Patient]:
    """Look up patient by name for a given doctor. Returns Patient or None."""
    from db.crud.patient import find_patient_by_name
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await find_patient_by_name(session, doctor_id, patient_name)


async def resolve(
    patient_name: Optional[str],
    doctor_id: str,
) -> Dict[str, Any]:
    """Resolve patient_name to a validated binding.

    Names are the LLM-facing interface; IDs are used internally for CRUD.
    Returns {"doctor_id", "patient_id", "patient_name"} on success,
    or {"status", "message"} on failure.
    """
    if not patient_name:
        return {"status": "missing", "message": "请指定患者姓名"}

    patient = await _find_patient(doctor_id, patient_name)
    if patient is None:
        return {"status": "not_found", "message": f"未找到患者{patient_name}"}

    return {
        "doctor_id": doctor_id,
        "patient_id": patient.id,
        "patient_name": patient.name,
    }
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_resolve.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/services/agent/tools/resolve.py tests/test_agent_resolve.py
git commit -m "feat: add simplified name-based resolve for agent tools"
```

---

## Task 5: Doctor Tools (Read)

**Files:**
- Create: `src/services/agent/tools/doctor.py`
- Test: `tests/test_agent_tools_read.py`

- [x] **Step 1: Write failing tests for read tools**

```python
# tests/test_agent_tools_read.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.agent.identity import set_current_doctor


@pytest.fixture(autouse=True)
def setup_identity():
    set_current_doctor("doc-123")


@pytest.mark.asyncio
async def test_query_records_found():
    from services.agent.tools.doctor import query_records

    mock_records = [{"id": 1, "content": "胸痛3天", "created_at": "2026-03-01T00:00:00"}]
    with patch("services.agent.tools.doctor.resolve", new_callable=AsyncMock,
               return_value={"doctor_id": "doc-123", "patient_id": 42, "patient_name": "张三"}), \
         patch("services.agent.tools.doctor._fetch_records", new_callable=AsyncMock,
               return_value=mock_records):
        result = await query_records.ainvoke({"patient_name": "张三"})
    assert result["status"] == "ok"
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_query_records_not_found():
    from services.agent.tools.doctor import query_records

    with patch("services.agent.tools.doctor.resolve", new_callable=AsyncMock,
               return_value={"status": "not_found", "message": "未找到患者X"}):
        result = await query_records.ainvoke({"patient_name": "X"})
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_list_patients():
    from services.agent.tools.doctor import list_patients

    mock_patients = [{"name": "张三"}, {"name": "李四"}]
    with patch("services.agent.tools.doctor._fetch_patients", new_callable=AsyncMock,
               return_value=mock_patients):
        result = await list_patients.ainvoke({})
    assert result["status"] == "ok"
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_list_tasks():
    from services.agent.tools.doctor import list_tasks

    mock_tasks = [{"title": "复诊", "patient": "张三"}]
    with patch("services.agent.tools.doctor._fetch_tasks", new_callable=AsyncMock,
               return_value=mock_tasks):
        result = await list_tasks.ainvoke({})
    assert result["status"] == "ok"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_read.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write read tool implementations**

```python
# src/services/agent/tools/doctor.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from services.agent.identity import get_current_doctor
from services.agent.tools.resolve import resolve
from services.agent.tools.truncate import truncate_result


# ── Serialization helpers ────────────────────────────────────────────

def _serialize_record(r: Any) -> Dict[str, Any]:
    """Serialize a MedicalRecordDB to a plain dict (no .to_dict() on models)."""
    tags = []
    if r.tags:
        try:
            tags = json.loads(r.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return {
        "id": r.id,
        "content": r.content or "",
        "tags": tags,
        "record_type": r.record_type,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_patient(p: Any) -> Dict[str, Any]:
    """Serialize a Patient to a plain dict."""
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "year_of_birth": p.year_of_birth,
    }


def _serialize_task(t: Any) -> Dict[str, Any]:
    """Serialize a DoctorTask to a plain dict."""
    return {
        "id": t.id,
        "task_type": t.task_type,
        "title": t.title,
        "content": t.content,
        "status": t.status,
        "patient_id": t.patient_id,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "scheduled_for": t.scheduled_for.isoformat() if t.scheduled_for else None,
    }


# ── Internal helpers (thin wrappers over existing CRUD) ──────────────


async def _fetch_records(
    doctor_id: str, patient_id: int, limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch patient records from DB. Wraps existing CRUD."""
    from db.crud.records import get_records_for_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(
            session, doctor_id, patient_id, limit=limit,
        )
        return [_serialize_record(r) for r in records]


async def _fetch_patients(doctor_id: str) -> List[Dict[str, Any]]:
    from db.crud.patient import get_all_patients
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        patients = await get_all_patients(session, doctor_id)
        return [_serialize_patient(p) for p in patients]


async def _fetch_tasks(
    doctor_id: str, status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from db.crud.tasks import list_tasks as db_list_tasks
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tasks = await db_list_tasks(session, doctor_id, status=status)
        return [_serialize_task(t) for t in tasks]


# ── Read tools ───────────────────────────────────────────────────────


@tool
async def query_records(
    patient_name: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """查询患者的既往病历记录。"""
    doctor_id = get_current_doctor()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    records = await _fetch_records(
        resolved["doctor_id"], resolved["patient_id"], limit,
    )
    return truncate_result({"status": "ok", "data": records})


@tool
async def list_patients() -> Dict[str, Any]:
    """列出医生的患者名单。"""
    doctor_id = get_current_doctor()
    patients = await _fetch_patients(doctor_id)
    return truncate_result({"status": "ok", "data": patients})


@tool
async def list_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """查询任务列表。可按状态筛选（pending/completed）。"""
    doctor_id = get_current_doctor()
    tasks = await _fetch_tasks(doctor_id, status)
    return truncate_result({"status": "ok", "data": tasks})
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_read.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/services/agent/tools/doctor.py tests/test_agent_tools_read.py
git commit -m "feat: add doctor read tools (query_records, list_patients, list_tasks)"
```

---

## Task 6: Doctor Tools (Write)

**Files:**
- Modify: `src/services/agent/tools/doctor.py`
- Test: `tests/test_agent_tools_write.py`

- [x] **Step 1: Write failing tests for write tools**

```python
# tests/test_agent_tools_write.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from services.agent.identity import set_current_doctor


@pytest.fixture(autouse=True)
def setup_identity():
    set_current_doctor("doc-123")


@pytest.mark.asyncio
async def test_create_record_returns_pending():
    from services.agent.tools.doctor import create_record

    with patch("services.agent.tools.doctor.resolve", new_callable=AsyncMock,
               return_value={"doctor_id": "doc-123", "patient_id": 42, "patient_name": "张三"}), \
         patch("services.agent.tools.doctor._create_pending_record", new_callable=AsyncMock,
               return_value={"status": "pending_confirmation", "preview": "主诉：胸痛3天"}):
        result = await create_record.ainvoke({"patient_name": "张三"})
    assert result["status"] == "pending_confirmation"
    assert "preview" in result


@pytest.mark.asyncio
async def test_update_record_returns_pending():
    from services.agent.tools.doctor import update_record

    with patch("services.agent.tools.doctor.resolve", new_callable=AsyncMock,
               return_value={"doctor_id": "doc-123", "patient_id": 42, "patient_name": "张三"}), \
         patch("services.agent.tools.doctor._update_pending_record", new_callable=AsyncMock,
               return_value={"status": "pending_confirmation", "preview": "修改后内容"}):
        result = await update_record.ainvoke({"instruction": "加上过敏史", "patient_name": "张三"})
    assert result["status"] == "pending_confirmation"


@pytest.mark.asyncio
async def test_create_task_commits_immediately():
    from services.agent.tools.doctor import create_task

    with patch("services.agent.tools.doctor.resolve", new_callable=AsyncMock,
               return_value={"doctor_id": "doc-123", "patient_id": 42, "patient_name": "张三"}), \
         patch("services.agent.tools.doctor._commit_task", new_callable=AsyncMock,
               return_value={"status": "ok", "task_id": 1}):
        result = await create_task.ainvoke({
            "patient_name": "张三", "title": "复诊",
        })
    assert result["status"] == "ok"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_write.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Add write tools to doctor.py**

Append to `src/services/agent/tools/doctor.py`:

```python
# ── Internal write helpers ───────────────────────────────────────────


async def _create_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    gender: Optional[str] = None, age: Optional[int] = None,
) -> Dict[str, Any]:
    """Collect clinical text from conversation history, structure, save as pending."""
    from services.ai.structuring import structure_medical_record
    from db.crud.pending import create_pending_record
    from db.engine import AsyncSessionLocal

    # Collect clinical text from recent conversation
    # Import here to avoid circular: doctor.py -> session.py -> setup.py -> doctor.py
    from services.agent import session as _session_mod
    history = _session_mod.get_agent_history(doctor_id)
    clinical_text = "\n".join(
        msg.content for msg in history
        if hasattr(msg, "content") and msg.content
    )

    # Structure via LLM — returns MedicalRecord (Pydantic model), not dict
    medical_record = await structure_medical_record(clinical_text, doctor_id=doctor_id)
    draft_json = medical_record.model_dump_json()

    import uuid
    record_id = str(uuid.uuid4())

    # Save as pending
    async with AsyncSessionLocal() as session:
        pending = await create_pending_record(
            session,
            record_id=record_id,
            doctor_id=doctor_id,
            draft_json=draft_json,
            patient_id=patient_id,
            patient_name=patient_name,
        )
        return {
            "status": "pending_confirmation",
            "preview": medical_record.content,
            "pending_id": str(pending.id),
        }


async def _update_pending_record(
    doctor_id: str, patient_id: int, patient_name: str,
    instruction: str,
) -> Dict[str, Any]:
    """Apply update instruction to latest record, save as pending."""
    from services.ai.structuring import structure_medical_record
    from db.crud.records import get_records_for_patient
    from db.crud.pending import create_pending_record
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=1)
        if not records:
            return {"status": "error", "message": f"{patient_name}没有病历可修改"}
        latest = records[0]
        # Re-structure the original content + instruction via LLM
        combined_text = f"{latest.content}\n\n医生修改指示：{instruction}"
        medical_record = await structure_medical_record(combined_text, doctor_id=doctor_id)
        draft_json = medical_record.model_dump_json()

        import uuid
        record_id = str(uuid.uuid4())

        pending = await create_pending_record(
            session,
            record_id=record_id,
            doctor_id=doctor_id,
            draft_json=draft_json,
            patient_id=patient_id,
            patient_name=patient_name,
        )
        return {
            "status": "pending_confirmation",
            "preview": medical_record.content,
            "pending_id": str(pending.id),
        }


async def _commit_task(
    doctor_id: str, patient_id: int,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    scheduled_for: Optional[str] = None,
    remind_at: Optional[str] = None,
) -> Dict[str, Any]:
    from db.crud.tasks import create_task as db_create_task
    from db.engine import AsyncSessionLocal
    from datetime import datetime

    sched = None
    remind = None
    if scheduled_for:
        sched = datetime.fromisoformat(scheduled_for)
    if remind_at:
        remind = datetime.fromisoformat(remind_at)

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session,
            doctor_id=doctor_id,
            task_type=task_type,
            title=title,
            content=content,
            patient_id=patient_id,
            scheduled_for=sched,
            remind_at=remind,
        )
        return {"status": "ok", "task_id": task.id, "title": title}


# ── Write tools ──────────────────────────────────────────────────────


@tool
async def create_record(
    patient_name: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> Dict[str, Any]:
    """为患者创建病历。收集对话中的临床信息，结构化后生成病历预览。
    医生确认后才会永久保存。"""
    doctor_id = get_current_doctor()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    result = await _create_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], gender, age,
    )
    return truncate_result(result)


@tool
async def update_record(
    instruction: str,
    patient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """按医生指示修改现有病历。返回修改预览，医生确认后才会保存。"""
    doctor_id = get_current_doctor()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    result = await _update_pending_record(
        resolved["doctor_id"], resolved["patient_id"],
        resolved["patient_name"], instruction,
    )
    return truncate_result(result)


@tool
async def create_task(
    patient_name: str,
    title: str,
    task_type: str = "general",
    content: Optional[str] = None,
    scheduled_for: Optional[str] = None,
    remind_at: Optional[str] = None,
) -> Dict[str, Any]:
    """为患者创建任务或预约。scheduled_for 和 remind_at 为 ISO-8601 格式。"""
    doctor_id = get_current_doctor()
    resolved = await resolve(patient_name, doctor_id)
    if "status" in resolved:
        return resolved
    return await _commit_task(
        resolved["doctor_id"], resolved["patient_id"],
        title=title, task_type=task_type, content=content,
        scheduled_for=scheduled_for, remind_at=remind_at,
    )
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_write.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/services/agent/tools/doctor.py tests/test_agent_tools_write.py
git commit -m "feat: add doctor write tools (create_record, update_record, create_task)"
```

---

## Task 7: LangChain Agent Setup

**Files:**
- Create: `src/services/agent/setup.py`
- Test: `tests/test_agent_setup.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agent_setup.py
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock


def test_build_prompt_has_placeholders():
    from services.agent.setup import build_prompt
    prompt = build_prompt("doctor")
    # Should have chat_history and agent_scratchpad placeholders
    input_vars = prompt.input_variables
    assert "input" in input_vars
    partial = [v.variable_name for v in prompt.messages if hasattr(v, "variable_name")]
    assert "chat_history" in partial
    assert "agent_scratchpad" in partial


def test_get_tools_for_role_doctor():
    from services.agent.setup import get_tools_for_role
    tools = get_tools_for_role("doctor")
    tool_names = {t.name for t in tools}
    assert "query_records" in tool_names
    assert "create_record" in tool_names
    assert "create_task" in tool_names
    assert len(tools) == 6


def test_get_tools_for_role_patient():
    from services.agent.setup import get_tools_for_role
    tools = get_tools_for_role("patient")
    # PATIENT_TOOLS is empty until Task 9 adds advance_interview
    assert len(tools) == 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_setup.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write implementation**

```python
# src/services/agent/setup.py
from __future__ import annotations

import os
from datetime import datetime
from typing import List

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from services.agent.tools.doctor import (
    create_record,
    create_task,
    list_patients,
    list_tasks,
    query_records,
    update_record,
)
from utils.prompt_loader import get_prompt_sync


DOCTOR_TOOLS: List[BaseTool] = [
    query_records, list_patients, list_tasks,
    create_record, update_record, create_task,
]

PATIENT_TOOLS: List[BaseTool] = []  # advance_interview added in Task 9


def get_tools_for_role(role: str) -> List[BaseTool]:
    if role == "doctor":
        return DOCTOR_TOOLS
    return PATIENT_TOOLS


def get_llm() -> ChatOpenAI:
    """Create LLM using our provider config."""
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name, _PROVIDERS.get("deepseek"))

    return ChatOpenAI(
        model=provider.get("model", "deepseek-chat"),
        base_url=provider["base_url"],
        api_key=os.environ.get(provider.get("api_key_env", ""), "nokeyneeded"),
        temperature=0.1,
        max_retries=1,
    )


def build_prompt(role: str) -> ChatPromptTemplate:
    """Build the agent prompt template for a given role."""
    prompt_name = "agent" if role == "doctor" else "agent-patient"
    system_text = get_prompt_sync(prompt_name)
    system_text = system_text.replace("{current_date}", datetime.now().strftime("%Y-%m-%d"))
    system_text = system_text.replace("{timezone}", os.environ.get("TZ", "Asia/Shanghai"))

    return ChatPromptTemplate.from_messages([
        ("system", system_text),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])


def get_agent_executor(role: str) -> AgentExecutor:
    """Create a LangChain AgentExecutor for the given role."""
    llm = get_llm()
    tools = get_tools_for_role(role)
    prompt = build_prompt(role)

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=10,
        handle_parsing_errors=True,
    )
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_agent_setup.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/services/agent/setup.py tests/test_agent_setup.py
git commit -m "feat: add LangChain agent setup (executor, prompt, LLM config)"
```

---

## Task 8: SessionAgent + handle_turn

**Files:**
- Create: `src/services/agent/session.py`
- Create: `src/services/agent/handle_turn.py`
- Test: `tests/test_agent_handle_turn.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agent_handle_turn.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.agent.session import SessionAgent, get_or_create_agent

MAX_HISTORY = 100


def test_session_agent_add_turn():
    agent = SessionAgent.__new__(SessionAgent)
    agent.history = []
    agent.identity = "test"
    agent._add_turn("hello", "hi there")
    assert len(agent.history) == 2
    assert agent.history[0].content == "hello"
    assert agent.history[1].content == "hi there"


def test_session_agent_trims_history():
    agent = SessionAgent.__new__(SessionAgent)
    agent.history = []
    agent.identity = "test"
    for i in range(MAX_HISTORY + 10):
        agent._add_turn(f"msg-{i}", f"reply-{i}")
    assert len(agent.history) == MAX_HISTORY * 2


def test_get_or_create_agent_caches():
    from services.agent import session
    session._agents.clear()
    a1 = get_or_create_agent("doctor-A", "doctor")
    a2 = get_or_create_agent("doctor-A", "doctor")
    assert a1 is a2


def test_get_or_create_agent_different_identities():
    from services.agent import session
    session._agents.clear()
    a1 = get_or_create_agent("doctor-A", "doctor")
    a2 = get_or_create_agent("doctor-B", "doctor")
    assert a1 is not a2
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_handle_turn.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write SessionAgent**

```python
# src/services/agent/session.py
from __future__ import annotations

from typing import Dict

from langchain_core.messages import AIMessage, HumanMessage

from services.agent.setup import get_agent_executor

MAX_HISTORY = 100


class SessionAgent:
    """Persistent agent instance per doctor/patient session."""

    def __init__(self, identity: str, role: str) -> None:
        self.identity = identity
        self.role = role
        self.executor = get_agent_executor(role)
        self.history: list = []

    async def handle(self, text: str) -> str:
        result = await self.executor.ainvoke({
            "input": text,
            "chat_history": self.history,
        })
        reply = result["output"]
        self._add_turn(text, reply)
        return reply

    def _add_turn(self, text: str, reply: str) -> None:
        self.history.append(HumanMessage(content=text))
        self.history.append(AIMessage(content=reply))
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]


_agents: Dict[str, SessionAgent] = {}


def get_or_create_agent(identity: str, role: str) -> SessionAgent:
    if identity not in _agents:
        _agents[identity] = SessionAgent(identity, role)
    return _agents[identity]


def get_agent_history(identity: str) -> list:
    """Access agent history for tools that need conversation context."""
    agent = _agents.get(identity)
    return agent.history if agent else []
```

- [x] **Step 4: Write handle_turn**

```python
# src/services/agent/handle_turn.py
from __future__ import annotations

import re
from typing import Optional

from messages import M
from services.agent.identity import set_current_doctor
from services.agent.session import get_or_create_agent
from services.runtime.context import archive_turns
from utils.log import log

# Fast-path patterns
_GREETING_RE = re.compile(
    r"^(你好|您好|hi|hello|hey|嗨|早上好|下午好|晚上好)\s*[。！.!?]*$",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(
    r"^(确认|确定|保存|是的?|对|好的?|ok|yes|save|confirm)\s*[。？！.?!]*$",
    re.IGNORECASE,
)
_ABANDON_RE = re.compile(
    r"^(取消|放弃|不要|不保存|不了|算了|cancel|abandon|discard|no)\s*[。？！.?!]*$",
    re.IGNORECASE,
)


async def _try_fast_path(text: str, identity: str) -> Optional[str]:
    """Check deterministic fast paths. Returns reply or None."""
    if _GREETING_RE.match(text):
        return M.greeting

    # Pending record confirm/abandon
    # get_pending_record(session, record_id, doctor_id) needs a record_id.
    # For the fast path, query the DB for any awaiting pending record for this doctor.
    from db.crud.pending import confirm_pending_record, abandon_pending_record
    from db.engine import AsyncSessionLocal
    from db.models import PendingRecord
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingRecord).where(
                PendingRecord.doctor_id == identity,
                PendingRecord.status == "awaiting",
            ).order_by(PendingRecord.created_at.desc()).limit(1)
        )
        pending = result.scalar_one_or_none()
        if pending:
            if _CONFIRM_RE.match(text):
                await confirm_pending_record(session, pending.id, identity)
                return "已保存"
            if _ABANDON_RE.match(text):
                await abandon_pending_record(session, pending.id, identity)
                return "已取消"

    return None


async def handle_turn(text: str, role: str, identity: str) -> str:
    """One turn. Channels call this directly."""
    agent = get_or_create_agent(identity, role)
    set_current_doctor(identity)

    # Fast path (0 LLM)
    fast = await _try_fast_path(text, identity)
    if fast:
        agent._add_turn(text, fast)
        try:
            await archive_turns(identity, text, fast)
        except Exception as exc:
            log(f"[handle_turn] archive failed: {exc}", level="error")
        return fast

    # LangChain agent (1-4 LLM)
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

- [x] **Step 5: Update package init**

```python
# src/services/agent/__init__.py
from __future__ import annotations

from services.agent.handle_turn import handle_turn

__all__ = ["handle_turn"]
```

- [x] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_agent_handle_turn.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add src/services/agent/ tests/test_agent_handle_turn.py
git commit -m "feat: add SessionAgent and handle_turn entry point"
```

---

## Task 9: Patient Interview Tool

**Files:**
- Create: `src/services/agent/tools/patient.py`
- Modify: `src/services/agent/setup.py` (add to PATIENT_TOOLS)
- Test: `tests/test_agent_tools_patient.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_patient.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.agent.identity import set_current_doctor


@pytest.fixture(autouse=True)
def setup_identity():
    set_current_doctor("patient-张三")


@pytest.mark.asyncio
async def test_advance_interview():
    from services.agent.tools.patient import advance_interview

    # InterviewResponse fields: reply, collected, progress, status
    mock_result = MagicMock()
    mock_result.reply = "疼痛的位置在哪里？"
    mock_result.collected = {"chief_complaint": "头疼三天"}
    mock_result.progress = {"filled": 1, "total": 7}
    mock_result.status = "interviewing"

    with patch("services.agent.tools.patient._process_interview", new_callable=AsyncMock,
               return_value=mock_result):
        result = await advance_interview.ainvoke({"answer": "我头疼三天了"})
    assert result["status"] == "interviewing"
    assert result["reply"] == "疼痛的位置在哪里？"
    assert result["progress"]["filled"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_patient.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL

- [x] **Step 3: Write implementation**

```python
# src/services/agent/tools/patient.py
from __future__ import annotations

from typing import Any, Dict

from langchain_core.tools import tool

from services.agent.identity import get_current_doctor


async def _process_interview(session_id: str, answer: str) -> Any:
    """Delegate to existing interview engine.

    The actual function is ``interview_turn`` (not process_interview_turn).
    Signature: interview_turn(session_id: str, patient_text: str) -> InterviewResponse
    InterviewResponse fields: reply, collected, progress, status
    """
    from services.patient_interview.turn import interview_turn
    return await interview_turn(session_id, answer)


@tool
async def advance_interview(answer: str) -> Dict[str, Any]:
    """推进患者预问诊流程。提取临床信息，推进状态机，返回下一个问题。
    当患者提供症状、病史等临床信息时调用此工具。"""
    session_id = get_current_doctor()  # for patient role, identity = session_id
    result = await _process_interview(session_id, answer)
    # InterviewResponse fields: reply, collected, progress, status
    return {
        "reply": result.reply,
        "collected": result.collected,
        "progress": result.progress,
        "status": result.status,
    }
```

- [x] **Step 4: Add to PATIENT_TOOLS in setup.py**

In `src/services/agent/setup.py`, update:
```python
from services.agent.tools.patient import advance_interview

PATIENT_TOOLS: List[BaseTool] = [advance_interview]
```

- [x] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_agent_tools_patient.py tests/test_agent_setup.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add src/services/agent/tools/patient.py src/services/agent/setup.py tests/test_agent_tools_patient.py
git commit -m "feat: add patient interview tool (advance_interview)"
```

---

## Task 10: Wire Channels to handle_turn

**Files:**
- Modify: `src/channels/web/chat.py`
- Modify: `src/channels/wechat/router.py`

- [x] **Step 1: Read current Web channel**

Read `src/channels/web/chat.py` to find all `process_turn()` call sites.

- [x] **Step 2: Update Web channel**

Replace `process_turn()` calls with `handle_turn()`. The Web channel
should extract `doctor_id` from the authenticated session and call:

```python
from services.agent import handle_turn

reply = await handle_turn(text, "doctor", doctor_id)
```

Keep the existing HTTP endpoint structure. Only change the internal
dispatch.

- [x] **Step 3: Read current WeChat channel**

Read `src/channels/wechat/router.py` to find all `process_turn()` call sites.

- [x] **Step 4: Update WeChat channel**

Replace `process_turn()` calls with `handle_turn()`. Keep WeChat-specific
dedup logic (check `msg_id` before calling handle_turn).

```python
from services.agent import handle_turn

if dedup.is_duplicate(msg.msg_id):
    return
reply = await handle_turn(text, "doctor", doctor_id)
```

- [x] **Step 5: Test end-to-end manually**

Start the dev server and test via the web UI:
```bash
./dev.sh
```

Test these scenarios:
1. Greeting: "你好" → fast path reply
2. Query: "查一下张三的病历" → agent calls query_records
3. Clinical: "张三，胸痛3天" → agent acknowledges, continues collection
4. Create record: "写病历" → agent calls create_record → preview
5. Confirm: "确认" → fast path commits

- [x] **Step 6: Commit**

```bash
git add src/channels/web/chat.py src/channels/wechat/router.py
git commit -m "feat: wire Web and WeChat channels to handle_turn"
```

---

## Task 11: Cleanup Old Pipeline

**Files:**
- Delete: `src/services/runtime/understand.py`
- Delete: `src/services/runtime/compose.py`
- Delete: `src/services/runtime/types.py`
- Delete: `src/services/runtime/models.py`
- Delete: `src/services/domain/intent_handlers/` (entire directory)
- Delete: `src/prompts/understand.md`
- Simplify: `src/services/runtime/context.py` (keep only archive functions)
- Simplify: `src/messages.py` (remove UEC-specific message constants)
- Move: `src/services/runtime/dedup.py` to `src/channels/wechat/dedup.py` (WeChat-only concern)

- [x] **Step 1: Verify no imports of deleted modules**

Search for imports of the modules being deleted. Fix any remaining
references before deleting.

```bash
grep -r "from services.runtime.understand" src/
grep -r "from services.runtime.compose" src/
grep -r "from services.runtime.types" src/
grep -r "from services.runtime.models import.*DoctorCtx\|WorkflowState\|MemoryState" src/
grep -r "from services.domain.intent_handlers" src/
grep -r "from services.runtime.dedup" src/
```

- [x] **Step 2: Delete old files**

```bash
rm src/services/runtime/understand.py
rm src/services/runtime/compose.py
rm src/services/runtime/types.py
rm src/services/runtime/models.py
rm src/prompts/understand.md
rm -rf src/services/domain/intent_handlers/
```

- [x] **Step 3: Simplify context.py**

Keep only `archive_turns` and `get_recent_turns`. Remove `load_context`,
`save_context`, and any DoctorCtx-related code.

- [x] **Step 4: Simplify messages.py**

Review `src/messages.py` and remove UEC-specific message constants
that are no longer referenced. Keep only messages used by the agent
pipeline (e.g., `M.greeting`, `M.service_unavailable`).

- [x] **Step 5: Move dedup.py to WeChat channel**

`src/services/runtime/dedup.py` is only used by the WeChat channel.
Move it to `src/channels/wechat/dedup.py` and update the import in
`src/channels/wechat/router.py`.

- [x] **Step 6: Update runtime __init__.py**

Remove exports of deleted modules. Add re-export of `handle_turn` if
needed for backward compatibility.

- [x] **Step 7: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All agent tests pass. Old UEC tests will fail (expected — delete them in next step).

- [x] **Step 8: Delete old UEC tests**

Remove test files that test deleted modules (understand, compose, types).

- [x] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: remove UEC pipeline (understand, compose, types, models, ctx, intent_handlers)"
```

---

## Task 12: Agent Prompt (doctor)

**Files:**
- Verify: `src/prompts/agent.md` (already created during design)

- [x] **Step 1: Verify prompt loads correctly**

```python
from utils.prompt_loader import get_prompt_sync
prompt = get_prompt_sync("agent")
assert "患者历史" in prompt
assert "病历收集规则" in prompt
assert "{current_date}" in prompt
```

- [x] **Step 2: Create patient prompt**

```python
# src/prompts/agent-patient.md
# (placeholder for patient agent — full content when patient pipeline is built)
```

- [x] **Step 3: End-to-end test with real LLM**

If LLM is available, test the full flow:
```bash
./dev.sh
# In web UI: send "张三来复诊了" → verify agent fetches history then responds
```

- [x] **Step 4: Commit**

```bash
git add src/prompts/
git commit -m "feat: finalize agent prompts for doctor and patient roles"
```
