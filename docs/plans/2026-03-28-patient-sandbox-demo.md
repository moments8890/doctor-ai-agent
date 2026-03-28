# Plan: AI-Backed Patient Sandbox for Dr. 陆华

**Goal:** Ship the product to Dr. 陆华 (江南大学附属医院副院长, 神经外科学科带头人) with AI-backed simulated patients that showcase every key feature over a 4-day daily use trial.

**Design doc:** `~/.gstack/projects/moments8890-doctor-ai-agent/jingwuxu-main-design-20260328-095518.md`

**Status:** APPROVED (eng review complete, Codex-validated)

---

## Affected Files

### Backend
- `src/db/models/doctor.py` — extend KB payload with source_url
- `src/domain/knowledge/knowledge_crud.py` — update encode/decode for source_url
- `src/domain/knowledge/knowledge_ingest.py` — store original files to uploads/
- `src/domain/knowledge/teaching.py` — already 80% done, add missing API endpoint wiring
- `src/channels/web/ui/knowledge_handlers.py` — upload endpoint saves original file, serve endpoint
- `src/channels/web/ui/draft_handlers.py` — add endpoint to finalize KB rule from edit
- `src/agent/prompts/intent/triage-classify.md` — add post-surgical 危险信号 to urgent examples

### Scripts
- `scripts/demo_sim.py` — NEW: YAML config parser + tick-based message scheduler
- `scripts/patient_sim/http_client.py` — NEW: shared HTTP client extracted from engine.py
- `scripts/demo_config.yaml` — NEW: 6 patient scenarios + 10 KB entries + timing config

### Frontend
- Patient list: triage color badges (red/yellow/green dots)
- KB detail: source footer with source_url link
- Draft reply: improve edit+send flow (existing page, polish)

### Tests
- `tests/prompts/cases/triage-classify.yaml` — add 2-3 post-surgical eval cases

---

## Steps

### Step 1: Triage prompt + eval (independent, no dependencies) -- DONE

1. ~~Edit `src/agent/prompts/intent/triage-classify.md`~~ — post-surgical 危险信号 added to urgent examples
2. ~~Add 2-3 eval cases~~ — 3 new cases added (15 total)
3. ~~Run eval~~ — all 15 cases pass
4. ~~Verify existing cases~~ — no regressions

### Step 2: KB payload extension (source_url) -- DONE

1. ~~`_encode_knowledge_payload()` updated~~ — source_url and file_path added to v1 payload
2. ~~`_decode_knowledge_payload()` updated~~ — extracts source_url and file_path
3. ~~`save_knowledge_item()` updated~~ — accepts source_url
4. ~~API responses updated~~ — include decoded source_url
5. No DB migration needed (payload is JSON inside content column)

### Step 3: Original file storage -- DONE

1. ~~`uploads/` directory~~ — created, gitignored
2. ~~`upload_extract()` updated~~ — saves original file to `uploads/{doctor_id}/{timestamp}_{filename}`
3. ~~`upload_save()` updated~~ — accepts file_path, saves to KB payload
4. ~~File serve endpoint~~ — `GET /api/manage/knowledge/file/{path}` with auth check
5. ~~Frontend~~ — "查看原文" button in KB detail page linking to file endpoint

### Step 4: Finish teaching loop (20% remaining)

1. In `draft_handlers.py`:
   - Add `POST /api/manage/drafts/{draft_id}/save-as-rule` endpoint
   - Calls `create_rule_from_edit()` from teaching.py
   - Returns created KB item
2. Frontend: when `teach_prompt=True` is returned from edit endpoint,
   show prompt: "您的修改已记录。要将这个回复模式保存为知识条目吗？" [保存] [跳过]
   - [保存] calls the new save-as-rule endpoint
   - [跳过] dismisses
3. Verify: after saving rule, future draft replies should cite it

### Step 5: Build demo_sim.py

1. Extract `scripts/patient_sim/http_client.py`:
   - `register_patient(server_url, doctor_id, name, gender, year_of_birth)`
   - `send_chat_message(server_url, patient_id, doctor_id, content)`
   - `seed_knowledge_item(server_url, doctor_id, text, source, source_url, category)`
   - `cleanup_sim_data(server_url, doctor_id_prefix)`
2. Create `scripts/demo_sim.py` with subcommands:
   - `--seed`: register 6 patients + seed 10 KB entries from YAML config
   - `--tick`: check YAML for messages whose delay has elapsed, send them
   - `--skip-to PATIENT MSG_NUM`: force-send a specific message immediately
   - `--reset`: delete all sim data (patients with doctor_id prefix `demo_`)
   - `--status`: show which messages have been sent, which are pending
3. State tracking: write `scripts/.demo_state.json` with sent message IDs and timestamps
4. Idempotent: `--tick` called twice for same window sends nothing new

### Step 6: Write demo config YAML

1. Create `scripts/demo_config.yaml` with:
   - 6 patient profiles (张阿姨, 李大爷, 王先生, 赵女士, 陈先生, 周老伯)
   - Scripted messages per design doc scenario scripts
   - 10 KB entries (full content from design doc sections KB-1 through KB-8)
   - Timing: Day 1-4 schedule with message delays in hours
2. Include realistic cerebrovascular patient data sourced from:
   - 中国破裂颅内动脉瘤临床管理指南(2024版)
   - 颅内动脉瘤显微手术治疗专家共识(2025版)
   - 陆华教授 神外前沿 WeChat articles
   - CEA/AVM/烟雾病 national guidelines

### Step 7: Frontend polish

1. Patient list: add triage color dot (red/yellow/green) based on latest message triage_category
2. KB detail page: show source (decoded from payload) as subtle footer, source_url as clickable link
3. Draft reply display: ensure [编辑后发送] / [直接发送] UX is clear in PatientDetail chat
4. Teaching prompt: after edit, show "save as rule?" prompt if teach_prompt=True

---

## Risks / Open Questions

1. **Timestamps**: Patient messages are timestamped at write time. If sim sends all Day 1-4 messages at once for rehearsal, the doctor sees same-day timestamps. Mitigation: temporal context is in the message text itself ("两天前开始头疼").
2. **Notifications**: Default is server logging. "已通知医生" is false without WeChat config. For demo: accept this limitation. The doctor opens the app voluntarily.
3. **3rd sim stack**: demo_sim.py is the 3rd simulation script. Shared http_client.py mitigates duplication but doesn't eliminate it. Acceptable for a product launch tool.
4. **Doctor's voice**: KB is mostly guidelines + publications. May bias toward formal prose rather than Dr. Lu's personal voice. Mitigation: get 3-5 sample WeChat replies from Dr. Lu and add as KB preference entries.

---

## Parallelization

```
Lane 1: Step 1 (triage prompt + eval)          — independent
Lane 2: Step 2 (KB payload) → Step 3 (files)   — sequential (Step 3 uses payload)
Lane 3: Step 5 (demo_sim.py) → Step 6 (YAML)   — sequential (config needs engine)
Lane 4: Step 4 (teaching loop)                  — independent
Lane 5: Step 7 (frontend)                       — after Steps 2, 4

Launch: Lanes 1-4 in parallel. Lane 5 after 2 + 4 complete.
```

---

## Cascading Impact

1. **DB schema** — No column changes. Payload extension only (source_url in JSON). `_backfill_missing_columns()` not needed.
2. **ORM models** — DoctorKnowledgeItem unchanged. Payload encode/decode updated.
3. **API endpoints** — 2 new: file serve, save-as-rule. 1 modified: upload/save (adds file_path).
4. **Domain logic** — teaching.py already built, just needs endpoint wiring.
5. **Prompt files** — triage-classify.md updated with 危险信号 examples.
6. **Frontend** — 4 small changes: triage dots, source footer, file view button, teaching prompt.
7. **Configuration** — None (sim config is a new standalone file).
8. **Existing tests** — 12 existing triage eval cases must still pass after prompt change.
9. **Cleanup** — None needed.
