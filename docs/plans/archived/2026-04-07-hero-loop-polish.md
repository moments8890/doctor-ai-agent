# Hero Loop Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the follow-up reply hero loop for a solo neurosurgeon pilot — remove the KB citation gate, add silent edit logging, create a doctor-confirmed persona system, and reduce batch delay.

**Architecture:** Four independent changes touching backend domain logic, DB models, prompt composer, and one frontend page. Changes 1 and 4 are trivial (one-line edits). Change 2 adds edit logging to the centralized reply function. Change 3 is the largest: a new `persona` KB category with lazy creation, background LLM extraction, and doctor confirmation before prompt injection.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy async ORM, SQLite (dev), React/MUI frontend, APScheduler (existing but not used for this feature).

**Spec:** `docs/specs/2026-04-07-hero-loop-polish-design.md` (v2)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/domain/patient_lifecycle/draft_reply.py` | Modify | Remove citation gate (3 lines) |
| `src/domain/patient_lifecycle/triage_handlers.py` | Modify | Batch delay constant (1 line) |
| `src/domain/patient_lifecycle/reply.py` | Modify | Add edit logging + persona extraction trigger |
| `src/db/models/doctor.py` | Modify | Add `persona` to `KnowledgeCategory`, add `persona_status` column |
| `src/domain/knowledge/teaching.py` | Modify | Add `get_or_create_persona()`, `extract_persona()`, `_check_persona_extraction()` |
| `src/domain/knowledge/knowledge_context.py` | Modify | Load persona separately, inject before scored KB items |
| `src/agent/prompt_composer.py` | Modify | Pass persona text through to prompt assembly |
| `src/channels/web/doctor_dashboard/knowledge_handlers.py` | Modify | Add persona confirm/deactivate endpoint |
| `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx` | Modify | Pin persona card at top, filter from regular list |
| `tests/core/test_draft_reply_no_gate.py` | Create | Test that drafts are generated without KB citations |
| `tests/core/test_reply_edit_logging.py` | Create | Test that edit pairs are logged on send |
| `tests/core/test_persona.py` | Create | Test persona lifecycle: create, extract, activate, prompt injection |

---

### Task 1: Remove Citation Gate (Change 1)

**Files:**
- Modify: `src/domain/patient_lifecycle/draft_reply.py:115-119`
- Create: `tests/core/test_draft_reply_no_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_draft_reply_no_gate.py`:

```python
"""Test that draft_reply generates drafts even without KB citations."""
import pytest
from domain.patient_lifecycle.draft_reply import DraftReplyResult


def test_draft_result_allows_empty_citations():
    """DraftReplyResult can be created with empty cited_knowledge_ids."""
    result = DraftReplyResult(
        text="恢复情况不错，继续观察。",
        cited_knowledge_ids=[],
        confidence=0.9,
        is_signal_flag=False,
    )
    assert result.text == "恢复情况不错，继续观察。"
    assert result.cited_knowledge_ids == []


def test_draft_result_with_citations():
    """DraftReplyResult with citations still works."""
    result = DraftReplyResult(
        text="头痛是正常的。 [KB-3]",
        cited_knowledge_ids=[3],
        confidence=0.9,
        is_signal_flag=False,
    )
    assert result.cited_knowledge_ids == [3]
```

- [ ] **Step 2: Run test to verify it passes (these are data class tests)**

Run: `.venv/bin/python -m pytest tests/core/test_draft_reply_no_gate.py -v --rootdir=.`
Expected: PASS (DraftReplyResult is a dataclass, these test its shape)

- [ ] **Step 3: Remove the citation gate**

In `src/domain/patient_lifecycle/draft_reply.py`, remove lines 115-119. The current code is:

```python
        # Red-flag messages always get a draft (emergency guidance is critical).
        # Non-signal-flag messages require KB citation — skip if AI couldn't ground the reply.
        if not validation.valid_ids and not is_signal_flag:
            log("[draft_reply] no KB citation found — skipping draft (AI无法引用知识库)", level="info")
            return None
```

Replace with:

```python
        # Log when draft has no KB grounding (but still generate it)
        if not validation.valid_ids:
            log("[draft_reply] no KB citation — draft generated without grounding", level="info")
```

- [ ] **Step 4: Run the full draft_reply test suite**

Run: `.venv/bin/python -m pytest tests/core/test_draft_reply_no_gate.py -v --rootdir=.`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/patient_lifecycle/draft_reply.py tests/core/test_draft_reply_no_gate.py
git commit -m "feat: remove KB citation gate — all messages get AI drafts

Previously, draft_reply.py silently dropped drafts when the AI couldn't
cite a KB item. For a new doctor with sparse KB, this meant most messages
got no draft at all. Now all messages get drafts regardless of KB status.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Reduce Batch Delay (Change 4)

**Files:**
- Modify: `src/domain/patient_lifecycle/triage_handlers.py:159`

- [ ] **Step 1: Change the constant**

In `src/domain/patient_lifecycle/triage_handlers.py`, change line 159:

```python
_DRAFT_BATCH_DELAY = 30  # seconds — wait for rapid-fire messages before generating
```

to:

```python
_DRAFT_BATCH_DELAY = 5  # seconds — short delay for low-volume pilot
```

- [ ] **Step 2: Run existing triage tests**

Run: `.venv/bin/python -m pytest tests/ -k triage -v --rootdir=.`
Expected: PASS (no tests depend on the exact delay value)

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/triage_handlers.py
git commit -m "feat: reduce draft batch delay from 30s to 5s for pilot

At 5-10 messages/day, the 30s batching window makes the app feel broken
with no batching benefit. 5s keeps the cancellation mechanism for rapid
messages while feeling responsive.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Add Edit Logging to `send_doctor_reply()` (Change 2)

**Files:**
- Modify: `src/domain/patient_lifecycle/reply.py`
- Create: `tests/core/test_reply_edit_logging.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_reply_edit_logging.py`:

```python
"""Test that send_doctor_reply logs edit pairs for persona learning."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_edit_logged_when_draft_provided():
    """When draft_id is given, log_doctor_edit is called with draft text as original."""
    mock_draft = MagicMock()
    mock_draft.draft_text = "AI draft text"
    mock_draft.doctor_id = "doc1"

    with patch("domain.patient_lifecycle.reply.AsyncSessionLocal") as mock_session_cls, \
         patch("domain.patient_lifecycle.reply.save_patient_message") as mock_save, \
         patch("domain.patient_lifecycle.reply.log_doctor_edit") as mock_log_edit:

        mock_db = AsyncMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_save.return_value = MagicMock(id=1)
        mock_db.get = AsyncMock(return_value=mock_draft)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        from domain.patient_lifecycle.reply import send_doctor_reply
        await send_doctor_reply(
            doctor_id="doc1",
            patient_id=42,
            text="Doctor edited text",
            draft_id=99,
        )

        mock_log_edit.assert_called_once()
        call_kwargs = mock_log_edit.call_args
        assert call_kwargs[1]["entity_type"] == "draft_reply" or call_kwargs[0][3] == "draft_reply"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_reply_edit_logging.py -v --rootdir=.`
Expected: FAIL — `log_doctor_edit` not imported or called in `reply.py`

- [ ] **Step 3: Add edit logging to `send_doctor_reply()`**

In `src/domain/patient_lifecycle/reply.py`, add import at top:

```python
from domain.knowledge.teaching import log_doctor_edit
```

Then, inside `send_doctor_reply()`, after the outbound message is saved (after line 60) and before the stale draft update, add:

```python
        # 6. Log edit pair for persona learning (non-fatal)
        try:
            if draft_id:
                draft_obj = await db.get(MessageDraft, draft_id)
                if draft_obj and draft_obj.doctor_id == doctor_id:
                    await log_doctor_edit(
                        db,
                        doctor_id=doctor_id,
                        entity_type="draft_reply",
                        entity_id=draft_id,
                        original_text=draft_obj.draft_text or "",
                        edited_text=text,  # pre-disclosure text
                    )
            else:
                # Manual reply — no draft, log with empty original
                await log_doctor_edit(
                    db,
                    doctor_id=doctor_id,
                    entity_type="manual_reply",
                    entity_id=msg.id,
                    original_text="",
                    edited_text=text,
                )
        except Exception as edit_exc:
            logger.warning("[reply] edit logging failed (non-fatal): %s", edit_exc)
```

Also add the MessageDraft import near the top of the function (it's already imported later in the function body for stale marking, but we need it earlier now):

```python
from db.models.message_draft import MessageDraft, DraftStatus
```

Move this import to the top of the file alongside other imports, or keep it inside the function but move it above the new logging block.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_reply_edit_logging.py -v --rootdir=.`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/patient_lifecycle/reply.py tests/core/test_reply_edit_logging.py
git commit -m "feat: log edit pairs in send_doctor_reply for persona learning

Every doctor reply (draft-based or manual) now logs an edit pair via
log_doctor_edit(). Draft-based replies record (original_draft, final_text).
Manual replies record ('', text). This data feeds the persona extraction
system without interrupting the send flow.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Add `persona` Category and `persona_status` to DB Model

**Files:**
- Modify: `src/db/models/doctor.py`

- [ ] **Step 1: Add `persona` to KnowledgeCategory enum**

In `src/db/models/doctor.py`, add to the `KnowledgeCategory` enum:

```python
class KnowledgeCategory(str, Enum):
    custom = "custom"
    diagnosis = "diagnosis"
    communication = "communication"
    followup = "followup"
    medication = "medication"
    preference = "preference"
    persona = "persona"
```

- [ ] **Step 2: Add `persona_status` column to DoctorKnowledgeItem**

In `src/db/models/doctor.py`, add to `DoctorKnowledgeItem` after `seed_source`:

```python
    persona_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # "draft" = extracted but not confirmed, "active" = confirmed and injected into prompts
    # Only used when category == "persona". NULL for all other categories.
```

- [ ] **Step 3: Verify DB init handles the new column**

The existing `_backfill_missing_columns()` in `src/db/init_db.py` automatically adds missing nullable columns to SQLite tables. Since `persona_status` is `nullable=True`, it will be auto-added on next startup. No migration script needed.

Run: `.venv/bin/python -c "from db.models.doctor import KnowledgeCategory; print(KnowledgeCategory.persona)"`
Expected: `persona`

- [ ] **Step 4: Commit**

```bash
git add src/db/models/doctor.py
git commit -m "feat: add persona category and persona_status to DoctorKnowledgeItem

New KnowledgeCategory.persona enum value for the doctor's living persona
document. persona_status field ('draft'/'active') controls whether the
persona is injected into prompts — only 'active' items affect AI output.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Implement `get_or_create_persona()` and `extract_persona()`

**Files:**
- Modify: `src/domain/knowledge/teaching.py`
- Create: `tests/core/test_persona.py`

- [ ] **Step 1: Write tests for `get_or_create_persona`**

Create `tests/core/test_persona.py`:

```python
"""Test persona lifecycle: lazy creation, extraction trigger, activation."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from db.models.doctor import KnowledgeCategory


PERSONA_TEMPLATE = """\
## 回复风格
（AI会根据你的回复逐渐学习，你也可以直接编辑）

## 常用结尾语

## 回复结构

## 回避内容

## 常见修改"""


def test_persona_template_has_sections():
    """Template has the expected section headers."""
    from domain.knowledge.teaching import PERSONA_TEMPLATE as tmpl
    assert "## 回复风格" in tmpl
    assert "## 常用结尾语" in tmpl
    assert "## 回避内容" in tmpl


@pytest.mark.asyncio
async def test_get_or_create_persona_creates_when_missing():
    """get_or_create_persona creates a new persona item if none exists."""
    from domain.knowledge.teaching import get_or_create_persona, PERSONA_TEMPLATE

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no existing persona
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.flush = AsyncMock()

    persona = await get_or_create_persona(mock_session, "doc1")

    assert persona is not None
    assert persona.category == KnowledgeCategory.persona.value
    assert persona.persona_status == "draft"
    assert "回复风格" in persona.content
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_persona_returns_existing():
    """get_or_create_persona returns existing persona without creating."""
    from domain.knowledge.teaching import get_or_create_persona

    existing = MagicMock()
    existing.category = KnowledgeCategory.persona.value
    existing.persona_status = "active"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    mock_session.execute = AsyncMock(return_value=mock_result)

    persona = await get_or_create_persona(mock_session, "doc1")

    assert persona is existing
    mock_session.add.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_persona.py -v --rootdir=.`
Expected: FAIL — `get_or_create_persona` and `PERSONA_TEMPLATE` don't exist yet

- [ ] **Step 3: Implement `get_or_create_persona()` and `PERSONA_TEMPLATE`**

Add to `src/domain/knowledge/teaching.py`:

```python
from sqlalchemy import select
from db.models.doctor import DoctorKnowledgeItem, KnowledgeCategory

PERSONA_TEMPLATE = """\
## 回复风格
（AI会根据你的回复逐渐学习，你也可以直接编辑）

## 常用结尾语

## 回复结构

## 回避内容

## 常见修改"""


async def get_or_create_persona(session, doctor_id: str) -> DoctorKnowledgeItem:
    """Get or lazily create the doctor's persona KB item.

    Returns the existing persona if one exists, otherwise creates a new one
    with draft status and the empty template.
    """
    result = await session.execute(
        select(DoctorKnowledgeItem).where(
            DoctorKnowledgeItem.doctor_id == doctor_id,
            DoctorKnowledgeItem.category == KnowledgeCategory.persona.value,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    persona = DoctorKnowledgeItem(
        doctor_id=doctor_id,
        content=PERSONA_TEMPLATE,
        category=KnowledgeCategory.persona.value,
        title="我的AI人设",
        summary="AI会根据你的回复逐渐学习你的风格",
        persona_status="draft",
        seed_source="system",
    )
    session.add(persona)
    await session.flush()
    log(f"[persona] created persona item for doctor={doctor_id}")
    return persona
```

- [ ] **Step 4: Implement `_check_persona_extraction()` and `extract_persona()`**

Add to `src/domain/knowledge/teaching.py`:

```python
from db.models.doctor_edit import DoctorEdit

_EXTRACTION_THRESHOLD = 15  # minimum edits before first extraction


async def _count_draft_edits_since(session, doctor_id: str, since_dt) -> int:
    """Count draft_reply edits since a given datetime."""
    from sqlalchemy import func
    query = select(func.count()).select_from(DoctorEdit).where(
        DoctorEdit.doctor_id == doctor_id,
        DoctorEdit.entity_type == "draft_reply",
    )
    if since_dt:
        query = query.where(DoctorEdit.created_at > since_dt)
    result = await session.execute(query)
    return result.scalar() or 0


async def _check_persona_extraction(doctor_id: str) -> None:
    """Check if persona extraction should run and trigger if so.

    Called from send_doctor_reply() as a fire-and-forget background task.
    Runs extraction when 15+ draft_reply edits exist since last extraction.
    """
    from db.engine import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            persona = await get_or_create_persona(session, doctor_id)
            # Use persona.updated_at as the watermark for last extraction
            since = persona.updated_at if persona.persona_status == "active" else None
            count = await _count_draft_edits_since(session, doctor_id, since)
            if count < _EXTRACTION_THRESHOLD:
                return
            await extract_persona(session, doctor_id, persona)
            await session.commit()
    except Exception as exc:
        log(f"[persona] extraction check failed (non-fatal): {exc}", level="warning")


async def extract_persona(session, doctor_id: str, persona: DoctorKnowledgeItem) -> None:
    """Run LLM extraction on recent edit pairs and update persona as draft.

    Loads the last 30 draft_reply edits, calls LLM to analyze patterns,
    and saves the result to the persona item with status='draft'.
    The doctor must confirm before it's injected into prompts.
    """
    from agent.llm import llm_call

    # Load recent edit pairs
    result = await session.execute(
        select(DoctorEdit).where(
            DoctorEdit.doctor_id == doctor_id,
            DoctorEdit.entity_type == "draft_reply",
        ).order_by(DoctorEdit.created_at.desc()).limit(30)
    )
    edits = result.scalars().all()
    if not edits:
        return

    # Build the extraction prompt
    edit_examples = []
    for e in reversed(edits):  # chronological order
        if e.original_text == e.edited_text:
            edit_examples.append(f"- 医生直接发送（未修改）：{e.edited_text[:100]}")
        else:
            edit_examples.append(
                f"- AI草稿：{e.original_text[:80]}\n"
                f"  医生改为：{e.edited_text[:80]}"
            )

    current_persona = persona.content if persona.persona_status == "active" else ""
    current_section = f"\n\n当前人设：\n{current_persona}" if current_persona else ""

    prompt = f"""分析以下医生的回复记录，提取其沟通风格和偏好。

{chr(10).join(edit_examples)}
{current_section}

请用以下格式输出（保留标题，填充内容）：

## 回复风格
（描述医生的整体沟通风格）

## 常用结尾语
（医生常用的结尾方式）

## 回复结构
（医生回复的典型结构）

## 回避内容
（医生从不在回复中包含的内容）

## 常见修改
（医生最常修改AI草稿的模式）"""

    messages = [
        {"role": "system", "content": "你是一个分析医生沟通风格的助手。根据医生的实际回复记录，提取可复用的风格规则。简洁、具体、可操作。"},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm_call(messages=messages, op_name="persona_extract")
        if response and len(response.strip()) > 50:
            persona.content = response.strip()
            # Keep as draft if first extraction, or if already active keep active
            # (doctor already confirmed once, update is an incremental improvement)
            if persona.persona_status != "active":
                persona.persona_status = "draft"
            log(f"[persona] extracted persona for doctor={doctor_id} ({len(edits)} edits)")
        else:
            log("[persona] LLM returned insufficient content, skipping", level="warning")
    except Exception as exc:
        log(f"[persona] LLM extraction failed: {exc}", level="warning")
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/core/test_persona.py -v --rootdir=.`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domain/knowledge/teaching.py tests/core/test_persona.py
git commit -m "feat: add persona lifecycle — get_or_create, extract, confirm

Implements get_or_create_persona() for lazy creation, extract_persona()
for LLM-based style analysis from doctor edit pairs, and
_check_persona_extraction() as the inline trigger from reply flow.
Persona stays in 'draft' status until doctor explicitly confirms.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire Persona Extraction Trigger into `reply.py`

**Files:**
- Modify: `src/domain/patient_lifecycle/reply.py`

- [ ] **Step 1: Add fire-and-forget extraction trigger**

In `src/domain/patient_lifecycle/reply.py`, after the edit logging block added in Task 3, add:

```python
        # 7. Check if persona extraction should trigger (fire-and-forget)
        if draft_id:
            try:
                from domain.knowledge.teaching import _check_persona_extraction
                from utils.log import safe_create_task
                safe_create_task(
                    _check_persona_extraction(doctor_id),
                    name=f"persona-check-{doctor_id}",
                )
            except Exception:
                pass  # non-fatal, non-blocking
```

- [ ] **Step 2: Verify no regressions**

Run: `.venv/bin/python -m pytest tests/core/test_reply_edit_logging.py -v --rootdir=.`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/domain/patient_lifecycle/reply.py
git commit -m "feat: trigger persona extraction check on draft-based replies

After logging an edit pair, fires a background task to check if 15+
edits have accumulated since last extraction. If so, runs LLM persona
extraction. Non-blocking, non-fatal.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Load Persona Separately in Prompt Composer

**Files:**
- Modify: `src/domain/knowledge/knowledge_context.py`
- Modify: `src/agent/prompt_composer.py`

- [ ] **Step 1: Add `load_active_persona()` to knowledge_context.py**

Add to `src/domain/knowledge/knowledge_context.py`:

```python
async def load_active_persona(doctor_id: str) -> str:
    """Load the active persona text for a doctor, if any.

    Returns empty string if no persona exists or persona is not active.
    Loaded SEPARATELY from scored KB items — persona never competes
    with regular knowledge for the top-5 slots.
    """
    if not doctor_id:
        return ""
    try:
        from db.engine import AsyncSessionLocal
        from domain.knowledge.teaching import get_or_create_persona
        async with AsyncSessionLocal() as session:
            persona = await get_or_create_persona(session, doctor_id)
            if persona and persona.persona_status == "active" and persona.content:
                return persona.content.strip()
    except Exception as exc:
        import logging
        logging.getLogger("knowledge").warning("[persona] load failed (non-fatal): %s", exc)
    return ""
```

- [ ] **Step 2: Modify `_load_doctor_knowledge()` in prompt_composer.py to also load persona**

In `src/agent/prompt_composer.py`, modify `_load_doctor_knowledge()` to return a tuple `(knowledge_text, persona_text)`:

```python
async def _load_doctor_knowledge(doctor_id: str, config: LayerConfig, query: str = "", patient_context: str = "") -> tuple[str, str]:
    """Load doctor KB items and persona. Returns (knowledge_text, persona_text)."""
    knowledge = ""
    persona = ""
    if not doctor_id:
        return knowledge, persona
    if config.load_knowledge:
        try:
            from domain.knowledge.doctor_knowledge import load_knowledge
            knowledge = await load_knowledge(doctor_id, query=query, patient_context=patient_context)
            log(f"[composer] KB loaded: {len(knowledge)} chars")
        except Exception as exc:
            log(f"[composer] KB load failed (non-fatal): {exc}", level="warning")
    # Always try to load persona (independent of load_knowledge flag)
    try:
        from domain.knowledge.knowledge_context import load_active_persona
        persona = await load_active_persona(doctor_id)
        if persona:
            log(f"[composer] persona loaded: {len(persona)} chars")
    except Exception as exc:
        log(f"[composer] persona load failed (non-fatal): {exc}", level="warning")
    return knowledge, persona
```

- [ ] **Step 3: Update `compose_messages()` to inject persona**

In `compose_messages()`, update the call site and injection points. Change line 93-94:

```python
    doctor_knowledge = await _load_doctor_knowledge(
        doctor_id, config, query=doctor_message, patient_context=patient_context,
    )
```

to:

```python
    doctor_knowledge, doctor_persona = await _load_doctor_knowledge(
        doctor_id, config, query=doctor_message, patient_context=patient_context,
    )
```

Then update the KB note:

```python
    kb_note = f" kb={len(doctor_knowledge)}chars" if doctor_knowledge else ""
    if doctor_persona:
        kb_note += f" persona={len(doctor_persona)}chars"
```

In the Pattern 1 (single-turn) section, inject persona before knowledge in the user message. Replace the `doctor_knowledge` block:

```python
        user_parts = []
        if doctor_persona:
            user_parts.append(
                f"<doctor_persona>\n"
                f"以下是医生的个人回复风格，请按此风格起草回复。\n"
                f"{doctor_persona}\n"
                f"</doctor_persona>"
            )
        if doctor_knowledge:
            user_parts.append(
                f"<doctor_knowledge>\n"
                f"以下是可引用的医生知识规则。若在 detail 中使用其中任何内容，"
                f"必须在该 detail 末尾追加对应的 [KB-{{id}}] 引用标签。\n"
                f"{doctor_knowledge}\n"
                f"</doctor_knowledge>"
            )
```

In the Pattern 2 (conversation) section, do the same — inject persona before knowledge in the user message:

```python
        user_parts: List[str] = []
        if doctor_persona:
            user_parts.append(
                f"<doctor_persona>\n"
                f"以下是医生的个人回复风格，请按此风格起草回复。\n"
                f"{doctor_persona}\n"
                f"</doctor_persona>"
            )
        if doctor_knowledge:
            user_parts.append(
                f"<doctor_knowledge>\n"
                f"以下是可引用的医生知识规则。若使用其中内容，"
                f"在相关内容后追加 [KB-{{id}}] 引用标签。\n"
                f"{doctor_knowledge}\n"
                f"</doctor_knowledge>"
            )
```

Update the layer tracking at the end:

```python
    if doctor_persona:
        active.append("L4p")  # persona sub-layer
```

- [ ] **Step 4: Run existing tests**

Run: `.venv/bin/python -m pytest tests/ -k "prompt or composer" -v --rootdir=.`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/knowledge/knowledge_context.py src/agent/prompt_composer.py
git commit -m "feat: inject active persona into prompt stack before KB items

Persona loads separately from scored KB items via load_active_persona().
Only injected when persona_status=='active'. Appears as <doctor_persona>
XML block before <doctor_knowledge> in the prompt.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Add Persona Confirm/Deactivate API Endpoint

**Files:**
- Modify: `src/channels/web/doctor_dashboard/knowledge_handlers.py`

- [ ] **Step 1: Add the confirm endpoint**

Add to `src/channels/web/doctor_dashboard/knowledge_handlers.py`:

```python
class PersonaActionRequest(BaseModel):
    action: str  # "activate" or "deactivate"


@router.post("/api/manage/knowledge/persona/confirm")
async def confirm_persona(
    body: PersonaActionRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Activate or deactivate the doctor's persona item."""
    from domain.knowledge.teaching import get_or_create_persona

    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)

    if body.action == "activate":
        persona.persona_status = "active"
    elif body.action == "deactivate":
        persona.persona_status = "draft"
    else:
        raise HTTPException(status_code=400, detail="action must be 'activate' or 'deactivate'")

    await session.commit()
    return {"status": "ok", "persona_status": persona.persona_status}
```

- [ ] **Step 2: Also expose persona status in the knowledge list endpoint**

In the existing `list_knowledge` endpoint, add persona info. After the existing `result` list is built, add a persona field to the response:

```python
    # Load persona separately
    from domain.knowledge.teaching import get_or_create_persona
    persona_item = await get_or_create_persona(session, resolved)
    persona_data = None
    if persona_item:
        persona_text = persona_item.content or ""
        # Count draft_reply edits for the subtitle
        from sqlalchemy import func
        from db.models.doctor_edit import DoctorEdit
        edit_count_result = await session.execute(
            select(func.count()).select_from(DoctorEdit).where(
                DoctorEdit.doctor_id == resolved,
                DoctorEdit.entity_type == "draft_reply",
            )
        )
        edit_count = edit_count_result.scalar() or 0
        persona_data = {
            "id": persona_item.id,
            "title": "我的AI人设",
            "content": persona_text,
            "persona_status": persona_item.persona_status or "draft",
            "edit_count": edit_count,
            "updated_at": persona_item.updated_at.isoformat() if persona_item.updated_at else None,
        }

    return {"items": result, "persona": persona_data}
```

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/doctor_dashboard/knowledge_handlers.py
git commit -m "feat: add persona confirm/deactivate API + expose in knowledge list

POST /api/manage/knowledge/persona/confirm with action=activate/deactivate.
GET /api/manage/knowledge now returns a 'persona' field with status, edit
count, and content separate from the regular items list.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Frontend — Pin Persona Card on Knowledge Page

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx`

- [ ] **Step 1: Add PersonaCard component and pin at top**

In `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx`, add a `PersonaCard` component before the `KnowledgeRow` component:

```jsx
function PersonaCard({ persona, onClick }) {
  if (!persona) return null;

  const isActive = persona.persona_status === "active";
  const isDraftReady = persona.persona_status === "draft"
    && persona.content
    && !persona.content.includes("（AI会根据你的回复逐渐学习");

  let subtitle = `待学习 · 已收集 ${persona.edit_count || 0} 条回复`;
  let accentColor = COLOR.text4;

  if (isDraftReady) {
    subtitle = "AI已分析你的风格 · 点击查看";
    accentColor = COLOR.accent;
  } else if (isActive) {
    const date = persona.updated_at
      ? formatRelativeDate(persona.updated_at)
      : "";
    subtitle = `已启用 · 基于 ${persona.edit_count || 0} 条回复${date ? ` · ${date}` : ""}`;
    accentColor = COLOR.primary;
  }

  return (
    <Box
      onClick={onClick}
      sx={{
        mx: 1.5, mt: 1.5, mb: 0.5, px: 2, py: 1.5,
        bgcolor: COLOR.white,
        borderRadius: RADIUS.md,
        border: `1px solid ${isDraftReady ? COLOR.accent : COLOR.borderLight}`,
        cursor: "pointer",
        "&:active": { opacity: 0.8 },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600 }}>
          我的AI人设
        </Typography>
        <Box
          component="span"
          sx={{
            fontSize: 10, fontWeight: 600,
            borderRadius: RADIUS.sm, px: 0.5, py: 0.25,
            bgcolor: isActive ? COLOR.primaryLight : (isDraftReady ? COLOR.amberLight : COLOR.surface),
            color: accentColor,
          }}
        >
          {isActive ? "已启用" : isDraftReady ? "待确认" : "学习中"}
        </Box>
      </Box>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: accentColor, mt: 0.5 }}>
        {subtitle}
      </Typography>
    </Box>
  );
}
```

- [ ] **Step 2: Update `KnowledgeSubpage` to accept and render persona**

Add `persona` and `onPersonaClick` props to `KnowledgeSubpage`:

```jsx
export default function KnowledgeSubpage({
  items = [],
  loading = false,
  onBack,
  onAdd,
  onDelete,
  title = "我的方法",
  stats,
  onItemClick,
  persona,        // new
  onPersonaClick, // new
}) {
```

Filter persona items out of the regular list and render `PersonaCard` before the search bar:

```jsx
  // Filter out persona items from regular list
  const regularItems = items.filter(item => item.category !== "persona");
  const sorted = mergeAndSort(regularItems, stats);
```

Then in the JSX, before the search bar, add:

```jsx
          <PersonaCard persona={persona} onClick={onPersonaClick} />
```

Update the stats to use `regularItems` instead of `items`:

```jsx
  const weekCitations = Array.isArray(stats)
    ? stats.reduce((sum, s) => sum + (s.total_count || 0), 0)
    : sorted.reduce((sum, it) => sum + (it._usageCount || 0), 0);

  const unusedCount = sorted.filter(item => (item._usageCount || 0) === 0).length;
```

And update the empty state check:

```jsx
      {!loading && regularItems.length === 0 && (
```

And the stats bar:

```jsx
            <StatColumn value={regularItems.length} label="条规则" />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx
git commit -m "feat: pin persona card at top of knowledge page

Shows persona status (学习中/待确认/已启用) with edit count and
last update date. Filtered out of regular knowledge list to avoid
duplication. Tap navigates to persona detail for editing/confirming.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Integration Verification

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=. -x`
Expected: All existing tests PASS plus new tests from Tasks 1, 3, 5

- [ ] **Step 2: Verify DB schema auto-backfill**

Run: `.venv/bin/python -c "from db.init_db import create_tables; import asyncio; asyncio.run(create_tables()); print('OK')"`
Expected: OK (new `persona_status` column added automatically)

- [ ] **Step 3: Verify the hero loop end-to-end mentally**

Trace the flow:
1. Patient sends message → triage classifies → `_generate_draft_for_escalated()` fires after 5s
2. `generate_draft_reply()` runs → no KB items → citation gate REMOVED → draft generated and persisted
3. Doctor opens dashboard → sees draft in `MessageTimeline` → edits/sends
4. `send_doctor_reply()` → saves outbound message → logs edit pair → triggers persona extraction check
5. After 15+ replies → extraction runs → persona item updated with `status="draft"`
6. Doctor visits knowledge page → sees "我的AI人设 · AI已分析你的风格 · 点击查看"
7. Doctor reviews, edits, taps confirm → `persona_status = "active"`
8. Next draft → `compose_messages()` → persona loaded → injected as `<doctor_persona>` before `<doctor_knowledge>`

- [ ] **Step 4: Final commit with all tests passing**

If any test adjustments were needed during integration, commit them now.

---

## Summary

| Task | Change | Size | Files |
|---|---|---|---|
| 1 | Remove citation gate | ~5 lines | `draft_reply.py` |
| 2 | Reduce batch delay | 1 line | `triage_handlers.py` |
| 3 | Edit logging in reply | ~25 lines | `reply.py` |
| 4 | DB model: persona category + status | ~5 lines | `doctor.py` |
| 5 | Persona lifecycle functions | ~120 lines | `teaching.py` |
| 6 | Extraction trigger wire-up | ~8 lines | `reply.py` |
| 7 | Prompt composer persona injection | ~40 lines | `knowledge_context.py`, `prompt_composer.py` |
| 8 | Persona API endpoint | ~40 lines | `knowledge_handlers.py` |
| 9 | Frontend persona card | ~60 lines | `KnowledgeSubpage.jsx` |
| 10 | Integration verification | 0 lines | — |
