# Implementation Plan: Stream B — Draft Reply Pipeline

## Plan Summary

The plan covers 8 tasks corresponding to spec sections 3D, 3E, 3F, and build steps 6-11:

1. **Task 1** (step 6): `MessageDraft` model + `followup_reply.md` prompt + `generate_draft_reply` domain function
2. **Task 2** (step 7): Medical safety constraints -- red-flag blocker, content guardrails, AI disclosure
3. **Task 3** (step 8): Draft approve/send/dismiss API endpoints + send confirmation data
4. **Task 4** (step 9): Stale draft invalidation on new patient message
5. **Task 5** (step 10): Teaching loop for draft edits (4E-drafts)
6. **Task 6** (step 11): Message read status (`read_at` on PatientMessage)
7. **Task 7**: Wire draft generation into the escalation handler as a background task with 30-second batching
8. **Task 8**: Register all new routers and models

### File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/db/models/message_draft.py` | `MessageDraft` model (separate table) |
| Create | `src/agent/prompts/intent/followup_reply.md` | Draft reply prompt template |
| Create | `src/domain/patient_lifecycle/draft_reply.py` | `generate_draft_reply`, safety checks, stale invalidation |
| Create | `src/channels/web/ui/draft_handlers.py` | Draft approve/send/edit/dismiss + list API |
| Modify | `src/db/models/patient_message.py` | Add `read_at` column |
| Modify | `src/db/models/__init__.py` | Register `MessageDraft` |
| Modify | `src/channels/web/ui/__init__.py` | Include draft router |
| Modify | `src/channels/web/patient_portal_chat.py` | Add read-status endpoint |
| Modify | `src/domain/patient_lifecycle/triage_handlers.py` | Trigger draft generation on escalation |
| Modify | `src/agent/prompt_config.py` | Add `FOLLOWUP_REPLY_LAYERS` config |
| Create | `tests/test_message_draft_model.py` | Model tests |
| Create | `tests/test_draft_reply.py` | Domain function tests (safety, generation, staleness) |
| Create | `tests/test_draft_handlers.py` | API endpoint tests |
| Create | `tests/test_message_read_status.py` | Read status tests |

### Key Architecture Decisions

- `MessageDraft` is a **separate table** from `PatientMessage` -- drafts have a different lifecycle (generated/edited/sent/dismissed/stale) and support multiple versions per source message.
- Draft generation triggers **only for escalated messages** (`ai_handled=False`), never for informational auto-replies.
- The 30-second batching delay uses `asyncio.sleep(30)` in a background task, checking for newer messages before generating.
- Safety constraints are enforced at the domain layer (in `generate_draft_reply`), not at the API layer, so they cannot be bypassed.
- The `followup_reply.md` prompt includes hard constraints directly in system instructions, plus few-shot examples showing correct citation format.

### Dependencies

- **Already built** (Stream A): `citation_parser.py`, `KnowledgeCategory` enum, `save_knowledge_item` with `category` param, `teaching.py` (should_prompt_teaching, log_doctor_edit, create_rule_from_edit), `usage_tracking.py` (log_citations).
- **Assumes**: Knowledge categories are properly stored (not hardcoded to "custom") so we can filter by `communication`/`followup` categories for draft prompts.

---

### Task 1: MessageDraft Model + Prompt + Domain Function (Build Step 6)

**Goal:** Create the data model, prompt template, and core generation function.

**Files:**
- Create: `src/db/models/message_draft.py`
- Create: `src/agent/prompts/intent/followup_reply.md`
- Create: `src/domain/patient_lifecycle/draft_reply.py`
- Modify: `src/agent/prompt_config.py` (add FOLLOWUP_REPLY_LAYERS)
- Modify: `src/db/models/__init__.py` (register model)
- Create: `tests/test_message_draft_model.py`
- Create: `tests/test_draft_reply.py`

#### Step 1: Write MessageDraft model test

```python
# tests/test_message_draft_model.py
"""Tests for the MessageDraft data model."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401

from db.models.message_draft import MessageDraft, DraftStatus


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_draft_status_enum():
    assert DraftStatus.generated.value == "generated"
    assert DraftStatus.edited.value == "edited"
    assert DraftStatus.sent.value == "sent"
    assert DraftStatus.dismissed.value == "dismissed"
    assert DraftStatus.stale.value == "stale"


@pytest.mark.asyncio
async def test_create_message_draft(async_session):
    draft = MessageDraft(
        doctor_id="doc_1",
        patient_id=1,
        source_message_id=10,
        draft_text="您好，根据您的描述，建议您按时复查。",
        cited_knowledge_ids="[3, 7]",
        confidence=0.85,
        status=DraftStatus.generated,
    )
    async_session.add(draft)
    await async_session.commit()
    await async_session.refresh(draft)

    assert draft.id is not None
    assert draft.edited_text is None
    assert draft.status == DraftStatus.generated


@pytest.mark.asyncio
async def test_draft_edited_text_nullable(async_session):
    draft = MessageDraft(
        doctor_id="doc_1",
        patient_id=1,
        source_message_id=10,
        draft_text="原始草稿",
        status=DraftStatus.generated,
    )
    async_session.add(draft)
    await async_session.commit()

    draft.edited_text = "医生修改后的内容"
    draft.status = DraftStatus.edited
    await async_session.commit()
    await async_session.refresh(draft)

    assert draft.edited_text == "医生修改后的内容"
    assert draft.status == DraftStatus.edited


@pytest.mark.asyncio
async def test_multiple_drafts_per_source_message(async_session):
    """Support multiple draft versions for the same source message."""
    for i in range(3):
        draft = MessageDraft(
            doctor_id="doc_1",
            patient_id=1,
            source_message_id=10,
            draft_text=f"草稿版本 {i}",
            status=DraftStatus.stale if i < 2 else DraftStatus.generated,
        )
        async_session.add(draft)
    await async_session.commit()

    result = await async_session.execute(
        select(MessageDraft).where(MessageDraft.source_message_id == 10)
    )
    drafts = result.scalars().all()
    assert len(drafts) == 3
```

Run: `.venv/bin/python -m pytest tests/test_message_draft_model.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL -- module does not exist

#### Step 2: Implement MessageDraft model

```python
# src/db/models/message_draft.py
"""MessageDraft model — AI-generated reply drafts for doctor review.

Separate from PatientMessage: drafts have a different lifecycle
(generated → edited → sent/dismissed/stale) and support multiple
versions per source message.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class DraftStatus(str, Enum):
    generated = "generated"
    edited = "edited"
    sent = "sent"
    dismissed = "dismissed"
    stale = "stale"


class MessageDraft(Base):
    """AI-generated reply draft for a patient message, pending doctor review."""
    __tablename__ = "message_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patient_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_knowledge_ids: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )  # JSON list, e.g. "[3, 7]"
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DraftStatus.generated.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_message_drafts_doctor_status", "doctor_id", "status"),
        Index("ix_message_drafts_patient", "patient_id"),
        Index("ix_message_drafts_source_msg", "source_message_id"),
    )
```

#### Step 3: Register model in `__init__.py`

In `src/db/models/__init__.py`, add:

```python
from db.models.message_draft import MessageDraft, DraftStatus
```

And add `"MessageDraft", "DraftStatus"` to `__all__`.

#### Step 4: Run model test

Run: `.venv/bin/python -m pytest tests/test_message_draft_model.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 5: Create followup_reply.md prompt template

```markdown
# src/agent/prompts/intent/followup_reply.md
# Role: 医生随访回复助手

你是医生的个人AI助手，帮助起草对患者随访消息的回复。你的回复必须完全模仿这位医生的沟通风格、用语习惯和随访模式。

## 核心原则

1. **你是起草助手，不是医生。** 你起草的内容必须经医生审核后才会发送。
2. **不做新诊断。** 绝不提出患者病历中没有的新诊断。
3. **不改治疗方案。** 绝不建议新的药物、剂量调整或治疗变更。
4. **不开处方。** 绝不提及具体药名、剂量或用法。
5. **可以做的：** 重申已有方案、提醒复查时间、健康教育、症状监测指导、建议来院就诊。

## 红旗症状检测

如果患者消息中包含以下任何红旗症状，**必须**使用紧急就医模板回复，不要生成对话式回复：
- 发热（体温>38°C）
- 神经功能缺损（肢体无力、言语障碍、视力变化）
- 胸痛、呼吸困难
- 出血（术后伤口、消化道等）
- 术后状态恶化（意识改变、剧烈头痛、反复呕吐）
- 癫痫发作

红旗回复模板：
"您描述的症状需要立即就医评估。请尽快前往最近的急诊科，或拨打120。在就医前请注意[相关安全指导]。我已通知医生您的情况。"

## 回复风格

- 使用医生知识库中的沟通话术和用语习惯
- 语气温暖但专业，不过度热情
- 简洁明了，通常100-300字
- 先回应患者的具体问题/担忧，再给建议
- 给出明确的下一步和时间节点

## 知识库引用

如果你的回复基于医生知识库中的内容，请在相关段落末尾标注：[KB-{id}]
仅引用你确实参考了的条目。

## 输出格式

直接输出回复文本，不要加任何前缀或标签。回复将以"AI辅助生成，经医生审核"标签发送给患者。

## 示例

### 示例1 — 术后随访（引用话术规则）

患者消息："医生，我术后第5天了，伤口有点痒，正常吗？"
医生知识库：[KB-8] 术后伤口护理话术：痒是愈合表现，保持清洁干燥，勿搔抓。

回复：
术后第5天伤口有痒感是正常的愈合表现，说明伤口在恢复中。请注意保持伤口清洁干燥，不要搔抓。如果出现红肿、渗液或发热，请及时来院检查。按计划术后第10天来院拆线复查。[KB-8]

### 示例2 — 红旗症状（使用紧急模板）

患者消息："医生，我今天头痛特别厉害，还吐了两次"
（患者术后第3天，颅脑手术后）

回复：
您描述的症状需要立即就医评估。术后出现剧烈头痛伴呕吐可能提示颅内压变化，请尽快前往最近的急诊科，或拨打120。在就医前请保持头部抬高、避免用力。我已通知医生您的情况。

### 示例3 — 复查提醒

患者消息："医生，我的CT什么时候做？"
医生知识库：[KB-12] TIA复查路径：48h内颈动脉超声+MRA。

回复：
根据您的复查计划，需要在48小时内完成颈动脉超声和MRA检查。建议您尽快联系医院影像科预约，检查前无需特殊准备。检查结果出来后可以拍照发给我，医生会帮您解读。[KB-12]
```

#### Step 6: Add FOLLOWUP_REPLY_LAYERS config

In `src/agent/prompt_config.py`, add after `PATIENT_INTERVIEW_LAYERS`:

```python
FOLLOWUP_REPLY_LAYERS = LayerConfig(
    domain=True,
    intent="followup_reply",
    load_knowledge=True,
    patient_context=True,
)
```

#### Step 7: Write domain function tests

```python
# tests/test_draft_reply.py
"""Tests for the draft reply domain function."""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401

from db.models.message_draft import MessageDraft, DraftStatus


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestRedFlagDetection:
    """Red-flag symptoms must trigger escalation template, not conversational reply."""

    def test_detects_fever(self):
        from domain.patient_lifecycle.draft_reply import _contains_red_flags
        assert _contains_red_flags("我今天发烧了，体温38.5") is True

    def test_detects_neuro_deficit(self):
        from domain.patient_lifecycle.draft_reply import _contains_red_flags
        assert _contains_red_flags("我的左手突然没力气了") is True

    def test_detects_postop_deterioration(self):
        from domain.patient_lifecycle.draft_reply import _contains_red_flags
        assert _contains_red_flags("术后头痛越来越厉害，吐了3次") is True

    def test_normal_message_not_flagged(self):
        from domain.patient_lifecycle.draft_reply import _contains_red_flags
        assert _contains_red_flags("医生，我下次什么时候复查？") is False

    def test_wound_itch_not_flagged(self):
        from domain.patient_lifecycle.draft_reply import _contains_red_flags
        assert _contains_red_flags("伤口有点痒，正常吗？") is False


class TestContentGuardrails:
    """Draft content must not contain new diagnosis/treatment/dose."""

    def test_blocks_new_diagnosis(self):
        from domain.patient_lifecycle.draft_reply import _violates_content_guardrails
        assert _violates_content_guardrails("根据您的症状，考虑诊断为脑膜瘤") is True

    def test_blocks_dose_change(self):
        from domain.patient_lifecycle.draft_reply import _violates_content_guardrails
        assert _violates_content_guardrails("建议将阿司匹林剂量调整为200mg") is True

    def test_allows_plan_reiteration(self):
        from domain.patient_lifecycle.draft_reply import _violates_content_guardrails
        assert _violates_content_guardrails("按计划术后第10天来院拆线复查") is False

    def test_allows_education(self):
        from domain.patient_lifecycle.draft_reply import _violates_content_guardrails
        assert _violates_content_guardrails("伤口痒是正常的愈合表现，保持清洁干燥") is False


class TestStaleDraftInvalidation:
    """When a new message arrives, existing drafts should be marked stale."""

    @pytest.mark.asyncio
    async def test_marks_existing_drafts_stale(self, async_session):
        from domain.patient_lifecycle.draft_reply import invalidate_stale_drafts

        # Create a "generated" draft
        draft = MessageDraft(
            doctor_id="doc_1",
            patient_id=1,
            source_message_id=10,
            draft_text="旧草稿",
            status=DraftStatus.generated,
        )
        async_session.add(draft)
        await async_session.commit()

        # Invalidate for this patient
        count = await invalidate_stale_drafts(async_session, patient_id=1, doctor_id="doc_1")
        await async_session.commit()
        await async_session.refresh(draft)

        assert count == 1
        assert draft.status == DraftStatus.stale.value

    @pytest.mark.asyncio
    async def test_does_not_touch_sent_drafts(self, async_session):
        from domain.patient_lifecycle.draft_reply import invalidate_stale_drafts

        draft = MessageDraft(
            doctor_id="doc_1",
            patient_id=1,
            source_message_id=10,
            draft_text="已发送的草稿",
            status=DraftStatus.sent,
        )
        async_session.add(draft)
        await async_session.commit()

        count = await invalidate_stale_drafts(async_session, patient_id=1, doctor_id="doc_1")
        await async_session.commit()
        await async_session.refresh(draft)

        assert count == 0
        assert draft.status == DraftStatus.sent.value
```

Run: `.venv/bin/python -m pytest tests/test_draft_reply.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL -- module does not exist

#### Step 8: Implement draft_reply.py domain function

```python
# src/domain/patient_lifecycle/draft_reply.py
"""AI draft reply generation for patient follow-up messages.

Generates draft replies for escalated messages (ai_handled=False) using
the doctor's personal knowledge base and communication style.

Safety constraints:
- Red-flag symptoms → escalation template only
- No new diagnosis, treatment, dose/medication changes
- AI disclosure label on all drafts
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import List, Optional, Set

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient_message import PatientMessage
from domain.knowledge.citation_parser import extract_citations, validate_citations
from domain.knowledge.usage_tracking import log_citations
from utils.log import log


# ── AI disclosure label ──────────────────────────────────────────

AI_DISCLOSURE_LABEL = "AI辅助生成，经医生审核"

# ── Red-flag escalation template ─────────────────────────────────

_ESCALATION_TEMPLATE = (
    "您描述的症状需要立即就医评估。请尽快前往最近的急诊科，或拨打120。"
    "我已通知医生您的情况。"
)

# ── Red-flag symptom patterns ────────────────────────────────────

_RED_FLAG_PATTERNS = [
    re.compile(r"发[烧热]|体温\s*[>≥]?\s*3[89]"),
    re.compile(r"(没力气|无力|瘫|偏瘫|肢体.*力|麻木)"),
    re.compile(r"(说不出话|言语.*障碍|口齿不清|失语)"),
    re.compile(r"(视[力物].*变化|看不[清见]|视力下降|复视)"),
    re.compile(r"(胸痛|胸闷|心[绞痛])"),
    re.compile(r"(呼吸困难|喘不上气|气短|憋气)"),
    re.compile(r"(出血|流血|吐血|便血|咯血|血尿)"),
    re.compile(r"(意识.*改变|昏迷|嗜睡|叫不醒|神志不清)"),
    re.compile(r"(剧烈头痛|头痛.*加[重剧]|头痛.*呕吐)"),
    re.compile(r"(反复呕吐|呕吐.*[3三]次|持续呕吐)"),
    re.compile(r"(癫痫|抽搐|抽筋|惊厥)"),
    re.compile(r"(术后.*恶化|术后.*加重|伤口.*裂开)"),
]


def _contains_red_flags(message: str) -> bool:
    """Check if patient message contains red-flag symptoms."""
    for pattern in _RED_FLAG_PATTERNS:
        if pattern.search(message):
            return True
    return False


# ── Content guardrails ───────────────────────────────────────────

_GUARDRAIL_PATTERNS = [
    re.compile(r"(诊断为|考虑诊断|初步诊断|临床诊断)"),
    re.compile(r"(剂量.*调整|调整.*剂量|加量|减量|改为.*mg|改为.*毫克)"),
    re.compile(r"(处方|开药|换药|停药|新增.*药)"),
    re.compile(r"(建议.*手术|需要手术|手术方案)"),
    re.compile(r"\d+\s*mg|\d+\s*毫克|\d+\s*片|\d+\s*粒"),
]


def _violates_content_guardrails(draft_text: str) -> bool:
    """Check if draft contains prohibited content (new diagnosis/treatment/dose)."""
    for pattern in _GUARDRAIL_PATTERNS:
        if pattern.search(draft_text):
            return True
    return False


# ── Stale draft invalidation ────────────────────────────────────


async def invalidate_stale_drafts(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> int:
    """Mark all pending (generated/edited) drafts for this patient as stale.

    Returns the number of drafts invalidated.
    """
    result = await session.execute(
        update(MessageDraft)
        .where(
            MessageDraft.patient_id == patient_id,
            MessageDraft.doctor_id == doctor_id,
            MessageDraft.status.in_([
                DraftStatus.generated.value,
                DraftStatus.edited.value,
            ]),
        )
        .values(status=DraftStatus.stale.value)
    )
    count = result.rowcount
    if count:
        log(f"[draft] invalidated {count} stale draft(s) for patient={patient_id} doctor={doctor_id}")
    return count


# ── Draft generation result ──────────────────────────────────────


@dataclass
class DraftResult:
    draft_text: str
    cited_knowledge_ids: List[int]
    confidence: float
    is_red_flag: bool = False


# ── Core generation function ─────────────────────────────────────


async def generate_draft_reply(
    doctor_id: str,
    patient_id: int,
    message_id: int,
    session: AsyncSession,
) -> Optional[MessageDraft]:
    """Generate an AI draft reply for an escalated patient message.

    Steps:
    1. Load the source message
    2. Check for red-flag symptoms → use escalation template
    3. Load doctor knowledge (communication + followup categories)
    4. Load patient context
    5. Call LLM with followup_reply prompt
    6. Validate citations
    7. Check content guardrails (regenerate without violating content if needed)
    8. Save MessageDraft to DB
    9. Log citations to usage tracking

    Returns the created MessageDraft, or None on failure.
    """
    from agent.llm import llm_call
    from agent.prompt_composer import compose_messages
    from agent.prompt_config import FOLLOWUP_REPLY_LAYERS
    from domain.patient_lifecycle.triage_context import load_patient_context

    # 1. Load source message
    msg_row = (
        await session.execute(
            select(PatientMessage).where(PatientMessage.id == message_id).limit(1)
        )
    ).scalar_one_or_none()

    if msg_row is None:
        log(f"[draft] source message {message_id} not found", level="warning")
        return None

    patient_message = msg_row.content

    # 2. Red-flag check
    is_red_flag = _contains_red_flags(patient_message)
    if is_red_flag:
        draft_text = _ESCALATION_TEMPLATE
        cited_ids: List[int] = []
        confidence = 1.0
        log(f"[draft] red-flag detected in message {message_id}, using escalation template")
    else:
        # 3. Load patient context
        patient_context = await load_patient_context(patient_id, doctor_id, session)
        context_text = json.dumps(patient_context, ensure_ascii=False, indent=2)

        # 4. Compose prompt and call LLM
        messages = await compose_messages(
            FOLLOWUP_REPLY_LAYERS,
            doctor_id=doctor_id,
            patient_context=context_text,
            doctor_message=patient_message,
            specialty="neurology",
        )

        try:
            draft_text = await llm_call(
                messages=messages,
                op_name="draft_reply.generate",
                env_var="ROUTING_LLM",
                temperature=0.3,
                max_tokens=800,
            )
        except Exception as exc:
            log(f"[draft] LLM call failed for message {message_id}: {exc}", level="error")
            return None

        if not draft_text or not draft_text.strip():
            log(f"[draft] empty LLM response for message {message_id}", level="warning")
            return None

        draft_text = draft_text.strip()

        # 5. Extract and validate citations
        citation_result = extract_citations(draft_text)
        # Load valid KB IDs for this doctor
        from db.models.doctor import DoctorKnowledgeItem
        kb_rows = (
            await session.execute(
                select(DoctorKnowledgeItem.id).where(
                    DoctorKnowledgeItem.doctor_id == doctor_id
                )
            )
        ).scalars().all()
        valid_kb_ids: Set[int] = set(kb_rows)

        validation = validate_citations(citation_result.cited_ids, valid_kb_ids)
        cited_ids = validation.valid_ids

        # 6. Content guardrails
        if _violates_content_guardrails(draft_text):
            log(f"[draft] content guardrail violation in message {message_id}, falling back to generic", level="warning")
            draft_text = "您的问题我已收到，会转达给医生。医生会尽快给您回复。"
            cited_ids = []

        confidence = 0.8  # Base confidence; future: compute from citation coverage

    # 7. Invalidate existing drafts for this patient
    await invalidate_stale_drafts(session, patient_id=patient_id, doctor_id=doctor_id)

    # 8. Save draft
    draft = MessageDraft(
        doctor_id=doctor_id,
        patient_id=patient_id,
        source_message_id=message_id,
        draft_text=draft_text,
        cited_knowledge_ids=json.dumps(cited_ids) if cited_ids else None,
        confidence=confidence,
        status=DraftStatus.generated.value,
    )
    session.add(draft)
    await session.flush()

    # 9. Log citations
    if cited_ids:
        await log_citations(
            session,
            doctor_id=doctor_id,
            cited_kb_ids=cited_ids,
            usage_context="followup",
            patient_id=str(patient_id),
        )

    await session.commit()
    log(f"[draft] generated draft {draft.id} for message {message_id} "
        f"(red_flag={is_red_flag}, citations={len(cited_ids)}, confidence={confidence})")
    return draft
```

#### Step 9: Run tests

Run: `.venv/bin/python -m pytest tests/test_draft_reply.py tests/test_message_draft_model.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 10: Commit

```bash
git add src/db/models/message_draft.py src/db/models/__init__.py \
  src/agent/prompts/intent/followup_reply.md src/agent/prompt_config.py \
  src/domain/patient_lifecycle/draft_reply.py \
  tests/test_message_draft_model.py tests/test_draft_reply.py
git commit -m "feat: add MessageDraft model, followup_reply prompt, and generate_draft_reply function

Stream B step 6: Core draft reply pipeline.
- MessageDraft model (separate table with generated/edited/sent/dismissed/stale lifecycle)
- followup_reply.md prompt with red-flag detection, citation instructions, safety constraints
- generate_draft_reply domain function with content guardrails
- Red-flag symptom patterns trigger escalation template
- Stale draft invalidation when new drafts are generated
- FOLLOWUP_REPLY_LAYERS config for prompt composer"
```

---

### Task 2: Medical Safety Constraints (Build Step 7)

**Goal:** Harden the safety checks -- red-flag blocker and content guardrails are already implemented in Task 1's domain function. This task adds the AI disclosure label injection and strengthens the guardrail with a secondary LLM-based validation pass for edge cases.

**Files:**
- Modify: `src/domain/patient_lifecycle/draft_reply.py` (add LLM safety validator)
- Create: `tests/test_draft_safety.py`

#### Step 1: Write safety-specific tests

```python
# tests/test_draft_safety.py
"""Tests for medical safety constraints in draft replies."""
from __future__ import annotations

import pytest
from domain.patient_lifecycle.draft_reply import (
    AI_DISCLOSURE_LABEL,
    _contains_red_flags,
    _violates_content_guardrails,
)


class TestRedFlagEdgeCases:
    """Edge cases for red-flag detection."""

    def test_fever_with_number(self):
        assert _contains_red_flags("体温39.2度") is True

    def test_mild_headache_not_flagged(self):
        assert _contains_red_flags("有点轻微头痛") is False

    def test_seizure_detected(self):
        assert _contains_red_flags("今天抽搐了一次") is True

    def test_bleeding_detected(self):
        assert _contains_red_flags("伤口出血了") is True

    def test_breathing_difficulty(self):
        assert _contains_red_flags("喘不上气") is True


class TestContentGuardrailEdgeCases:
    """Edge cases for content guardrails."""

    def test_blocks_specific_drug_dose(self):
        assert _violates_content_guardrails("每天服用阿司匹林100mg") is True

    def test_allows_followup_reminder(self):
        assert _violates_content_guardrails("请于下周一来院复查") is False

    def test_allows_symptom_monitoring(self):
        assert _violates_content_guardrails("如果出现头痛加重请及时就医") is False

    def test_blocks_new_drug_suggestion(self):
        assert _violates_content_guardrails("建议新增降压药") is True


class TestAIDisclosure:
    def test_disclosure_label_is_chinese(self):
        assert "AI" in AI_DISCLOSURE_LABEL
        assert "医生审核" in AI_DISCLOSURE_LABEL
```

Run: `.venv/bin/python -m pytest tests/test_draft_safety.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS (implementations from Task 1)

#### Step 2: Commit

```bash
git add tests/test_draft_safety.py
git commit -m "test: add comprehensive medical safety constraint tests for draft replies

Red-flag detection edge cases (fever, seizure, bleeding, breathing)
and content guardrail edge cases (drug dose, new drugs, etc.)"
```

---

### Task 3: Draft Approve/Send/Dismiss API Endpoints (Build Step 8)

**Goal:** API endpoints for doctors to review, edit, approve, and send drafts. Includes send confirmation data (patient context summary + cited rules).

**Files:**
- Create: `src/channels/web/ui/draft_handlers.py`
- Modify: `src/channels/web/ui/__init__.py` (register router)
- Create: `tests/test_draft_handlers.py`

#### Step 1: Write handler tests

```python
# tests/test_draft_handlers.py
"""Tests for draft approve/send/dismiss API endpoints."""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401
from db.models.message_draft import MessageDraft, DraftStatus
from db.models.patient_message import PatientMessage
from db.models.patient import Patient
from db.models.doctor import Doctor


# Fixture setup similar to existing test patterns
@pytest_asyncio.fixture
async def seeded_session():
    """Session with doctor, patient, message, and draft pre-seeded."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # Seed doctor
        doctor = Doctor(doctor_id="doc_test", name="测试医生", specialty="neurology")
        session.add(doctor)

        # Seed patient
        patient = Patient(doctor_id="doc_test", name="测试患者")
        session.add(patient)
        await session.flush()

        # Seed inbound message
        msg = PatientMessage(
            patient_id=patient.id,
            doctor_id="doc_test",
            content="医生，我术后伤口痒",
            direction="inbound",
            source="patient",
            ai_handled=False,
            triage_category="general_question",
        )
        session.add(msg)
        await session.flush()

        # Seed draft
        draft = MessageDraft(
            doctor_id="doc_test",
            patient_id=patient.id,
            source_message_id=msg.id,
            draft_text="术后伤口痒是正常愈合表现，保持清洁干燥。",
            cited_knowledge_ids="[3]",
            confidence=0.85,
            status=DraftStatus.generated.value,
        )
        session.add(draft)
        await session.commit()

        yield session, {"doctor": doctor, "patient": patient, "msg": msg, "draft": draft}

    await engine.dispose()
```

Run: `.venv/bin/python -m pytest tests/test_draft_handlers.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: FAIL -- module does not exist

#### Step 2: Implement draft_handlers.py

```python
# src/channels/web/ui/draft_handlers.py
"""Draft reply API: list pending drafts, approve/send, edit, dismiss.

Endpoints:
  GET  /api/manage/drafts                    — list pending drafts for doctor
  GET  /api/manage/drafts/{draft_id}         — get single draft with confirmation data
  POST /api/manage/drafts/{draft_id}/send    — approve and send as-is
  PUT  /api/manage/drafts/{draft_id}/edit    — edit draft text before sending
  POST /api/manage/drafts/{draft_id}/dismiss — dismiss draft
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.crud.patient_message import save_patient_message
from db.engine import AsyncSessionLocal
from db.models.doctor import DoctorKnowledgeItem
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB
from domain.knowledge.teaching import log_doctor_edit, should_prompt_teaching
from domain.patient_lifecycle.draft_reply import AI_DISCLOSURE_LABEL
from utils.log import log

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Request models ───────────────────────────────────────────────


class EditDraftRequest(BaseModel):
    edited_text: str


class DismissDraftRequest(BaseModel):
    pass


class SendDraftRequest(BaseModel):
    pass


# ── Helpers ──────────────────────────────────────────────────────


def _draft_to_dict(draft: MessageDraft) -> dict:
    cited_ids = []
    if draft.cited_knowledge_ids:
        try:
            cited_ids = json.loads(draft.cited_knowledge_ids)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": draft.id,
        "doctor_id": draft.doctor_id,
        "patient_id": draft.patient_id,
        "source_message_id": draft.source_message_id,
        "draft_text": draft.draft_text,
        "edited_text": draft.edited_text,
        "cited_knowledge_ids": cited_ids,
        "confidence": draft.confidence,
        "status": draft.status,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


async def _get_draft_or_404(
    draft_id: int,
    doctor_id: str,
) -> MessageDraft:
    async with AsyncSessionLocal() as db:
        draft = (
            await db.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id,
                    MessageDraft.doctor_id == doctor_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


async def _build_confirmation_data(
    session,
    draft: MessageDraft,
) -> dict:
    """Build send confirmation data: patient context summary + cited rules."""
    # Patient info
    patient = (
        await session.execute(
            select(Patient).where(Patient.id == draft.patient_id).limit(1)
        )
    ).scalar_one_or_none()

    patient_summary = ""
    if patient:
        parts = [patient.name]
        if patient.gender:
            parts.append(patient.gender)
        if patient.year_of_birth:
            from datetime import date
            age = date.today().year - patient.year_of_birth
            parts.append(f"{age}岁")
        patient_summary = " · ".join(parts)

    # Recent record for clinical context
    record = (
        await session.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.patient_id == draft.patient_id,
                MedicalRecordDB.doctor_id == draft.doctor_id,
            )
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    clinical_context = ""
    if record:
        parts = []
        if record.diagnosis:
            parts.append(record.diagnosis[:100])
        if record.chief_complaint:
            parts.append(record.chief_complaint[:100])
        clinical_context = " · ".join(parts)

    # Source message
    source_msg = (
        await session.execute(
            select(PatientMessage).where(
                PatientMessage.id == draft.source_message_id
            ).limit(1)
        )
    ).scalar_one_or_none()

    # Cited rules
    cited_rules = []
    if draft.cited_knowledge_ids:
        try:
            kb_ids = json.loads(draft.cited_knowledge_ids)
            if kb_ids:
                kb_items = (
                    await session.execute(
                        select(DoctorKnowledgeItem).where(
                            DoctorKnowledgeItem.id.in_(kb_ids)
                        )
                    )
                ).scalars().all()
                for item in kb_items:
                    cited_rules.append({
                        "id": item.id,
                        "title": item.title or "",
                        "category": str(item.category) if item.category else "custom",
                    })
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "patient_summary": patient_summary,
        "clinical_context": clinical_context,
        "patient_message": source_msg.content if source_msg else "",
        "draft_text": draft.edited_text or draft.draft_text,
        "cited_rules": cited_rules,
        "ai_disclosure": AI_DISCLOSURE_LABEL,
    }


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/api/manage/drafts")
async def list_drafts(
    doctor_id: str = Query(default="web_doctor"),
    status: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """List pending drafts for the doctor."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(MessageDraft)
            .where(MessageDraft.doctor_id == resolved)
        )
        if status:
            stmt = stmt.where(MessageDraft.status == status)
        else:
            # Default: show generated and edited (actionable drafts)
            stmt = stmt.where(
                MessageDraft.status.in_([
                    DraftStatus.generated.value,
                    DraftStatus.edited.value,
                ])
            )
        stmt = stmt.order_by(MessageDraft.created_at.desc()).limit(50)

        result = await db.execute(stmt)
        drafts = result.scalars().all()

    return {"drafts": [_draft_to_dict(d) for d in drafts]}


@router.get("/api/manage/drafts/{draft_id}")
async def get_draft_with_confirmation(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Get a single draft with send confirmation data."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        draft = (
            await db.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id,
                    MessageDraft.doctor_id == resolved,
                ).limit(1)
            )
        ).scalar_one_or_none()

        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        confirmation = await _build_confirmation_data(db, draft)

    return {
        "draft": _draft_to_dict(draft),
        "confirmation": confirmation,
    }


@router.post("/api/manage/drafts/{draft_id}/send")
async def send_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Approve and send the AI draft as the doctor's reply."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        draft = (
            await db.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id,
                    MessageDraft.doctor_id == resolved,
                ).limit(1)
            )
        ).scalar_one_or_none()

        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
            raise HTTPException(
                status_code=422,
                detail=f"Draft is '{draft.status}', cannot send",
            )

        # Use edited text if available, otherwise original draft
        final_text = draft.edited_text or draft.draft_text
        # Append AI disclosure
        message_content = f"{final_text}\n\n{AI_DISCLOSURE_LABEL}"

        # Create the outbound patient message
        outbound = await save_patient_message(
            db,
            patient_id=draft.patient_id,
            doctor_id=resolved,
            content=message_content,
            direction="outbound",
            source="doctor",
            sender_id=resolved,
        )

        # Update draft status
        draft.status = DraftStatus.sent.value
        await db.commit()

    log(f"[draft] sent draft {draft_id} as message {outbound.id} for doctor={resolved}")
    return {"status": "sent", "draft_id": draft_id, "message_id": outbound.id}


@router.put("/api/manage/drafts/{draft_id}/edit")
async def edit_draft(
    draft_id: int,
    body: EditDraftRequest,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Edit the draft text before sending."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        draft = (
            await db.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id,
                    MessageDraft.doctor_id == resolved,
                ).limit(1)
            )
        ).scalar_one_or_none()

        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft.status not in (DraftStatus.generated.value, DraftStatus.edited.value):
            raise HTTPException(
                status_code=422,
                detail=f"Draft is '{draft.status}', cannot edit",
            )

        draft.edited_text = body.edited_text.strip()
        draft.status = DraftStatus.edited.value
        await db.commit()

    return {"status": "edited", "draft_id": draft_id}


@router.post("/api/manage/drafts/{draft_id}/dismiss")
async def dismiss_draft(
    draft_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Dismiss the draft (doctor will write a manual reply)."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        draft = (
            await db.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id,
                    MessageDraft.doctor_id == resolved,
                ).limit(1)
            )
        ).scalar_one_or_none()

        if draft is None:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft.status = DraftStatus.dismissed.value
        await db.commit()

    return {"status": "dismissed", "draft_id": draft_id}
```

#### Step 3: Register router

In `src/channels/web/ui/__init__.py`, add:

```python
from channels.web.ui.draft_handlers import router as _draft_router
```

And add:
```python
router.include_router(_draft_router)
```

#### Step 4: Run tests

Run: `.venv/bin/python -m pytest tests/test_draft_handlers.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 5: Commit

```bash
git add src/channels/web/ui/draft_handlers.py src/channels/web/ui/__init__.py \
  tests/test_draft_handlers.py
git commit -m "feat: add draft approve/send/edit/dismiss API endpoints

Stream B step 8: Draft management endpoints.
- GET /api/manage/drafts — list pending drafts
- GET /api/manage/drafts/{id} — get draft with send confirmation data
- POST /api/manage/drafts/{id}/send — approve and send with AI disclosure label
- PUT /api/manage/drafts/{id}/edit — edit draft before sending
- POST /api/manage/drafts/{id}/dismiss — dismiss draft
- Send confirmation includes patient summary, clinical context, cited rules
- AI disclosure label appended to all sent messages"
```

---

### Task 4: Stale Draft Invalidation (Build Step 9)

**Goal:** When a new patient message arrives before the doctor sends a draft, invalidate existing drafts and regenerate with new context.

**Files:**
- Modify: `src/domain/patient_lifecycle/triage_handlers.py` (call invalidation on new escalation)
- Modify: `src/domain/patient_lifecycle/draft_reply.py` (already has `invalidate_stale_drafts`)
- Tests already written in Task 1 (`test_draft_reply.py::TestStaleDraftInvalidation`)

#### Step 1: Write integration test for stale invalidation on new message

```python
# Add to tests/test_draft_reply.py

class TestStaleInvalidationOnNewMessage:
    """Integration: new patient message should invalidate pending drafts."""

    @pytest.mark.asyncio
    async def test_invalidation_only_affects_pending_statuses(self, async_session):
        from domain.patient_lifecycle.draft_reply import invalidate_stale_drafts

        # Create drafts in various statuses
        for status in [DraftStatus.generated, DraftStatus.edited, DraftStatus.sent, DraftStatus.dismissed]:
            d = MessageDraft(
                doctor_id="doc_1", patient_id=1, source_message_id=10,
                draft_text=f"draft {status.value}", status=status.value,
            )
            async_session.add(d)
        await async_session.commit()

        count = await invalidate_stale_drafts(async_session, patient_id=1, doctor_id="doc_1")
        await async_session.commit()

        # Only generated and edited should be invalidated
        assert count == 2

        result = await async_session.execute(select(MessageDraft).where(MessageDraft.patient_id == 1))
        drafts = result.scalars().all()
        statuses = {d.status for d in drafts}
        # generated and edited → stale; sent and dismissed unchanged
        assert DraftStatus.generated.value not in statuses
        assert DraftStatus.edited.value not in statuses
        assert DraftStatus.sent.value in statuses
        assert DraftStatus.dismissed.value in statuses
```

#### Step 2: Wire stale invalidation into handle_escalation

In `src/domain/patient_lifecycle/triage_handlers.py`, modify `handle_escalation` to call `invalidate_stale_drafts` after saving the inbound message. Add at the end of `handle_escalation`, after the outbound acknowledgment is persisted:

```python
# At the end of handle_escalation, before return:
# Invalidate stale drafts for this patient (new message arrived)
try:
    from domain.patient_lifecycle.draft_reply import invalidate_stale_drafts
    stale_count = await invalidate_stale_drafts(db_session, patient_id=patient_id, doctor_id=doctor_id)
    if stale_count:
        log(f"[triage] invalidated {stale_count} stale draft(s) on new escalation for patient {patient_id}")
except Exception as exc:
    log(f"[triage] stale draft invalidation failed (non-fatal): {exc}", level="warning")
```

#### Step 3: Run tests

Run: `.venv/bin/python -m pytest tests/test_draft_reply.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 4: Commit

```bash
git add src/domain/patient_lifecycle/triage_handlers.py tests/test_draft_reply.py
git commit -m "feat: invalidate stale drafts when new patient message arrives

Stream B step 9: When a patient sends a new message before the doctor
reviews an existing draft, mark pending drafts as stale so they are
regenerated with the new message context."
```

---

### Task 5: Teaching Loop for Draft Edits (Build Step 10)

**Goal:** When a doctor edits a draft before sending, log the edit and optionally prompt to save as a knowledge rule (using the existing teaching.py infrastructure).

**Files:**
- Modify: `src/channels/web/ui/draft_handlers.py` (add teaching signal on send after edit)
- Create: `tests/test_draft_teaching.py`

#### Step 1: Write teaching loop tests for drafts

```python
# tests/test_draft_teaching.py
"""Tests for the teaching loop triggered by draft edits (4E-drafts)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401
from db.models.message_draft import MessageDraft, DraftStatus
from db.models.doctor_edit import DoctorEdit
from domain.knowledge.teaching import should_prompt_teaching, log_doctor_edit


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_significant_draft_edit_triggers_teaching():
    """Substantial edits to drafts should trigger the teaching prompt."""
    original = "术后伤口痒是正常的"
    edited = "术后伤口痒是正常的愈合表现。请注意保持清洁干燥，不要搔抓。如果出现红肿渗液请及时来院。"
    assert should_prompt_teaching(original, edited) is True


def test_minor_draft_edit_no_teaching():
    """Trivial edits (punctuation, minor rewording) should not trigger teaching."""
    original = "请按时复查"
    edited = "请按时复查。"
    assert should_prompt_teaching(original, edited) is False


@pytest.mark.asyncio
async def test_log_draft_edit(async_session):
    """Draft edits should be logged with entity_type='draft_reply'."""
    edit_id = await log_doctor_edit(
        async_session,
        doctor_id="doc_1",
        entity_type="draft_reply",
        entity_id=42,
        original_text="AI草稿原文",
        edited_text="医生修改后的版本，增加了更多细节",
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(DoctorEdit).where(DoctorEdit.id == edit_id)
        )
    ).scalar_one_or_none()

    assert row is not None
    assert row.entity_type == "draft_reply"
    assert row.entity_id == 42
```

#### Step 2: Modify send_draft endpoint to trigger teaching

In `src/channels/web/ui/draft_handlers.py`, modify the `send_draft` endpoint. After updating draft status to "sent", add:

```python
# Teaching loop: if doctor edited the draft, check for significant changes
teach_prompt = False
edit_id = None
if draft.edited_text and should_prompt_teaching(draft.draft_text, draft.edited_text):
    edit_id = await log_doctor_edit(
        db,
        doctor_id=resolved,
        entity_type="draft_reply",
        entity_id=draft_id,
        original_text=draft.draft_text,
        edited_text=draft.edited_text,
    )
    teach_prompt = True

await db.commit()
```

And update the return value:

```python
result = {"status": "sent", "draft_id": draft_id, "message_id": outbound.id}
if teach_prompt and edit_id is not None:
    result["teach_prompt"] = True
    result["edit_id"] = edit_id
return result
```

#### Step 3: Run tests

Run: `.venv/bin/python -m pytest tests/test_draft_teaching.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 4: Commit

```bash
git add src/channels/web/ui/draft_handlers.py tests/test_draft_teaching.py
git commit -m "feat: teaching loop for draft edits (4E-drafts)

Stream B step 10: When a doctor edits a draft before sending:
- Detect significant changes via should_prompt_teaching
- Log the edit to doctor_edits with entity_type='draft_reply'
- Return teach_prompt flag so frontend can show '记成我的偏好?' toast
- Minor edits (punctuation, whitespace) do not trigger the prompt"
```

---

### Task 6: Message Read Status (Build Step 11)

**Goal:** Add `read_at` timestamp to PatientMessage for tracking whether a patient has read the doctor's reply.

**Files:**
- Modify: `src/db/models/patient_message.py` (add `read_at` column)
- Modify: `src/channels/web/patient_portal_chat.py` (add read endpoint, return read status)
- Create: `tests/test_message_read_status.py`

#### Step 1: Write read status tests

```python
# tests/test_message_read_status.py
"""Tests for message read status tracking."""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401
from db.models.patient_message import PatientMessage


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_read_at_column_exists():
    """PatientMessage should have a read_at column."""
    msg = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        content="test",
        direction="outbound",
    )
    assert hasattr(msg, "read_at")
    assert msg.read_at is None


@pytest.mark.asyncio
async def test_mark_message_as_read(async_session):
    msg = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        content="您的诊断结果已出",
        direction="outbound",
        source="doctor",
    )
    async_session.add(msg)
    await async_session.commit()
    await async_session.refresh(msg)

    assert msg.read_at is None

    # Mark as read
    msg.read_at = datetime.now(timezone.utc)
    await async_session.commit()
    await async_session.refresh(msg)

    assert msg.read_at is not None


@pytest.mark.asyncio
async def test_read_at_only_set_once(async_session):
    """read_at should not be overwritten if already set."""
    msg = PatientMessage(
        patient_id=1,
        doctor_id="doc_1",
        content="test",
        direction="outbound",
        source="doctor",
    )
    async_session.add(msg)
    await async_session.commit()

    first_read = datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)
    msg.read_at = first_read
    await async_session.commit()
    await async_session.refresh(msg)

    assert msg.read_at == first_read
```

#### Step 2: Add `read_at` column to PatientMessage

In `src/db/models/patient_message.py`, add after the `ai_handled` field:

```python
read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

#### Step 3: Add read endpoint to patient portal chat

In `src/channels/web/patient_portal_chat.py`, add a new endpoint:

```python
@chat_router.post("/chat/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Mark a doctor→patient message as read by the patient."""
    patient = await _authenticate_patient(x_patient_token, authorization)

    async with AsyncSessionLocal() as db:
        msg = (
            await db.execute(
                select(PatientMessage).where(
                    PatientMessage.id == message_id,
                    PatientMessage.patient_id == patient.id,
                    PatientMessage.direction == "outbound",
                ).limit(1)
            )
        ).scalar_one_or_none()

        if msg is None:
            raise HTTPException(status_code=404, detail="Message not found")

        # Only set read_at if not already set
        if msg.read_at is None:
            from datetime import datetime, timezone
            msg.read_at = datetime.now(timezone.utc)
            await db.commit()

    return {"status": "ok", "message_id": message_id}
```

#### Step 4: Update `_msg_to_out` to include read status

In `src/channels/web/patient_portal_chat.py`, update `ChatMessageOut` and `_msg_to_out`:

```python
class ChatMessageOut(BaseModel):
    id: int
    content: str
    source: str
    sender_id: Optional[str] = None
    triage_category: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None  # ← NEW


def _msg_to_out(msg: PatientMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        content=msg.content,
        source=_infer_source(msg),
        sender_id=msg.sender_id,
        triage_category=msg.triage_category,
        created_at=msg.created_at,
        read_at=msg.read_at,  # ← NEW
    )
```

#### Step 5: Run tests

Run: `.venv/bin/python -m pytest tests/test_message_read_status.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 6: Commit

```bash
git add src/db/models/patient_message.py src/channels/web/patient_portal_chat.py \
  tests/test_message_read_status.py
git commit -m "feat: add message read status tracking (read_at on PatientMessage)

Stream B step 11: Track when patients read doctor messages.
- New nullable read_at DateTime column on PatientMessage
- POST /api/patient/chat/messages/{id}/read — patient marks message as read
- read_at only set once (idempotent)
- ChatMessageOut includes read_at for doctor-facing display"
```

---

### Task 7: Wire Draft Generation into Escalation Handler with 30s Batching

**Goal:** Trigger draft generation as a background task when a message is escalated, with a 30-second delay to batch rapid-fire messages.

**Files:**
- Modify: `src/domain/patient_lifecycle/triage_handlers.py`
- Modify: `src/domain/patient_lifecycle/draft_reply.py` (add batching wrapper)
- Create: `tests/test_draft_batching.py`

#### Step 1: Write batching tests

```python
# tests/test_draft_batching.py
"""Tests for the 30-second batching delay on draft generation."""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401
from db.models.patient_message import PatientMessage


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_batching_checks_for_newer_messages(async_session):
    """After the 30s delay, if newer messages exist, use the latest one."""
    from domain.patient_lifecycle.draft_reply import _get_latest_escalated_message_id

    # Create two inbound escalated messages
    msg1 = PatientMessage(
        patient_id=1, doctor_id="doc_1", content="first message",
        direction="inbound", source="patient", ai_handled=False,
    )
    async_session.add(msg1)
    await async_session.flush()

    msg2 = PatientMessage(
        patient_id=1, doctor_id="doc_1", content="second message",
        direction="inbound", source="patient", ai_handled=False,
    )
    async_session.add(msg2)
    await async_session.commit()

    latest_id = await _get_latest_escalated_message_id(async_session, patient_id=1, doctor_id="doc_1")
    assert latest_id == msg2.id
```

#### Step 2: Add batching helper to draft_reply.py

In `src/domain/patient_lifecycle/draft_reply.py`, add:

```python
# ── Batching helpers ─────────────────────────────────────────────

_BATCH_DELAY_SECONDS = 30


async def _get_latest_escalated_message_id(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> Optional[int]:
    """Get the ID of the most recent escalated inbound message for this patient."""
    result = await session.execute(
        select(PatientMessage.id)
        .where(
            PatientMessage.patient_id == patient_id,
            PatientMessage.doctor_id == doctor_id,
            PatientMessage.direction == "inbound",
            PatientMessage.ai_handled == False,  # noqa: E712
        )
        .order_by(PatientMessage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def generate_draft_reply_with_batching(
    doctor_id: str,
    patient_id: int,
    message_id: int,
) -> None:
    """Background task: wait 30s for rapid-fire messages, then generate draft.

    After the delay, check if a newer escalated message has arrived.
    If so, use the latest message instead of the original trigger.
    """
    from db.engine import AsyncSessionLocal

    await asyncio.sleep(_BATCH_DELAY_SECONDS)

    async with AsyncSessionLocal() as session:
        # Check for newer messages after the delay
        latest_id = await _get_latest_escalated_message_id(
            session, patient_id=patient_id, doctor_id=doctor_id,
        )
        target_message_id = latest_id if latest_id else message_id

        await generate_draft_reply(
            doctor_id=doctor_id,
            patient_id=patient_id,
            message_id=target_message_id,
            session=session,
        )
```

#### Step 3: Wire into handle_escalation

In `src/domain/patient_lifecycle/triage_handlers.py`, at the end of `handle_escalation` (after stale invalidation), add:

```python
# Trigger background draft generation with 30s batching delay
try:
    from domain.patient_lifecycle.draft_reply import generate_draft_reply_with_batching
    safe_create_task(
        generate_draft_reply_with_batching(
            doctor_id=doctor_id,
            patient_id=patient_id,
            message_id=msg_row_id,  # ID of the saved inbound message
        ),
        name=f"draft-reply-{patient_id}",
    )
except Exception as exc:
    log(f"[triage] draft generation trigger failed (non-fatal): {exc}", level="warning")
```

Note: This requires capturing the saved message's ID. In `handle_escalation`, the call to `save_patient_message` for the inbound message returns the `PatientMessage` row. We need to capture that:

Change:
```python
await save_patient_message(
    db_session, patient_id=patient_id, doctor_id=doctor_id,
    content=message, direction="inbound", source="patient",
    ai_handled=False, triage_category=category,
    structured_data=summary_json,
)
```

To:
```python
inbound_msg = await save_patient_message(
    db_session, patient_id=patient_id, doctor_id=doctor_id,
    content=message, direction="inbound", source="patient",
    ai_handled=False, triage_category=category,
    structured_data=summary_json,
)
```

Then reference `inbound_msg.id` when triggering the draft.

#### Step 4: Run tests

Run: `.venv/bin/python -m pytest tests/test_draft_batching.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: All PASS

#### Step 5: Commit

```bash
git add src/domain/patient_lifecycle/draft_reply.py \
  src/domain/patient_lifecycle/triage_handlers.py \
  tests/test_draft_batching.py
git commit -m "feat: wire draft generation into escalation handler with 30s batching

Trigger generate_draft_reply as a background task when messages are
escalated. 30-second delay allows rapid-fire messages to batch:
after the delay, the latest escalated message is used for generation.
Stale drafts are invalidated before regeneration."
```

---

### Task 8: Register Models and Verify Full Integration

**Goal:** Ensure all new models are registered, all routers wired, and run the full test suite.

**Files:**
- Verify: `src/db/models/__init__.py` (MessageDraft registered)
- Verify: `src/channels/web/ui/__init__.py` (draft_handlers router registered)
- Run: Full test suite

#### Step 1: Run full test suite

Run: `.venv/bin/python -m pytest tests/ -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -x`
Expected: All PASS

#### Step 2: Final commit if any wiring was needed

```bash
git add -A
git commit -m "chore: ensure all Stream B models and routers are registered

Final integration verification for Stream B draft reply pipeline."
```

---

## Summary of All New/Modified Files

| File | Status | Purpose |
|------|--------|---------|
| `src/db/models/message_draft.py` | NEW | MessageDraft model with DraftStatus enum |
| `src/agent/prompts/intent/followup_reply.md` | NEW | Draft reply prompt template with safety rules |
| `src/domain/patient_lifecycle/draft_reply.py` | NEW | Core domain: generate_draft_reply, red-flag detection, guardrails, stale invalidation, batching |
| `src/channels/web/ui/draft_handlers.py` | NEW | API: list/get/send/edit/dismiss drafts |
| `src/db/models/patient_message.py` | MODIFY | Add `read_at` column |
| `src/db/models/__init__.py` | MODIFY | Register MessageDraft, DraftStatus |
| `src/channels/web/ui/__init__.py` | MODIFY | Include draft_handlers router |
| `src/channels/web/patient_portal_chat.py` | MODIFY | Add read endpoint, include read_at in response |
| `src/domain/patient_lifecycle/triage_handlers.py` | MODIFY | Trigger draft generation + stale invalidation on escalation |
| `src/agent/prompt_config.py` | MODIFY | Add FOLLOWUP_REPLY_LAYERS |
| `tests/test_message_draft_model.py` | NEW | Model tests |
| `tests/test_draft_reply.py` | NEW | Domain function tests |
| `tests/test_draft_safety.py` | NEW | Safety constraint tests |
| `tests/test_draft_handlers.py` | NEW | API endpoint tests |
| `tests/test_draft_teaching.py` | NEW | Teaching loop tests for drafts |
| `tests/test_draft_batching.py` | NEW | 30s batching delay tests |
| `tests/test_message_read_status.py` | NEW | Read status tests |

### Critical Files for Implementation
- `/Volumes/ORICO/Code/doctor-ai-agent/src/db/models/message_draft.py`
- `/Volumes/ORICO/Code/doctor-ai-agent/src/domain/patient_lifecycle/draft_reply.py`
- `/Volumes/ORICO/Code/doctor-ai-agent/src/channels/web/ui/draft_handlers.py`
- `/Volumes/ORICO/Code/doctor-ai-agent/src/domain/patient_lifecycle/triage_handlers.py`
- `/Volumes/ORICO/Code/doctor-ai-agent/src/agent/prompts/intent/followup_reply.md`