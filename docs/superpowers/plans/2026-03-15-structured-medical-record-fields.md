# Structured Medical Record Fields — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist 13 regulatory outpatient record fields alongside the free-text narrative at write time, eliminating on-demand LLM extraction during export.

**Architecture:** A single nullable `structured_fields` JSON column on `medical_records` is populated by the existing structuring LLM call (prompt extended via a new `.md` file). Export reads stored fields first, falls back to LLM for legacy records. PATCH endpoints use merge-patch semantics; chat-driven updates use full replace.

**Tech Stack:** Python 3.9+ / SQLAlchemy / Pydantic v2 / FastAPI / React (MUI)

**Spec:** `docs/superpowers/specs/2026-03-15-structured-medical-record-fields-design.md`

**Testing policy:** Per AGENTS.md, do not add unit tests unless explicitly asked. Verify changes manually or via existing E2E replay.

---

## Chunk 1: Data Layer (models, repository, CRUD)

### Task 1: DB Models — add columns

**Files:**
- Modify: `src/db/models/records.py`

- [ ] **Step 1: Add `structured_fields` to `MedicalRecordDB`**

In `src/db/models/records.py`, add after the `encounter_type` column (line 24):

```python
structured_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Add `old_structured_fields` to `MedicalRecordVersion`**

In the same file, add after `old_record_type` (line 53):

```python
old_structured_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 3: Run ALTER TABLE for dev DB**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -c "
from db.engine import engine
import asyncio
from sqlalchemy import text

async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(text('ALTER TABLE medical_records ADD COLUMN structured_fields TEXT'))
        except Exception as e:
            print(f'medical_records: {e}')
        try:
            await conn.execute(text('ALTER TABLE medical_record_versions ADD COLUMN old_structured_fields TEXT'))
        except Exception as e:
            print(f'medical_record_versions: {e}')
    print('done')

asyncio.run(migrate())
"
```

- [ ] **Step 4: Commit**

```bash
git add src/db/models/records.py
git commit -m "feat: add structured_fields column to medical_records and versions"
```

---

### Task 2: Pydantic model — add field

**Files:**
- Modify: `src/db/models/medical_record.py`

- [ ] **Step 1: Add `structured_fields` to `MedicalRecord`**

Add import at top:

```python
from typing import Dict, List, Optional
```

Add field after `record_type`:

```python
structured_fields: Optional[Dict[str, str]] = Field(default=None)
"""按《病历书写基本规范》的13项门诊病历结构化字段。"""
```

- [ ] **Step 2: Commit**

```bash
git add src/db/models/medical_record.py
git commit -m "feat: add structured_fields to MedicalRecord Pydantic model"
```

---

### Task 3: Update `OUTPATIENT_FIELDS` and export `OUTPATIENT_FIELD_KEYS`

**Files:**
- Modify: `src/services/export/outpatient_report.py`

- [ ] **Step 1: Update `OUTPATIENT_FIELDS` list**

Replace the current list (lines 32-46) with:

```python
OUTPATIENT_FIELDS = [
    ("department",         "科别"),
    ("chief_complaint",    "主诉"),
    ("present_illness",    "现病史"),
    ("past_history",       "既往史"),
    ("allergy_history",    "过敏史"),
    ("personal_history",   "个人史"),
    ("marital_history",    "婚育史"),
    ("family_history",     "家族史"),
    ("physical_exam",      "体格检查"),
    ("aux_exam",           "辅助检查"),
    ("diagnosis",          "初步诊断"),
    ("treatment",          "治疗方案"),
    ("followup",           "医嘱及随访"),
]
```

Changes: removed `encounter_type` (handled by DB column), added `marital_history`.

- [ ] **Step 2: Replace private `_FIELD_KEYS` with public `OUTPATIENT_FIELD_KEYS`**

Replace `_FIELD_KEYS` (line 51) with:

```python
OUTPATIENT_FIELD_KEYS: FrozenSet[str] = frozenset(k for k, _ in OUTPATIENT_FIELDS)
```

Add `FrozenSet` to the typing import at top of file (add `from typing import FrozenSet` or ensure `from __future__ import annotations` is present).

- [ ] **Step 3: Replace all `_FIELD_KEYS` references with `OUTPATIENT_FIELD_KEYS`**

Search the file for every occurrence of `_FIELD_KEYS` and replace with
`OUTPATIENT_FIELD_KEYS`. There are at least two:
- Line 183: `result = {k: str(data.get(k, "") or "") for k in _FIELD_KEYS}`
- Line 188: `f"non_empty={sum(1 for v in result.values() if v)}/{len(_FIELD_KEYS)}"`

- [ ] **Step 4: Remove `encounter_type` validation from `extract_outpatient_fields`**

Remove lines 184-185:

```python
if result.get("encounter_type") not in ("初诊", "复诊"):
    result["encounter_type"] = "初诊"
```

- [ ] **Step 5: Update `_HEADER_ONLY_FIELDS`**

At line 49, `_HEADER_ONLY_FIELDS` contains `"encounter_type"`. Since
`encounter_type` is no longer in `OUTPATIENT_FIELDS`, update:

```python
_HEADER_ONLY_FIELDS = {"department"}
```

The `encounter_type` display is now handled by the export handler which derives
it from the DB column (see Task 10 Step 3).

- [ ] **Step 5: Commit**

```bash
git add src/services/export/outpatient_report.py
git commit -m "feat: update OUTPATIENT_FIELDS, export OUTPATIENT_FIELD_KEYS"
```

---

### Task 4: Repository layer — persist structured_fields

**Files:**
- Modify: `src/db/repositories/records.py`

- [ ] **Step 1: Update `RecordRepository.create()`**

In `create()` (line 39), add `structured_fields` to the `MedicalRecordDB` constructor:

```python
db_record = MedicalRecordDB(
    doctor_id=doctor_id,
    patient_id=patient_id,
    record_type=record.record_type,
    content=record.content,
    tags=json.dumps(record.tags, ensure_ascii=False) if record.tags else None,
    encounter_type=encounter_type,
    structured_fields=(
        json.dumps(record.structured_fields, ensure_ascii=False)
        if record.structured_fields else None
    ),
)
```

- [ ] **Step 2: Update `RecordRepository.update()` signature**

Add optional `structured_fields` parameter and handling (lines 51-72):

```python
async def update(
    self,
    *,
    record_id: int,
    doctor_id: str,
    content: str,
    tags: List[str],
    structured_fields: Optional[Dict[str, str]] = None,
) -> MedicalRecordDB:
    result = await self.session.execute(
        select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == doctor_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise ValueError(f"Record {record_id} not found for doctor {doctor_id}")
    record.content = content
    record.tags = json.dumps(tags, ensure_ascii=False) if tags else "[]"
    if structured_fields is not None:
        record.structured_fields = json.dumps(
            structured_fields, ensure_ascii=False
        )
    record.updated_at = datetime.now(timezone.utc)
    await self.session.flush()
    return record
```

Add imports at top: `from typing import Dict, List, Optional`

- [ ] **Step 3: Commit**

```bash
git add src/db/repositories/records.py
git commit -m "feat: persist structured_fields in RecordRepository create/update"
```

---

### Task 5: CRUD — version snapshot + field allowlist

**Files:**
- Modify: `src/db/crud/records.py`

- [ ] **Step 1: Update `save_record_version()`**

Add `old_structured_fields` to the version snapshot (line 248-256):

```python
version = MedicalRecordVersion(
    record_id=record.id,
    doctor_id=doctor_id,
    old_content=record.content,
    old_tags=record.tags,
    old_record_type=record.record_type,
    old_structured_fields=record.structured_fields,
)
```

- [ ] **Step 2: Extend `_RECORD_CLINICAL_FIELDS`**

Update the frozenset (line 278):

```python
_RECORD_CLINICAL_FIELDS = frozenset({"content", "tags", "record_type", "structured_fields"})
```

- [ ] **Step 3: Commit**

```bash
git add src/db/crud/records.py
git commit -m "feat: include structured_fields in version snapshots and field allowlist"
```

---

## Chunk 2: Structuring Pipeline (prompt, coercion, commit engine)

### Task 6: Prompt file — structured fields instruction

**Files:**
- Create: `src/prompts/structuring-structured-fields.md`

- [ ] **Step 1: Create the prompt file**

```markdown
在返回的 JSON 中，额外包含 "structured_fields" 对象，按以下13项门诊病历标准字段从对话内容中提取：

"structured_fields": {
  "department": "科别（如：神经内科）",
  "chief_complaint": "主诉",
  "present_illness": "现病史",
  "past_history": "既往史",
  "allergy_history": "过敏史",
  "personal_history": "个人史",
  "marital_history": "婚育史",
  "family_history": "家族史",
  "physical_exam": "体格检查",
  "aux_exam": "辅助检查",
  "diagnosis": "初步诊断",
  "treatment": "治疗方案",
  "followup": "医嘱及随访"
}

规则：
- 根据临床内容填写各字段。无信息的字段填 ""（不得编造）。
- 部分字段缺失是正常的，不要为了填充而推测内容。
```

- [ ] **Step 2: Commit**

```bash
git add src/prompts/structuring-structured-fields.md
git commit -m "feat: add structured fields prompt instruction file"
```

---

### Task 7: Structuring — load prompt + coerce fields + max_tokens

**Files:**
- Modify: `src/services/ai/structuring.py`

- [ ] **Step 1: Append structured fields prompt in `_build_system_prompt`**

Add after the follow_up suffix block (after line 117):

```python
    # Always append structured_fields instruction
    system_prompt = system_prompt + "\n\n" + await get_prompt(
        "structuring-structured-fields"
    )
```

- [ ] **Step 2: Add coercion in `_validate_and_coerce_fields`**

Insert **before** `return data` at line 261:

```python
    # Coerce structured_fields
    sf = data.get("structured_fields")
    if sf is not None and not isinstance(sf, dict):
        data["structured_fields"] = None
    elif isinstance(sf, dict):
        from services.export.outpatient_report import OUTPATIENT_FIELD_KEYS
        data["structured_fields"] = {
            k: str(v) if v is not None else ""
            for k, v in sf.items()
            if k in OUTPATIENT_FIELD_KEYS
        }
    # else: sf is None — normal for legacy calls without updated prompt

    return data
```

This replaces the existing `return data` at line 261.

- [ ] **Step 3: Increase `max_tokens` in `_make_llm_caller`**

Change line 132 from:

```python
max_tokens=1500,
```

to:

```python
max_tokens=int(os.environ.get("STRUCTURING_MAX_TOKENS", "2500")),
```

- [ ] **Step 4: Commit**

```bash
git add src/services/ai/structuring.py
git commit -m "feat: load structured fields prompt, add coercion, increase max_tokens"
```

---

### Task 8: Commit engine — pass structured_fields through update

**Files:**
- Modify: `src/services/runtime/commit_engine.py`

- [ ] **Step 1: Update `_update_record` repo.update() call**

At line 304, add `structured_fields`:

```python
await repo.update(
    record_id=record_id,
    doctor_id=ctx.doctor_id,
    content=record.content,
    tags=record.tags,
    structured_fields=record.structured_fields,
)
```

- [ ] **Step 2: Commit**

```bash
git add src/services/runtime/commit_engine.py
git commit -m "feat: pass structured_fields through update_record path"
```

---

### Task 9: Auto-learn fix — call site + key names

**Files:**
- Modify: `src/services/domain/intent_handlers/_confirm_pending.py`
- Modify: `src/channels/wechat/wechat_bg.py`
- Modify: `src/services/knowledge/doctor_knowledge.py`

- [ ] **Step 1: Fix call site in `_confirm_pending.py`**

At line 105, change:

```python
structured_fields=record.model_dump(exclude_none=True),
```

to:

```python
structured_fields=record.structured_fields,
```

- [ ] **Step 2: Fix call site in `wechat_bg.py`**

At line 54 in `src/channels/wechat/wechat_bg.py`, change:

```python
structured_fields=record.model_dump(exclude_none=True),
```

to:

```python
structured_fields=record.structured_fields,
```

- [ ] **Step 3: Fix key names in `_extract_auto_candidates`**

In `doctor_knowledge.py` lines 94-96, change:

```python
diagnosis = _normalize_text(str(fields.get("diagnosis") or ""))
treatment = _normalize_text(str(fields.get("treatment_plan") or ""))
follow_up = _normalize_text(str(fields.get("follow_up_plan") or ""))
```

to:

```python
diagnosis = _normalize_text(str(fields.get("diagnosis") or ""))
treatment = _normalize_text(str(fields.get("treatment") or ""))
follow_up = _normalize_text(str(fields.get("followup") or ""))
```

- [ ] **Step 4: Commit**

```bash
git add src/services/domain/intent_handlers/_confirm_pending.py \
       src/channels/wechat/wechat_bg.py \
       src/services/knowledge/doctor_knowledge.py
git commit -m "fix: pass record.structured_fields to auto-learn, fix key names"
```

---

## Chunk 3: Export, Serialization, API Endpoints

### Task 10: Export — DB-first with LLM fallback

**Files:**
- Modify: `src/services/export/outpatient_report.py`

- [ ] **Step 1: Add `_merge_stored_fields` helper**

Add before `extract_outpatient_fields()`:

```python
def _merge_stored_fields(records: list) -> Dict[str, str]:
    """Merge structured_fields across records. Most recent wins per field."""
    merged: Dict[str, str] = {}
    for rec in reversed(records):  # oldest first so newest overwrites
        sf_raw = getattr(rec, "structured_fields", None)
        if not sf_raw:
            continue
        try:
            sf = json.loads(sf_raw) if isinstance(sf_raw, str) else sf_raw
        except (json.JSONDecodeError, TypeError):
            continue
        for k, v in sf.items():
            if k in OUTPATIENT_FIELD_KEYS and v:
                merged[k] = v
    return merged


def _fields_sufficient(fields: Dict[str, str]) -> bool:
    """True if stored fields have enough data to skip LLM extraction."""
    return bool(fields.get("chief_complaint")) and bool(fields.get("diagnosis"))
```

- [ ] **Step 2: Refactor `extract_outpatient_fields` to try stored fields first**

Rename existing LLM-based extraction logic to `_llm_extract_fields()` (private),
then rewrite `extract_outpatient_fields()` as the public entry point:

```python
async def extract_outpatient_fields(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> Dict[str, str]:
    """Extract structured fields — from DB if available, LLM fallback for legacy."""
    stored = _merge_stored_fields(records)
    if _fields_sufficient(stored):
        log(f"[OutpatientReport] using stored fields doctor={doctor_id} "
            f"non_empty={sum(1 for v in stored.values() if v)}/{len(OUTPATIENT_FIELD_KEYS)}")
        return stored

    log(f"[OutpatientReport] legacy fallback, calling LLM doctor={doctor_id}")
    return await _llm_extract_fields(records, patient, doctor_id)
```

The existing body of `extract_outpatient_fields` becomes `_llm_extract_fields`
(same signature, same logic — just renamed). **Note:** Task 3 already renamed
`_FIELD_KEYS` → `OUTPATIENT_FIELD_KEYS` throughout this file, so the renamed
function inherits the correct references.

- [ ] **Step 3: Handle `encounter_type` in export handler**

In `src/channels/web/export.py`, at line 306 (after the
`_extract_outpatient_fields_safe` call), add `encounter_type` derivation from
the DB column before the PDF is rendered:

```python
fields = await _extract_outpatient_fields_safe(
    records, patient, resolved_doctor_id, patient_id,
)
# Derive encounter_type from DB column (not in structured_fields)
if records:
    enc = getattr(records[0], "encounter_type", "unknown")
    fields["encounter_type"] = {"first_visit": "初诊", "follow_up": "复诊"}.get(enc, "初诊")
```

- [ ] **Step 4: Commit**

```bash
git add src/services/export/outpatient_report.py src/channels/web/export.py
git commit -m "feat: DB-first structured field extraction with LLM fallback"
```

---

### Task 11: Serializers — add structured_fields to API responses

**Files:**
- Modify: `src/channels/web/ui/record_handlers.py`
- Modify: `src/channels/web/ui/admin_table_rows.py`
- Modify: `src/services/runtime/read_engine.py`
- Modify: `src/channels/web/chat.py`

- [ ] **Step 1: `_serialize_record_with_patient` in `record_handlers.py`**

Add to the returned dict:

```python
"structured_fields": json.loads(record.structured_fields) if record.structured_fields else None,
```

Add `import json` if not already present.

- [ ] **Step 2: `_rows_medical_records` in `admin_table_rows.py`**

Add to the dict comprehension:

```python
"structured_fields": json.loads(r.structured_fields) if r.structured_fields else None,
```

- [ ] **Step 3: `_rows_record_versions` in `admin_table_rows.py`**

Add to the dict comprehension:

```python
"old_structured_fields": json.loads(v.old_structured_fields) if v.old_structured_fields else None,
```

- [ ] **Step 4: `_query_records` view_payload in `read_engine.py`**

Add to the data dict appended per record:

```python
"structured_fields": json.loads(r.structured_fields) if r.structured_fields else None,
```

- [ ] **Step 5: `RecordVersionResponse` in `chat.py`**

Add field to the Pydantic response model:

```python
old_structured_fields: Optional[str] = None
```

And include it in the serialization where version rows are returned.

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/ui/record_handlers.py \
       src/channels/web/ui/admin_table_rows.py \
       src/services/runtime/read_engine.py \
       src/channels/web/chat.py
git commit -m "feat: include structured_fields in all record serializers"
```

---

### Task 12: PATCH endpoints — RecordUpdate, merge-patch, version snapshot

**Files:**
- Modify: `src/channels/web/ui/__init__.py`

- [ ] **Step 1: Extend `RecordUpdate` model**

Add to `RecordUpdate` (line 452-455):

```python
class RecordUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    record_type: Optional[str] = None
    structured_fields: Optional[Dict[str, str]] = None
```

Add `Dict` to typing imports.

- [ ] **Step 2: Doctor PATCH — add version snapshot + merge-patch**

In `update_record()` (line 458), after fetching `rec` and before applying
updates, add version snapshot:

```python
from db.crud.records import save_record_version
await save_record_version(db, rec, resolved_doctor_id)
```

Then add merge-patch logic after the existing `tags` serialization:

```python
if "structured_fields" in updates and isinstance(updates["structured_fields"], dict):
    from services.export.outpatient_report import OUTPATIENT_FIELD_KEYS
    patch = {k: v for k, v in updates["structured_fields"].items()
             if k in OUTPATIENT_FIELD_KEYS}
    existing_sf = json.loads(rec.structured_fields or "{}")
    existing_sf.update(patch)
    updates["structured_fields"] = json.dumps(existing_sf, ensure_ascii=False)
```

Add `structured_fields` to the response dict:

```python
"structured_fields": json.loads(rec.structured_fields) if rec.structured_fields else None,
```

- [ ] **Step 3: Admin PATCH — extend allowlist + merge-patch**

At line 518, update:

```python
_ADMIN_RECORD_ALLOWED_FIELDS = {"content", "tags", "record_type", "structured_fields"}
```

Add the same merge-patch logic for `structured_fields` as the doctor PATCH
(after the existing `tags` serialization block).

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/ui/__init__.py
git commit -m "feat: RecordUpdate with structured_fields merge-patch + version snapshot"
```

---

## Chunk 4: Frontend

### Task 13: Frontend — display and edit structured fields

**Files:**
- Modify: `frontend/src/components/RecordFields.jsx`
- Modify: `frontend/src/pages/doctor/RecordCard.jsx`
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Update `RecordFields.jsx`**

Add structured fields display. If `record.structured_fields` exists, render as
a labeled field list; otherwise fall back to showing `content` as today.

```jsx
const FIELD_LABELS = {
  department: "科别",
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  personal_history: "个人史",
  marital_history: "婚育史",
  family_history: "家族史",
  physical_exam: "体格检查",
  aux_exam: "辅助检查",
  diagnosis: "初步诊断",
  treatment: "治疗方案",
  followup: "医嘱及随访",
};

// Inside the component, before the existing content display:
if (record.structured_fields) {
  return (
    <Box>
      {Object.entries(FIELD_LABELS).map(([key, label]) => {
        const value = record.structured_fields[key];
        if (!value) return null;
        return (
          <Box key={key} sx={{ mb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
              {value}
            </Typography>
          </Box>
        );
      })}
      {/* Still show tags */}
      <Stack direction="row" spacing={0.6} sx={{ mt: 1 }}>
        {tags.map((tag, i) => <Chip key={i} label={tag} size="small" />)}
      </Stack>
    </Box>
  );
}
// else: fall through to existing content-only display
```

- [ ] **Step 2: Update `RecordCard.jsx`**

In the collapsed card view, show `diagnosis` and `chief_complaint` from
`structured_fields` as summary text if available:

```jsx
const sf = record.structured_fields;
const summary = sf
  ? [sf.chief_complaint, sf.diagnosis].filter(Boolean).join(" — ")
  : null;
```

Display `summary` in the card header area if non-null, otherwise use the
existing content preview.

- [ ] **Step 3: Update `api.js`**

In the `updateRecord` function, ensure `structured_fields` is included in the
PATCH payload when provided:

```js
export async function updateRecord(doctorId, recordId, fields) {
  // fields may include: content, tags, record_type, structured_fields
  const resp = await fetch(`/api/manage/records/${recordId}?doctor_id=${doctorId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  return resp.json();
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/RecordFields.jsx \
       frontend/src/pages/doctor/RecordCard.jsx \
       frontend/src/api.js
git commit -m "feat: display structured fields in RecordFields and RecordCard"
```

---

## Final: Verification

### Task 14: Manual smoke test

- [ ] **Step 1: Start the app**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Create a record via chat**

Send a message with clinical content (e.g., "患者张三，男，45岁，头痛3天，伴恶心呕吐，既往高血压5年，青霉素过敏，已婚育1子，父亲高血压。查体血压140/90。CT未见异常。诊断偏头痛，布洛芬治疗，1周复诊"). Verify:

- Response includes `record_id`
- DB record has `structured_fields` JSON with populated fields
- `content` (narrative) is also present

- [ ] **Step 3: Export outpatient report**

Hit `/api/export/patient/{patient_id}/outpatient-report`. Verify:
- PDF is generated without an LLM call (check logs for "using stored fields")
- PDF shows the 13 structured fields

- [ ] **Step 4: PATCH a field**

```bash
curl -X PATCH "http://localhost:8000/api/manage/records/{record_id}?doctor_id=test_doctor" \
  -H "Content-Type: application/json" \
  -d '{"structured_fields": {"diagnosis": "紧张型头痛"}}'
```

Verify:
- Response has updated `structured_fields.diagnosis`
- Other fields are preserved (merge-patch)
- A version snapshot was created

- [ ] **Step 5: Check legacy fallback**

For a record with `structured_fields = NULL`, verify export still works via LLM
fallback (check logs for "legacy fallback, calling LLM").
