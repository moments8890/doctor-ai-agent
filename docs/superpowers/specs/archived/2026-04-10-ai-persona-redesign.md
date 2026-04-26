# AI Persona (我的AI人设) Redesign

**Date:** 2026-04-10
**Status:** Design approved (v2, post-review), pending implementation plan

## Problem

The current AI persona system has four core problems:

1. **Opacity** — doctor edits 15+ drafts with no feedback, then a persona suddenly
   appears. No visibility into what the system is learning.
2. **All-or-nothing** — extraction overwrites the entire persona text at once. Can't
   accept one insight and reject another.
3. **No iteration** — once extracted, can't say "that's wrong" and have it re-learn.
   Must manually edit text or wait for another 15 edits.
4. **Arbitrary timing** — fixed 15-edit threshold. Sometimes 3 edits show a clear
   pattern. Sometimes 30 aren't enough.

Additionally, persona is stored as a special `DoctorKnowledgeItem` (category=persona),
which creates confusion between persona and knowledge at the data, API, and UI levels.

## Design Decisions

### Two concepts, clearly separated

| | 我的AI人设 | 我的知识库 |
|---|---|---|
| **What** | How the AI behaves | What the AI knows |
| **Contains** | Style + rules + boundaries | Medical facts, protocols, documents |
| **Scope** | Global — applies to every response | Contextual — scored by relevance |
| **Label** | "决定AI怎么说话" | "决定AI知道什么" |
| **Examples** | 口语化回复, 控制3-5句, 不主动提风险 | 术后VAS≤6属正常, 开浦兰副作用列表 |
| **Updates from** | Edits to AI drafts + manual additions | Uploaded documents + manual additions |

The doctor's mental model: **人设 = 我命令AI做什么, 知识 = 我教AI知道什么**.

### Persona owns both style AND rules

No third concept. The persona contains:
- Auto-learned style (tone, phrasing, casualness)
- Explicit rules ("控制在3-5句")
- Boundaries ("不主动提手术风险")

Stored as structured JSON with 5 named fields, not a free-text blob. Each field
is independently editable, updatable, and versionable.

### Rules in persona get citation tracking

Clinical rules stored in persona (e.g., "不推荐非本科室药物") need the same
traceability as KB items. Persona rules are individually tagged with `[P-N]`
markers in AI output, analogous to `[KB-N]` for knowledge items. This ensures:
- Rules are auditable — doctor can see which persona rule shaped a response
- Rules are trackable — usage stats per rule, not just per persona blob
- Rules are verifiable — if a response seems wrong, doctor can trace it to a rule

### KB categories `preference` and `communication` removed

These overlapped with persona. Remaining KB categories:
- `custom` — manual additions (default)
- `diagnosis` — differential diagnosis rules
- `followup` — follow-up protocols
- `medication` — drug/dosage rules

Categories remain internal (not user-facing). Doctor sees a flat knowledge list.

## Lifecycle Redesign

### 1. Onboarding — "Pick Your Style"

**Trigger:** First visit to 我的AI人设 when persona has no active rules
(all fields empty). Distinguished from "skipped" via an `onboarded` boolean
on `doctor_personas` — the lazy-create in the API sets `onboarded=false`,
the onboarding flow sets it to `true` on completion or explicit skip.

**Flow:**
1. Show 3 realistic clinical scenarios (specialty-aware if specialty is set,
   generic fallback otherwise).
   Each scenario shows 2-3 sample AI responses to the same patient message.
   Responses differ subtly — all professional, but different in tone, structure,
   risk communication style.
2. Doctor picks which response sounds most like them for each scenario.
   Every scenario includes a "都不像我 — 我来写一个" escape hatch.
3. System extracts preferences from all picks immediately.
4. Doctor reviews the generated persona rules, can edit before confirming.
5. Persona is live.

**If skipped:** `onboarded=true` is set, no onboarding shown again. The normal
micro-learning loop will populate persona from real edits over time.

**Scenario content pipeline:** Start with one specialty (neurosurgery — existing
user base). 3 scenarios x 3 options = 9 sample responses. Other specialties
use a generic fallback set (3 scenarios applicable to any specialty: post-visit
follow-up, medication question, urgent symptom). Expand per-specialty scenarios
as each specialty gains users.

### 2. Micro-Learning Loop — Per-Edit Learning

**Current:** 15 edits silently accumulate → batch extraction → full overwrite.

**New:** Every edit is analyzed individually.

**Flow per edit:**

1. Doctor edits an AI draft (follow-up reply, diagnosis, etc.)
2. System classifies the edit asynchronously (see Edit Classification section):
   - **Style/preference signal** → persona candidate
   - **Factual correction** → skip (suggest as KB item if substantial)
   - **Context-specific** → skip
3. If persona candidate, check suppression list. If this pattern was previously
   rejected by the doctor, skip silently.
4. Compare against current persona rules:
   - **New preference:** Not covered by current persona → add to pending
   - **Reinforcement:** Matches existing rule (3+ occurrences) →
     silently boost confidence, no notification
   - **Contradiction:** Conflicts with existing rule → add to pending with flag
5. Non-blocking toast notification (only when confidence >= medium):
   "AI注意到：你倾向先给结论再解释" with [查看] [忽略]
6. Learning goes to pending queue on 人设 page.

**Noise control:**
- Not every edit triggers a toast — only clear structural/style changes
- Factual corrections are filtered out by the classifier
- Auto-reinforcement (3+ matching patterns) doesn't bother the doctor
- One-off context-specific edits are classified as `context_specific` and ignored
- Previously rejected patterns are suppressed (see Suppression below)

### 3. Pending Review Queue

Each pending suggestion shows:
- The proposed change (which field it affects + proposed rule text)
- The evidence — a summary of what the doctor changed, NOT raw before/after text
  (evidence is redacted to remove patient-specific names, dates, and values —
  shows the structural change only, e.g., "你把正式表达改成了口语化")
- What AI discovered (one-line summary)
- Actions: 确认 / 编辑 / 忽略

**Concurrency model:** Each pending item targets a specific field and proposes
an additive change (new rule to append), not a replacement of the whole field.
Accepting a pending item appends the rule to the field's rule list. Manual edits
and pending accepts don't conflict because they operate on individual rules,
not the full field text.

**Suppression:** When a doctor taps "忽略" on a pending item, the pattern
signature (field + summary hash) is recorded in a suppression list on
`persona_pending_items` (status=rejected). Future edits matching the same
pattern check this list before creating a new pending item. Suppression
expires after 90 days or 50 edits (whichever comes first), allowing the
system to re-surface the pattern if the doctor's behavior has genuinely changed.

### 4. Teach by Example

Available anytime from the 人设 page. Doctor pastes a response they're satisfied
with (e.g., from their WeChat history). System extracts style/structure
preferences only — patient-specific content (names, dates, lab values, drug
specifics) is stripped before writing rules. Extracted rules are proposed as
pending items, not directly written.

### 5. Manual Editing

Doctor can directly add, edit, or remove individual rules in any field. This
is the most direct way to configure the persona.

## Data Architecture

### New table: `doctor_personas`

```
doctor_personas
├── doctor_id      (String 64, PK, FK → doctors)
├── fields         (JSON — structured persona, see schema below)
├── status         (String: draft / active)
├── onboarded      (Boolean — distinguishes "never started" from "skipped")
├── edit_count     (Integer — number of edits the system has learned from)
├── version        (Integer — incremented on every write, for optimistic locking)
├── created_at     (DateTime)
└── updated_at     (DateTime)
```

**`fields` JSON schema:**

```json
{
  "reply_style": [
    {"id": "ps_1", "text": "口语化，像微信聊天", "source": "onboarding", "usage_count": 23},
    {"id": "ps_2", "text": "称呼用昵称（张叔、李阿姨）", "source": "edit", "usage_count": 15}
  ],
  "closing": [
    {"id": "ps_3", "text": "有问题随时联系我", "source": "onboarding", "usage_count": 31}
  ],
  "structure": [
    {"id": "ps_4", "text": "先给结论再简短解释", "source": "edit", "usage_count": 18}
  ],
  "avoid": [
    {"id": "ps_5", "text": "不主动展开罕见风险", "source": "manual", "usage_count": 9}
  ],
  "edits": [
    {"id": "ps_6", "text": "把建议改成直接指令", "source": "edit", "usage_count": 7}
  ]
}
```

Each rule has:
- `id` — stable identifier for citation tracking (`[P-ps_1]` in AI output)
- `text` — the rule content
- `source` — how it was created: `onboarding` / `edit` / `manual` / `teach`
- `usage_count` — times this rule was used in prompt composition

Single row per doctor. Replaces the special `DoctorKnowledgeItem` with
`category=persona`.

### New table: `persona_pending_items`

```
persona_pending_items
├── id             (Integer, PK)
├── doctor_id      (String 64, FK → doctors)
├── field          (String: reply_style / closing / structure / avoid / edits)
├── proposed_rule  (Text — the rule text to add)
├── summary        (Text — redacted one-line description of the discovery)
├── evidence_summary (Text — structural description of the edit, no patient data)
├── evidence_edit_ids (JSON array — references to doctor_edits for internal audit)
├── confidence     (String: low / medium / high)
├── pattern_hash   (String — for suppression matching)
├── status         (String: pending / accepted / rejected)
├── created_at     (DateTime)
└── updated_at     (DateTime)
```

### Persona usage tracking

New table or extension to existing `knowledge_usage_log`:

```
persona_usage_log
├── id             (Integer, PK)
├── doctor_id      (String 64, FK → doctors)
├── rule_id        (String — e.g., "ps_1", matches rule.id in persona fields)
├── flow_type      (String: followup_reply / diagnosis / intake / etc.)
├── entity_id      (Integer — the draft/diagnosis/record ID)
├── created_at     (DateTime)
```

This provides the data source for per-rule usage stats ("本周引用 N 次") and
for the `[P-N]` citation markers in AI output.

### Migration

1. Read existing persona `DoctorKnowledgeItem` rows, parse the 5-field text format
   into structured JSON, write to `doctor_personas`
2. Migrate existing `preference` KB items: inspect content, if it matches a persona
   field pattern, add as a rule in the appropriate field. Otherwise migrate to `custom`.
3. Update `teaching.py` code paths that create `preference` items to instead create
   `persona_pending_items`
4. Update `draft_handlers.py` code paths that call teaching flows to use new async
   classification
5. Remove `persona` from `KnowledgeCategory` enum
6. Remove `persona_status` column from `doctor_knowledge_items`
7. Remove `preference` and `communication` from `KnowledgeCategory` enum

## UI Changes

### MyAI Page — Two separate sections

Current: persona card is embedded inside "我的知识库" list.
New: two independent visual sections.

**Section 1: 我的AI人设**
- Section header: "我的AI人设" with subtitle "决定AI怎么说话"
- Single card with:
  - Pending badge (if pending items exist): "N 条新发现待确认 → 查看"
  - Preview of persona rules (truncated)
  - Stats: "已学习 N 次编辑 · 本周引用 N 次"
  - "编辑" link → opens persona subpage

**Section 2: 我的知识库**
- Section header: "我的知识库" with subtitle "决定AI知道什么"
- List of knowledge items with citation counts (existing KnowledgeCard pattern)
- "添加知识" entry point

**"教AI" action** — placed in content area (persona card), not top bar.
Follows existing UI convention of keeping top bar minimal.

### Persona Subpage (我的AI人设)

- Top: pending banner (if items exist)
- 5 field sections, each showing its rules as individual items
- Each rule shows: text, source badge (learned/manual), usage count
- Each rule is individually editable and deletable
- "添加规则" per field
- Bottom: stats row + "教AI一个新偏好" entry point

### Pending Review Subpage

- List of pending items, each showing redacted evidence + proposed rule
- Actions per item: 确认 / 编辑 / 忽略
- Accept appends the rule to the target field

### "放哪里" Guide

On first use or accessible from help: simple reference page showing examples of
what belongs in 人设 vs 知识库, with gray-area examples resolved.

## Prompt Composition Changes

### Persona injection (L4)

Persona rules are rendered from structured JSON into a prompt block:

```xml
<doctor_persona>
以下是医生的个人回复风格和规则，请按此风格起草回复。
回复风格：口语化，像微信聊天 [P-ps_1]；称呼用昵称 [P-ps_2]
常用结尾语：有问题随时联系我 [P-ps_3]
回复结构：先给结论再简短解释 [P-ps_4]
回避内容：不主动展开罕见风险 [P-ps_5]
常见修改：把建议改成直接指令 [P-ps_6]
</doctor_persona>
```

Each rule is tagged with `[P-{id}]` for citation tracking, same pattern as
`[KB-N]` for knowledge items. Post-processing strips `[P-*]` markers from
user-facing output and records which rules were cited.

### Flow scope — explicit LayerConfig flag

Add `load_persona: bool` to `LayerConfig`. Explicitly set per intent:

| Flow | load_persona | Reason |
|------|-------------|--------|
| followup_reply | true | Expression flow — style matters |
| diagnosis | true | Narrative output — style matters |
| intake | false | Structured extraction — style distorts |
| create_record | false | Data entry — no style needed |
| query_record | false | Data retrieval — no style needed |
| daily_summary | true | Narrative output — style matters |
| general | true | Free-form chat — style matters |

This replaces the current implicit behavior where persona loads for any flow
with a doctor_id.

### Rule cap

Hard cap: render at most 15 rules in the persona block. If more exist,
prioritize by field order: avoid (boundaries) > structure > reply_style >
closing > edits. Within each field, prioritize by usage_count descending.

Total rendered persona text capped at 500 characters. This prevents prompt
bloat while keeping the most impactful rules.

### KB remains separate

Knowledge items continue to be relevance-scored and injected with `[KB-N]`
citation markers. No change to KB prompt composition.

## Edit Classification

New LLM call per doctor edit, run asynchronously via background task after the
edit is saved (not blocking the doctor's workflow). Uses the fastest available
model (e.g., qwen-turbo or equivalent ~1-2s latency).

**Task execution:** Uses the existing async pattern in the codebase (background
coroutine after response). No new task queue infrastructure required for v1.
If classification fails (LLM error, timeout), the edit is silently skipped —
no pending item created, no user impact.

**Input:** original AI text + doctor's edited text.

**Output:**

```json
{
  "type": "style | factual | context_specific",
  "persona_field": "reply_style | closing | structure | avoid | edits | null",
  "summary": "一句话结构性描述（不含患者信息）",
  "confidence": "low | medium | high"
}
```

Only `type=style` with `confidence>=medium` becomes a pending persona item.
`type=factual` may be suggested as a KB item if substantial enough.
`type=context_specific` is ignored.

**Multi-dimensional edits:** The classifier returns the single dominant signal.
If an edit genuinely touches multiple dimensions (rare), subsequent similar
edits will surface the secondary signals over time. This is acceptable because
the pending queue is incremental — missing one signal on one edit is self-
correcting across multiple edits.

## Implementation Phases

This is a large change. Ship in three phases to reduce risk:

### Phase 1: Data separation + UI split (no new learning)
- Create `doctor_personas` table with structured JSON
- Migrate existing persona data
- Split MyAI page into two sections
- New persona subpage with individual rules
- Update prompt_composer to load from new table
- Add `load_persona` flag to LayerConfig
- Remove `persona`, `preference`, `communication` from KnowledgeCategory
- Update teaching.py and draft_handlers.py code paths

**Ship and validate before Phase 2.**

### Phase 2: Micro-learning + pending review
- Edit classification (async LLM call)
- Pending items table and API
- Pending review UI
- Toast notifications
- Suppression logic
- Citation tracking (`[P-N]` markers, persona_usage_log)

### Phase 3: Onboarding + teach by example
- Onboarding scenario content (neurosurgery + generic fallback)
- Pick-your-style flow UI
- Teach-by-example flow
- "放哪里" guide page

## Out of Scope

- Knowledge item categorization UI (categories remain internal)
- Persona versioning / rollback (optimistic locking handles concurrency)
- Cross-doctor persona comparison
- Persona preview / sandbox testing
- Per-specialty onboarding beyond neurosurgery + generic (expand later)

## Success Criteria

1. New doctor can have a working persona within 60 seconds of onboarding
2. Doctor never sees "待学习" for more than one session if they complete onboarding
3. Every auto-learned persona update has visible evidence (redacted edit summary)
4. Doctor can accept/reject individual updates, not all-or-nothing
5. Doctor never asks "should I put this in 人设 or 知识库?" — the labels and
   examples make it obvious
6. Persona rules are individually citable in AI output (`[P-N]` markers)
7. No patient-specific data leaks into persona rules or pending evidence

## Mockups

Visual mockups created during brainstorming session are in:
`.superpowers/brainstorm/80068-1775883716/content/`

- `onboarding-v2.html` — onboarding pick-your-style flow
- `persona-page-v2.html` — persona page, pending review, teach by example
- `myai-split.html` — MyAI page with persona/knowledge separation + guide
