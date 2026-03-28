# Knowledge Foundation Implementation Plan (Stream A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the knowledge foundation that all other streams depend on: fix category hardcoding, add title/summary fields, build citation parsing, wire usage tracking, and add the edit-to-rule teaching loop for diagnosis edits.

**Architecture:** Fix 3 hardcoded `category="custom"` call sites → add `title`/`summary` columns to `DoctorKnowledgeItem` → build `citation_parser.py` that extracts `[KB-{id}]` from LLM output → create `knowledge_usage_log` table and logging pipeline → add `doctor_edits` table and "记成我的偏好?" trigger on diagnosis edits.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x (async), FastAPI, pytest, Qwen3:32b via Groq

**Spec:** `docs/specs/2026-03-27-personal-ai-redesign.md` sections 4A, 4B, 3A, 4E-diagnosis

**Depends on:** Nothing (this is Stream A — build first)
**Blocks:** Plan 2 (Draft Reply Pipeline), Plan 3 (Query & Aggregation), Plan 4 (Frontend)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/db/models/doctor.py` | Add `title`, `summary` fields to `DoctorKnowledgeItem` |
| Modify | `src/db/crud/doctor.py` | Accept `category` param properly, add title/summary |
| Modify | `src/domain/knowledge/knowledge_crud.py` | Pass category through, extract title |
| Modify | `src/domain/knowledge/knowledge_ingest.py` | Pass category through |
| Modify | `src/channels/web/ui/knowledge_handlers.py` | Accept category from frontend |
| Create | `src/domain/knowledge/citation_parser.py` | Extract + validate `[KB-id]` from LLM output |
| Create | `src/db/models/knowledge_usage.py` | `KnowledgeUsageLog` model |
| Create | `src/domain/knowledge/usage_tracking.py` | Log citations, query stats |
| Modify | `src/agent/prompt_composer.py` | Call citation parser after LLM response |
| Modify | `src/agent/prompts/intent/query.md` | Add citation instructions |
| Create | `src/db/models/doctor_edit.py` | `DoctorEdit` model |
| Create | `src/domain/knowledge/teaching.py` | Edit-to-rule trigger logic |
| Modify | `src/channels/web/ui/diagnosis_handlers.py` | Log edits to `doctor_edits` table |
| Create | `src/channels/web/ui/knowledge_stats_handlers.py` | Stats + activity API endpoints |
| Create | `tests/test_citation_parser.py` | Citation extraction tests |
| Create | `tests/test_knowledge_category.py` | Category fix tests |
| Create | `tests/test_usage_tracking.py` | Usage logging tests |
| Create | `tests/test_teaching_loop.py` | Edit-to-rule tests |

---

### Task 1: Fix Knowledge Category Hardcoding (4A)

**Files:**
- Modify: `src/domain/knowledge/knowledge_crud.py:143-168`
- Modify: `src/domain/knowledge/knowledge_ingest.py:155-170`
- Modify: `src/db/crud/doctor.py:71-83`
- Modify: `src/channels/web/ui/knowledge_handlers.py:70-91`
- Create: `tests/test_knowledge_category.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_category.py
import pytest
from domain.knowledge.knowledge_crud import save_knowledge_item

@pytest.mark.asyncio
async def test_save_knowledge_item_respects_category(async_session):
    """Category should be stored as provided, not hardcoded to 'custom'."""
    item = await save_knowledge_item(
        async_session, "doc_1", "术后头痛先排除再出血",
        source="doctor", confidence=1.0, category="diagnosis",
    )
    assert item is not None
    assert item.category == "diagnosis"


@pytest.mark.asyncio
async def test_save_knowledge_item_defaults_to_custom(async_session):
    """When no category provided, default to 'custom'."""
    item = await save_knowledge_item(
        async_session, "doc_1", "一般性知识条目",
        source="doctor", confidence=1.0,
    )
    assert item is not None
    assert item.category == "custom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_knowledge_category.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `save_knowledge_item` does not accept `category` parameter

- [ ] **Step 3: Add `category` parameter to `save_knowledge_item`**

In `src/domain/knowledge/knowledge_crud.py`, change `save_knowledge_item`:

```python
async def save_knowledge_item(
    session,
    doctor_id: str,
    text: str,
    source: str = "doctor",
    confidence: float = 1.0,
    category: str = "custom",  # ← ADD THIS PARAMETER
) -> Optional[DoctorKnowledgeItem]:
    """Persist a single knowledge item. Returns None if duplicate."""
    cleaned = _normalize_text(text)
    if not cleaned:
        return None
    if await _is_duplicate(session, doctor_id, cleaned):
        return None
    payload = _encode_knowledge_payload(cleaned, source=source, confidence=confidence)
    return await add_doctor_knowledge_item(session, doctor_id, payload, category=category)  # ← PASS THROUGH
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_knowledge_category.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 5: Fix `save_uploaded_knowledge` in `knowledge_ingest.py`**

In `src/domain/knowledge/knowledge_ingest.py`, change `save_uploaded_knowledge`:

```python
async def save_uploaded_knowledge(
    doctor_id: str, text: str, source_filename: str, category: str = "custom",
) -> dict:
```

And change the call to `add_doctor_knowledge_item` inside:
```python
item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
```

- [ ] **Step 6: Accept category in knowledge handler endpoints**

In `src/channels/web/ui/knowledge_handlers.py`, update `AddKnowledgeRequest`:

```python
class AddKnowledgeRequest(BaseModel):
    content: str
    category: str = "custom"
```

And pass it through in `add_knowledge`:
```python
item = await save_knowledge_item(
    session, resolved, content,
    source="doctor", confidence=1.0,
    category=body.category,
)
```

Update `UploadSaveRequest` and `upload_save` similarly:
```python
class UploadSaveRequest(BaseModel):
    text: str
    source_filename: str
    category: str = "custom"
```

```python
result = await save_uploaded_knowledge(
    resolved, text, body.source_filename, category=body.category,
)
```

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/domain/knowledge/knowledge_crud.py src/domain/knowledge/knowledge_ingest.py \
  src/db/crud/doctor.py src/channels/web/ui/knowledge_handlers.py \
  tests/test_knowledge_category.py
git commit -m "fix: pass category through knowledge save pipeline instead of hardcoding 'custom'

Three call sites were hardcoding category='custom':
- knowledge_crud.save_knowledge_item
- knowledge_ingest.save_uploaded_knowledge
- knowledge_handlers upload_save endpoint

All now accept and pass through the category parameter.
Frontend can send category in AddKnowledgeRequest and UploadSaveRequest."
```

---

### Task 2: Add Title and Summary Fields to Knowledge Items (4A)

**Files:**
- Modify: `src/db/models/doctor.py:15-26`
- Modify: `src/domain/knowledge/knowledge_crud.py`
- Modify: `src/channels/web/ui/knowledge_handlers.py:35-67`
- Create: `tests/test_knowledge_title.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_title.py
import pytest
from db.models.doctor import DoctorKnowledgeItem

def test_knowledge_item_has_title_and_summary():
    """DoctorKnowledgeItem should have title and summary fields."""
    item = DoctorKnowledgeItem(
        doctor_id="doc_1",
        content='{"v":1,"text":"test","source":"doctor","confidence":1.0}',
        title="术后头痛红旗",
        summary="先排除再出血，再评估颅压",
    )
    assert item.title == "术后头痛红旗"
    assert item.summary == "先排除再出血，再评估颅压"


def test_knowledge_item_title_defaults_to_none():
    """Title and summary should default to None for backwards compat."""
    item = DoctorKnowledgeItem(
        doctor_id="doc_1",
        content='{"v":1,"text":"test","source":"doctor","confidence":1.0}',
    )
    assert item.title is None
    assert item.summary is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_knowledge_title.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `DoctorKnowledgeItem` has no `title` attribute

- [ ] **Step 3: Add title and summary columns to model**

In `src/db/models/doctor.py`, add after the `category` field:

```python
class DoctorKnowledgeItem(Base):
    """Per-doctor reusable knowledge snippets for prompt grounding."""
    __tablename__ = "doctor_knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="custom")
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # ← NEW
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # ← NEW
    reference_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_knowledge_title.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: PASS

- [ ] **Step 5: Add title extraction helper**

In `src/domain/knowledge/knowledge_crud.py`, add a helper function:

```python
def extract_title_from_text(text: str, max_len: int = 50) -> str:
    """Extract a short title from knowledge text.

    Strategy: use the first line/sentence, truncated to max_len.
    Falls back to first max_len chars if no line break found.
    """
    if not text:
        return ""
    # Try first line
    first_line = text.split("\n")[0].strip()
    # Try first sentence (Chinese period or colon)
    for sep in ("。", "：", ":", "，"):
        if sep in first_line:
            first_line = first_line.split(sep)[0].strip()
            break
    if len(first_line) > max_len:
        first_line = first_line[:max_len] + "…"
    return first_line
```

- [ ] **Step 6: Wire title into save pipeline**

In `save_knowledge_item`, add title extraction:

```python
async def save_knowledge_item(
    session,
    doctor_id: str,
    text: str,
    source: str = "doctor",
    confidence: float = 1.0,
    category: str = "custom",
    title: Optional[str] = None,  # ← ADD
    summary: Optional[str] = None,  # ← ADD
) -> Optional[DoctorKnowledgeItem]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return None
    if await _is_duplicate(session, doctor_id, cleaned):
        return None
    # Auto-extract title if not provided
    if not title:
        title = extract_title_from_text(cleaned)
    payload = _encode_knowledge_payload(cleaned, source=source, confidence=confidence)
    item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
    if item:
        item.title = title
        item.summary = summary
        await session.commit()
        await session.refresh(item)
    return item
```

- [ ] **Step 7: Return title in list endpoint**

In `src/channels/web/ui/knowledge_handlers.py`, update the list endpoint response to include title:

```python
result.append({
    "id": item.id,
    "title": item.title or "",
    "text": text,
    "summary": item.summary or "",
    "source": source,
    "confidence": confidence,
    "category": getattr(item, "category", None) or "custom",
    "created_at": item.created_at.isoformat() if item.created_at else None,
})
```

- [ ] **Step 8: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/db/models/doctor.py src/domain/knowledge/knowledge_crud.py \
  src/channels/web/ui/knowledge_handlers.py tests/test_knowledge_title.py
git commit -m "feat: add title and summary fields to DoctorKnowledgeItem

- New nullable columns: title (String 200), summary (Text)
- Auto-extract title from first line/sentence when not provided
- List endpoint returns title and summary in response
- Backwards compatible: existing items have null title/summary"
```

---

### Task 3: Citation Parsing Spike (4B)

**Files:**
- Create: `src/domain/knowledge/citation_parser.py`
- Modify: `src/agent/prompts/intent/query.md`
- Create: `tests/test_citation_parser.py`

- [ ] **Step 1: Write comprehensive citation parser tests**

```python
# tests/test_citation_parser.py
import pytest
from domain.knowledge.citation_parser import (
    extract_citations,
    validate_citations,
    CitationResult,
)


class TestExtractCitations:
    """Test [KB-{id}] extraction from various LLM output formats."""

    def test_single_citation_in_text(self):
        text = "建议使用钙通道阻滞剂控制血压 [KB-42]"
        result = extract_citations(text)
        assert result.cited_ids == [42]

    def test_multiple_citations(self):
        text = "同时注意肾功能监测 [KB-42][KB-15]"
        result = extract_citations(text)
        assert set(result.cited_ids) == {42, 15}

    def test_citations_in_json_detail_field(self):
        """Citations inside a JSON string field (diagnosis pipeline output)."""
        text = '{"detail": "术后第7天头痛加剧，需排除迟发性血肿 [KB-3]"}'
        result = extract_citations(text)
        assert result.cited_ids == [3]

    def test_no_citations(self):
        text = "这是一段普通的医学文本，没有引用任何知识库条目"
        result = extract_citations(text)
        assert result.cited_ids == []

    def test_duplicate_citations_deduplicated(self):
        text = "参考 [KB-5] 和 [KB-5] 的内容"
        result = extract_citations(text)
        assert result.cited_ids == [5]

    def test_escaped_citations_ignored(self):
        """Escaped citations (from user content sanitization) should not match."""
        text = "用户输入包含 \\[KB-99] 不应被解析"
        result = extract_citations(text)
        assert result.cited_ids == []

    def test_citations_across_multiple_fields(self):
        text = """
        {"differentials": [{"detail": "考虑TIA [KB-7]"}],
         "workup": [{"detail": "建议MRA [KB-12]"}],
         "treatment": [{"detail": "阿司匹林 [KB-7]"}]}
        """
        result = extract_citations(text)
        assert set(result.cited_ids) == {7, 12}


class TestValidateCitations:
    """Test that extracted IDs are validated against real KB items."""

    def test_valid_ids_kept(self):
        valid_ids = {1, 3, 5, 7}
        extracted = [3, 7]
        result = validate_citations(extracted, valid_ids)
        assert result.valid_ids == [3, 7]
        assert result.hallucinated_ids == []

    def test_hallucinated_ids_removed(self):
        valid_ids = {1, 3, 5}
        extracted = [3, 99, 42]
        result = validate_citations(extracted, valid_ids)
        assert result.valid_ids == [3]
        assert set(result.hallucinated_ids) == {99, 42}

    def test_empty_extraction(self):
        valid_ids = {1, 3, 5}
        extracted = []
        result = validate_citations(extracted, valid_ids)
        assert result.valid_ids == []
        assert result.hallucinated_ids == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_citation_parser.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — `citation_parser` module does not exist

- [ ] **Step 3: Implement the citation parser**

```python
# src/domain/knowledge/citation_parser.py
"""Extract and validate [KB-{id}] citations from LLM output.

This is the load-bearing primitive for the entire product.
Every citation-dependent feature (stats, activity feed, UI treatment,
teaching loop) depends on this module working reliably.
"""
import re
from dataclasses import dataclass, field
from typing import List, Set

from utils.log import log

# Matches [KB-123] but NOT \[KB-123] (escaped by sanitizer)
_CITATION_RE = re.compile(r'(?<!\\)\[KB-(\d+)\]')


@dataclass
class CitationResult:
    """Raw extraction result from LLM text."""
    cited_ids: List[int] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ValidationResult:
    """Validated citations against actual KB item IDs."""
    valid_ids: List[int] = field(default_factory=list)
    hallucinated_ids: List[int] = field(default_factory=list)


def extract_citations(text: str) -> CitationResult:
    """Extract [KB-{id}] markers from LLM output text.

    Works on both free text and JSON-embedded strings (e.g., detail
    fields inside structured diagnosis output).

    Returns deduplicated list of cited KB item IDs.
    """
    if not text:
        return CitationResult(cited_ids=[], raw_text="")

    matches = _CITATION_RE.findall(text)
    # Deduplicate while preserving first-occurrence order
    seen: Set[int] = set()
    cited_ids: List[int] = []
    for m in matches:
        try:
            kb_id = int(m)
        except (ValueError, TypeError):
            continue
        if kb_id not in seen:
            seen.add(kb_id)
            cited_ids.append(kb_id)

    return CitationResult(cited_ids=cited_ids, raw_text=text)


def validate_citations(
    extracted_ids: List[int],
    valid_kb_ids: Set[int],
) -> ValidationResult:
    """Validate extracted IDs against the doctor's actual KB items.

    Removes hallucinated IDs (LLM cited an ID that doesn't exist).
    Logs anomalies for monitoring.
    """
    valid: List[int] = []
    hallucinated: List[int] = []

    for kb_id in extracted_ids:
        if kb_id in valid_kb_ids:
            valid.append(kb_id)
        else:
            hallucinated.append(kb_id)
            log(f"[citation] hallucinated KB-{kb_id} (not in doctor's KB)", level="warning")

    return ValidationResult(valid_ids=valid, hallucinated_ids=hallucinated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_citation_parser.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

- [ ] **Step 5: Add citation instructions to query prompt**

In `src/agent/prompts/intent/query.md`, add at the end before any closing section:

```markdown
## 知识库引用

如果你的回答参考了医生知识库中的内容，请在相关段落末尾标注引用来源。
格式：[KB-{id}]
可以引用多个来源：[KB-{id1}][KB-{id2}]
仅引用你确实参考了的知识库条目，不要编造不存在的引用。
```

- [ ] **Step 6: Commit**

```bash
git add src/domain/knowledge/citation_parser.py tests/test_citation_parser.py \
  src/agent/prompts/intent/query.md
git commit -m "feat: add citation parser for [KB-id] extraction from LLM output

- Regex-based extraction that handles JSON-embedded strings
- Ignores escaped citations (from sanitizer)
- Deduplication preserving first-occurrence order
- Validation against real KB item IDs with hallucination logging
- Added citation instructions to query.md prompt"
```

---

### Task 4: Knowledge Usage Tracking (3A)

**Files:**
- Create: `src/db/models/knowledge_usage.py`
- Create: `src/domain/knowledge/usage_tracking.py`
- Create: `src/channels/web/ui/knowledge_stats_handlers.py`
- Modify: `src/main.py` (register router)
- Create: `tests/test_usage_tracking.py`

- [ ] **Step 1: Write the usage tracking tests**

```python
# tests/test_usage_tracking.py
import pytest
from datetime import datetime, timedelta
from domain.knowledge.usage_tracking import (
    log_citations,
    get_knowledge_stats,
    get_recent_activity,
)


@pytest.mark.asyncio
async def test_log_citations_stores_records(async_session):
    """Logging citations should create usage log entries."""
    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[3, 7],
        usage_context="diagnosis",
        patient_id="pat_1",
        record_id=10,
    )
    stats = await get_knowledge_stats(async_session, "doc_1")
    assert len(stats) >= 2
    kb3_stat = next(s for s in stats if s["knowledge_item_id"] == 3)
    assert kb3_stat["total_count"] >= 1


@pytest.mark.asyncio
async def test_log_citations_empty_list(async_session):
    """Empty citation list should be a no-op."""
    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[],
        usage_context="diagnosis",
    )
    stats = await get_knowledge_stats(async_session, "doc_1")
    assert len(stats) == 0


@pytest.mark.asyncio
async def test_get_recent_activity(async_session):
    """Recent activity should return latest citation events."""
    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[5],
        usage_context="followup",
        patient_id="pat_2",
    )
    activity = await get_recent_activity(async_session, "doc_1", limit=10)
    assert len(activity) >= 1
    assert activity[0]["usage_context"] == "followup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_usage_tracking.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — modules don't exist

- [ ] **Step 3: Create the KnowledgeUsageLog model**

```python
# src/db/models/knowledge_usage.py
"""Knowledge usage log — tracks when and where KB items are cited by the AI."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base

def _utcnow() -> datetime:
    return datetime.utcnow()


class KnowledgeUsageLog(Base):
    __tablename__ = "knowledge_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctor_knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_context: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # diagnosis, chat, followup, interview
    patient_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    record_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

- [ ] **Step 4: Create the usage tracking domain functions**

```python
# src/domain/knowledge/usage_tracking.py
"""Log and query knowledge citation usage."""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.knowledge_usage import KnowledgeUsageLog
from db.models.doctor import DoctorKnowledgeItem
from utils.log import log


async def log_citations(
    session: AsyncSession,
    doctor_id: str,
    cited_kb_ids: List[int],
    usage_context: str,
    patient_id: Optional[str] = None,
    record_id: Optional[int] = None,
) -> int:
    """Log citation events. Returns count of logged entries."""
    if not cited_kb_ids:
        return 0

    count = 0
    for kb_id in cited_kb_ids:
        entry = KnowledgeUsageLog(
            doctor_id=doctor_id,
            knowledge_item_id=kb_id,
            usage_context=usage_context,
            patient_id=patient_id,
            record_id=record_id,
        )
        session.add(entry)
        count += 1

        # Also increment reference_count on the KB item
        item = await session.get(DoctorKnowledgeItem, kb_id)
        if item and item.doctor_id == doctor_id:
            item.reference_count = (item.reference_count or 0) + 1

    await session.commit()
    log(f"[usage] logged {count} citations for doctor {doctor_id} ({usage_context})")
    return count


async def get_knowledge_stats(
    session: AsyncSession,
    doctor_id: str,
    days: int = 7,
) -> List[Dict[str, Any]]:
    """Per-item usage counts for a doctor within the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(
            KnowledgeUsageLog.knowledge_item_id,
            func.count().label("total_count"),
            func.max(KnowledgeUsageLog.created_at).label("last_used"),
        )
        .where(
            KnowledgeUsageLog.doctor_id == doctor_id,
            KnowledgeUsageLog.created_at >= since,
        )
        .group_by(KnowledgeUsageLog.knowledge_item_id)
        .order_by(desc("total_count"))
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "knowledge_item_id": r.knowledge_item_id,
            "total_count": r.total_count,
            "last_used": r.last_used.isoformat() if r.last_used else None,
        }
        for r in rows
    ]


async def get_recent_activity(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Recent citation events for the activity feed."""
    stmt = (
        select(KnowledgeUsageLog)
        .where(KnowledgeUsageLog.doctor_id == doctor_id)
        .order_by(desc(KnowledgeUsageLog.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "knowledge_item_id": r.knowledge_item_id,
            "usage_context": r.usage_context,
            "patient_id": r.patient_id,
            "record_id": r.record_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_usage_tracking.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

- [ ] **Step 6: Create stats API endpoint**

```python
# src/channels/web/ui/knowledge_stats_handlers.py
"""Knowledge stats and activity feed API endpoints."""
from typing import Optional

from fastapi import APIRouter, Query, Header

from channels.web.ui._auth import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from domain.knowledge.usage_tracking import get_knowledge_stats, get_recent_activity

router = APIRouter()


@router.get("/api/manage/knowledge/stats")
async def knowledge_stats(
    doctor_id: str = Query(...),
    days: int = Query(default=7),
    authorization: Optional[str] = Header(default=None),
):
    """Per-item usage counts for the last N days."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        stats = await get_knowledge_stats(session, resolved, days=days)
    return {"stats": stats}


@router.get("/api/manage/knowledge/activity")
async def knowledge_activity(
    doctor_id: str = Query(...),
    limit: int = Query(default=20),
    authorization: Optional[str] = Header(default=None),
):
    """Recent citation events for the activity feed."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        activity = await get_recent_activity(session, resolved, limit=limit)
    return {"activity": activity}
```

- [ ] **Step 7: Register the router in main.py**

In `src/main.py`, add:
```python
from channels.web.ui.knowledge_stats_handlers import router as knowledge_stats_router
app.include_router(knowledge_stats_router)
```

- [ ] **Step 8: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/db/models/knowledge_usage.py src/domain/knowledge/usage_tracking.py \
  src/channels/web/ui/knowledge_stats_handlers.py src/main.py \
  tests/test_usage_tracking.py
git commit -m "feat: add knowledge usage tracking with stats and activity API

- New KnowledgeUsageLog table: tracks each [KB-id] citation
- log_citations(): stores entries and increments reference_count
- get_knowledge_stats(): per-item counts for last N days
- get_recent_activity(): recent events for activity feed
- API: GET /api/manage/knowledge/stats, GET /api/manage/knowledge/activity"
```

---

### Task 5: Teaching Loop — Diagnosis Edits (4E-diagnosis)

**Files:**
- Create: `src/db/models/doctor_edit.py`
- Create: `src/domain/knowledge/teaching.py`
- Modify: `src/channels/web/ui/diagnosis_handlers.py:158-203`
- Create: `src/channels/web/ui/teaching_handlers.py`
- Modify: `src/main.py` (register router)
- Create: `tests/test_teaching_loop.py`

- [ ] **Step 1: Write the teaching loop tests**

```python
# tests/test_teaching_loop.py
import pytest
from domain.knowledge.teaching import (
    should_prompt_teaching,
    log_doctor_edit,
    create_rule_from_edit,
)


def test_should_prompt_ignores_minor_edits():
    """Edits under 10 chars diff should not trigger the prompt."""
    assert should_prompt_teaching("术后复查", "术后复查CT") is False


def test_should_prompt_triggers_on_significant_edits():
    """Edits over 10 chars diff should trigger the prompt."""
    original = "建议观察"
    edited = "建议48小时内复查头颅CT，排除迟发性血肿"
    assert should_prompt_teaching(original, edited) is True


def test_should_prompt_ignores_whitespace_only():
    """Whitespace-only changes should not trigger."""
    assert should_prompt_teaching("术后复查CT", "术后复查CT  ") is False


@pytest.mark.asyncio
async def test_log_doctor_edit(async_session):
    """Logging an edit should create a doctor_edits record."""
    edit_id = await log_doctor_edit(
        session=async_session,
        doctor_id="doc_1",
        entity_type="diagnosis",
        entity_id=42,
        original_text="建议观察",
        edited_text="建议48小时内复查头颅CT",
    )
    assert edit_id is not None
    assert edit_id > 0


@pytest.mark.asyncio
async def test_create_rule_from_edit(async_session):
    """Creating a rule from an edit should save a knowledge item."""
    edit_id = await log_doctor_edit(
        session=async_session,
        doctor_id="doc_1",
        entity_type="diagnosis",
        entity_id=42,
        original_text="建议观察",
        edited_text="建议48小时内复查头颅CT，排除迟发性血肿",
    )
    rule = await create_rule_from_edit(
        session=async_session,
        doctor_id="doc_1",
        edit_id=edit_id,
    )
    assert rule is not None
    assert "复查" in rule.content or "复查" in (rule.title or "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_teaching_loop.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL — modules don't exist

- [ ] **Step 3: Create DoctorEdit model**

```python
# src/db/models/doctor_edit.py
"""Unified edit log for teaching loop — captures doctor corrections across all entity types."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base

def _utcnow() -> datetime:
    return datetime.utcnow()


class DoctorEdit(Base):
    __tablename__ = "doctor_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # diagnosis, draft_reply, record
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[str] = mapped_column(Text, nullable=False)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # LLM-generated one-line
    rule_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

- [ ] **Step 4: Create teaching domain functions**

```python
# src/domain/knowledge/teaching.py
"""Edit-to-preference learning: detect significant edits and offer to save as rules."""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.doctor_edit import DoctorEdit
from domain.knowledge.knowledge_crud import save_knowledge_item
from utils.log import log


def should_prompt_teaching(original: str, edited: str) -> bool:
    """Determine if an edit is significant enough to prompt '记成我的偏好?'

    Returns False for:
    - Minor edits (<10 char diff)
    - Whitespace-only changes
    """
    orig_clean = (original or "").strip()
    edit_clean = (edited or "").strip()

    if orig_clean == edit_clean:
        return False

    # Character-level diff length
    diff_len = abs(len(edit_clean) - len(orig_clean))
    # Also check if the content itself changed significantly
    # (handles rewording at similar length)
    common = sum(1 for a, b in zip(orig_clean, edit_clean) if a == b)
    max_len = max(len(orig_clean), len(edit_clean), 1)
    similarity = common / max_len

    # Trigger if diff is >= 10 chars OR content similarity < 80%
    return diff_len >= 10 or similarity < 0.8


async def log_doctor_edit(
    session: AsyncSession,
    doctor_id: str,
    entity_type: str,
    entity_id: int,
    original_text: str,
    edited_text: str,
    field_name: Optional[str] = None,
) -> int:
    """Log a doctor edit. Returns the edit ID."""
    edit = DoctorEdit(
        doctor_id=doctor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        original_text=original_text,
        edited_text=edited_text,
    )
    session.add(edit)
    await session.commit()
    await session.refresh(edit)
    log(f"[teaching] logged edit #{edit.id} for doctor {doctor_id} ({entity_type})")
    return edit.id


async def create_rule_from_edit(
    session: AsyncSession,
    doctor_id: str,
    edit_id: int,
) -> Optional:
    """Convert a doctor edit into a knowledge rule. Called when doctor taps '记成我的偏好?'"""
    edit = await session.get(DoctorEdit, edit_id)
    if not edit or edit.doctor_id != doctor_id:
        return None

    # Save the edited text as a new knowledge item
    rule = await save_knowledge_item(
        session,
        doctor_id,
        text=edit.edited_text,
        source="edit",
        confidence=1.0,
        category="preference",
        title=None,  # Auto-extracted by save_knowledge_item
    )

    if rule:
        edit.rule_created = True
        edit.rule_id = rule.id
        await session.commit()
        log(f"[teaching] created rule #{rule.id} from edit #{edit_id}")

    return rule
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_teaching_loop.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

- [ ] **Step 6: Wire edit logging into diagnosis decision handler**

In `src/channels/web/ui/diagnosis_handlers.py`, after the `update_decision` call in `decide_suggestion`, add edit logging:

```python
# After line ~195 (after update_decision call)
if updated and decision_enum == SuggestionDecision.edited and body.edited_text:
    from domain.knowledge.teaching import should_prompt_teaching, log_doctor_edit
    original = row.content or ""
    if should_prompt_teaching(original, body.edited_text):
        edit_id = await log_doctor_edit(
            db, resolved, "diagnosis", suggestion_id,
            original_text=original, edited_text=body.edited_text,
        )
        return {
            "status": "ok", "id": updated.id, "decision": updated.decision,
            "teach_prompt": True, "edit_id": edit_id,
        }

return {"status": "ok", "id": updated.id, "decision": updated.decision}
```

- [ ] **Step 7: Create teaching API endpoint**

```python
# src/channels/web/ui/teaching_handlers.py
"""Teaching loop API — convert doctor edits to knowledge rules."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

from channels.web.ui._auth import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from domain.knowledge.teaching import create_rule_from_edit
from domain.knowledge.knowledge_context import invalidate_knowledge_cache

router = APIRouter()


class CreateRuleRequest(BaseModel):
    edit_id: int


@router.post("/api/manage/teaching/create-rule")
async def create_rule_from_doctor_edit(
    body: CreateRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Doctor tapped '记成我的偏好?' — convert edit to a knowledge rule."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as session:
        rule = await create_rule_from_edit(session, resolved, body.edit_id)

    if not rule:
        raise HTTPException(404, "Edit not found or already converted")

    invalidate_knowledge_cache(resolved)
    return {
        "status": "ok",
        "rule_id": rule.id,
        "title": rule.title or "",
    }
```

- [ ] **Step 8: Register the router in main.py**

In `src/main.py`, add:
```python
from channels.web.ui.teaching_handlers import router as teaching_router
app.include_router(teaching_router)
```

- [ ] **Step 9: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add src/db/models/doctor_edit.py src/domain/knowledge/teaching.py \
  src/channels/web/ui/teaching_handlers.py \
  src/channels/web/ui/diagnosis_handlers.py src/main.py \
  tests/test_teaching_loop.py
git commit -m "feat: add teaching loop for diagnosis edits (4E-diagnosis)

- New DoctorEdit model: unified edit log across entity types
- should_prompt_teaching(): skip minor edits (<10 char diff)
- log_doctor_edit(): stores original + edited text
- create_rule_from_edit(): converts edit to KB rule on doctor tap
- Wired into diagnosis decide endpoint: returns teach_prompt flag
- API: POST /api/manage/teaching/create-rule"
```

---

## Plan Completion Checklist

After all 5 tasks are complete, verify:

- [ ] `category` parameter flows through all 3 save paths
- [ ] Knowledge items have `title` and `summary` fields populated
- [ ] Citation parser extracts `[KB-id]` with >80% recall (run spike test)
- [ ] Usage log records citations and stats endpoint returns data
- [ ] Diagnosis edit → "记成我的偏好?" → rule created flow works end-to-end
- [ ] All tests pass: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
- [ ] No regressions in existing features

## Next Plans

After this plan completes:
- **Plan 2: Draft Reply Pipeline** (Stream B) — depends on Tasks 1+3 from this plan
- **Plan 3: Query & Aggregation** (Stream C) — depends on Task 3 from this plan
- **Plan 4: Frontend Redesign** (Stream D) — depends on all backend APIs
