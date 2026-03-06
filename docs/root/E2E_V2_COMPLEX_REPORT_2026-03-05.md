# E2E v2 Complex Chat Report (March 5, 2026)

## Scope

- Dataset: `e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v2.json`
- Cases: `100` complex real-world doctor-to-agent chats
- Focus: multi-step chains across create/list/query/delete/context/task flows

## Run Command

```bash
.venv/bin/python scripts/run_chatlog_e2e.py e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v2.json --max-cases 100 --response-keywords-only --timeout 120 --retries 1
```

## Result

- Summary: `100/100 passed`
- Total suite time: `443.51s`
- Log artifact: `/tmp/e2e_v2_100.log`

## Added Validation

- New integration test: `e2e/integration/test_realworld_v2_dataset_e2e.py`
  - Verifies dataset structure/size (`100` cases)
  - Runs deterministic API flow and verifies DB table coverage for:
    - `patients`
    - `medical_records`
    - `doctor_tasks`
    - `doctor_contexts`
    - `neuro_cases`
    - `system_prompts`

Integration run result:
- `2 passed in 17.67s`

## Notes

- v2 corpus keeps human-language realism while avoiding brittle per-case strict-name assertions that are highly model-variant.
- Table persistence coverage is enforced by a deterministic integration flow in addition to chatlog replay.
