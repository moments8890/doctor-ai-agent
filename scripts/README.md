# Scripts Index

All operational scripts are centralized in this folder.

## Developer Workflow

- `test.sh`: unified test runner (`unit`, `integration`, `chatlog-half`, `chatlog-full`, `all`)
- `run_chatlog_e2e.py`: human-language chatlog E2E runner against API + DB checks (targets port 8001)
- `preload_patients.py`: preload mock patients for a doctor (`--doctor-id` required)
- `chat.py`: interactive chat client for local/manual verification (`--token` for auth)
- `db_inspect.py`: inspect database content quickly from CLI

## E2E Data

- `run_chatlog_e2e.py`: replays human-language cases from `e2e/fixtures/data/*.json`
- v2 complex corpus: `e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v2.json` (100 doctor-agent cases)

## Document Import Testing

- `test_document_import.py`: local pipeline test for PDF, image, .docx, text, and chat exports
  - PDF extraction mirrors production (LLM first, local fallback)
  - Chat exports require `--sender` for multi-sender disambiguation
  - `.doc` (legacy) is not supported — convert to `.docx` first

## OCR Evaluation

- `eval_ocr_accuracy.py`: evaluate vision OCR accuracy against CMDD ground truth

## Maintenance

- `seed_db.py`: export/import seed data
- `recompute_patient_categories.py`: recompute patient category fields
- `start_db_ui.sh`: start Datasette web UI (default port 8002)

Primary developer entrypoint remains `../dev.sh`.
