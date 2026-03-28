# D6.7 Bulk Data Export — Design Spec

> Date: 2026-03-27
> Status: Approved (revised after Codex review + performance analysis)
> Parity Matrix: D6.7

## Goal

Enable doctors to export all their patient data as a downloadable ZIP archive for backup, sharing with patients, and offline review. Also fix the existing single-patient export to respect section/range selections from the frontend dialog.

## Scope

- Records + patient demographics only
- No AI-generated content (no ai_suggestions, no diagnosis output, no interview conversation logs)
- Pure clinical data the doctor and patient own

## Part 1: Single Patient Report (fix existing)

### Problem

`ExportSelectorDialog.jsx` has section checkboxes and a range selector, but the backend endpoint `GET /api/export/patient/{patient_id}/pdf` ignores them — always exports everything.

### Fix

Pass selected sections and range as query params:

```
GET /api/export/patient/{patient_id}/pdf
  ?sections=basic,diagnosis,visits,prescriptions,allergies
  &visit_range=5|10|all
```

**Auth:** `doctor_id` resolved from JWT token (not client-supplied).

**Section → NHC field mapping:**

| Section key | Label | NHC fields included |
|-------------|-------|---------------------|
| `basic` | 基本信息 | Patient name, gender, age, phone (always included) |
| `diagnosis` | 诊断信息 | `diagnosis`, `final_diagnosis`, `key_symptoms` |
| `visits` | 就诊记录 | `chief_complaint`, `present_illness`, `past_history`, `physical_exam`, `specialist_exam`, `auxiliary_exam`, `treatment_plan`, `orders_followup` |
| `prescriptions` | 处方记录 | `orders_followup` (prescription subset) |
| `allergies` | 过敏信息 | `allergy_history` |

**Range:** `visit_range=5` → last 5 records, `10` → last 10, `all` → all records (no silent cap — if doctor selects "all", export all).

**Input validation:** Reject unknown section keys. Empty sections → default to all. `visit_range` must be `5`, `10`, or `all`.

**Backend changes:** `src/domain/records/pdf_export.py` — filter fields based on `sections` param before rendering (create filtered copies, never mutate ORM objects). `src/channels/web/export.py` — accept and pass query params.

**Frontend changes:** `ExportSelectorDialog.jsx` — pass selected sections and range to the `exportPatientPdf()` API call.

## Part 2: Bulk Export (new)

### Trigger

New "导出全部数据" button in Settings page, in the existing settings list (near QR code / template section).

### User Flow

1. Doctor taps "导出全部数据" in Settings
2. Confirmation dialog: "将导出所有患者病历为ZIP文件，可能需要几分钟"
3. Loading state with progress indicator ("12/45 患者已处理")
4. Download triggers automatically when ready
5. Success toast: "导出完成"

### Performance Estimates

| Doctor size | Patients | Est. time | Strategy |
|------------|----------|-----------|----------|
| Small | 10-30 | 5-30s | Synchronous, spinner |
| Medium | 50-100 | 30s-1.5min | Async, progress bar |
| Large | 200-500 | 2-3min | Async, progress bar |

**Key bottleneck:** CJK font loading in fpdf2 (~200-500ms per PDF instance).

**Font caching optimization:** Load CJK font file bytes into memory once at export start. Pass cached font bytes to each FPDF instance. Reduces 500-patient export from ~7min to ~2min.

**Hard cap:** 500 patients per export. If exceeded, show warning and ask doctor to export in batches.

### API

**Auth:** All endpoints resolve `doctor_id` from JWT token. No client-supplied doctor_id.

```
POST /api/export/bulk
  Response: 202 Accepted, { task_id }

GET /api/export/bulk/{task_id}
  Auth check: task.doctor_id must match authenticated doctor
  Response (generating): 202 { status: "generating", progress: "12/45" }
  Response (ready): 200 { status: "ready", download_url: "/api/export/bulk/{task_id}/download" }
  Response (failed): 200 { status: "failed", error: "导出失败，请稍后重试" }
  Response (expired/not found): 404

GET /api/export/bulk/{task_id}/download
  Auth check: task.doctor_id must match authenticated doctor
  Response: application/zip
  Headers: Content-Disposition: attachment; filename*=UTF-8''导出_{date}.zip
```

**Error responses:** Never expose internal paths or exception details. Use generic Chinese error messages.

### ZIP Structure

```
导出_2026-03-27.zip
├── 患者汇总.csv
├── 张三_p123/
│   └── 病历_张三.pdf
├── 李四_p456/
│   └── 病历_李四.pdf
└── ...
```

**Filename sanitization:** Strip characters outside `[a-zA-Z0-9\u4e00-\u9fff_-]` from patient/doctor names in paths. Replace with `_`. Prevents zip-slip and path traversal.

**患者汇总.csv columns:** 姓名, 性别, 年龄, 手机号, 病历数, 最近就诊日期, 文件夹名

**CSV injection defense:** Prefix cell values starting with `=`, `+`, `-`, `@` with a single quote (`'`).

### Backend Implementation

**New file:** `src/services/export/bulk_export.py`

```python
async def generate_bulk_export(doctor_id: str, task: BulkExportTask) -> None:
    """Generate ZIP of all patient PDFs. Streams to disk, never holds all in memory."""
    # 1. Load CJK font bytes once into memory
    # 2. Query all patients for doctor (count for progress)
    # 3. Create ZipFile on disk
    # 4. For each patient:
    #    a. Open fresh DB session (don't hold one long session)
    #    b. Query patient + records
    #    c. Generate PDF bytes (reuse cached font)
    #    d. Write PDF directly into ZipFile
    #    e. Update task.progress
    # 5. Generate 患者汇总.csv, write into ZipFile
    # 6. Close ZipFile, update task.status = "ready"
    # 7. On any error: cleanup partial files, task.status = "failed"
```

**Streaming design (memory safety):**
- Generate one PDF at a time, write directly into `zipfile.ZipFile`
- Never hold all PDFs in memory simultaneously
- Open/close DB session per patient (prevent connection exhaustion)
- Delete temp files on error

**Execution:** Run in `asyncio.run_in_executor(None, ...)` to avoid blocking the event loop. PDF generation is CPU-bound synchronous code.

**New router:** Add to `src/channels/web/export.py`

- `POST /api/export/bulk` — start async generation, return task_id
- `GET /api/export/bulk/{task_id}` — poll status (with ownership check)
- `GET /api/export/bulk/{task_id}/download` — serve ZIP file (with ownership check)

**Task tracking:** In-memory dict `_bulk_tasks: dict[str, BulkExportTask]` with fields:
- `doctor_id`: for ownership verification
- `status`: generating | ready | failed
- `progress`: "N/M" patients processed
- `file_path`: path to ZIP when ready
- `created_at`: for expiry check
- `downloading`: bool flag to prevent cleanup during active download

### Security

- **Auth:** doctor_id from JWT on every endpoint, never client-supplied
- **Task ownership:** every GET verifies `task.doctor_id == jwt_doctor_id`
- **Rate limit:** 1 bulk export per hour per doctor. Atomic check (check-and-set, not check-then-set) to prevent race condition on parallel requests.
- **Global concurrency cap:** Max 1 concurrent bulk export across all doctors. Queue or reject others.
- **Cleanup:** ZIP auto-deleted after 30 minutes, but only when no active download is in progress. On server restart, sweep and delete orphan temp files.
- **Hard timeout:** If generation exceeds 30 minutes, mark as failed and clean up.
- **Audit:** Log export start, completion (with file count/size), failure, and download events.
- **No PHI in URLs:** Download URL uses opaque task_id
- **No AI content** in any exported PDF
- **Filename sanitization:** All names stripped of special characters before use in ZIP paths or Content-Disposition headers

### Frontend

**Settings page addition:** New row in SettingsListSubpage:
- Icon: download/archive icon
- Label: "导出全部数据"
- Subtitle: "下载所有患者病历 (ZIP)"
- Tap → confirmation dialog → loading with progress → download

**New state in SettingsPage.jsx:**
- `bulkExportTaskId` — null or active task ID (persisted to localStorage to survive page refresh)
- `bulkExportStatus` — idle | generating | ready | failed
- `bulkExportProgress` — "12/45"
- Poll `GET /bulk/{task_id}` every 3 seconds while generating

**New API methods in api.js:**
- `startBulkExport()` → POST (no doctor_id param, from JWT)
- `getBulkExportStatus(taskId)` → GET
- `downloadBulkExport(taskId)` → trigger browser download

## Files Modified

| File | Change |
|------|--------|
| `src/domain/records/pdf_export.py` | Filter fields based on sections param (filtered copies, not ORM mutation) |
| `src/channels/web/export.py` | Accept sections/range query params; add bulk export endpoints with ownership checks |
| `src/services/export/bulk_export.py` | **New** — streaming ZIP generation with font caching |
| `frontend/web/src/api.js` | Add bulk export API methods; update exportPatientPdf to pass sections |
| `frontend/web/src/components/ExportSelectorDialog.jsx` | Pass sections/range to API call |
| `frontend/web/src/pages/doctor/SettingsPage.jsx` | Add bulk export button + polling UI + localStorage persistence |

## No Changes

- `VoiceInput.jsx`, patient pages — untouched
- AI suggestion models — not included in export
- Interview conversation logs — not included in export

## Deferred

- JSON/CSV structured data export (for migration use case)
- Incremental export (only new records since last export)
- Scheduled automatic backups
- WeChat bulk export (file size limits)
- Step-up re-auth before PHI export (defer to multi-user phase)
- Multi-worker distributed task queue
- Encrypted ZIP / file-level encryption
- Temp file private storage path / permissions
