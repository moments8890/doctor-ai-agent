# ADR 0014: Execution Plan — Medical Record Import/Export

## Goal

Implement medical record export (JSON + PDF, 14 fields) and import
(image/PDF/scan via Vision LLM) as specified in
[ADR 0014](../adr/0014-medical-record-import-export.md).

## Source of Truth

- **ADR**: `docs/adr/0014-medical-record-import-export.md`
- **Spec**: `docs/superpowers/specs/2026-03-16-medical-record-import-export-design.md`

When in doubt, the spec wins over this plan.

## Dependency Graph

```text
A (schema) ─── gate ───┬──→ B (export: prompt + extraction)
                        ├──→ C (export: PDF 14 fields)
                        ├──→ D (shared pdf_to_images utility)
                        └──→ E (import: vision pipeline)

B ──→ F (export: JSON endpoint + format param)
C ──→ F
D ──→ E
E ──→ G (import: API endpoint + routes)
F ──→ H (DB: needs_review column)
G ──→ H
H ──→ I (smoke test)
```

**A is the gate.** Schema defines the shared contract. After A lands,
export and import streams can fan out. API endpoints (F, G) go after
their service layers. DB column (H) and smoke test (I) are last.

---

## Stream A: Schema (gate)

### A. Create `OutpatientRecord` schema

**New file:** `src/services/medical_record_schema.py`

```python
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field

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

# Field metadata: (key, chinese_label)
OUTPATIENT_FIELD_META = [
    ("department",          "科别"),
    ("chief_complaint",     "主诉"),
    ("present_illness",     "现病史"),
    ("past_history",        "既往史"),
    ("allergy_history",     "过敏史"),
    ("personal_history",    "个人史"),
    ("marital_reproductive","婚育史"),
    ("family_history",      "家族史"),
    ("physical_exam",       "体格检查"),
    ("specialist_exam",     "专科检查"),
    ("auxiliary_exam",      "辅助检查"),
    ("diagnosis",           "初步诊断"),
    ("treatment_plan",      "治疗方案"),
    ("orders_followup",     "医嘱及随访"),
]

FIELD_KEYS = [k for k, _ in OUTPATIENT_FIELD_META]
```

**Verification:** Import the module, instantiate `OutpatientRecord()` with no
args, confirm all fields default to `None`.

---

## Stream B: Export — Prompt + Extraction

### B1. Expand `report-extract.md` prompt

**File:** `src/prompts/report-extract.md`

Changes:

1. Change "12 个字段" → "14 个字段"
2. Rename existing keys:
   - `aux_exam` → `auxiliary_exam`
   - `treatment` → `treatment_plan`
   - `followup` → `orders_followup`
3. Add 2 new field descriptions:
   - `marital_reproductive`（婚育史）— 婚姻状况、生育史。
     示例: `{"marital_reproductive": "已婚，育有1子1女。"}`
   - `specialist_exam`（专科检查）— 针对本科的专项体格检查。
     示例: `{"specialist_exam": "心尖搏动正常，未闻及杂音。"}`
4. Adjust `personal_history` description: remove "婚育" from the description,
   keep only smoking, alcohol, occupation.
5. Add multi-record merge guidance at the top of requirements:
   ```
   - 当输入包含多条病历记录（以 --- 分隔）时：
     - 覆盖型字段（主诉、诊断、治疗方案、医嘱及随访）：以最新一条记录为准。
     - 累积型字段（既往史、过敏史、家族史、婚育史）：合并所有记录中的信息。
     - 检查型字段（体格检查、专科检查、辅助检查）：以最新一条记录为准。
   ```

### B2. Update `outpatient_report.py`

**File:** `src/services/export/outpatient_report.py`

Changes:

1. Replace `OUTPATIENT_FIELDS` list (12 → 14 entries, with renamed keys):
   ```python
   from services.medical_record_schema import OUTPATIENT_FIELD_META
   OUTPATIENT_FIELDS = OUTPATIENT_FIELD_META  # single source of truth
   ```

2. Update `_FIELD_KEYS`:
   ```python
   from services.medical_record_schema import FIELD_KEYS
   _FIELD_KEYS = FIELD_KEYS
   ```

3. Add `export_as_json()` function:
   ```python
   async def export_as_json(
       records: list,
       patient: Any = None,
       doctor_id: Optional[str] = None,
   ) -> dict:
       """Extract fields and return as OutpatientRecord dict."""
       fields = await extract_outpatient_fields(records, patient, doctor_id)
       from services.medical_record_schema import OutpatientRecord, PatientInfo
       patient_info = PatientInfo()
       if patient:
           patient_info.name = getattr(patient, "name", None)
           patient_info.gender = getattr(patient, "gender", None)
           yob = getattr(patient, "year_of_birth", None)
           if yob:
               from datetime import date
               patient_info.age = date.today().year - int(yob)
       record = OutpatientRecord(patient=patient_info, **fields)
       return record.model_dump()
   ```

**Verification:** Call `export_as_json()` with a test record, confirm 14
fields present in output + patient info populated.

---

## Stream C: Export — PDF 14 Fields

### C. Update `pdf_export.py`

**File:** `src/services/export/pdf_export.py`

Changes:

1. Import `OUTPATIENT_FIELD_META` from `medical_record_schema` instead of
   using local field list.

2. Update `generate_outpatient_report_pdf()` to iterate over 14 fields
   (the existing loop already iterates `OUTPATIENT_FIELDS`, so updating the
   import is sufficient).

3. Add source annotation line below the patient info header:
   ```
   "综合 {earliest_date} 至 {latest_date} 共 {n} 条记录"
   ```
   Only shown when multiple records are included.

**Verification:** Generate a PDF, confirm 婚育史 and 专科检查 sections appear.

---

## Stream D: Shared PDF Utility

### D. Extract `pdf_to_images()` to shared utility

**New file:** `src/services/utils/pdf_utils.py`

Extract `_pdf_to_images()` from `services/knowledge/pdf_extract_llm.py`:

```python
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from typing import List

def pdf_to_images(pdf_bytes: bytes, max_pages: int = 10) -> List[bytes]:
    """Convert PDF to list of PNG page images using pdftoppm.

    Raises ValueError if page count exceeds max_pages.
    """
    # ... extract existing logic from pdf_extract_llm.py
```

Update `pdf_extract_llm.py` to import from the new location:
```python
from services.utils.pdf_utils import pdf_to_images
```

Create `src/services/utils/__init__.py` if it doesn't exist.

**Verification:** Import from both locations works. Existing knowledge
pipeline still functions.

---

## Stream E: Import — Vision Pipeline

### E. Create `vision_import.py`

**New file:** `src/services/import/vision_import.py`

Create `src/services/import/__init__.py`.

```python
from __future__ import annotations
import json
from typing import List, Optional

from services.medical_record_schema import OutpatientRecord, PatientInfo, FIELD_KEYS

async def extract_from_images(
    images: List[bytes],
    prompt_text: str,
) -> OutpatientRecord:
    """Send images to Vision LLM, return validated OutpatientRecord.

    Uses existing vision client infra (provider selection, PHI egress gate,
    retry/fallback) from vision.py.
    """
    # 1. Build multi-image message (reuse _build_page_content pattern)
    # 2. PHI egress check: is_local_provider() / check_cloud_egress()
    # 3. Call Vision LLM with temperature=0.1
    # 4. Parse JSON response:
    #    - Try json.loads() on response content
    #    - If fails, bracket-matching fallback: find first {, last }, json.loads()
    # 5. Validate into OutpatientRecord
    # 6. Return OutpatientRecord

async def import_medical_record(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    doctor_id: str,
    patient_id: Optional[int] = None,
) -> dict:
    """Full import pipeline: file → images → Vision LLM → save record.

    Returns dict with created record details + extracted OutpatientRecord.
    """
    # 1. Validate file type (MIME + magic bytes)
    # 2. Convert to images:
    #    - PDF: pdf_to_images() from services.utils.pdf_utils
    #    - Image: [file_bytes]
    # 3. Load prompt from prompts/vision-import.md
    # 4. Call extract_from_images()
    # 5. Format content as label-value prose:
    #    【主诉】{chief_complaint}
    #    【现病史】{present_illness}
    #    ...
    # 6. Save via save_record() with:
    #    - record_type = "import"
    #    - needs_review = True
    #    - tags = [] (empty for MVP)
    # 7. Return { record: {...}, extracted: OutpatientRecord.model_dump() }
```

### E2. Create `vision-import.md` prompt

**New file:** `src/prompts/vision-import.md`

```markdown
# 门诊病历图片提取

你是门诊病历识别助手。请仔细阅读以下病历图片，提取标准门诊病历字段。

## 要求

- 仅提取图片中可见的信息，不得推断或虚构。
- 若某字段在图片中未出现，将值设为空字符串 ""。
- 若图片包含多页，综合所有页面提取完整信息。
- 输出合法 JSON 对象，包含以下字段。

## 患者信息

- **patient**：包含 name（姓名）、gender（性别）、age（年龄，整数）。
  若图片中未显示患者信息，设为空字符串或 null。

## 14 个病历字段

[同 report-extract.md 的 14 个字段定义，含示例]

## 输出格式

{
  "patient": {"name": "...", "gender": "...", "age": ...},
  "department": "...",
  "chief_complaint": "...",
  ...（14 fields）
}
```

### File validation helpers

In `vision_import.py`, add:

```python
import struct

_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"%PDF": "application/pdf",
}
_ALLOWED_TYPES = frozenset(_MAGIC.values())
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

def validate_upload(file_bytes: bytes, content_type: str) -> str:
    """Validate file type and size. Returns detected MIME type.

    Raises:
        ValueError: 415 if type invalid, 413 if too large.
    """
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise ValueError("413:File exceeds 20 MB limit")
    for magic, mime in _MAGIC.items():
        if file_bytes[:len(magic)] == magic:
            return mime
    raise ValueError("415:Unsupported file type. Accepted: JPG, PNG, PDF")
```

**Verification:** Upload a test image, confirm OutpatientRecord JSON returned
with expected fields.

---

## Stream F: Export API Endpoint

### F. Add `format` parameter to export endpoint

**File:** `src/channels/web/export.py`

Changes to `export_outpatient_report()`:

1. Add `format` query parameter (default `"pdf"`):
   ```python
   @router.get("/api/export/patient/{patient_id}/outpatient-report")
   async def export_outpatient_report(
       patient_id: int,
       format: str = Query("pdf", regex="^(json|pdf)$"),
       ...
   ):
   ```

2. After fetching records, branch on format:
   ```python
   if format == "json":
       from services.export.outpatient_report import export_as_json
       data = await export_as_json(records, patient, resolved_doctor_id)
       # Audit log with export_format="json"
       return JSONResponse(data)
   else:
       # Existing PDF flow
       ...
   ```

3. Add source annotation data to both paths: earliest/latest date, record count.

**Verification:** `GET /api/export/patient/1/outpatient-report` → PDF (backward
compat). `GET /api/export/patient/1/outpatient-report?format=json` → JSON.

---

## Stream G: Import API Endpoint

### G. Create import routes

**New file:** `src/channels/web/import_routes.py`

```python
from __future__ import annotations
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

router = APIRouter()

@router.post("/api/import/medical-record")
async def import_medical_record(
    file: UploadFile = File(...),
    patient_id: Optional[int] = Form(None),
    doctor_id: str = Form("web_doctor"),
):
    """Import a medical record from image/PDF/scan."""
    file_bytes = await file.read()

    try:
        from services.import.vision_import import import_medical_record as do_import
        result = await do_import(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            doctor_id=doctor_id,
            patient_id=patient_id,
        )
        return JSONResponse(result, status_code=201)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("413:"):
            raise HTTPException(413, msg[4:])
        if msg.startswith("415:"):
            raise HTTPException(415, msg[4:])
        raise HTTPException(422, msg)
    except RuntimeError:
        raise HTTPException(502, "Vision LLM unavailable")
```

**Register in `main.py`:**

```python
from channels.web.import_routes import router as import_router
app.include_router(import_router)
```

**Verification:** `POST /api/import/medical-record` with a test image → 201
with record details + extracted fields.

---

## Stream H: DB — needs_review Column

### H. Add `needs_review` column

**File:** `src/db/models/records.py`

Add to `MedicalRecordDB`:
```python
needs_review = Column(Boolean, nullable=True, default=None)
```

**Manual ALTER TABLE** (no Alembic per project rules):
```sql
ALTER TABLE medical_records ADD COLUMN needs_review BOOLEAN DEFAULT NULL;
```

Add to `create_tables()` in `db/engine.py` if needed (SQLAlchemy
`create_all()` will handle new columns on fresh DBs).

**Verification:** `SELECT needs_review FROM medical_records LIMIT 1` works.
Imported records have `needs_review = True`.

---

## Stream I: Smoke Test

### I. Manual verification

Start app, test all paths:

**Export:**

| Test | URL | Expected |
|------|-----|----------|
| PDF export (backward compat) | `GET /api/export/patient/{id}/outpatient-report` | PDF with 14 fields |
| PDF export explicit | `GET /api/export/patient/{id}/outpatient-report?format=pdf` | Same PDF |
| JSON export | `GET /api/export/patient/{id}/outpatient-report?format=json` | JSON with 14 fields + patient info |
| Multi-record source annotation | Export patient with 3+ records | "综合 ... 共 N 条记录" shown |

**Import:**

| Test | Input | Expected |
|------|-------|----------|
| JPG upload | Photo of printed medical record | 201 + OutpatientRecord JSON |
| PNG upload | Screenshot of HIS record | 201 + OutpatientRecord JSON |
| PDF upload (2 pages) | Scanned 2-page record | 201 + combined extraction |
| PDF > 10 pages | Large PDF | 413 error |
| File > 20 MB | Large image | 413 error |
| Invalid file type | .docx file | 415 error |
| needs_review flag | After any import | `SELECT needs_review FROM medical_records WHERE id=? → True` |

**Verify:**
- Exported JSON validates against `OutpatientRecord` schema
- Imported record `content` uses 【字段名】format
- Imported record `record_type = "import"`
- Imported record `tags = []`
- `medical_record_exports` audit table has entry for JSON exports
- Existing PDF export still works unchanged

---

## Implementation Order Summary

| Step | Stream | Description | Depends On | Parallelizable |
|------|--------|-------------|------------|----------------|
| 1 | A | Create `OutpatientRecord` schema | — | Gate |
| 2 | B | Expand prompt + extraction (14 fields) | A | Yes with C, D |
| 3 | C | Update PDF rendering (14 fields) | A | Yes with B, D |
| 4 | D | Extract shared `pdf_to_images()` | A | Yes with B, C |
| 5 | E | Vision import pipeline + prompt | A, D | After D |
| 6 | F | Export API: `?format=json\|pdf` | B, C | After B, C |
| 7 | G | Import API endpoint + routes | E | After E |
| 8 | H | DB: `needs_review` column | — | Anytime |
| 9 | I | Smoke test all paths | All | Last |
