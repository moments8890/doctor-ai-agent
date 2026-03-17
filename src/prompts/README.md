# Prompts

LLM prompt files — one `.md` file per prompt.  Edit directly to tune behavior.

## How it works

- `utils/prompt_loader.py` reads files by key: `get_prompt("structuring")` → `prompts/structuring.md`
- Files are cached in memory on first read; call `invalidate()` to reload
- `db/init_db.py` seeds these prompts to the `system_prompts` table on first startup

## Index

| File | Used by | Purpose |
|------|---------|---------|
| `understand.md` | `services/runtime/understand.py` | Intent classification, JSON output format (ADR 0013) |
| `structuring.md` | `services/ai/structuring.py` | Transform doctor dictation into clinical narrative + tags (JSON) |
| `vision-ocr.md` | `services/ai/vision.py` | Image-to-text OCR for medical documents |
| `vision-import.md` | `services/record_import/vision_import.py` | Extract outpatient fields + patient info from medical record images |
| `patient-chat.md` | `channels/wechat/patient_pipeline.py` | Patient-facing chat assistant (non-doctor) |
| `report-extract.md` | `services/export/outpatient_report.py` | Extract outpatient report fields (template: `{records_text}`) |
