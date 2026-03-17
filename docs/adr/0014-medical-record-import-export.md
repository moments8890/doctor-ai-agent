# ADR 0014: Medical Record Import/Export

## Status

Proposed

## Date

2026-03-16

## Implementation Status

Not Started

Last reviewed: 2026-03-16

Notes:

- Spec: `docs/superpowers/specs/2026-03-16-medical-record-import-export-design.md`
- Plan: `docs/plans/adr-0014-execution-plan.md`

## Context

Doctors need to export medical records in standard 《病历书写基本规范》
(卫医政发〔2010〕11号) format and import records from external sources
(scanned paper records, PDFs from other HIS systems, photos).

Current state:

1. **Export exists but is limited.** PDF export with 12 fields via LLM
   extraction (`outpatient_report.py`). No JSON export. Missing 婚育史
   (marital/reproductive history) and 专科检查 (specialist exam) fields.

2. **No import capability.** Doctors cannot bring external records into the
   system. `record_type="import"` exists as a value but no pipeline produces it.

3. **No structured schema contract.** Field definitions live only in the prompt
   and the `OUTPATIENT_FIELDS` list. Export code and any future import code
   would independently define field structures.

## Decision

### 1. Unified OutpatientRecord Schema

Introduce a shared `OutpatientRecord` Pydantic model (14 fields per standard)
as the data contract for both export and import. All fields Optional.

The 14 fields:
科别, 主诉, 现病史, 既往史, 过敏史, 个人史, 婚育史, 家族史,
体格检查, 专科检查, 辅助检查, 初步诊断, 治疗方案, 医嘱及随访.

### 2. Export: Expand Existing Pipeline

- Expand `report-extract.md` prompt from 12 → 14 fields
- Rename 3 field keys for consistency: `aux_exam` → `auxiliary_exam`,
  `treatment` → `treatment_plan`, `followup` → `orders_followup`
- Add `?format=json|pdf` parameter to existing export endpoint
- JSON export function lives in `outpatient_report.py` (no new file)

### 3. Import: Vision LLM Pipeline

- Vision LLM (Qwen-VL via existing Ollama infra) directly extracts 14 fields
  from uploaded images/PDFs in a single call
- PDF → per-page images via shared `pdf_to_images()` utility
- Auto-creates record with `record_type="import"` and `needs_review=True`
- No confirmation step (consistent with current create workflow)
- Web API only for MVP; WeChat deferred

### 4. No DB Schema Changes (except needs_review)

- `medical_records.content` remains prose text
- Add nullable `needs_review` boolean column for imported records
- No structured field columns — LLM re-extraction on export is acceptable
  for MVP (label-value prose format is highly extractable)

### 5. Security

- File upload: MIME + magic bytes validation, 20 MB limit, 10 page limit
- PHI egress gate on Vision LLM calls (same as existing vision infra)

## Consequences

### Positive

- Doctors can export standard-format records (JSON + PDF) for use elsewhere
- Doctors can import external records into the system for unified management
- Shared schema ensures import/export format consistency
- Minimal changes to existing code — extends rather than replaces

### Negative

- Lossy round-trip: import stores prose, export re-extracts. Acceptable for
  MVP; `structured_json` column can be added later if fidelity is an issue.
- Vision LLM quality on handwritten records may be poor. Mitigated by
  `needs_review` flag.
- One upload = one record. Multi-record splitting deferred.

### Neutral

- Tags left empty for imported records (MVP simplification)
- Multi-record merge for export is entirely LLM-driven (no programmatic
  validation). Source annotation shows date range for doctor awareness.
