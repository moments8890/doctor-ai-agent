# Medical Record Import/Export Design

## Goal

Add medical record export (JSON + PDF) and import (image/PDF/scanned copy) following the Chinese 《病历书写基本规范》(卫医政发〔2010〕11号) outpatient record standard, with 14 structured fields.

## Standard Fields (14)

Per 《病历书写基本规范》 outpatient record format:

| # | Key | Chinese Label | Notes |
|---|-----|---------------|-------|
| 1 | `department` | 科别 | Header field |
| 2 | `chief_complaint` | 主诉 | |
| 3 | `present_illness` | 现病史 | |
| 4 | `past_history` | 既往史 | |
| 5 | `allergy_history` | 过敏史 | |
| 6 | `personal_history` | 个人史 | Smoking, alcohol, occupation (no longer includes marital/reproductive) |
| 7 | `marital_reproductive` | 婚育史 | **New** — split from personal_history |
| 8 | `family_history` | 家族史 | |
| 9 | `physical_exam` | 体格检查 | General: T, P, R, BP etc. |
| 10 | `specialist_exam` | 专科检查 | **New** — specialty-specific focused exam |
| 11 | `auxiliary_exam` | 辅助检查 | Labs, imaging, ECG etc. |
| 12 | `diagnosis` | 初步诊断 | |
| 13 | `treatment_plan` | 治疗方案 | |
| 14 | `orders_followup` | 医嘱及随访 | |

## Architecture: Unified Schema Layer (Approach B)

### Core Principle

A shared `OutpatientRecord` Pydantic model serves as the data contract for both export and import. No DB schema changes — `medical_records.content` remains prose text.

### Shared Schema

**File:** `src/services/medical_record_schema.py`

```python
class PatientInfo(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None

class OutpatientRecord(BaseModel):
    """门诊病历标准格式 — 14 fields per 《病历书写基本规范》"""
    patient: PatientInfo = Field(default_factory=PatientInfo)

    department: Optional[str] = None          # 科别
    chief_complaint: Optional[str] = None     # 主诉
    present_illness: Optional[str] = None     # 现病史
    past_history: Optional[str] = None        # 既往史
    allergy_history: Optional[str] = None     # 过敏史
    personal_history: Optional[str] = None    # 个人史
    marital_reproductive: Optional[str] = None # 婚育史
    family_history: Optional[str] = None      # 家族史
    physical_exam: Optional[str] = None       # 体格检查
    specialist_exam: Optional[str] = None     # 专科检查
    auxiliary_exam: Optional[str] = None      # 辅助检查
    diagnosis: Optional[str] = None           # 初步诊断
    treatment_plan: Optional[str] = None      # 治疗方案
    orders_followup: Optional[str] = None     # 医嘱及随访
```

All fields are Optional because external records may be incomplete.

## Export Pipeline

### Data Flow

```
MedicalRecordDB.content (prose, possibly multiple records)
        |
        v
  LLM extraction (report-extract.md prompt, 14 fields)
        |
        v
  OutpatientRecord (Pydantic validated)
        |
   +----+----+
   |         |
  JSON      PDF
```

### Multi-Record Merge Strategy

When a patient has multiple records, all are concatenated (separated by `---`) and passed to the LLM in chronological order (`created_at asc`). The extraction prompt instructs the LLM:

- **Override fields** (chief_complaint, diagnosis, treatment_plan): use the most recent record
- **Cumulative fields** (past_history, allergy_history, family_history): merge information from all records
- **Physical/exam fields** (physical_exam, specialist_exam, auxiliary_exam): use the most recent values

This requires no code logic — the LLM handles merging guided by the prompt. The exported PDF/JSON includes a source annotation ("综合 {date_range} 共 {n} 条记录") so the doctor knows the data coverage.

### Changes to Existing Files

1. **`src/prompts/report-extract.md`**: Expand from 12 to 14 fields. Add `marital_reproductive` (婚育史) and `specialist_exam` (专科检查). Adjust `personal_history` description to exclude marital/reproductive info. Add multi-record merge guidance (override vs cumulative fields).

2. **`src/services/export/outpatient_report.py`**: Expand `OUTPATIENT_FIELDS` list from 12 to 14 entries. Update `_FIELD_KEYS` and extraction result parsing. Add `export_as_json()` function (thin wrapper: extract → validate into OutpatientRecord → `model_dump()`).
   - **Field key renames** (align with OutpatientRecord schema):
     - `aux_exam` → `auxiliary_exam`
     - `treatment` → `treatment_plan`
     - `followup` → `orders_followup`
   - These renames only affect the internal extraction dict keys and prompt. No stored data uses these keys (extraction is always done on-the-fly), so no backward-compatibility issue.

3. **`src/services/export/pdf_export.py`**: Update `generate_outpatient_report_pdf()` to render 14 fields.

### API

Extend existing endpoint with format parameter:

```
GET /api/export/patient/{patient_id}/outpatient-report?format=json|pdf
```

- `format=pdf` (default): current behavior, returns PDF. Backward compatible — existing clients without the query parameter get the same PDF behavior.
- `format=json`: returns `OutpatientRecord` JSON

Audit logging via `MedicalRecordExport` table (existing) with `export_format="json"`.

## Import Pipeline

### Data Flow

```
Doctor uploads image/PDF/scan (Web UI)
        |
        v
  MIME + magic bytes validation (JPG/PNG/PDF only)
        |
        v
  File preprocessing (PDF -> per-page images via pdftoppm)
        |
        v
  Vision LLM sees all pages -> OutpatientRecord JSON
        |
        v
  Pydantic validation
        |
        v
  Auto-create MedicalRecordDB
    - content = structured prose from 14 fields
    - tags = empty (no auto-extraction for MVP)
    - record_type = "import"
    - needs_review = True
```

### File Handling

| Input | Processing |
|-------|------------|
| Image (JPG/PNG) | Validate MIME type + magic bytes, pass directly to Vision LLM |
| PDF | Validate MIME + magic bytes, convert to per-page images via shared `pdf_to_images()` utility, pass all pages as multi-image input |
| Scanned copy | Same as image |

**Page limit:** 10 pages max. If exceeded, return 413 error asking doctor to split the file.
**File size limit:** 20 MB max upload size.
**File type validation:** Check Content-Type header and file magic bytes. Reject with 415 Unsupported Media Type if not JPG/PNG/PDF.

### Vision LLM

- New prompt: `src/prompts/vision-import.md`
- Model: Qwen-VL or equivalent via `VISION_LLM_*` env vars (existing Ollama infra)
- Multi-image input: reuse the multi-image pattern from `pdf_extract_llm.py` (`_build_page_content()`), sharing the provider/egress/retry infrastructure from `vision.py`
- All pages sent in one call with instruction "以下是同一份病历的多页扫描，请综合所有页面提取"
- Output: 14-field JSON matching `OutpatientRecord` schema + `patient` info (name/gender/age if visible on the document)
- `temperature: 0.1`. If the vision model does not support `response_format: json_object`, fall back to bracket-matching extraction (find first `{`, find last `}`, `json.loads()`) rather than regex.
- **PHI egress gate:** Must go through `is_local_provider()` / `check_cloud_egress()` (same as existing `vision.py`) before sending images to any cloud provider.

### Patient Info on Import

The Vision LLM prompt also extracts patient demographics (name, gender, age) from the document header if visible. These populate the `PatientInfo` sub-model. If the doctor provides a `patient_id` at upload time, the DB patient data takes precedence over LLM-extracted demographics.

### Needs Review Flag

All imported records are created with `needs_review = True`. This signals to the UI that the record was machine-extracted and should be reviewed by the doctor. The doctor can mark it as reviewed after checking the content. This avoids polluting patient history with garbled Vision LLM output from low-quality scans.

Implementation: add a nullable `needs_review` boolean column to `medical_records` table (default `NULL` for existing records, `True` for imports). Simple `ALTER TABLE`, no migration needed per project rules.

### Fallback Design

`vision_import.py` exposes an `extract_from_images()` function. If Vision LLM quality is insufficient for handwritten records in the future, this function can be replaced with a two-step pipeline (Document OCR -> text LLM extraction) without changing callers.

### Storage

- `content`: 14 fields formatted as label-value prose using a simple template:
  ```
  【主诉】{chief_complaint}
  【现病史】{present_illness}
  ...
  ```
  This is consistent with how doctors expect to read records, and can be re-extracted later if needed.
- `tags`: empty for imported records (MVP simplification)
- `record_type`: `"import"` (already a supported value)
- `patient_id`: optional, passed by doctor at upload time

### API

```
POST /api/import/medical-record
```

- **Request:** multipart form — `file` (image/PDF, max 20 MB), `patient_id` (optional), `doctor_id`
- **Response:** created record details + extracted `OutpatientRecord` JSON (so doctor can see extraction result)
- **Error responses:**
  - 413: file too large (> 20 MB) or too many pages (> 10)
  - 415: unsupported file type (not JPG/PNG/PDF)
  - 422: Vision LLM returned invalid/unparseable JSON
  - 502: Vision LLM unavailable after retries
- No confirmation step — auto-creates record with `needs_review = True`

### New Files

1. **`src/services/import/vision_import.py`** — file preprocessing + Vision LLM call + OutpatientRecord validation. Reuses vision client infra from `vision.py`.
2. **`src/prompts/vision-import.md`** — Vision extraction prompt for 14 fields + patient info from medical record images.
3. **`src/channels/web/import_routes.py`** — POST endpoint for file upload. Register in `main.py` alongside existing `export_router`.
4. **`src/services/utils/pdf_utils.py`** — Shared `pdf_to_images()` utility extracted from `pdf_extract_llm.py`. Both import and knowledge features import from here.

## Scope

### In Scope
- 14-field OutpatientRecord schema (shared)
- JSON + PDF export via LLM extraction
- Image/PDF/scan import via Vision LLM
- Web API endpoints
- Export audit logging (existing infra)
- Multi-record merge for export (prompt-guided)
- Multi-page PDF import (up to 10 pages)
- `needs_review` flag for imported records
- File type/size validation on import
- Shared `pdf_to_images()` utility

### Deferred
- **Multi-record splitting on import** — one upload = one record for now
- **WeChat channel support** — Web only for MVP
- **Handwritten record OCR** — rely on Vision LLM; add Document OCR fallback later if needed
- **Structured DB storage** — fields remain in prose content, not as DB columns; add `structured_json` column later if round-trip fidelity is an issue
- **ICD coding** — diagnosis stored as text, no ICD code lookup
- **Tags for imported records** — leave empty for MVP

## Known Risks

| Risk | Mitigation |
|------|------------|
| Vision LLM misreads handwritten text | `needs_review` flag; extraction result returned to doctor; doctor can edit/delete |
| Multi-record merge produces inaccurate summary | Prompt specifies override vs cumulative field rules; source annotation shows date range and record count |
| PDF > 10 pages | Hard limit with 413 error |
| Vision LLM model not available | `call_with_retry_and_fallback()` with configurable fallback model |
| Lossy round-trip (import prose → re-extract on export) | Acceptable for MVP; label-value format is highly extractable. Defer `structured_json` column optimization |
| Malicious file upload | MIME + magic bytes validation; file size limit; 415 rejection |
