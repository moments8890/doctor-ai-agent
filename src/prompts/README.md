# Prompts

LLM prompt files — one `.md` file per prompt.  Edit directly to tune behavior.

## How it works

- `utils/prompt_loader.py` reads files by key: `get_prompt("structuring")` → `prompts/structuring.md`
- Files are cached in memory on first read; call `invalidate()` to reload
- `db/init_db.py` seeds these prompts to the `system_prompts` table on first startup

## Index

| File | Used by | Purpose |
|------|---------|---------|
| `understand.md` | `services/runtime/understand.py` | Understand phase system prompt (ZH) — intent classification, JSON output format (ADR 0012) |
| `structuring.md` | `services/ai/structuring.py` | Transform doctor dictation into structured clinical notes (JSON) |
| `structuring-consultation-suffix.md` | same | Suffix appended for consultation dialogue mode |
| `structuring-followup-suffix.md` | same | Suffix appended for follow-up/revisit records |
| `neuro-cvd.md` | `services/ai/neuro_structuring.py` | Neuro/CVD specialty case structuring (full 3-section output) |
| `neuro-fast-cvd.md` | same | Fast CVD context extraction (single JSON, no markdown sections) |
| `vision-ocr.md` | `services/ai/vision.py` | Image-to-text OCR for medical documents |
| `transcription-medical.md` | `services/ai/transcription.py` | Whisper vocabulary bias for medical terminology |
| `transcription-consultation.md` | same | Whisper bias for doctor-patient dialogue transcription |
| `score-extraction.md` | `services/patient/score_extraction.py` | Extract specialty scale scores (NIHSS, mRS, etc.) from text |
| `patient-chat.md` | `channels/wechat/patient_pipeline.py` | Patient-facing chat assistant (non-doctor) |
| `report-extract.md` | `services/export/outpatient_report.py` | Extract outpatient report fields (template: `{records_text}`) |
