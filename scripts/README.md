# Scripts Index

All operational scripts are centralized in this folder.

## Developer Workflow

- `test.sh`: unified test runner (`unit`, `integration`, `chatlog-half`, `chatlog-full`, `all`)
- `run_chatlog_e2e.py`: human-language chatlog E2E runner against API + DB checks
- `preload_patients.py`: preload mock patients for a doctor (`doctor_id` or `doctor_name`)
- `chat.py`: interactive chat client for local/manual verification
- `db_inspect.py`: inspect database content quickly from CLI

## E2E Data

- `run_chatlog_e2e.py`: replays human-language cases from `e2e/fixtures/data/*.json`
- v2 complex corpus: `e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v2.json` (100 doctor-agent cases)

## Maintenance

- `seed_db.py`: export/import seed data
- `recompute_patient_categories.py`: recompute patient category fields
- `recompute_patient_risk.py`: recompute patient risk fields
- `start_db_ui.sh`: start local DB UI helper
- `chat.sh`, `train.sh`: convenience wrappers

Primary developer entrypoint remains `../dev.sh`.
