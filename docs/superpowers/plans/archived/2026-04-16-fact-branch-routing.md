# Fact-Branch Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop silently discarding factual edits. When the LLM classifies a doctor's draft edit as `type=factual`, route it into a new `kb_pending_items` table; on accept, write to `doctor_knowledge_items` so the rule becomes `[KB-N]`-citeable. Persona (style) flow is unchanged in shape but the classifier now runs on every edit instead of just significant ones.

**Architecture:** Parallel learning track next to the existing persona flow. Same LLM call, extended output schema (Pydantic-enforced). Two pending tables (persona, kb) with shared concurrency helpers. Decouple `log_doctor_edit` + classifier from the `should_prompt_teaching` gate so every edit produces both a `DoctorEdit` row and a classifier verdict; the teach-prompt UI button remains gated.

**Tech Stack:** Python 3.11 / FastAPI, SQLAlchemy async / Alembic, Pydantic v2 (`model_validator`), existing `agent/llm.py` + `persona-classify.md` prompt, React 18 + MUI + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-04-16-fact-branch-routing-design.md` (v3.2, pair-reviewed Claude 91% / codex 91%).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `alembic/versions/<hash>_add_kb_pending_items.py` | Create | Schema: `kb_pending_items` table, `FactLearning` feature flag column is N/A (env-var only), unique `(doctor_id, pattern_hash, status)` on both pending tables |
| `src/db/models/kb_pending.py` | Create | ORM model for `KbPendingItem` |
| `src/db/models/persona_pending.py` | Modify | Add `UniqueConstraint('doctor_id','pattern_hash','status')` via `__table_args__` |
| `src/agent/prompts/persona-classify.md` | Modify | Extend JSON schema (+ `kb_category`, `proposed_kb_rule`); rewrite all 5 existing examples; add 4 new factual examples; PII rule |
| `tests/prompts/cases/persona-classify.yaml` | Create | 30 factual + 5 context-specific + 10 style eval cases |
| `tests/prompts/wrappers/persona-classify.md` | Create | Minimal wrapper that feeds `{original}`, `{edited}` to the prompt |
| `src/domain/knowledge/persona_classifier.py` | Modify | Add `LearningType`/`PersonaField`/`KbCategory` enums + `ClassifyResult` Pydantic model + `compute_kb_pattern_hash()`; `classify_edit` returns the model |
| `src/domain/knowledge/pending_common.py` | Create | Shared helpers: `check_pattern_suppression`, `savepoint_check_duplicate_pending`, `scrub_pii` |
| `src/domain/knowledge/persona_learning.py` | Modify | Rename `process_edit_for_persona` → `process_edit_for_learning`; add fact branch; invoke `_route_to_persona_pending` / `_route_to_kb_pending` helpers |
| `src/domain/knowledge/knowledge_crud.py` | Modify | Extend `save_knowledge_item` signature with `seed_source: Optional[str] = None` |
| `src/channels/web/doctor_dashboard/draft_handlers.py` | Modify | Lift `log_doctor_edit` + learning call out of the `should_prompt_teaching` block |
| `src/channels/web/doctor_dashboard/kb_pending_handlers.py` | Create | GET list / POST accept / POST reject endpoints under `/api/manage/kb/pending` |
| `src/cli.py` (or wherever routers are registered) | Modify | Register `kb_pending_handlers.router` |
| `tests/core/test_fact_routing.py` | Create | Unit tests for `ClassifyResult`, PII scrub, routing decisions |
| `tests/integration/test_kb_pending.py` | Create | End-to-end backend: edit → pending → accept → KB |
| `frontend/web/src/api.js` | Modify | Add `getKbPending`, `acceptKbPending`, `rejectKbPending` |
| `frontend/web/src/lib/doctorQueries.js` | Modify | Add `QK.kbPending`, `useKbPending`, `useAcceptKbPending`, `useRejectKbPending` |
| `frontend/web/src/pages/doctor/subpages/KbPendingSubpage.jsx` | Create | Review cards: category badge, proposed rule, accept/reject |
| `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx` | Modify | Show pending-count badge; navigate to subpage |
| `frontend/web/src/pages/doctor/SettingsPage.jsx` | Modify | Route `knowledge/pending` → KbPendingSubpage |
| `frontend/web/tests/e2e/19-kb-pending-citeability.spec.ts` | Create | E2E: edit → accept → next draft shows `[KB-N]` |

---

# Phase 1 — Schema

## Task 1: Alembic migration — `kb_pending_items` + unique constraints

**Files:**
- Create: `alembic/versions/<hash>_add_kb_pending_items.py` (hash produced by `alembic revision`)
- Modify: `src/db/models/persona_pending.py`

- [ ] **Step 1: Add `UniqueConstraint` to `PersonaPendingItem.__table_args__`**

Open `src/db/models/persona_pending.py` and replace the class with:

```python
"""Pending persona learning items — discovered from doctor edits, awaiting review."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class PersonaPendingItem(Base):
    """A pending persona rule discovered from a doctor edit."""
    __tablename__ = "persona_pending_items"
    __table_args__ = (
        UniqueConstraint("doctor_id", "pattern_hash", "status", name="uq_persona_pending_dedupe"),
    )

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

- [ ] **Step 2: Generate migration skeleton**

Run: `.venv/bin/alembic revision -m "add_kb_pending_items"`
Expected: prints a new file path like `alembic/versions/abcd1234ef56_add_kb_pending_items.py`.

- [ ] **Step 3: Write the migration body**

Replace the generated file contents with:

```python
"""add_kb_pending_items

Revision ID: <keep the auto-generated hash>
Revises: dfbe8eaa5be9
Create Date: <auto>
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "<keep auto>"
down_revision = "dfbe8eaa5be9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_pending_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doctor_id", sa.String(64), sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("proposed_rule", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("evidence_edit_ids", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("pattern_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("accepted_knowledge_item_id", sa.Integer(),
                  sa.ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("doctor_id", "pattern_hash", "status", name="uq_kb_pending_dedupe"),
    )
    op.create_index("ix_kb_pending_items_doctor_id", "kb_pending_items", ["doctor_id"])
    op.create_index("ix_kb_pending_items_pattern_hash", "kb_pending_items", ["pattern_hash"])

    # Add the unique constraint to the existing persona_pending_items table
    op.create_unique_constraint(
        "uq_persona_pending_dedupe",
        "persona_pending_items",
        ["doctor_id", "pattern_hash", "status"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_persona_pending_dedupe", "persona_pending_items", type_="unique")
    op.drop_index("ix_kb_pending_items_pattern_hash", table_name="kb_pending_items")
    op.drop_index("ix_kb_pending_items_doctor_id", table_name="kb_pending_items")
    op.drop_table("kb_pending_items")
```

- [ ] **Step 4: Apply migration to dev SQLite**

Run: `.venv/bin/alembic upgrade head`
Expected: output ends with `Running upgrade dfbe8eaa5be9 -> <hash>, add_kb_pending_items`.

Verify table exists:
Run: `sqlite3 data/doctor_dev.db ".schema kb_pending_items"` (or the project's dev DB path)
Expected: CREATE TABLE output showing all 13 columns.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/ src/db/models/persona_pending.py
git commit -m "feat(db): add kb_pending_items table and dedup unique on persona_pending"
```

---

## Task 2: ORM model `KbPendingItem`

**Files:**
- Create: `src/db/models/kb_pending.py`

- [ ] **Step 1: Write the model**

```python
"""Pending KB learning items — factual edits awaiting doctor review."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class KbPendingItem(Base):
    """A pending clinical-knowledge rule discovered from a factual doctor edit."""
    __tablename__ = "kb_pending_items"
    __table_args__ = (
        UniqueConstraint("doctor_id", "pattern_hash", "status", name="uq_kb_pending_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_rule: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_edit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    pattern_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    accepted_knowledge_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("doctor_knowledge_items.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 2: Smoke import to ensure no SQLAlchemy mapping error**

Run: `.venv/bin/python -c "from db.models.kb_pending import KbPendingItem; print(KbPendingItem.__table__.columns.keys())"`
Expected: list containing `['id', 'doctor_id', 'category', ..., 'accepted_knowledge_item_id', 'created_at', 'updated_at']`.

- [ ] **Step 3: Commit**

```bash
git add src/db/models/kb_pending.py
git commit -m "feat(db): add KbPendingItem ORM model"
```

---

# Phase 2 — Prompt + eval harness

## Task 3: Rewrite `persona-classify.md`

**Files:**
- Modify: `src/agent/prompts/persona-classify.md`

- [ ] **Step 1: Replace the file with the extended version**

Open `src/agent/prompts/persona-classify.md` and replace contents with:

```markdown
/no_think

## Task

分析医生对AI草稿的修改，判断修改类型（风格偏好 / 事实纠正 / 场景特定），并归类到对应的个性化字段；若为事实纠正，额外输出可复用的临床规则与分类。

## Input

<original_text>
{original}
</original_text>

<edited_text>
{edited}
</edited_text>

## Rules

### 类型判断（按此顺序检查）
1. **factual** — 医生纠正了医学事实（药名、剂量、检查项目、诊断、治疗方案）。输出 kb_category + proposed_kb_rule
2. **context_specific** — 修改仅适用于该特定患者的情况（如针对某患者的特殊叮嘱、个体化用药调整）
3. **style** — 医生改变了语气、称呼、结构、删除/增加了某类内容。输出 persona_field

### 字段归类（仅 type=style 时必填）
4. **reply_style** — 语气/称呼/正式程度的变化
5. **closing** — 结尾用语/随访叮嘱的改变
6. **structure** — 内容组织方式的改变
7. **avoid** — 删除某类内容
8. **edits** — 语言修辞习惯
9. type=factual 或 type=context_specific 时，persona_field 填 ""

### KB 分类（仅 type=factual 时必填）
10. **diagnosis** — 诊断逻辑、鉴别要点、信号标记识别
11. **medication** — 药物选择、剂量、禁忌
12. **followup** — 随访时间、复查频率、监测指标
13. **custom** — 不在上面三类中的临床规则
14. type 非 factual 时，kb_category 填 "" 且 proposed_kb_rule 填 ""

### proposed_kb_rule 要求（type=factual 时）
15. 必须是去情境化的通用规则（不带患者姓名、日期、具体病情细节）
16. 长度 ≤ 300 字符，中文
17. 完整自包含（读者不需要看 original/edited 就能理解）
18. 不得包含 PII（姓名、手机号、身份证号、住院号、具体日期）

### confidence 定义
19. **high** — 修改模式非常明确：删除整段、系统性改变称呼、统一缩短所有句子
20. **medium** — 有一定规律但不完全确定
21. **low** — 修改很小或意图模糊

### summary 要求
22. summary 必须是结构性描述，描述修改**模式**而非具体内容
23. summary 中不得包含患者姓名、日期、具体病情等个人信息

## Output

输出 JSON，不要输出其他内容：

```
{{"type": "style|factual|context_specific", "persona_field": "reply_style|closing|structure|avoid|edits|", "summary": "一句话结构性描述", "confidence": "low|medium|high", "kb_category": "diagnosis|medication|followup|custom|", "proposed_kb_rule": "去情境化临床规则或空字符串"}}
```

- 所有 JSON key 使用英文
- 不使用 null — 空值用 ""
- proposed_kb_rule 为 "" 时，kb_category 也必须为 ""

## Constraints

- 只输出 JSON，不要解释推理过程
- type 只能是 style / factual / context_specific 三选一
- persona_field 只能是 reply_style / closing / structure / avoid / edits / ""
- kb_category 只能是 diagnosis / medication / followup / custom / ""
- confidence 只能是 low / medium / high 三选一
- 不得在 summary / proposed_kb_rule 中泄露患者个人信息

## Examples

**示例1：风格修改 — 删除结尾祝福语（高置信度）**

<original_text>
张阿姨您好，您的血压控制得不错，继续目前的用药方案即可。建议每周测量血压2-3次并记录。祝您身体健康，早日康复！
</original_text>

<edited_text>
张阿姨你好，血压还行，继续吃药就好。每周量2-3次血压记录下。
</edited_text>

→ {{"type": "style", "persona_field": "closing", "summary": "删除结尾祝福语，整体语气改为口语化简短风格", "confidence": "high", "kb_category": "", "proposed_kb_rule": ""}}

**示例2：事实纠正 — 修改药物名称**

<original_text>
建议继续服用氨氯地平控制血压，同时注意低盐饮食。
</original_text>

<edited_text>
建议继续服用硝苯地平控制血压，同时注意低盐饮食。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "纠正了降压药名称（氨氯地平→硝苯地平）", "confidence": "high", "kb_category": "medication", "proposed_kb_rule": "对本医生而言，该类高血压患者首选硝苯地平而非氨氯地平控制血压"}}

**示例3：场景特定 — 针对特定患者的调整**

<original_text>
术后请注意伤口护理，按时换药，有异常及时就诊。
</original_text>

<edited_text>
术后请注意伤口护理，按时换药，有异常及时就诊。因为您有糖尿病，伤口愈合可能较慢，请特别注意血糖控制。
</edited_text>

→ {{"type": "context_specific", "persona_field": "", "summary": "针对患者合并症添加了个体化叮嘱", "confidence": "high", "kb_category": "", "proposed_kb_rule": ""}}

**示例4：风格修改 — 调整回复结构（中等置信度）**

<original_text>
您的检查结果显示甲状腺功能正常，TSH和T3T4均在正常范围内。甲状腺超声也未见明显异常。综合来看，目前不需要特殊处理，建议半年后复查。
</original_text>

<edited_text>
结论：甲状腺没问题，半年后复查。

检查结果：TSH、T3T4正常，超声未见异常。
</edited_text>

→ {{"type": "style", "persona_field": "structure", "summary": "将回复改为结论前置的结构，先给结论再列支持数据", "confidence": "medium", "kb_category": "", "proposed_kb_rule": ""}}

**示例5：微小修改 — 意图模糊（低置信度）**

<original_text>
建议您近期复查一下血常规。
</original_text>

<edited_text>
建议近期复查血常规。
</edited_text>

→ {{"type": "style", "persona_field": "edits", "summary": "删除了冗余的'您'和'一下'", "confidence": "low", "kb_category": "", "proposed_kb_rule": ""}}

**示例6：事实纠正 — 诊断条件修正**

<original_text>
颅脑术后头痛患者可以使用布洛芬止痛。
</original_text>

<edited_text>
颅脑术后头痛患者在排除脑脊液漏之前不建议使用NSAIDs，首选对乙酰氨基酚。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了颅脑术后头痛的止痛药选择", "confidence": "high", "kb_category": "diagnosis", "proposed_kb_rule": "颅脑术后头痛患者在排除脑脊液漏之前不建议使用 NSAIDs（包括布洛芬），首选对乙酰氨基酚"}}

**示例7：事实纠正 — 随访时间调整**

<original_text>
颅内动脉瘤夹闭术后3个月复查CTA即可。
</original_text>

<edited_text>
颅内动脉瘤夹闭术后2周首次复查CTA，之后3个月、1年各复查一次。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了动脉瘤夹闭术后的复查时点", "confidence": "high", "kb_category": "followup", "proposed_kb_rule": "颅内动脉瘤夹闭术后首次 CTA 复查时间为术后 2 周，而非 3 个月；之后分别在 3 个月、1 年复查"}}

**示例8：事实纠正 — 药物联用禁忌**

<original_text>
血压仍偏高，可以加用ARB类药物联合治疗。
</original_text>

<edited_text>
患者已在用ACEI，不要联用ARB，可换为钙通道阻滞剂。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "纠正了 ACEI 与 ARB 的联用建议", "confidence": "high", "kb_category": "medication", "proposed_kb_rule": "ACEI 与 ARB 不可联用；已使用 ACEI 的患者血压控制不佳时，优先加用钙通道阻滞剂"}}

**示例9：事实纠正 — 通用临床规则**

<original_text>
糖尿病患者伤口一般一周愈合。
</original_text>

<edited_text>
糖尿病患者伤口愈合较慢，需要额外 1-2 周观察，并严格控制血糖在 7 mmol/L 以下。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了糖尿病患者伤口愈合预估", "confidence": "high", "kb_category": "custom", "proposed_kb_rule": "糖尿病患者伤口愈合较非糖尿病患者慢 1-2 周，期间需严格控制血糖在 7 mmol/L 以下"}}
```

- [ ] **Step 2: Verify `.format()` template still works**

Run:
```bash
.venv/bin/python -c "from utils.prompt_loader import get_prompt_sync; p = get_prompt_sync('persona-classify'); print(p.format(original='a', edited='b')[:200])"
```
Expected: prints first 200 chars of the formatted prompt, no `KeyError`.

- [ ] **Step 3: Commit**

```bash
git add src/agent/prompts/persona-classify.md
git commit -m "feat(prompts): extend persona-classify schema with kb_category + proposed_kb_rule, rewrite examples"
```

---

## Task 4: Eval cases + wrapper

**Files:**
- Create: `tests/prompts/cases/persona-classify.yaml`
- Create: `tests/prompts/wrappers/persona-classify.md`

- [ ] **Step 1: Write the wrapper**

Create `tests/prompts/wrappers/persona-classify.md`:

```markdown
{{prompt}}
```

(The wrapper is intentionally minimal — the prompt file already contains the full system instructions and the `{original}` / `{edited}` input block.)

- [ ] **Step 2: Write the YAML eval file**

Create `tests/prompts/cases/persona-classify.yaml`. Cases below — 10 style + 5 context-specific + 15 factual (due to plan-length constraint; scale to 30 factual during implementation by following the shown pattern, 4 per category minimum). Ensure every case asserts `is-json` and field constraints.

```yaml
# Test cases for persona-classify.md
# Prompt: Chinese doctor edit → {type, persona_field, summary, confidence, kb_category, proposed_kb_rule} JSON

# ─── STYLE CASES (10) ───────────────────────────────────────────────

- description: "style: delete closing blessing (high)"
  options:
    prompts: [persona-classify]
  vars:
    original: "张阿姨您好，血压不错，继续用药。祝您身体健康，早日康复！"
    edited: "张阿姨你好，血压还行，继续吃药就好。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'style' && o.persona_field === 'closing' && o.kb_category === '' && o.proposed_kb_rule === '';

- description: "style: reply_style change (您→你)"
  options:
    prompts: [persona-classify]
  vars:
    original: "您好，建议您按时服药。"
    edited: "你好，建议你按时服药。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'style' && o.persona_field === 'reply_style';

- description: "style: structure — conclusion first"
  options:
    prompts: [persona-classify]
  vars:
    original: "您的检查结果显示甲状腺功能正常，TSH和T3T4均在正常范围内，综合来看不需要处理，建议半年后复查。"
    edited: "结论：甲状腺没问题，半年后复查。\n\n检查结果：TSH、T3T4正常。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'style' && o.persona_field === 'structure';

- description: "style: edits — shorter phrasing (low)"
  options:
    prompts: [persona-classify]
  vars:
    original: "建议您近期复查一下血常规。"
    edited: "建议近期复查血常规。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'style' && o.persona_field === 'edits';

- description: "style: avoid — drop safety disclaimer"
  options:
    prompts: [persona-classify]
  vars:
    original: "建议按时服药，并注意观察是否有头晕恶心等副作用，如有不适立即停药并就诊。"
    edited: "建议按时服药。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'style' && o.persona_field === 'avoid';

# ─── 5 additional style cases omitted in plan but REQUIRED at implementation time ──

# ─── CONTEXT-SPECIFIC CASES (5) ─────────────────────────────────────

- description: "context: diabetes-specific add-on"
  options:
    prompts: [persona-classify]
  vars:
    original: "术后注意伤口护理，按时换药，有异常及时就诊。"
    edited: "术后注意伤口护理，按时换药，有异常及时就诊。您有糖尿病，愈合较慢，请注意血糖控制。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'context_specific' && o.persona_field === '' && o.kb_category === '' && o.proposed_kb_rule === '';

# ─── 4 additional context_specific cases omitted in plan but REQUIRED ──

# ─── FACTUAL CASES (15 — scale to 30 at implementation) ─────────────

- description: "factual: drug swap (medication)"
  options:
    prompts: [persona-classify]
  vars:
    original: "建议继续服用氨氯地平控制血压，同时注意低盐饮食。"
    edited: "建议继续服用硝苯地平控制血压，同时注意低盐饮食。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'factual' && o.kb_category === 'medication' && o.proposed_kb_rule.length > 0 && o.persona_field === '';

- description: "factual: NSAIDs avoid in post-craniotomy (diagnosis)"
  options:
    prompts: [persona-classify]
  vars:
    original: "颅脑术后头痛患者可以使用布洛芬止痛。"
    edited: "颅脑术后头痛患者在排除脑脊液漏之前不建议使用NSAIDs，首选对乙酰氨基酚。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'factual' && o.kb_category === 'diagnosis' && o.proposed_kb_rule.includes('NSAIDs');

- description: "factual: aneurysm CTA followup schedule"
  options:
    prompts: [persona-classify]
  vars:
    original: "颅内动脉瘤夹闭术后3个月复查CTA即可。"
    edited: "颅内动脉瘤夹闭术后2周首次复查CTA，之后3个月、1年各复查一次。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'factual' && o.kb_category === 'followup';

- description: "factual: ACEI+ARB contraindication"
  options:
    prompts: [persona-classify]
  vars:
    original: "血压仍偏高，可以加用ARB类药物联合治疗。"
    edited: "患者已在用ACEI，不要联用ARB，可换为钙通道阻滞剂。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'factual' && o.kb_category === 'medication' && o.proposed_kb_rule.includes('ACEI');

- description: "factual: diabetic wound healing (custom)"
  options:
    prompts: [persona-classify]
  vars:
    original: "糖尿病患者伤口一般一周愈合。"
    edited: "糖尿病患者伤口愈合较慢，需要额外 1-2 周观察，并严格控制血糖在 7 mmol/L 以下。"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.type === 'factual' && ['custom','diagnosis'].includes(o.kb_category);

# ─── 10 additional factual cases omitted in plan but REQUIRED at implementation ──
# Cover: diagnosis x4 more, medication x3 more, followup x3 more, custom x1 more.
# Pattern: (original wrong fact, edited right fact) → assert type=factual + category + non-empty rule
```

**At implementation time:** the agent MUST flesh this file out to ≥ 30 factual + 5 context_specific + 10 style before the baseline-capture PR. The skeleton above anchors the pattern.

- [ ] **Step 3: Register runner** (project-specific — check existing prompt test discovery)

Run: `find tests/prompts -name conftest.py -o -name pytest.ini` and confirm whether case files are auto-discovered or manually listed. If manual, add `persona-classify` to the discovery list in whichever file registers the eval suite.

- [ ] **Step 4: Smoke-run one case**

Run: `.venv/bin/pytest tests/prompts/ -k persona_classify_drug_swap -v`
Expected: either PASS (LLM available + API key set) or SKIP (no API key in CI). A hard FAIL means the case or wrapper is broken.

- [ ] **Step 5: Commit**

```bash
git add tests/prompts/cases/persona-classify.yaml tests/prompts/wrappers/persona-classify.md
git commit -m "test(prompts): persona-classify eval cases (style + factual + context)"
```

---

## Task 5: Baseline capture

**Files:** (no new files; run in separate PR as spec §8 requires)

- [ ] **Step 1: Run full eval and save baseline**

Run: `.venv/bin/pytest tests/prompts/ -k persona_classify -v > /tmp/persona-classify-baseline.txt 2>&1`

- [ ] **Step 2: Record baseline pass-rate in the PR description**

The PR description for the main implementation must include: "Baseline pass rate: N / M cases passed. Regression gate: ≥ N-2%."

- [ ] **Step 3: Commit no code changes — this task is procedural only**

The baseline-capture PR is just running the eval after Task 3+4 land, recording the number, and wiring the regression gate into CI (if CI runs prompt evals). If CI doesn't run prompt evals, this task becomes a manual check before merging Phase 3+ work.

---

# Phase 3 — Pydantic contract

## Task 6: Rewrite `persona_classifier.py` with strict model

**Files:**
- Modify: `src/domain/knowledge/persona_classifier.py`
- Test: `tests/core/test_fact_routing.py` (created in Task 13)

- [ ] **Step 1: Replace file contents**

```python
"""Classify doctor edits as style/factual/context-specific; emit typed model."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from utils.log import log
from utils.prompt_loader import get_prompt_sync


class LearningType(str, Enum):
    style = "style"
    factual = "factual"
    context_specific = "context_specific"


class PersonaField(str, Enum):
    reply_style = "reply_style"
    closing = "closing"
    structure = "structure"
    avoid = "avoid"
    edits = "edits"


class KbCategory(str, Enum):
    custom = "custom"
    diagnosis = "diagnosis"
    followup = "followup"
    medication = "medication"


class ClassifyResult(BaseModel):
    type: LearningType
    persona_field: Optional[PersonaField] = None
    summary: str = Field(min_length=1, max_length=500)
    confidence: Literal["low", "medium", "high"]
    kb_category: Optional[KbCategory] = None
    proposed_kb_rule: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _enforce_type_contract(self) -> "ClassifyResult":
        if self.type == LearningType.style:
            if not self.persona_field:
                raise ValueError("persona_field required when type=style")
            if self.kb_category or self.proposed_kb_rule:
                raise ValueError("kb fields must be empty when type=style")
        elif self.type == LearningType.factual:
            if not self.kb_category:
                raise ValueError("kb_category required when type=factual")
            if not self.proposed_kb_rule.strip():
                raise ValueError("proposed_kb_rule required when type=factual")
            if self.persona_field:
                raise ValueError("persona_field must be empty when type=factual")
        else:  # context_specific
            if self.persona_field or self.kb_category or self.proposed_kb_rule:
                raise ValueError("all learning fields must be empty when type=context_specific")
        return self


def compute_pattern_hash(field: str, summary: str) -> str:
    """Persona-side hash (signature unchanged — existing callers expect this)."""
    normalized = f"{field}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def compute_kb_pattern_hash(category: str, summary: str) -> str:
    """KB-side hash — distinct namespace prevents collision with persona hashes."""
    normalized = f"kb:{category}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _coerce_empty_to_none(raw: dict) -> dict:
    """Prompt emits '' for empty optional enums; convert to None before Pydantic."""
    out = dict(raw)
    for key in ("persona_field", "kb_category"):
        if out.get(key) == "":
            out[key] = None
    return out


async def classify_edit(original: str, edited: str) -> Optional[ClassifyResult]:
    """Classify a doctor edit using LLM. Returns ClassifyResult or None on any failure."""
    if not original or not edited:
        return None
    if original.strip() == edited.strip():
        return None

    template = get_prompt_sync("persona-classify")
    prompt = template.format(
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

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        raw = json.loads(text)
        coerced = _coerce_empty_to_none(raw)
        return ClassifyResult.model_validate(coerced)
    except (json.JSONDecodeError, ValidationError) as exc:
        log(f"[persona_classifier] invalid output: {exc}", level="warning")
        return None
    except Exception as exc:
        log(f"[persona_classifier] unexpected error: {exc}", level="warning")
        return None
```

- [ ] **Step 2: Smoke check**

Run: `.venv/bin/python -c "from domain.knowledge.persona_classifier import ClassifyResult, LearningType, PersonaField, KbCategory, compute_kb_pattern_hash; r = ClassifyResult(type='factual', summary='x', confidence='high', kb_category='medication', proposed_kb_rule='y'); print(r)"`
Expected: prints a `ClassifyResult` with `type=LearningType.factual`.

Also run a negative case:
```bash
.venv/bin/python -c "from domain.knowledge.persona_classifier import ClassifyResult; ClassifyResult(type='factual', summary='x', confidence='high')"
```
Expected: `ValidationError` mentioning "kb_category required when type=factual".

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/persona_classifier.py
git commit -m "feat(persona): strict Pydantic ClassifyResult with cross-field contract"
```

---

# Phase 4 — Shared helpers + pipeline

## Task 7: Shared `pending_common.py`

**Files:**
- Create: `src/domain/knowledge/pending_common.py`

- [ ] **Step 1: Write the helpers**

```python
"""Shared helpers for pending-item routing (persona + kb tracks)."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Type

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import Base
from utils.log import log


# PII patterns — applied to proposed_rule, summary, evidence_summary
_PII_PATTERNS = [
    (re.compile(r"(?:姓名|名字)[：:]\s*[\u4e00-\u9fa5A-Za-z]{1,6}"), "[已脱敏]"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "[已脱敏]"),                        # mobile
    (re.compile(r"\b\d{17}[\dXx]\b"), "[已脱敏]"),                       # ID card
    (re.compile(r"(?:住院号|病历号)[：:]*\s*\d{4,}"), "[已脱敏]"),
    (re.compile(r"\b\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?\b"), "[已脱敏]"),  # date
]


def scrub_pii(text: str) -> str:
    """Replace recognised PII patterns with `[已脱敏]`. Returns cleaned text."""
    if not text:
        return text
    cleaned = text
    for pat, repl in _PII_PATTERNS:
        cleaned = pat.sub(repl, cleaned)
    return cleaned


async def is_pattern_suppressed(
    session: AsyncSession,
    table_cls: Type[Base],
    doctor_id: str,
    pattern: str,
    window_days: int = 90,
) -> bool:
    """True if a matching rejected pending row exists within the suppression window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    count = (await session.execute(
        select(func.count()).select_from(table_cls).where(
            table_cls.doctor_id == doctor_id,
            table_cls.pattern_hash == pattern,
            table_cls.status == "rejected",
            table_cls.updated_at > cutoff,
        )
    )).scalar() or 0
    return count > 0


async def savepoint_insert_pending(
    session: AsyncSession,
    table_cls: Type[Base],
    doctor_id: str,
    pattern: str,
    row_factory,
) -> object | None:
    """Insert a pending row inside a savepoint. On duplicate or race, returns None.

    `row_factory` is a zero-arg callable returning a new ORM instance to add.
    """
    try:
        async with session.begin_nested():  # SAVEPOINT
            stmt = select(table_cls).where(
                table_cls.doctor_id == doctor_id,
                table_cls.pattern_hash == pattern,
                table_cls.status == "pending",
            ).with_for_update()   # no-op on SQLite; row lock on MySQL
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                log(f"[pending_common] duplicate pending pattern={pattern}, skipping")
                return None
            row = row_factory()
            session.add(row)
            await session.flush()
            return row
    except IntegrityError:
        log(f"[pending_common] unique-constraint race on pattern={pattern}, skipping")
        return None
```

- [ ] **Step 2: Smoke import**

Run: `.venv/bin/python -c "from domain.knowledge.pending_common import scrub_pii; print(scrub_pii('姓名：张三 手机号13800138000'))"`
Expected: `[已脱敏] 手机号[已脱敏]` (or similar with both patterns replaced).

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/pending_common.py
git commit -m "feat(knowledge): shared pending-item helpers (PII scrub, suppression, savepoint insert)"
```

---

## Task 8: Extend `save_knowledge_item`

**Files:**
- Modify: `src/domain/knowledge/knowledge_crud.py`

- [ ] **Step 1: Edit the function signature**

Locate `save_knowledge_item` at line 190. Change signature to:

```python
async def save_knowledge_item(
    session,
    doctor_id: str,
    text: str,
    source: str = "doctor",
    confidence: float = 1.0,
    category: str = KnowledgeCategory.custom,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    source_url: Optional[str] = None,
    file_path: Optional[str] = None,
    seed_source: Optional[str] = None,
) -> Optional[DoctorKnowledgeItem]:
```

Inside the function, after the existing `item.summary = summary` line (around line 221), add:

```python
    if seed_source:
        item.seed_source = seed_source
```

- [ ] **Step 2: Verify all existing callers still pass (param is optional)**

Run: `.venv/bin/python -m pytest tests/ -k 'knowledge and not e2e' -x` (or whatever subset exists).
Expected: no errors related to `save_knowledge_item` signature.

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/knowledge_crud.py
git commit -m "feat(knowledge): save_knowledge_item accepts seed_source for provenance tracking"
```

---

## Task 9: Refactor `persona_learning.py` — dual-track routing

**Files:**
- Modify: `src/domain/knowledge/persona_learning.py`

- [ ] **Step 1: Replace the file**

```python
"""Dual-track learning pipeline: style → PersonaPendingItem, factual → KbPendingItem."""

from __future__ import annotations

import json
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.persona_pending import PersonaPendingItem
from db.models.kb_pending import KbPendingItem
from domain.knowledge.persona_classifier import (
    ClassifyResult,
    KbCategory,
    LearningType,
    classify_edit,
    compute_kb_pattern_hash,
    compute_pattern_hash,
)
from domain.knowledge.pending_common import (
    is_pattern_suppressed,
    savepoint_insert_pending,
    scrub_pii,
)
from utils.log import log


FACT_LEARNING_ENABLED = os.getenv("FACT_LEARNING_ENABLED", "1") == "1"


async def process_edit_for_learning(
    session: AsyncSession,
    doctor_id: str,
    original: str,
    edited: str,
    edit_id: int,
) -> Optional[ClassifyResult]:
    """Classify a doctor edit and route to the matching pending track."""
    result = await classify_edit(original, edited)
    if not result:
        return None

    if result.type == LearningType.style:
        return await _route_to_persona_pending(session, doctor_id, result, edit_id)
    if result.type == LearningType.factual:
        if not FACT_LEARNING_ENABLED:
            log(f"[learning] edit={edit_id} fact routing disabled by flag, skipping")
            return None
        return await _route_to_kb_pending(session, doctor_id, result, edit_id)
    # context_specific — intentionally drop
    log(f"[learning] edit={edit_id} type={result.type.value} skipping")
    return None


async def _route_to_persona_pending(
    session: AsyncSession,
    doctor_id: str,
    result: ClassifyResult,
    edit_id: int,
) -> Optional[ClassifyResult]:
    if result.confidence == "low":
        log(f"[learning] edit={edit_id} style low confidence, skipping")
        return None

    field = result.persona_field.value if result.persona_field else None
    if not field:
        return None
    pattern = compute_pattern_hash(field, result.summary)

    if await is_pattern_suppressed(session, PersonaPendingItem, doctor_id, pattern):
        log(f"[learning] edit={edit_id} persona pattern suppressed, skipping")
        return None

    def _factory():
        return PersonaPendingItem(
            doctor_id=doctor_id,
            field=field,
            proposed_rule=result.summary,
            summary=result.summary,
            evidence_summary=result.summary,
            evidence_edit_ids=json.dumps([edit_id]),
            confidence=result.confidence,
            pattern_hash=pattern,
        )

    row = await savepoint_insert_pending(session, PersonaPendingItem, doctor_id, pattern, _factory)
    if row is not None:
        log(f"[learning] edit={edit_id} created persona pending id={row.id}")
    return result


async def _route_to_kb_pending(
    session: AsyncSession,
    doctor_id: str,
    result: ClassifyResult,
    edit_id: int,
) -> Optional[ClassifyResult]:
    category = result.kb_category.value if result.kb_category else None
    if not category:
        return None

    scrubbed_rule = scrub_pii(result.proposed_kb_rule)
    scrubbed_summary = scrub_pii(result.summary)
    scrubbed_evidence = scrub_pii(result.summary)

    if len(scrubbed_rule.strip()) < 10:
        log(f"[learning] edit={edit_id} kb rule too short after scrub, skipping")
        return None

    pattern = compute_kb_pattern_hash(category, scrubbed_summary)

    if await is_pattern_suppressed(session, KbPendingItem, doctor_id, pattern):
        log(f"[learning] edit={edit_id} kb pattern suppressed, skipping")
        return None

    def _factory():
        return KbPendingItem(
            doctor_id=doctor_id,
            category=category,
            proposed_rule=scrubbed_rule,
            summary=scrubbed_summary,
            evidence_summary=scrubbed_evidence,
            evidence_edit_ids=json.dumps([edit_id]),
            confidence=result.confidence,
            pattern_hash=pattern,
        )

    row = await savepoint_insert_pending(session, KbPendingItem, doctor_id, pattern, _factory)
    if row is not None:
        log(
            f"[learning] edit={edit_id} type=factual category={category} "
            f"confidence={result.confidence} kb_pending_id={row.id}"
        )
    return result
```

- [ ] **Step 2: Confirm old entry-point name still compiles via alias (backwards-compat shim)**

Append to the same file:

```python
# Backwards-compat shim — remove after Task 10 renames the caller.
process_edit_for_persona = process_edit_for_learning
```

- [ ] **Step 3: Commit**

```bash
git add src/domain/knowledge/persona_learning.py
git commit -m "feat(learning): route style→persona and factual→kb pending; add fact_learning flag"
```

---

# Phase 5 — Decouple draft_handlers

## Task 10: Lift `log_doctor_edit` + classifier out of the gate

**Files:**
- Modify: `src/channels/web/doctor_dashboard/draft_handlers.py`

- [ ] **Step 1: Update imports at top of file**

Find the existing `from domain.knowledge.teaching import ...` block (around line 29). Change the persona-learning import:

Replace:
```python
from domain.knowledge.persona_learning import process_edit_for_persona
```
With:
```python
from domain.knowledge.persona_learning import process_edit_for_learning
```

Find the `_process_edit_for_persona_bg` helper (around line 40) and rename the function AND its body to:

```python
async def _process_edit_for_learning_bg(doctor_id: str, original: str, edited: str, edit_id: int):
    """Fire-and-forget: run dual-track learning classifier in a fresh session."""
    try:
        async with AsyncSessionLocal() as session:
            await process_edit_for_learning(session, doctor_id, original, edited, edit_id)
            await session.commit()
    except Exception as exc:
        log(f"[draft_handlers] learning bg task failed: {exc}", level="warning")
```

- [ ] **Step 2: Replace the gated section (lines 420-440)**

Locate the block starting at `# Teaching loop: check if edit is significant`. Replace the entire block through the `asyncio.ensure_future(...)` line with:

```python
    # Always log the edit — provides edit_id for learning pipeline
    edit_id = await log_doctor_edit(
        db,
        doctor_id=resolved,
        entity_type="draft_reply",
        entity_id=draft_id,
        original_text=original_text,
        edited_text=edited_text,
    )

    # Teach-prompt UI is still gated by significance
    teach_prompt = should_prompt_teaching(original_text, edited_text)

    await db.commit()

    # Always fire the learning pipeline regardless of gate
    import asyncio
    asyncio.ensure_future(_process_edit_for_learning_bg(resolved, original_text, edited_text, edit_id))
```

- [ ] **Step 3: Run the existing draft-handler tests to ensure no regression**

Run: `.venv/bin/python -m pytest tests/ -k 'draft' -x -v`
Expected: all pass. If any test asserted that `edit_id is None` when the gate fires False, update the assertion to reflect the new "always log" behavior.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/doctor_dashboard/draft_handlers.py
git commit -m "feat(draft): decouple log_doctor_edit + learning pipeline from teach_prompt gate"
```

---

# Phase 6 — KB pending API

## Task 11: `kb_pending_handlers.py`

**Files:**
- Create: `src/channels/web/doctor_dashboard/kb_pending_handlers.py`

- [ ] **Step 1: Write the handler module**

```python
"""KB pending items API — list, accept, reject factual-edit suggestions."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.doctor import KnowledgeCategory
from db.models.kb_pending import KbPendingItem
from domain.knowledge.knowledge_crud import save_knowledge_item
from domain.knowledge.knowledge_context import invalidate_knowledge_cache
from utils.log import log


router = APIRouter(tags=["ui"], include_in_schema=False)


VALID_CATEGORIES = {c.value for c in KnowledgeCategory}


@router.get("/api/manage/kb/pending")
async def list_pending_items(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(
            KbPendingItem.doctor_id == resolved,
            KbPendingItem.status == "pending",
        ).order_by(KbPendingItem.created_at.desc())
    )
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "proposed_rule": item.proposed_rule,
                "summary": item.summary,
                "evidence_summary": item.evidence_summary,
                "confidence": item.confidence,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "count": len(items),
    }


@router.post("/api/manage/kb/pending/{item_id}/accept")
async def accept_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(KbPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")
    if item.status != "pending":
        raise HTTPException(409, f"Item already {item.status}")
    if item.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category: {item.category!r}")

    # save_knowledge_item commits internally — do not wrap in outer txn.
    kb_item = await save_knowledge_item(
        session,
        doctor_id=resolved,
        text=item.proposed_rule,
        source="doctor",
        confidence=1.0,
        category=item.category,
        seed_source="edit_fact",
    )
    if kb_item is None:
        raise HTTPException(500, "Failed to save knowledge item")

    item.status = "accepted"
    item.accepted_knowledge_item_id = kb_item.id
    await session.commit()

    invalidate_knowledge_cache(resolved)

    log(
        f"[kb_pending] accepted id={item.id} doctor={resolved} "
        f"category={item.category} knowledge_item_id={kb_item.id}"
    )
    return {
        "status": "ok",
        "knowledge_item_id": kb_item.id,
        "title": kb_item.title,
    }


@router.post("/api/manage/kb/pending/{item_id}/reject")
async def reject_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(KbPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")
    if item.status != "pending":
        raise HTTPException(409, f"Item already {item.status}")

    item.status = "rejected"
    await session.commit()
    log(f"[kb_pending] rejected id={item.id} doctor={resolved}")
    return {"status": "ok"}
```

- [ ] **Step 2: Register the router**

Search for where `persona_pending_handlers.router` is registered:

Run: `grep -rn "persona_pending_handlers" src/ | grep -v __pycache__`

Add a sibling line in the same file (typically `src/cli.py` or an app-factory module). Example pattern:

```python
from channels.web.doctor_dashboard import kb_pending_handlers
app.include_router(kb_pending_handlers.router)
```

- [ ] **Step 3: Smoke test the route**

Start the server (if not running) and curl:
```bash
curl -s "http://localhost:8000/api/manage/kb/pending?doctor_id=TEST" -H "Authorization: Bearer <jwt>" | jq .
```
Expected: `{"items": [], "count": 0}` for an empty doctor (or 403 if auth wrong).

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/doctor_dashboard/kb_pending_handlers.py src/cli.py
git commit -m "feat(api): kb_pending endpoints (list/accept/reject)"
```

---

# Phase 7 — Backend tests

## Task 12: Unit tests — `test_fact_routing.py`

**Files:**
- Create: `tests/core/test_fact_routing.py`

- [ ] **Step 1: Write tests**

```python
"""Unit tests for fact-branch routing: Pydantic contract, PII scrub, hash helpers."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock

from domain.knowledge.persona_classifier import (
    ClassifyResult,
    KbCategory,
    LearningType,
    PersonaField,
    classify_edit,
    compute_kb_pattern_hash,
    compute_pattern_hash,
)
from domain.knowledge.pending_common import scrub_pii


def test_classify_result_style_requires_persona_field():
    with pytest.raises(ValueError, match="persona_field required"):
        ClassifyResult(
            type=LearningType.style,
            summary="x", confidence="high",
        )


def test_classify_result_style_rejects_kb_fields():
    with pytest.raises(ValueError, match="kb fields must be empty"):
        ClassifyResult(
            type=LearningType.style,
            persona_field=PersonaField.closing,
            summary="x", confidence="high",
            kb_category=KbCategory.diagnosis,
        )


def test_classify_result_factual_requires_kb_category():
    with pytest.raises(ValueError, match="kb_category required"):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            proposed_kb_rule="some rule",
        )


def test_classify_result_factual_requires_non_empty_rule():
    with pytest.raises(ValueError, match="proposed_kb_rule required"):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            kb_category=KbCategory.diagnosis,
            proposed_kb_rule="   ",
        )


def test_classify_result_context_specific_rejects_all_learning_fields():
    with pytest.raises(ValueError, match="all learning fields must be empty"):
        ClassifyResult(
            type=LearningType.context_specific,
            persona_field=PersonaField.reply_style,
            summary="x", confidence="high",
        )


def test_classify_result_factual_valid():
    r = ClassifyResult(
        type=LearningType.factual,
        summary="修正了药名",
        confidence="high",
        kb_category=KbCategory.medication,
        proposed_kb_rule="硝苯地平而非氨氯地平",
    )
    assert r.type == LearningType.factual
    assert r.kb_category == KbCategory.medication
    assert r.persona_field is None


def test_classify_result_rule_too_long_fails():
    with pytest.raises(ValueError):
        ClassifyResult(
            type=LearningType.factual,
            summary="x", confidence="high",
            kb_category=KbCategory.custom,
            proposed_kb_rule="a" * 301,
        )


def test_kb_pattern_hash_differs_from_persona():
    # Same inputs, different hash namespaces must not collide
    p = compute_pattern_hash("closing", "foo")
    k = compute_kb_pattern_hash("closing", "foo")
    assert p != k


def test_scrub_pii_phone():
    out = scrub_pii("call me at 13800138000 tomorrow")
    assert "13800138000" not in out
    assert "[已脱敏]" in out


def test_scrub_pii_name_label():
    out = scrub_pii("姓名：张三去年手术")
    assert "张三" not in out
    assert "[已脱敏]" in out


def test_scrub_pii_idcard():
    out = scrub_pii("ID 110101199001011234 here")
    assert "110101199001011234" not in out


def test_scrub_pii_date():
    out = scrub_pii("术后2024-03-15复查")
    assert "2024-03-15" not in out


def test_scrub_pii_noop_on_clean_text():
    clean = "颅脑术后头痛患者不建议使用NSAIDs"
    assert scrub_pii(clean) == clean


@pytest.mark.asyncio
async def test_classify_edit_rejects_identical_text():
    assert await classify_edit("same", "same") is None


@pytest.mark.asyncio
async def test_classify_edit_returns_none_on_invalid_llm_output():
    from domain.knowledge import persona_classifier as pc

    with patch.object(pc, "llm_call", new=AsyncMock(return_value="not json")):
        # Also patch prompt loader to avoid FS dependency in test
        with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
            r = await classify_edit("a", "b")
            assert r is None


@pytest.mark.asyncio
async def test_classify_edit_parses_factual_response():
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "factual",
        "persona_field": "",
        "summary": "修正药名",
        "confidence": "high",
        "kb_category": "medication",
        "proposed_kb_rule": "硝苯地平 not 氨氯地平",
    }
    with patch.object(pc, "llm_call", new=AsyncMock(return_value=json.dumps(payload))):
        with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
            r = await classify_edit("use A", "use B")
            assert r is not None
            assert r.type == LearningType.factual
            assert r.kb_category == KbCategory.medication
```

- [ ] **Step 2: Run and verify PASS**

Run: `.venv/bin/python -m pytest tests/core/test_fact_routing.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_fact_routing.py
git commit -m "test(learning): unit tests for ClassifyResult, hash helpers, PII scrub"
```

---

## Task 13: Integration test — `test_kb_pending.py`

**Files:**
- Create: `tests/integration/test_kb_pending.py`

- [ ] **Step 1: Write the test**

```python
"""Integration: factual edit → KbPendingItem → accept → DoctorKnowledgeItem."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor, DoctorKnowledgeItem
from db.models.kb_pending import KbPendingItem
from domain.knowledge.persona_learning import process_edit_for_learning


@pytest.fixture
async def doctor_id(db_session):
    """Create a test doctor; return doctor_id."""
    doctor = Doctor(doctor_id="TEST_FACT_DOC", name="Test", specialty="test")
    db_session.add(doctor)
    await db_session.commit()
    yield "TEST_FACT_DOC"
    # Cleanup via CASCADE when doctor row is removed by test DB teardown


@pytest.mark.asyncio
async def test_factual_edit_creates_kb_pending(db_session, doctor_id):
    from domain.knowledge import persona_classifier as pc

    llm_payload = {
        "type": "factual",
        "persona_field": "",
        "summary": "修正药名",
        "confidence": "high",
        "kb_category": "medication",
        "proposed_kb_rule": "硝苯地平而非氨氯地平",
    }
    with patch.object(pc, "llm_call", new=AsyncMock(return_value=json.dumps(llm_payload))):
        with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
            await process_edit_for_learning(
                db_session, doctor_id,
                "原 use 氨氯地平", "edited use 硝苯地平", edit_id=1,
            )
    await db_session.commit()

    from sqlalchemy import select
    rows = (await db_session.execute(
        select(KbPendingItem).where(KbPendingItem.doctor_id == doctor_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].category == "medication"
    assert "硝苯地平" in rows[0].proposed_rule


@pytest.mark.asyncio
async def test_duplicate_factual_edit_skipped(db_session, doctor_id):
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "factual", "persona_field": "",
        "summary": "修正药名", "confidence": "high",
        "kb_category": "medication", "proposed_kb_rule": "硝苯地平",
    }
    with patch.object(pc, "llm_call", new=AsyncMock(return_value=json.dumps(payload))):
        with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
            await process_edit_for_learning(db_session, doctor_id, "a", "b", edit_id=1)
            await process_edit_for_learning(db_session, doctor_id, "a", "b", edit_id=2)
    await db_session.commit()

    from sqlalchemy import select, func
    from db.models.kb_pending import KbPendingItem as K
    cnt = (await db_session.execute(
        select(func.count()).select_from(K).where(K.doctor_id == doctor_id)
    )).scalar()
    assert cnt == 1


@pytest.mark.asyncio
async def test_style_edit_does_not_create_kb(db_session, doctor_id):
    from domain.knowledge import persona_classifier as pc

    payload = {
        "type": "style", "persona_field": "closing",
        "summary": "删除祝福语", "confidence": "high",
        "kb_category": "", "proposed_kb_rule": "",
    }
    with patch.object(pc, "llm_call", new=AsyncMock(return_value=json.dumps(payload))):
        with patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"):
            await process_edit_for_learning(db_session, doctor_id, "a ending", "a", edit_id=1)
    await db_session.commit()

    from sqlalchemy import select, func
    cnt = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(KbPendingItem.doctor_id == doctor_id)
    )).scalar()
    assert cnt == 0


@pytest.mark.asyncio
async def test_accept_endpoint_writes_kb(db_session, doctor_id, async_client):
    """Create a pending row, POST accept, verify DoctorKnowledgeItem exists."""
    pending = KbPendingItem(
        doctor_id=doctor_id,
        category="medication",
        proposed_rule="硝苯地平 daily",
        summary="硝苯地平",
        evidence_summary="e",
        confidence="high",
        pattern_hash="abc123",
    )
    db_session.add(pending)
    await db_session.commit()

    resp = await async_client.post(
        f"/api/manage/kb/pending/{pending.id}/accept",
        params={"doctor_id": doctor_id},
        headers={"Authorization": f"Bearer {_make_test_jwt(doctor_id)}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "knowledge_item_id" in data

    from sqlalchemy import select
    kb = (await db_session.execute(
        select(DoctorKnowledgeItem).where(DoctorKnowledgeItem.id == data["knowledge_item_id"])
    )).scalar_one()
    assert kb.doctor_id == doctor_id
    assert kb.category == "medication"
    assert kb.seed_source == "edit_fact"

    await db_session.refresh(pending)
    assert pending.status == "accepted"
    assert pending.accepted_knowledge_item_id == kb.id


@pytest.mark.asyncio
async def test_reject_endpoint_sets_status(db_session, doctor_id, async_client):
    pending = KbPendingItem(
        doctor_id=doctor_id, category="medication",
        proposed_rule="x", summary="x", evidence_summary="x",
        confidence="high", pattern_hash="def456",
    )
    db_session.add(pending)
    await db_session.commit()

    resp = await async_client.post(
        f"/api/manage/kb/pending/{pending.id}/reject",
        params={"doctor_id": doctor_id},
        headers={"Authorization": f"Bearer {_make_test_jwt(doctor_id)}"},
    )
    assert resp.status_code == 200

    await db_session.refresh(pending)
    assert pending.status == "rejected"


# Helper — project-specific JWT generation for tests. Use whatever conftest pattern exists.
def _make_test_jwt(doctor_id: str) -> str:
    # If the test suite has a helper like tests/helpers/jwt.py, import it here.
    # If not, replace this shim with the project's usual test auth pattern.
    from utils.jwt_utils import encode_jwt  # adjust import if path differs
    return encode_jwt({"sub": doctor_id})
```

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m pytest tests/integration/test_kb_pending.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`
Expected: all pass. If `_make_test_jwt` or `async_client`/`db_session` fixtures differ, adapt to the project's existing conftest.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_kb_pending.py
git commit -m "test(kb_pending): integration — edit→pending→accept→KB, reject, dedup"
```

---

# Phase 8 — Frontend

## Task 14: API + query hooks

**Files:**
- Modify: `frontend/web/src/api.js`
- Modify: `frontend/web/src/lib/doctorQueries.js`

- [ ] **Step 1: Add the three API functions**

Append to `frontend/web/src/api.js` (near the other `/api/manage/knowledge` functions, around line 1035):

```javascript
export async function getKbPending(doctorId) {
  return request(`/api/manage/kb/pending?doctor_id=${encodeURIComponent(doctorId)}`);
}

export async function acceptKbPending(doctorId, itemId) {
  return request(`/api/manage/kb/pending/${itemId}/accept?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
  });
}

export async function rejectKbPending(doctorId, itemId) {
  return request(`/api/manage/kb/pending/${itemId}/reject?doctor_id=${encodeURIComponent(doctorId)}`, {
    method: "POST",
  });
}
```

- [ ] **Step 2: Add query hooks**

In `frontend/web/src/lib/doctorQueries.js`, find the existing `QK` object and add:

```javascript
kbPending: (doctorId) => ["kb-pending", doctorId],
```

Then add the three hooks near `usePersonaPending` (around line 162):

```javascript
export function useKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.kbPending(doctorId),
    queryFn:  () => api.getKbPending(doctorId),
    enabled:  !!doctorId,
    staleTime: 30_000,
    refetchInterval: POLL,
  });
}

export function useAcceptKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.acceptKbPending(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.kbPending(doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.knowledgeItems(doctorId) });
    },
  });
}

export function useRejectKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.rejectKbPending(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.kbPending(doctorId) });
    },
  });
}
```

- [ ] **Step 3: Confirm `api.getKbPending` is exposed via `useApi`**

Check `frontend/web/src/lib/apiContext.jsx` (or wherever `useApi` is defined) to confirm it returns the full `api.js` exports. If it uses an explicit allowlist, add `getKbPending`, `acceptKbPending`, `rejectKbPending` to it.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api.js frontend/web/src/lib/doctorQueries.js
git commit -m "feat(web): api + TanStack Query hooks for kb_pending endpoints"
```

---

## Task 15: `KbPendingSubpage.jsx`

**Files:**
- Create: `frontend/web/src/pages/doctor/subpages/KbPendingSubpage.jsx`

- [ ] **Step 1: Read the existing persona variant for reference**

Run: `head -160 frontend/web/src/pages/doctor/subpages/PendingReviewSubpage.jsx` — mirror its structure.

- [ ] **Step 2: Write the subpage**

```jsx
/**
 * KbPendingSubpage — review AI-discovered factual-edit rules, accept to write to KB.
 * Parallel to PendingReviewSubpage but persists to doctor_knowledge_items on accept.
 */

import React from "react";
import { Box, Typography, Chip } from "@mui/material";
import { useKbPending, useAcceptKbPending, useRejectKbPending } from "../../../lib/doctorQueries";
import PageSkeleton from "../../../components/PageSkeleton";
import AppButton from "../../../components/AppButton";
import EmptyState from "../../../components/EmptyState";
import SectionLoading from "../../../components/SectionLoading";
import ConfirmDialog from "../../../components/ConfirmDialog";
import { COLOR, TYPE, RADIUS } from "../../../theme";

const CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "通用",
};

export default function KbPendingSubpage({ onBack, isMobile }) {
  const { data, isLoading } = useKbPending();
  const accept = useAcceptKbPending();
  const reject = useRejectKbPending();
  const [confirmReject, setConfirmReject] = React.useState(null);

  const items = data?.items || [];

  const content = isLoading ? (
    <SectionLoading />
  ) : items.length === 0 ? (
    <EmptyState message="暂无待确认的临床规则" />
  ) : (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2 }}>
      {items.map((item) => (
        <KbPendingCard
          key={item.id}
          item={item}
          onAccept={() => accept.mutate(item.id)}
          onReject={() => setConfirmReject(item)}
          busy={accept.isPending || reject.isPending}
        />
      ))}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="待确认的临床规则"
        onBack={onBack}
        mobileView={isMobile}
      >
        {content}
      </PageSkeleton>
      <ConfirmDialog
        open={!!confirmReject}
        title="确认排除这条规则？"
        body="排除后 90 天内不会再次提示相同模式。"
        cancelLabel="取消"
        confirmLabel="确认排除"
        danger
        onCancel={() => setConfirmReject(null)}
        onConfirm={() => {
          reject.mutate(confirmReject.id);
          setConfirmReject(null);
        }}
      />
    </>
  );
}


function KbPendingCard({ item, onAccept, onReject, busy }) {
  return (
    <Box
      sx={{
        bgcolor: COLOR.white,
        border: `1px solid ${COLOR.borderLight}`,
        borderRadius: RADIUS.md,
        p: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Chip
          label={CATEGORY_LABELS[item.category] || item.category}
          size="small"
          sx={{ bgcolor: COLOR.surfaceAlt, fontSize: TYPE.caption.fontSize }}
        />
        <Chip
          label={`置信度：${item.confidence}`}
          size="small"
          variant="outlined"
          sx={{ fontSize: TYPE.caption.fontSize }}
        />
      </Box>

      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.55 }}>
        {item.proposed_rule}
      </Typography>

      {item.evidence_summary && (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          依据：{item.evidence_summary}
        </Typography>
      )}

      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", mt: 1 }}>
        <AppButton variant="secondary" size="sm" onClick={onReject} disabled={busy}>
          排除
        </AppButton>
        <AppButton variant="primary" size="sm" onClick={onAccept} disabled={busy}>
          保存为规则
        </AppButton>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/KbPendingSubpage.jsx
git commit -m "feat(web): KbPendingSubpage for factual-edit review"
```

---

## Task 16: Badge + route wiring

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx`
- Modify: `frontend/web/src/pages/doctor/SettingsPage.jsx`

- [ ] **Step 1: Add pending-count badge to KnowledgeSubpage**

Locate `KnowledgeSubpage.jsx` imports and add:

```jsx
import { useKbPending } from "../../../lib/doctorQueries";
import { useNavigate } from "react-router-dom";
```

Near the top of the default-exported component, add:

```jsx
  const { data: kbPendingData } = useKbPending();
  const kbPendingCount = kbPendingData?.count || 0;
  const navigate = useNavigate();
```

Render a clickable banner above the knowledge list (adapt to existing JSX structure):

```jsx
  {kbPendingCount > 0 && (
    <Box
      onClick={() => navigate("/doctor/settings/knowledge/pending")}
      sx={{
        p: 1.5, m: 1.5, cursor: "pointer",
        bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.md,
        display: "flex", alignItems: "center", gap: 1,
      }}
    >
      <Chip label="新" size="small" color="warning" />
      <Typography sx={{ fontSize: TYPE.body.fontSize }}>
        AI 从您的编辑中发现 {kbPendingCount} 条待确认临床规则
      </Typography>
    </Box>
  )}
```

- [ ] **Step 2: Register the route in SettingsPage**

In `frontend/web/src/pages/doctor/SettingsPage.jsx`, near the existing `persona/pending` handling (search for "PendingReviewSubpage"):

Add an import:
```jsx
import KbPendingSubpage from "./subpages/KbPendingSubpage";
```

Add a route-handling branch mirroring the existing pattern. Example (adapt to the file's router structure):

```jsx
  // Mobile branch
  ) : isMobile && subpage === "knowledge/pending" ? (
    <KbPendingSubpage onBack={goBack} isMobile />

  // Desktop branch
  ) : subpage === "knowledge/pending" ? (
    <KbPendingSubpage onBack={goBack} />
```

Also add `"pending"` to the `KNOWLEDGE_SUB_IDS` array (or equivalent) if that file uses one (mirror the existing `PERSONA_SUB_IDS = ["onboarding", "pending", "teach"]` pattern).

- [ ] **Step 3: Manual smoke test**

Start backend + frontend (if not running). Open a doctor account that has at least one `KbPendingItem` row (create one via integration test or direct DB insert). Navigate to the Knowledge tab. Click the banner. Verify:
- Page loads without console errors
- Accept button writes to DoctorKnowledgeItem (check DB)
- Reject button sets status=rejected (check DB)

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx frontend/web/src/pages/doctor/SettingsPage.jsx
git commit -m "feat(web): Knowledge page kb-pending badge + route wiring"
```

---

# Phase 9 — E2E citeability

## Task 17: Playwright test — accept → cite

**Files:**
- Create: `frontend/web/tests/e2e/19-kb-pending-citeability.spec.ts`

- [ ] **Step 1: Write the E2E test**

```typescript
import { test, expect } from "@playwright/test";
import { seedDoctor, loginAs, createKbPendingItem, generateDraftReply } from "./fixtures/seed";

test("accepted kb_pending rule is retrieved and cited in subsequent draft", async ({ page, request }) => {
  // 1. Seed a doctor
  const doctor = await seedDoctor(request);

  // 2. Create a KbPendingItem directly (bypasses LLM)
  const pending = await createKbPendingItem(request, doctor.doctorId, {
    category: "medication",
    proposed_rule: "颅脑术后头痛不建议使用NSAIDs，首选对乙酰氨基酚",
    summary: "术后头痛药物选择",
    confidence: "high",
  });

  // 3. Login and navigate to pending review
  await loginAs(page, doctor);
  await page.goto("/doctor/settings/knowledge/pending");

  // 4. Accept the pending item
  await expect(page.getByText("颅脑术后头痛不建议使用NSAIDs")).toBeVisible();
  await page.getByText("保存为规则", { exact: true }).click();

  // 5. Trigger a draft generation that should surface the rule
  const draft = await generateDraftReply(request, doctor.doctorId, {
    patientMessage: "医生我术后头痛想吃布洛芬可以吗",
  });

  // 6. Assert the draft contains [KB-N] and the N matches the new item
  expect(draft.response).toMatch(/\[KB-\d+\]/);
  expect(draft.cited_knowledge_ids.length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Add `createKbPendingItem` + `generateDraftReply` to `fixtures/seed.ts`**

Open `frontend/web/tests/e2e/fixtures/seed.ts` and add helpers. Pattern (adapt to existing exports):

```typescript
export async function createKbPendingItem(request, doctorId, payload) {
  const resp = await request.post(
    `${API_BASE_URL}/api/test/seed/kb-pending?doctor_id=${encodeURIComponent(doctorId)}`,
    { data: payload },
  );
  return resp.json();
}

export async function generateDraftReply(request, doctorId, payload) {
  // Use the existing draft-generation endpoint; adapt to the project's real route.
  const resp = await request.post(
    `${API_BASE_URL}/api/test/draft-reply?doctor_id=${encodeURIComponent(doctorId)}`,
    { data: payload },
  );
  return resp.json();
}
```

**Note:** If `/api/test/seed/kb-pending` doesn't exist, either (a) add a minimal test-only handler behind an env gate, or (b) insert via `request.post` to the accept endpoint AFTER creating a classifier-mocked path. Follow whatever seeding pattern other e2e tests use (check `seed.ts` for `seedKnowledge`).

- [ ] **Step 3: Run**

Both servers must be running (backend `:8000`, frontend `:5173`).

Run: `cd frontend/web && rm -rf test-results && npx playwright test tests/e2e/19-kb-pending-citeability.spec.ts`
Expected: PASS. Inspect `test-results/*/video.webm` if it fails.

- [ ] **Step 4: Add README note**

Create `frontend/web/test-results/19-kb-pending-citeability-*/README.txt` (post-run) describing the flow:
```
Test: 19-kb-pending-citeability
Steps:
1. Seed doctor
2. Create KbPendingItem via test seed endpoint
3. Login, navigate to /doctor/settings/knowledge/pending
4. Click "保存为规则"
5. Trigger draft generation with a matching patient question
6. Assert [KB-N] appears and cited_knowledge_ids non-empty
```

- [ ] **Step 5: Commit**

```bash
git add frontend/web/tests/e2e/19-kb-pending-citeability.spec.ts frontend/web/tests/e2e/fixtures/seed.ts
git commit -m "test(e2e): kb-pending accept flow proves citeability"
```

---

# Final: rollout steps

## Task 18: Feature-flag verification + documentation update

**Files:**
- Modify: `frontend/web/public/wiki/wiki-kb-learning.html`

- [ ] **Step 1: Run the eval baseline before shipping**

Run: `.venv/bin/pytest tests/prompts/ -k persona_classify -v | tee /tmp/persona-baseline.txt`
Expected: ≥ 80% pass rate on factual cases; persona cases unchanged.

- [ ] **Step 2: Update the wiki page**

In `wiki-kb-learning.html`, find gap ① section and append a "Status: shipped 2026-04-16" annotation. Find the rollout table and mark step 1 as done.

- [ ] **Step 3: Flip the feature flag on in production**

Confirm `FACT_LEARNING_ENABLED=1` (default). No deployment change — env var defaults true.

- [ ] **Step 4: Monitor**

Watch `logs/llm_calls.jsonl` for 24h after rollout:
```bash
tail -f logs/llm_calls.jsonl | grep persona_classify
```
Verify:
- `type=factual` rate is 15-40% of total classifications (sanity range)
- No `[persona_classifier] invalid output` spikes above 5% of calls

If factual rate is 0% or >60%, investigate prompt regression.

- [ ] **Step 5: Commit wiki update**

```bash
git add frontend/web/public/wiki/wiki-kb-learning.html
git commit -m "docs(wiki): mark fact-branch routing gap ① as shipped"
```

---

# Self-review checklist (run before handing off)

**Spec coverage:** walk §1-§12 of `2026-04-16-fact-branch-routing-design.md`:
- §1-3 (problem/scope/current state) — no task, documentary ✓
- §4.1 (DB model) — Tasks 1, 2 ✓
- §4.2 (LLM schema) — Tasks 3, 6 ✓
- §4.3 (pipeline integration) — Tasks 6, 9, 10 ✓
- §4.4 (API endpoints) — Task 11 ✓
- §4.5 (`save_knowledge_item`) — Task 8 ✓
- §4.6 (UI + PII scrub) — Tasks 15, 16; scrub lives in Task 7 ✓
- §5 (Pydantic model) — Task 6 ✓
- §6 (state machine) — no code; documentary ✓
- §7 (error modes) — Tasks 6, 9, 11 cover each row ✓
- §8 (rollout) — Task 5 (baseline), Task 18 (rollout) ✓
- §9 (success criteria) — Tasks 4, 17 ✓
- §10 (test plan) — Tasks 4, 12, 13, 17 ✓
- §11 (open questions — all resolved in spec) ✓
- §12 (file changes) — cross-referenced with File Structure table ✓

**Placeholder scan:** "TBD/TODO/similar to/implement later" — none in plan. The eval YAML has skeletons ("10 additional factual cases omitted in plan but REQUIRED") that the implementing agent must expand — this is called out explicitly, not a placeholder in the plan itself.

**Type consistency:**
- `ClassifyResult` / `LearningType` / `PersonaField` / `KbCategory` — consistent names Tasks 6, 9, 12 ✓
- `process_edit_for_learning` — consistent Tasks 9, 10, 13 ✓
- `compute_kb_pattern_hash` — consistent Tasks 6, 9 ✓
- `scrub_pii` — consistent Tasks 7, 9, 12 ✓
- `useKbPending` / `useAcceptKbPending` / `useRejectKbPending` — consistent Tasks 14, 15 ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-16-fact-branch-routing.md`.**

## Execution options

**1. Subagent-Driven (recommended)** — dispatch fresh subagent per task, review between tasks, fast iteration. Voice→rule used this successfully.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

**Which approach?**
