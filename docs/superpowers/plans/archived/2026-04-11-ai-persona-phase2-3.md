# AI Persona Phase 2-3: Micro-Learning + Onboarding

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the AI persona system — edit classification, pending review queue, citation tracking, onboarding flow, teach-by-example, and toast notifications.

**Architecture:** Phase 2 adds an async edit classifier (LLM call), pending items table/API/UI, persona citation markers `[P-N]` in prompt output, and toast notifications. Phase 3 adds the pick-your-style onboarding and teach-by-example flows.

**Tech Stack:** SQLAlchemy (async), FastAPI, React + MUI, qwen-turbo for classification

**Spec:** `docs/superpowers/specs/2026-04-10-ai-persona-redesign.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/db/models/persona_pending.py` | PersonaPendingItem ORM model |
| Modify | `src/db/models/__init__.py` | Register new model |
| Create | `src/domain/knowledge/persona_classifier.py` | Edit classification (LLM call) |
| Create | `src/domain/knowledge/persona_learning.py` | Micro-learning pipeline (classify → pending) |
| Modify | `src/channels/web/doctor_dashboard/draft_handlers.py` | Trigger learning after edit |
| Create | `src/channels/web/doctor_dashboard/persona_pending_handlers.py` | Pending items API |
| Modify | `src/channels/web/doctor_dashboard/__init__.py` | Register pending router |
| Modify | `src/agent/prompt_composer.py` | Strip [P-N] markers from output |
| Create | `src/domain/knowledge/persona_citations.py` | Parse + log persona citations |
| Modify | `src/db/models/knowledge_usage.py` | Add persona_rule_id column |
| Create | `frontend/web/src/pages/doctor/subpages/PendingReviewSubpage.jsx` | Pending review UI |
| Modify | `frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx` | Add pending banner |
| Modify | `frontend/web/src/pages/doctor/SettingsPage.jsx` | Add pending route |
| Modify | `frontend/web/src/api.js` | Add pending API functions |
| Modify | `frontend/web/src/lib/doctorQueries.js` | Add usePendingItems hook |
| Modify | `frontend/web/src/lib/queryKeys.js` | Add pending query key |
| Create | `frontend/web/src/components/PersonaToast.jsx` | Toast notification component |
| Create | `src/domain/knowledge/onboarding_scenarios.py` | Scenario content + extraction |
| Create | `frontend/web/src/pages/doctor/subpages/PersonaOnboardingSubpage.jsx` | Onboarding flow UI |
| Create | `frontend/web/src/pages/doctor/subpages/TeachByExampleSubpage.jsx` | Teach-by-example UI |

---

### Task 1: PersonaPendingItem Model

**Files:**
- Create: `src/db/models/persona_pending.py`
- Modify: `src/db/models/__init__.py`

- [ ] **Step 1: Create the model**

```python
# src/db/models/persona_pending.py
"""Pending persona learning items — discovered from doctor edits, awaiting review."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class PersonaPendingItem(Base):
    """A pending persona rule discovered from a doctor edit."""
    __tablename__ = "persona_pending_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_rule: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_edit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    pattern_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 2: Register in `__init__.py`**

Add `from db.models.persona_pending import PersonaPendingItem` and add to `__all__`.

- [ ] **Step 3: Write tests**

```python
# tests/test_persona_pending.py
from db.models.persona_pending import PersonaPendingItem

def test_pending_item_defaults():
    item = PersonaPendingItem(
        doctor_id="doc_1",
        field="reply_style",
        proposed_rule="口语化回复",
        summary="偏好口语化",
        evidence_summary="把正式表达改成了口语化",
    )
    assert item.status == "pending"
    assert item.confidence == "medium"
    assert item.field == "reply_style"
```

- [ ] **Step 4: Run tests, commit**

Run: `.venv/bin/python -m pytest tests/test_persona_pending.py -v --rootdir=.`

```bash
git add src/db/models/persona_pending.py src/db/models/__init__.py tests/test_persona_pending.py
git commit -m "feat(persona): add PersonaPendingItem model"
```

---

### Task 2: Edit Classifier

**Files:**
- Create: `src/domain/knowledge/persona_classifier.py`

- [ ] **Step 1: Create the classifier**

```python
# src/domain/knowledge/persona_classifier.py
"""Classify doctor edits as style/factual/context-specific for persona learning."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from utils.log import log


CLASSIFICATION_PROMPT = """分析以下医生对AI草稿的修改，判断这是风格偏好还是事实纠正。

AI原文：
{original}

医生修改后：
{edited}

请用JSON格式回答（不要输出其他内容）：
{{
  "type": "style" 或 "factual" 或 "context_specific",
  "persona_field": "reply_style" 或 "closing" 或 "structure" 或 "avoid" 或 "edits" 或 null,
  "summary": "一句话结构性描述（不含患者姓名、日期等个人信息）",
  "confidence": "low" 或 "medium" 或 "high"
}}

判断规则：
- 如果医生改变了语气、称呼、结构、删除了某类内容 → type=style
- 如果医生纠正了药名、剂量、检查项目、医学事实 → type=factual
- 如果修改只适用于这个特定患者场景 → type=context_specific
- confidence=high 当修改模式非常明确（如删除整段、改变称呼方式）
- confidence=low 当修改很小或意图模糊"""


def compute_pattern_hash(field: str, summary: str) -> str:
    """Compute a hash for suppression matching."""
    normalized = f"{field}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


async def classify_edit(original: str, edited: str) -> Optional[dict]:
    """Classify a doctor edit using LLM.

    Returns dict with type, persona_field, summary, confidence.
    Returns None if classification fails.
    """
    if not original or not edited:
        return None
    if original.strip() == edited.strip():
        return None

    prompt = CLASSIFICATION_PROMPT.format(
        original=original[:500],
        edited=edited[:500],
    )

    try:
        from agent.llm import llm_call
        response = await llm_call(
            messages=[
                {"role": "system", "content": "你是一个分析医生编辑行为的助手。只输出JSON，不要输出其他内容。"},
                {"role": "user", "content": prompt},
            ],
            op_name="persona_classify",
        )

        if not response:
            return None

        # Extract JSON from response (may be wrapped in markdown code block)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(text)

        # Validate required fields
        valid_types = {"style", "factual", "context_specific"}
        valid_fields = {"reply_style", "closing", "structure", "avoid", "edits", None}
        if result.get("type") not in valid_types:
            return None
        if result.get("persona_field") not in valid_fields:
            result["persona_field"] = None

        return result
    except (json.JSONDecodeError, Exception) as exc:
        log(f"[persona_classifier] classification failed: {exc}", level="warning")
        return None
```

- [ ] **Step 2: Write tests**

```python
# tests/test_persona_classifier.py
from domain.knowledge.persona_classifier import compute_pattern_hash

def test_pattern_hash_deterministic():
    h1 = compute_pattern_hash("reply_style", "偏好口语化")
    h2 = compute_pattern_hash("reply_style", "偏好口语化")
    assert h1 == h2

def test_pattern_hash_different_fields():
    h1 = compute_pattern_hash("reply_style", "偏好口语化")
    h2 = compute_pattern_hash("avoid", "偏好口语化")
    assert h1 != h2

def test_pattern_hash_case_insensitive():
    h1 = compute_pattern_hash("reply_style", "Test Summary")
    h2 = compute_pattern_hash("reply_style", "test summary")
    assert h1 == h2
```

- [ ] **Step 3: Run tests, commit**

```bash
git add src/domain/knowledge/persona_classifier.py tests/test_persona_classifier.py
git commit -m "feat(persona): add edit classifier for persona learning"
```

---

### Task 3: Micro-Learning Pipeline

**Files:**
- Create: `src/domain/knowledge/persona_learning.py`
- Modify: `src/channels/web/doctor_dashboard/draft_handlers.py`

- [ ] **Step 1: Create the learning pipeline**

```python
# src/domain/knowledge/persona_learning.py
"""Micro-learning pipeline: classify edit → check suppression → create pending item."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.persona_pending import PersonaPendingItem
from domain.knowledge.persona_classifier import classify_edit, compute_pattern_hash
from utils.log import log


async def process_edit_for_persona(
    session: AsyncSession,
    doctor_id: str,
    original: str,
    edited: str,
    edit_id: int,
) -> dict | None:
    """Process a doctor edit through the persona learning pipeline.

    Returns the classification result if a pending item was created, None otherwise.
    Called asynchronously after the edit is saved.
    """
    # 1. Classify the edit
    result = await classify_edit(original, edited)
    if not result:
        return None

    # Only process style edits with medium+ confidence
    if result["type"] != "style":
        log(f"[persona_learning] edit {edit_id}: type={result['type']}, skipping")
        return None
    if result.get("confidence") == "low":
        log(f"[persona_learning] edit {edit_id}: low confidence, skipping")
        return None

    field = result.get("persona_field")
    if not field:
        return None

    summary = result.get("summary", "")
    pattern = compute_pattern_hash(field, summary)

    # 2. Check suppression (rejected items with same pattern in last 90 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    suppressed = (await session.execute(
        select(func.count()).select_from(PersonaPendingItem).where(
            PersonaPendingItem.doctor_id == doctor_id,
            PersonaPendingItem.pattern_hash == pattern,
            PersonaPendingItem.status == "rejected",
            PersonaPendingItem.updated_at > cutoff,
        )
    )).scalar() or 0

    if suppressed > 0:
        log(f"[persona_learning] edit {edit_id}: pattern suppressed, skipping")
        return None

    # 3. Check for duplicate pending items
    existing = (await session.execute(
        select(func.count()).select_from(PersonaPendingItem).where(
            PersonaPendingItem.doctor_id == doctor_id,
            PersonaPendingItem.pattern_hash == pattern,
            PersonaPendingItem.status == "pending",
        )
    )).scalar() or 0

    if existing > 0:
        log(f"[persona_learning] edit {edit_id}: duplicate pending item, skipping")
        return None

    # 4. Create pending item
    pending = PersonaPendingItem(
        doctor_id=doctor_id,
        field=field,
        proposed_rule=summary,
        summary=summary,
        evidence_summary=result.get("summary", ""),
        evidence_edit_ids=json.dumps([edit_id]),
        confidence=result.get("confidence", "medium"),
        pattern_hash=pattern,
    )
    session.add(pending)
    await session.flush()
    log(f"[persona_learning] created pending item {pending.id} for edit {edit_id}")
    return result
```

- [ ] **Step 2: Wire into draft_handlers.py**

Find where `log_doctor_edit` is called in `src/channels/web/doctor_dashboard/draft_handlers.py` (after a draft reply is edited). After the edit is logged, add an async fire-and-forget call to process the edit:

```python
# After log_doctor_edit returns edit_id:
import asyncio
from domain.knowledge.persona_learning import process_edit_for_persona

asyncio.ensure_future(_process_edit_background(doctor_id, original_text, edited_text, edit_id))

# Add this helper at module level:
async def _process_edit_background(doctor_id, original, edited, edit_id):
    """Fire-and-forget persona learning from edit."""
    try:
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await process_edit_for_persona(session, doctor_id, original, edited, edit_id)
            await session.commit()
    except Exception as exc:
        from utils.log import log
        log(f"[persona_learning] background processing failed (non-fatal): {exc}", level="warning")
```

Search `draft_handlers.py` for where edits are logged. There may be multiple call sites — wire them all.

- [ ] **Step 3: Run tests, commit**

```bash
git add src/domain/knowledge/persona_learning.py src/channels/web/doctor_dashboard/draft_handlers.py
git commit -m "feat(persona): add micro-learning pipeline, wire to draft edits"
```

---

### Task 4: Pending Items API

**Files:**
- Create: `src/channels/web/doctor_dashboard/persona_pending_handlers.py`
- Modify: `src/channels/web/doctor_dashboard/__init__.py`

- [ ] **Step 1: Create pending API handlers**

Endpoints:
- `GET /api/manage/persona/pending` — list pending items for doctor
- `POST /api/manage/persona/pending/{item_id}/accept` — accept a pending item (creates rule in persona)
- `POST /api/manage/persona/pending/{item_id}/reject` — reject (mark as rejected for suppression)

On accept:
1. Load the pending item
2. Create a rule from it: `{"id": generate_rule_id(), "text": pending.proposed_rule, "source": "edit", "usage_count": 0}`
3. Add rule to persona via `add_rule_to_persona`
4. Mark pending item as "accepted"
5. Auto-activate persona if draft

On reject:
1. Mark pending item as "rejected" (keeps pattern_hash for suppression)

- [ ] **Step 2: Register router in __init__.py**

- [ ] **Step 3: Add frontend API functions**

In `api.js`:
```javascript
export async function getPersonaPending(doctorId) { ... }
export async function acceptPendingItem(doctorId, itemId) { ... }
export async function rejectPendingItem(doctorId, itemId) { ... }
```

In `queryKeys.js`: `personaPending: (did) => ["doctor", did, "persona-pending"],`

In `doctorQueries.js`: `export function usePersonaPending() { ... }`

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/doctor_dashboard/persona_pending_handlers.py src/channels/web/doctor_dashboard/__init__.py frontend/web/src/api.js frontend/web/src/lib/queryKeys.js frontend/web/src/lib/doctorQueries.js
git commit -m "feat(persona): add pending items API and frontend hooks"
```

---

### Task 5: Pending Review UI

**Files:**
- Create: `frontend/web/src/pages/doctor/subpages/PendingReviewSubpage.jsx`
- Modify: `frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx` — add pending banner
- Modify: `frontend/web/src/pages/doctor/SettingsPage.jsx` — add route

- [ ] **Step 1: Create PendingReviewSubpage**

Shows list of pending items. Each item displays:
- Field label (回复风格, etc.)
- Proposed rule text
- Evidence summary
- Confidence badge
- Two buttons: 忽略 (reject) | 确认 (accept)

Use `usePersonaPending()` hook. On accept/reject, call API and invalidate cache.

Follow existing UI patterns (PageSkeleton, ListCard style, button conventions).

- [ ] **Step 2: Add pending banner to PersonaSubpage**

At the top of PersonaSubpage, if there are pending items, show a banner:
```jsx
{pendingCount > 0 && (
  <Box onClick={() => navigate(dp("settings/persona/pending"))} sx={{
    mx: 2, mt: 1.5, bgcolor: COLOR.warningLight, px: 1.5, py: 1.25,
    borderRadius: RADIUS.md, display: "flex", justifyContent: "space-between",
    alignItems: "center", cursor: "pointer",
  }}>
    <Box>
      <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500, color: "#b28704" }}>
        {pendingCount} 条新发现待确认
      </Typography>
    </Box>
    <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#b28704" }}>查看 ›</Typography>
  </Box>
)}
```

Use `usePersonaPending()` to get the count.

- [ ] **Step 3: Add route in SettingsPage.jsx**

Add `persona/pending` subpage routing (similar pattern to `persona`).

- [ ] **Step 4: Build and commit**

```bash
git add frontend/web/src/pages/doctor/subpages/PendingReviewSubpage.jsx frontend/web/src/pages/doctor/subpages/PersonaSubpage.jsx frontend/web/src/pages/doctor/SettingsPage.jsx
git commit -m "feat(persona): add pending review UI with accept/reject"
```

---

### Task 6: Persona Citation Tracking

**Files:**
- Create: `src/domain/knowledge/persona_citations.py`
- Modify: `src/domain/patient_lifecycle/draft_reply.py` or wherever citations are stripped

- [ ] **Step 1: Create citation parser**

```python
# src/domain/knowledge/persona_citations.py
"""Parse and log [P-xxx] persona citations from LLM output."""

import re
from typing import List

from utils.log import log

_PERSONA_CITATION_RE = re.compile(r"\[P-(ps_[a-z0-9]+)\]")


def extract_persona_citations(text: str) -> List[str]:
    """Extract persona rule IDs from [P-ps_xxx] markers in text."""
    return _PERSONA_CITATION_RE.findall(text)


def strip_persona_citations(text: str) -> str:
    """Remove [P-xxx] markers from text for user-facing display."""
    return _PERSONA_CITATION_RE.sub("", text).strip()
```

- [ ] **Step 2: Wire citation stripping into draft reply post-processing**

Find where `[KB-N]` citations are stripped in the draft reply flow and add `strip_persona_citations` alongside it. The existing code strips KB citations — add persona citation stripping at the same point.

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/persona_citations.py
git commit -m "feat(persona): add [P-N] citation parsing and stripping"
```

---

### Task 7: Onboarding Scenarios + Flow

**Files:**
- Create: `src/domain/knowledge/onboarding_scenarios.py`
- Create: `frontend/web/src/pages/doctor/subpages/PersonaOnboardingSubpage.jsx`
- Modify: `frontend/web/src/pages/doctor/SettingsPage.jsx`
- Modify: `src/channels/web/doctor_dashboard/persona_handlers.py`

- [ ] **Step 1: Create onboarding scenario content**

```python
# src/domain/knowledge/onboarding_scenarios.py
"""Onboarding scenario content for persona pick-your-style flow."""

GENERIC_SCENARIOS = [
    {
        "id": "postop_followup",
        "title": "术后随访",
        "patient_message": "医生，术后第三天头还是有点疼，VAS大概5-6分，伤口周围有点胀，体温37.1度。这些正常吗？要不要加点止疼药？",
        "patient_info": "患者张先生，56岁，术后第3天",
        "options": [
            {
                "id": "a",
                "text": "张叔，VAS 5-6分在术后第三天是正常的，伤口周围胀也是局部水肿的表现，体温37.1不算发热。目前不需要加止疼药，继续观察就行。如果VAS超过7分或者体温超过38.5度，随时联系我。",
                "traits": {"reply_style": "口语化，称呼用昵称", "structure": "先给结论再解释", "avoid": "以安抚为主，给具体阈值"}
            },
            {
                "id": "b",
                "text": "张先生您好。术后第三天头痛VAS 5-6分属于正常范围，伤口周围肿胀系术区局部水肿所致，体温37.1°C处于正常体温上限，暂不需要特殊处理。目前不建议增加止痛药物，继续按现有方案即可。如疼痛明显加重（VAS≥7）、体温超过38.5°C或出现恶心呕吐等情况，请及时联系。",
                "traits": {"reply_style": "书面语，称呼用全名敬称", "structure": "逐项回应", "avoid": "标注具体指标"}
            },
            {
                "id": "c",
                "text": "都是正常的。VAS 5-6分术后三天没问题，不用加药。体温也正常。疼得厉害或者烧起来了再说。",
                "traits": {"reply_style": "极简直接", "structure": "只给结论", "avoid": "不展开解释"}
            },
        ],
    },
    {
        "id": "medication_question",
        "title": "用药咨询",
        "patient_message": "医生，这个药吃了两周了，最近老觉得困，白天也没精神，是药的副作用吗？能不能换个药或者减量？",
        "patient_info": "患者李阿姨，62岁，服用左乙拉西坦",
        "options": [
            {
                "id": "a",
                "text": "李阿姨，困和没精神确实是常见的副作用，一般吃一段时间身体适应了会好一些。现在先不要自己减量，因为这个阶段预防很重要。下次复查的时候我看看情况再决定要不要调整，如果实在影响生活可以提前来一趟。",
                "traits": {"reply_style": "口语亲切，安抚为主", "closing": "留口子下次调整"}
            },
            {
                "id": "b",
                "text": "嗜睡乏力是该药的常见不良反应，多数患者2-4周内可自行缓解。目前不建议减量或换药。建议下次门诊复查时评估，如症状严重影响日常生活，可提前就诊讨论方案调整。",
                "traits": {"reply_style": "专业书面", "structure": "先解释机制再给建议"}
            },
            {
                "id": "c",
                "text": "是药的副作用，正常的，再坚持坚持。别自己减药，下次来的时候我给你看看要不要调。",
                "traits": {"reply_style": "极简口语", "structure": "直接确认+指令"}
            },
        ],
    },
    {
        "id": "urgent_symptom",
        "title": "紧急情况",
        "patient_message": "医生，我爸今天突然说头很疼，比前几天厉害多了，还吐了一次。是不是有什么问题？",
        "patient_info": "家属代问，患者术后第5天",
        "options": [
            {
                "id": "a",
                "text": "这个情况需要重视。术后突然头痛加重伴呕吐，需要排除颅内出血或脑水肿加重的可能。请尽快带他到最近的医院急诊做一个头颅CT，拿到结果后拍给我看。如果是在我们医院附近，直接来急诊找我。",
                "traits": {"reply_style": "严肃但不恐慌", "structure": "说明原因+给行动路径"}
            },
            {
                "id": "b",
                "text": "头痛突然加重加上呕吐，术后第五天这个时间点要警惕。赶紧去急诊做个CT，做完了把片子发给我。能来我们医院最好。",
                "traits": {"reply_style": "简洁紧迫", "structure": "直接给行动"}
            },
            {
                "id": "c",
                "text": "术后新发剧烈头痛伴呕吐属于危险信号，不排除迟发性颅内出血可能，建议立即前往就近医院急诊行头颅CT平扫。如结果异常请随时联系我，或直接转至我院神经外科急诊处理。",
                "traits": {"reply_style": "标准书面", "structure": "明确诊断方向+完整就医路径"}
            },
        ],
    },
]


def extract_rules_from_picks(picks: list[dict]) -> dict:
    """Extract persona rules from onboarding picks.

    picks: [{"scenario_id": "postop_followup", "option_id": "a"}, ...]
    Returns: persona fields dict ready to write.
    """
    from db.crud.persona import generate_rule_id
    from db.models.doctor_persona import EMPTY_PERSONA_FIELDS

    fields = EMPTY_PERSONA_FIELDS()

    for pick in picks:
        scenario = next((s for s in GENERIC_SCENARIOS if s["id"] == pick.get("scenario_id")), None)
        if not scenario:
            continue
        option = next((o for o in scenario["options"] if o["id"] == pick.get("option_id")), None)
        if not option:
            continue

        traits = option.get("traits", {})
        for field_key, text in traits.items():
            if field_key in fields and text:
                # Avoid duplicate rules
                existing_texts = {r["text"] for r in fields[field_key]}
                if text not in existing_texts:
                    fields[field_key].append({
                        "id": generate_rule_id(),
                        "text": text,
                        "source": "onboarding",
                        "usage_count": 0,
                    })

    return fields
```

- [ ] **Step 2: Add onboarding API endpoint**

In `persona_handlers.py`, add:

```python
@router.get("/api/manage/persona/onboarding/scenarios")
async def get_onboarding_scenarios(...):
    """Return onboarding scenarios for pick-your-style."""
    from domain.knowledge.onboarding_scenarios import GENERIC_SCENARIOS
    return {"scenarios": GENERIC_SCENARIOS}

@router.post("/api/manage/persona/onboarding/complete")
async def complete_onboarding(body, ...):
    """Process onboarding picks and populate persona."""
    # body.picks = [{"scenario_id": "...", "option_id": "..."}, ...]
    # Extract rules from picks
    # Write to persona fields
    # Set onboarded=True, status=active
```

- [ ] **Step 3: Create PersonaOnboardingSubpage.jsx**

Mobile-first flow:
1. Show scenarios one at a time with patient message + 3 option cards
2. Doctor taps an option to select (highlighted)
3. "都不像我" option opens a text input
4. After all 3 scenarios, show extracted rules for review
5. Confirm → save and navigate to persona page

- [ ] **Step 4: Route it**

Trigger: when navigating to persona subpage and `personaData.onboarded === false`, show onboarding instead.

Or add a separate route: `settings/persona/onboarding`.

- [ ] **Step 5: Build, commit**

```bash
git commit -m "feat(persona): add onboarding scenarios and pick-your-style flow"
```

---

### Task 8: Teach by Example

**Files:**
- Create: `frontend/web/src/pages/doctor/subpages/TeachByExampleSubpage.jsx`
- Modify: `src/channels/web/doctor_dashboard/persona_handlers.py`

- [ ] **Step 1: Add teach-by-example API endpoint**

```python
@router.post("/api/manage/persona/teach")
async def teach_by_example(body, ...):
    """Extract style rules from a pasted example response."""
    # Uses LLM to extract style/structure/tone from the text
    # Returns extracted rules as pending items
```

- [ ] **Step 2: Create TeachByExampleSubpage.jsx**

Simple UI:
1. Text area: "粘贴一段你满意的回复"
2. Submit → calls API
3. Shows extracted rules
4. Confirm → creates pending items (or directly adds rules)

- [ ] **Step 3: Route and link**

Add to PersonaSubpage bottom: "教AI新偏好" button → navigates to teach page.

- [ ] **Step 4: Build, commit**

```bash
git commit -m "feat(persona): add teach-by-example flow"
```

---

### Task 9: Toast Notification Component

**Files:**
- Create: `frontend/web/src/components/PersonaToast.jsx`
- Modify: `frontend/web/src/pages/doctor/MyAIPage.jsx` or app-level component

- [ ] **Step 1: Create PersonaToast**

A non-blocking toast that appears when a new pending item is created:
"AI注意到：{summary}" with [查看] [忽略]

Use MUI Snackbar with action buttons. Auto-dismiss after 6 seconds.

The toast data comes from the persona pending query — if a new pending item appears since last check, show the toast.

- [ ] **Step 2: Integrate at app level**

Place the toast component in the doctor page layout so it appears on any page.

- [ ] **Step 3: Build, commit**

```bash
git commit -m "feat(persona): add persona learning toast notification"
```

---

### Task 10: Full Integration Test + QA

- [ ] **Step 1: Run all backend tests**
- [ ] **Step 2: Build frontend**
- [ ] **Step 3: Run migration**
- [ ] **Step 4: Start dev server, manual QA**

QA checklist:
1. MyAI page shows separate persona + knowledge sections
2. Persona subpage shows 5 fields with rules
3. Can add/edit/delete individual rules
4. Onboarding flow works for new doctor (no rules)
5. Teach-by-example extracts rules from pasted text
6. After editing a draft reply, pending items appear
7. Pending review page shows items with accept/reject
8. Accepted rules appear in persona
9. Rejected patterns don't reappear
10. Toast appears when new pending item is created
11. Persona rules affect AI output (test a follow-up reply)
