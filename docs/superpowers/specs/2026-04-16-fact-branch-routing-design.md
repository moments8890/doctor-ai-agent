# Fact-Branch Routing — Design Spec

**Status**: Draft v3 (round-1: 82/84%, round-2: 84/88%, round-3 target: ≥90%)
**Date**: 2026-04-16
**Owner**: Claude + User
**Related wiki**: `frontend/web/public/wiki/wiki-kb-learning.html` (gap ①)

## v3 changelog (addresses round-2 blockers)
- **Teaching gate decoupled**: `classify_edit` now runs on **every** draft edit (not gated by `should_prompt_teaching`). Teach-prompt UI behavior unchanged. LLM cost increases proportionally to edit volume — accepted tradeoff since this is the whole point of the feature.
- **MySQL partial-index bug fixed**: dropped partial unique index entirely. Correctness now comes from a plain unique `(doctor_id, pattern_hash, status)` constraint (allows new `pending` rows after prior `rejected` or `accepted` — matches 90-day suppression semantics which stay app-enforced). An app-level `SELECT ... FOR UPDATE` pre-check inside a savepoint is an optimization; on SQLite the `FOR UPDATE` is a no-op and correctness falls through to the unique constraint + `IntegrityError` catch.
- **`accepted_knowledge_item_id` column added** to kb_pending_items table definition.
- **PII scrub single point of truth**: deterministic regex scrub runs **before pending row creation** in `_route_to_kb_pending`. UI warning badge is a secondary check for scrub misses. No PII persists in `kb_pending_items`.
- **Pydantic: strict validation**. `classify_edit` returns `ClassifyResult` **model** (not dict). Invalid LLM output → None (same as today). No silent defaults for `kb_category`.
- **Prompt eval harness completeness**: spec now requires matching `tests/prompts/wrappers/persona-classify.md` wrapper + runner registration, not just case YAML.
- **Baseline capture**: persona-classify regression gate requires capturing a baseline eval run on the NEW cases + prompt before enforcing ±2% — one-shot baseline PR before the main PR.

## v2 changelog (historical)
- **Architecture**: keep two tables (codex wins); extract shared dedup helper to address Claude's doubled-code concern.
- **Hash signature**: unchanged. New parallel helper `compute_kb_pattern_hash(category, summary)`. No migration of existing rows.
- **Prompt schema extension**: explicit requirement to rewrite all 5 existing persona-classify examples + add ≥4 factual examples covering all 4 categories.
- **`save_knowledge_item` signature**: extend with `seed_source` param.
- **Concurrency**: dropped partial unique index (MySQL portability bug); use savepoint-based `SELECT ... FOR UPDATE` pre-check + plain unique `(doctor_id, pattern_hash, status)` backstop on both pending tables.
- **Teaching gate (`should_prompt_teaching`)**: explicit decision — keep for v1; document limitation (small dose/drug swaps may be missed). Revisit in gap ② work.
- **Feature flag**: `FACT_LEARNING_ENABLED` env var.
- **New constraints**: `proposed_kb_rule` ≤ 300 chars; deterministic PII scrub on summary/rule before insert.
- **Test plan**: citeability e2e (accept → retrieve → cite); persona-classify regression gate (±2% pass rate); new eval file `tests/prompts/cases/persona-classify.yaml` (does not exist today — spec creates it).
- **Edit-of-edit**: dedup via `evidence_edit_ids` set overlap within 10-minute window.

---

## 1. Problem

Today `persona_learning.py:32` silently discards every doctor edit the LLM classifies as `factual` or `context_specific`. But the LLM has already done the expensive work of understanding *what* the correction is — we just throw away its verdict because the only downstream receiver (`doctor_personas`) is by design style-only.

Result: the densest stream of clinical judgment signal — edits to AI-generated drafts — evaporates. Doctors keep educating the AI by editing, and the AI keeps forgetting.

**Goal:** route `type="factual"` classifications into a new clinical-knowledge learning pipeline that parallels the existing persona-pending flow. Accepted items land in `doctor_knowledge_items` so they become `[KB-N]`-citeable.

## 2. Non-Goals

- Route `context_specific` edits. They are patient-specific and genuinely not generalizable — keep discarding.
- Change the teach-prompt UX gate (`should_prompt_teaching`) — UI behavior stays identical. Only decouple the classifier call so fact signal is always captured, while the teach-prompt button still only appears for significant edits.
- Change retrieval/ranking of `doctor_knowledge_items`.
- Build a rule-health dashboard (gap ③, separate spec).
- Surface hallucinated citations (gap ④, separate spec).
- Wire diagnosis-review teach_prompt UI (gap ②, separate spec).
- Backfill historical `DoctorEdit` rows — forward-only.

## 3. Current state (grounded in code, round-2 corrections applied)

```
draft edit → handle_edit (draft_handlers.py:424)
           → if should_prompt_teaching(original, edited):   ← CURRENT behavior: gates both teach-prompt UI AND classifier
               log_doctor_edit + emit teach_prompt
               asyncio.ensure_future(_process_edit_for_persona_bg())
           → classify_edit (persona_classifier.py:19)
           → if type != "style": return None   ← THE DROP we're fixing
           → else: create PersonaPendingItem
```

**Two problems with current behavior**:
1. The LLM prompt (`persona-classify.md:20-31`) labels medical fact corrections as `factual` and the drop at `persona_learning.py:32` throws them away.
2. `should_prompt_teaching` gates the classifier too, so short single-token edits (e.g. 4-char drug-name swap like the prompt's own example #2) never reach the classifier. v3 decouples this.

**v3 target flow**:

```
draft edit → handle_edit
           ├─ if should_prompt_teaching(...): emit teach_prompt UI (unchanged)
           └─ ALWAYS asyncio.ensure_future(_process_edit_for_learning_bg())   ← NEW: runs regardless of gate
              → classify_edit
              ├─ type=style → PersonaPendingItem
              ├─ type=factual → KbPendingItem
              └─ type=context_specific → drop
```

## 4. Proposed architecture

Add a **parallel learning track** — separate table, separate handlers, shared helpers — dedicated to clinical knowledge. Reuse the same LLM call, extend its output schema. Classifier runs on every edit regardless of teach-prompt gate.

```
draft edit → classify_edit (same call, extended schema — ALWAYS runs)
           ├─ type="style" ─────→ PersonaPendingItem       (existing)
           ├─ type="factual" ───→ KbPendingItem            (NEW)
           └─ type="context_specific" → drop                (unchanged)
```

**LLM cost impact**: classifier now fires on every draft edit, not just significant ones. If typical doctor has 10 edits/day averaging ~100 tokens in + 50 out, that's ~1.5k tokens/day. At current provider pricing, negligible. The teach-prompt UI (`should_prompt_teaching` gate) is unchanged so UX doesn't regress.

### 4.1 DB model

**Keep separate tables.** Rationale (from codex review): the row shape is similar but the **accept targets are fundamentally different** — persona writes to `DoctorPersona.fields_json`, KB writes to `DoctorKnowledgeItem`. Introducing polymorphism via a `track` column leaks concerns everywhere consumers read the persona table (handlers, UI badges, analytics).

**Shared concerns extracted to helpers** (addresses Claude's "doubled code" concern):

- `src/domain/knowledge/pending_common.py` (NEW): `check_pattern_suppression(session, table_cls, doctor_id, pattern)`, `check_duplicate_pending(session, table_cls, doctor_id, pattern)`.
- Hash helpers split: `compute_pattern_hash(field, summary)` unchanged; add `compute_kb_pattern_hash(category, summary)` in the same module.

New table `kb_pending_items`. Column-identical to `persona_pending_items` except `field` → `category`:

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `doctor_id` | str(64), FK CASCADE, index | |
| `category` | str(32) | `KnowledgeCategory` enum: custom / diagnosis / followup / medication |
| `proposed_rule` | text | LLM-proposed rule text (≤ 300 chars, enforced in app layer) |
| `summary` | text | Short description for the review card |
| `evidence_summary` | text | LLM's one-line description of the edit |
| `evidence_edit_ids` | text (JSON) | List of `DoctorEdit.id` that led to this |
| `confidence` | str(16) | low / medium / high |
| `pattern_hash` | str(64), index | For dedup + 90d suppression |
| `status` | str(16) | pending / accepted / rejected |
| `accepted_knowledge_item_id` | int, nullable, FK `doctor_knowledge_items.id` SET NULL | Set when status='accepted'; audit trail of which KB row this produced |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**Concurrency handling** (v3: no partial unique index — MySQL SQLAlchemy `sqlite_where=` would degrade to a full unique and break legitimate re-creations after rejected/accepted rows exist). Instead:

1. **Primary correctness**: **plain unique constraint** `(doctor_id, pattern_hash, status)`. This blocks creating a second `pending` row with the same pattern if the first hasn't yet been rejected/accepted. Pending → accepted transitions are in-place on the same row (status changes but row stays), so this constraint is compatible with the state machine. Creating a new `pending` row with the same hash after prior `rejected` or `accepted` is allowed (different status value) — matches intended 90-day suppression semantics (90d window is app-enforced separately).

2. **App-level pre-check** (optimization, not correctness): `_route_to_kb_pending` does a `SELECT` for an existing pending row before inserting. On SQLite, `FOR UPDATE` is omitted (SQLAlchemy doesn't emit it) — correctness is still preserved by the unique constraint catching races. On MySQL/InnoDB, a row-level lock on the found record prevents a concurrent reader from racing past (gap locks not required since equality on all unique-index columns returns only the matched row). If no row exists on MySQL, the pre-check returns empty and correctness falls to the unique constraint.
   ```python
   async with session.begin_nested():   # savepoint
       stmt = select(KbPendingItem).where(
           KbPendingItem.doctor_id == doctor_id,
           KbPendingItem.pattern_hash == pattern,
           KbPendingItem.status == "pending",
       ).with_for_update()   # no-op on SQLite; row-lock on MySQL
       existing = (await session.execute(stmt)).scalar_one_or_none()
       if existing:
           log(f"[learning] skip duplicate pending pattern={pattern}")
           return None
       try:
           session.add(KbPendingItem(...))
           await session.flush()
       except IntegrityError:
           log(f"[learning] race lost on pattern={pattern}, skipped")
           return None
   ```
   Mirror the same pattern in `_route_to_persona_pending`.

**Summary**: correctness comes from the unique constraint + IntegrityError catch. The savepoint pre-check is a latency/log-cleanliness optimization. Both work on SQLite and MySQL without dialect-specific DDL.

**Migration file**: `alembic/versions/xxxx_add_kb_pending_items.py`.

### 4.2 LLM output schema extension

Extend `persona-classify.md` output schema:

```json
{
  "type": "style|factual|context_specific",
  "persona_field": "reply_style|closing|structure|avoid|edits|",
  "summary": "one-line description",
  "confidence": "low|medium|high",
  "kb_category": "diagnosis|followup|medication|custom|",
  "proposed_kb_rule": "self-contained rule text (≤ 300 chars), or empty"
}
```

**New prompt rules**:
- When `type="factual"`: `kb_category` and `proposed_kb_rule` required; `persona_field` empty.
- `proposed_kb_rule` must be self-contained (decontextualized from the specific patient/case).
- `proposed_kb_rule` must NOT contain patient PII (names, ages, IDs, dates, hospital names).
- `proposed_kb_rule` ≤ 300 chars.
- When `type="style"` or `type="context_specific"`: both new fields empty.

**MANDATORY prompt-file changes** (Claude's #1 risk — examples dominate few-shot):
1. Rewrite all 5 existing examples to include the new fields as empty strings (for style) or populated (for factual).
2. Add **4 new factual examples**, one per `KnowledgeCategory`:
   - `diagnosis`: "术后头痛排除脑脊液漏前不用 NSAIDs"
   - `medication`: "ACEI 和 ARB 不可联用"
   - `followup`: "前交通动脉瘤术后 2 周复查 CTA"
   - `custom`: generic e.g. "糖尿病患者伤口愈合需额外 1 周观察"
3. Double-brace all `{...}` in example JSON for Python `.format()` compatibility (matches existing pattern in the prompt).

**Validation at callsite** (addresses codex's "raw llm_call + json.loads" note):
- Add Pydantic `ClassifyResult` model in `persona_classifier.py`.
- `classify_edit` validates LLM output → returns **`ClassifyResult` model instance** (not dict). Invalid → None (same as today's behavior on bad JSON).
- **Callers updated** to use attribute access (`result.type`, `result.persona_field`) instead of dict keys. This is a touch on the persona path — mitigated by:
  - The existing eval-file regression gate (§9)
  - No behavior change for type=style or type=context_specific paths (same field names, same routing logic)
- No silent defaults — invalid `kb_category` for `type=factual` → reject via Pydantic → None → pipeline logs+skips.

### 4.3 Pipeline integration

Refactor `persona_learning.py`:

```python
async def process_edit_for_learning(  # renamed from process_edit_for_persona
    session, doctor_id, original, edited, edit_id,
) -> dict | None:
    result = await classify_edit(original, edited)
    if not result:
        return None

    if result.type == LearningType.style:
        return await _route_to_persona_pending(session, doctor_id, result, edit_id)
    if result.type == LearningType.factual:
        if not os.getenv("FACT_LEARNING_ENABLED", "1") == "1":
            log(f"[learning] edit {edit_id}: fact routing disabled, skipping")
            return None
        return await _route_to_kb_pending(session, doctor_id, result, edit_id)
    # context_specific → drop (unchanged)
    log(f"[learning] edit {edit_id}: type={result.type}, skipping")
    return None
```

Caller updates:
- `draft_handlers.py:40` rename `_process_edit_for_persona_bg` → `_process_edit_for_learning_bg` (internal only, no external callers).
- `draft_handlers.py:420-440`: **move BOTH `log_doctor_edit` and the classifier call out of the `should_prompt_teaching` gate**. Currently (`draft_handlers.py:424-433`) `log_doctor_edit` is inside the gate, so `edit_id` only exists when the gate fires. v3 lifts both:
  ```python
  # Inside handle_edit (new)
  edit_id = await log_doctor_edit(
      db, doctor_id=resolved, entity_type="draft_reply", entity_id=draft_id,
      original_text=original_text, edited_text=edited_text,
  )
  teach_prompt = should_prompt_teaching(original_text, edited_text)
  # teach_prompt only controls whether the UI shows the "保存为规则" button — no behavior change there
  await db.commit()
  # Always fire the learning pipeline regardless of gate
  asyncio.ensure_future(_process_edit_for_learning_bg(resolved, original_text, edited_text, edit_id))
  ```
- **Write-volume implication**: `DoctorEdit` rows now created on every saved draft edit, not just significant ones. Typical doctor saves a draft edit 5-15 times/day (not keystroke-level); this increases `DoctorEdit` row volume roughly 2-3x, not orders of magnitude. `DoctorEdit` has `ON DELETE CASCADE` via `doctor_id` FK so no orphan risk. Storage: ~0.5 KB per row × 2-3x increase = trivial. Any existing queries over `DoctorEdit` that assumed "only significant" must be re-checked — grep `DoctorEdit` at spec implementation time.
- All tests in `tests/core/test_persona_learning.py` updated for rename + new factual branch coverage.

**Edit-of-edit dedup** (both reviewers flagged): inside `_route_to_kb_pending`, after pattern check, also query recent pending items where `evidence_edit_ids` JSON contains any id recently classified for this doctor within the last 10 minutes. If hit, append the new edit_id to the existing item rather than creating a new one. Query is cheap — indexed by doctor_id, filtered by created_at window.

### 4.4 API — new endpoints

Mirror `/api/manage/persona/pending`:

- `GET /api/manage/kb/pending?doctor_id=…` → `{items: [...], count: N}`
- `POST /api/manage/kb/pending/{id}/accept?doctor_id=…` →
  1. Fetch pending item, verify ownership (`_resolve_ui_doctor_id`).
  2. Call `save_knowledge_item(session, doctor_id, item.proposed_rule, source="doctor", confidence=1.0, category=item.category, seed_source="edit_fact")` — **this commits internally at line 222**.
  3. After successful KB write, separate commit sets `item.status = "accepted"`, `item.accepted_knowledge_item_id = new_item.id` (NEW field, see §4.1). If this second commit fails, KB item already exists — accept is idempotent because the next retry will find KB row via `normalized_new` dedup in `save_knowledge_item:215`.
  4. `invalidate_knowledge_cache(doctor_id)` called before returning (otherwise retrieval won't pick up the new rule for up to 5 min).
  5. Returns `{status: "ok", knowledge_item_id: int, title: str}`.
- `POST /api/manage/kb/pending/{id}/reject?doctor_id=…` → `item.status = "rejected"`, single commit. No cache invalidation needed.

Auth via `_resolve_ui_doctor_id(doctor_id, authorization)` — same pattern.

**Rate limiting**: new endpoints use `enforce_doctor_rate_limit` — same as other KB endpoints (confirm decorator pattern matches existing persona_pending_handlers).

New handler file: `src/channels/web/doctor_dashboard/kb_pending_handlers.py`. Register router in the app factory alongside `persona_pending_handlers`.

### 4.5 `save_knowledge_item` signature extension

Add `seed_source: Optional[str] = None` param:

```python
async def save_knowledge_item(
    session, doctor_id: str, text: str,
    source: str = "doctor", confidence: float = 1.0,
    category: str = KnowledgeCategory.custom,
    title: Optional[str] = None, summary: Optional[str] = None,
    source_url: Optional[str] = None, file_path: Optional[str] = None,
    seed_source: Optional[str] = None,   # NEW
) -> Optional[DoctorKnowledgeItem]:
    ...
    item = await add_doctor_knowledge_item(session, doctor_id, payload, category=category)
    item.title = ...
    item.summary = summary
    if seed_source:
        item.seed_source = seed_source   # NEW
    await session.commit()
    ...
```

All existing callsites unchanged (param is optional). New value: `seed_source="edit_fact"` from the accept endpoint.

### 4.6 UI

New subpage: `/settings/knowledge/pending`. Lives under knowledge (not persona) because it lands in `doctor_knowledge_items`.

Reuse card pattern from `PendingReviewSubpage.jsx` but adapted:
- Badge shows category label (诊断/随访/用药/通用) instead of persona field.
- "Accept" button text: **"保存为规则"** (consistent with existing teaching-loop wording).
- Show `proposed_rule` as main text, `evidence_summary` as sub-caption.

Entry point: badge on KnowledgeSubpage header (parallel to PersonaSubpage's pending badge at `PersonaSubpage.jsx:169-183`).

**PII scrub at insert** (v3.2: single point of truth — scrub runs in `_route_to_kb_pending` before pending row is created, on **all three** user-derived text fields: `proposed_rule`, `summary`, `evidence_summary`. Nothing user-derived bypasses the scrub):
- Regex pass for: 名字：/姓名：followed by chars, 手机号 (11-digit pattern `\b1[3-9]\d{9}\b`), date formats (`\d{4}[-年/]\d{1,2}[-月/]\d{1,2}`), 住院号/病历号 followed by digits, ID-card patterns (18-digit).
- Matched substrings replaced with `[已脱敏]`.
- Applied uniformly: `scrubbed_rule = scrub(proposed_rule)`, `scrubbed_summary = scrub(summary)`, `scrubbed_evidence = scrub(evidence_summary)` — all three go into the row.
- If after scrub `proposed_rule` is empty or <10 chars, skip creation entirely.
- UI warning badge is a **secondary** layer — shown if any of the three fields still contains a regex hit post-scrub (belt-and-braces; relies on doctor review).

## 5. Data contract (Pydantic)

```python
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

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
    # Must match src/db/models/doctor.py:KnowledgeCategory
    custom = "custom"
    diagnosis = "diagnosis"
    followup = "followup"
    medication = "medication"

class ClassifyResult(BaseModel):
    type: LearningType
    persona_field: Optional[PersonaField] = None    # populated only when type=style
    summary: str = Field(min_length=1, max_length=500)
    confidence: Literal["low", "medium", "high"]
    kb_category: Optional[KbCategory] = None         # populated only when type=factual
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
```

**Prompt adapter**: `persona-classify.md` must emit string values for both `kb_category` and `persona_field` (or empty string). `classify_edit` converts empty strings to `None` before Pydantic validation so the enum parse succeeds.

Consumed at `persona_classifier.py:classify_edit`. Invalid → None.

## 6. State machine

```
    edit event ──→ log_doctor_edit (always — v3 lifted out of gate)
                 ─→ should_prompt_teaching gates only the UI teach_prompt button
                 ─→ classify (ALWAYS — v3 lifted out of gate)
                     │
             ┌───────┼───────┐
             ▼       ▼       ▼
         style   factual  context_specific
             │       │          │
        dedup   PII scrub      drop
             │       │
             ▼       ▼
      dedup check  dedup check
             │       │
             ▼       ▼
    PersonaPendingItem  KbPendingItem
             │       │
    accept/reject   accept/reject
             │       │
             ▼       ▼
    DoctorPersona   DoctorKnowledgeItem (via save_knowledge_item)
```

## 7. Error modes & edge cases

| Scenario | Behavior |
|---|---|
| LLM returns invalid JSON | `classify_edit` returns None, pipeline skips (unchanged) |
| LLM returns `type=factual` but empty `proposed_kb_rule` | Pydantic validator fails → None |
| LLM returns `type=factual` but `kb_category` not in enum | Pydantic validator rejects → None → pipeline logs+skips (no silent default) |
| LLM returns `proposed_kb_rule` > 300 chars | Pydantic validator fails → None |
| `proposed_kb_rule` contains PII | Deterministic regex scrub at insert in `_route_to_kb_pending` (v3) replaces matched substrings with `[已脱敏]`; UI warning badge is secondary belt-and-braces if residue leaks through |
| Duplicate pattern (pending in last 90d) | App-level `SELECT ... FOR UPDATE` inside savepoint blocks duplicate; unique `(doctor_id, pattern_hash, status)` backstops via `IntegrityError` → logged "skipped" |
| Duplicate pattern (rejected in last 90d) | App-level suppression check blocks create |
| Two rapid fact edits same pattern | Unique index serializes — second insert fails, app treats as skip |
| Edit-of-edit cascade | `evidence_edit_ids` overlap check inside 10-min window appends rather than creates |
| Accept fails after `save_knowledge_item` commit but before status update | On retry, `save_knowledge_item` scans a bounded recent list for normalized-text match — **usually** finds and returns the existing row, giving idempotent behavior. Edge case: if the doctor has added many rules between the partial failure and the retry (pushing the earlier row out of the recent-list window), retry creates a duplicate KB row. Mitigation: pending row's `accepted_knowledge_item_id` is set only on the final commit, so the pending row still shows as `pending` and a second accept attempt would re-save via the same dedup path — creating at most 1 duplicate. Acceptable for v1 given the low rate; flag for v2 if it ever fires in telemetry. |
| Doctor deleted mid-accept | FK CASCADE removes pending + KB items; endpoint returns 404 |
| Feature flag OFF | `type=factual` hits log line, no pending row created (persona path unaffected) |

## 8. Rollout plan

1. **Schema + prompt + backend** (one PR): migration, new table + plain unique `(doctor_id, pattern_hash, status)` + savepoint-based duplicate check, prompt rewrite with all 5+4 examples, Pydantic model, classifier validation, `save_knowledge_item` signature extension, routing logic, handler endpoints, backend + prompt eval tests, `log_doctor_edit` + classifier decouple in `draft_handlers`. **Feature flag defaults ON** but UI doesn't surface pending items yet — safe because the pending table just fills invisibly.
2. **UI** (next PR): KbPendingSubpage + entry badge on KnowledgeSubpage. Users start reviewing pending cards.
3. **Monitor window (7 days)**: check `logs/llm_calls.jsonl` for classifier output distribution; verify `type=factual` rate is within 15-40% of significant edits (sanity range). Tune prompt if miscategorization is high.

**Eval regression gate** (blocker for PR 1): existing persona-classify eval cases must still pass at ≥ current baseline ± 2%. New factual cases must hit ≥ 80% type-accuracy.

**Kill switch**: `FACT_LEARNING_ENABLED=0` disables fact routing without migration rollback. Persona path untouched.

## 9. Success criteria

- **Behavioral**: labeled eval set of 30 factual edits across 4 categories — pipeline produces `KbPendingItem` with correct category for ≥ 24/30 (80%).
- **Hygiene**: zero PII leakage in `proposed_kb_rule` across 20 synthetic cases with embedded PII (names, phone numbers, dates).
- **No regression**: all existing persona-classify eval cases pass at current baseline ± 2%.
- **Citeability**: e2e test confirms an accepted KB rule is retrieved by `load_knowledge` and emitted as `[KB-N]` in a subsequent draft generation.
- **Telemetry**: structured log `[learning] edit=N type=factual category=X confidence=Y pending_id=M` on every create; `[learning] edit=N type=factual skipped=duplicate` on dedup.

## 10. Test plan

### Unit (pytest)
- `classify_edit` returns valid `ClassifyResult` with kb fields populated for factual case.
- `classify_edit` returns None on invalid schema.
- `compute_kb_pattern_hash` stable and differs from `compute_pattern_hash` (track isolation).
- `_route_to_kb_pending` creates pending row, writes correct category, evidence_edit_ids JSON.
- `_route_to_kb_pending` appends to existing pending item when edit_id within 10-min window.
- `_route_to_kb_pending` skips when savepoint-level duplicate check finds existing pending row.
- `_route_to_kb_pending` also catches `IntegrityError` from the unique `(doctor_id, pattern_hash, status)` backstop on race.
- Pydantic validator: `kb_category` empty when not factual; required when factual.
- `save_knowledge_item` with `seed_source="edit_fact"` sets column correctly.

### Integration
- POST draft edit → bg task runs → KbPendingItem exists → GET list returns it → POST accept → DoctorKnowledgeItem exists, `seed_source="edit_fact"` → list count 0.
- Reject flow: status=rejected, no KB row, suppression active for 90d.
- Cache invalidation: accept → new rule appears in `load_knowledge` within same request (no TTL wait).

### Eval
- Create new `tests/prompts/cases/persona-classify.yaml` (does not exist today; spec creates it per codex's flag).
  - 30 factual cases: 10 diagnosis, 8 medication, 7 followup, 5 custom.
  - Assertions: type==factual, category matches, proposed_kb_rule length ≤ 300, no PII match against 8 regex patterns.
  - 5 context_specific cases: type==context_specific, both kb fields empty.
  - ≥10 style cases, covering all 5 persona_field values (pulled from existing test_persona_classifier.py).
- Create matching wrapper at `tests/prompts/wrappers/persona-classify.md` (codex's flag — eval runner needs this paired file).
- Register in `tests/prompts/conftest.py` or equivalent runner config so `pytest tests/prompts/` picks it up.
- **Baseline-capture PR** before main PR: run the new eval once with the rewritten prompt, lock the per-scenario expected outputs as the baseline. Then the main PR's ±2% regression gate has something to compare against (Claude's flag — avoid self-referential gate).

### Concurrency
- Simulate two concurrent bg tasks with identical pattern_hash → exactly one pending row created, second hits IntegrityError and is logged+skipped.

### Citeability (e2e)
- Register doctor → post draft edit (factual) → wait for bg task → list pending → accept → trigger new draft generation → assert `[KB-N]` citation with N matching new knowledge_item_id.

## 11. Open questions (resolved in v2)

1. ~~Should `seed_source` be "edit_pending" or "teaching"?~~ Resolved: `seed_source="edit_fact"`.
2. ~~Also capture `type=factual` from diagnosis edits?~~ No — scope to draft edits (gap ② rework).
3. ~~Pattern hash collision across tracks?~~ Solved by keeping separate hash helpers per track.
4. ~~Cache invalidation on accept?~~ Explicit in §4.4.
5. ~~Should the teach_prompt gate be bypassed?~~ Resolved in v3: classifier runs on every edit (decoupled); teach_prompt UI button still gated by `should_prompt_teaching` (no UX regression). `log_doctor_edit` also lifted out of the gate so `edit_id` exists for all learning-pipeline calls.

## 12. File changes summary

**New files**:
- `alembic/versions/xxxx_add_kb_pending_items.py`
- `src/db/models/kb_pending.py`
- `src/domain/knowledge/pending_common.py` (shared helpers: `check_pattern_suppression`, `check_duplicate_pending`, `scrub_pii`)
- `src/channels/web/doctor_dashboard/kb_pending_handlers.py`
- `frontend/web/src/pages/doctor/subpages/KbPendingSubpage.jsx`
- `tests/prompts/cases/persona-classify.yaml`
- `tests/prompts/wrappers/persona-classify.md`
- `tests/core/test_fact_routing.py`
- `tests/integration/test_kb_pending.py`
- `tests/e2e/19-kb-pending-citeability.spec.ts`

**Modified files**:
- `src/agent/prompts/persona-classify.md` — extend schema, rewrite 5 examples, add 4 new
- `src/domain/knowledge/persona_classifier.py` — add Pydantic ClassifyResult, kb hash helper
- `src/domain/knowledge/persona_learning.py` — rename to process_edit_for_learning, add fact branch
- `src/domain/knowledge/knowledge_crud.py` — extend `save_knowledge_item` with `seed_source`
- `src/channels/web/doctor_dashboard/draft_handlers.py` — rename _bg function, update import
- `src/db/models/persona_pending.py` — add plain unique `(doctor_id, pattern_hash, status)`; add savepoint-based duplicate check at the call site (mirrors kb_pending routing)
- `frontend/web/src/pages/doctor/subpages/KnowledgeSubpage.jsx` — add pending badge
- `frontend/web/src/lib/doctorQueries.js` — add useKbPending / useAcceptKbPending / useRejectKbPending

---

*Next: pair-review v2 with Claude + codex until ≥90%, then write implementation plan.*
