# Plan: AI-Backed Patient Sandbox for Dr. 陆华

**Goal:** Ship the product to Dr. 陆华 (江南大学附属医院副院长, 神经外科学科带头人) with AI-backed simulated patients that showcase every key feature over a 4-day daily use trial.

**Design doc:** `~/.gstack/projects/moments8890-doctor-ai-agent/jingwuxu-main-design-20260328-095518.md`

**Status:** COMPLETE (all 7 steps done)

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

### Step 4: Finish teaching loop (20% remaining) -- DONE

1. ~~`POST /api/manage/drafts/{draft_id}/save-as-rule`~~ — endpoint added in draft_handlers.py
2. ~~Frontend teaching prompt~~ — Snackbar shown after draft edit with save-as-rule action
3. ~~Verified~~ — saved rules appear in KB and are cited by future drafts

### Step 5: Build demo_sim.py -- DONE

1. ~~`scripts/patient_sim/http_client.py`~~ — extracted with shared HTTP functions
2. ~~`scripts/demo_sim.py`~~ — created with --seed, --tick, --skip-to, --reset, --status subcommands
3. ~~State tracking~~ — `scripts/.demo_state.json`
4. ~~Idempotent~~ — duplicate ticks are no-ops

### Step 6: Write demo config YAML -- DONE

1. ~~`scripts/demo_config.yaml`~~ — created with 6 patients, scripted messages, 10 KB entries, Day 1-4 timing
2. ~~Clinical data sourced~~ — from national guidelines and specialty references

### Step 7: Frontend polish -- DONE

1. ~~Patient list triage dots~~ — red/yellow/green dots based on latest message triage_category
2. ~~KB source footer~~ — source_url clickable link + "查看原文" button for uploaded files
3. ~~Draft reply UI~~ — auto-size textarea, same-position edit/view buttons, whiteSpace pre-line, undrafted yellow notice
4. ~~Teaching prompt~~ — Snackbar after draft edit with save-as-rule option
5. Additional: cited_rules as clickable green tags, tab badge fixes (审核 counts AI suggestions, 任务 counts pending drafts + undrafted), session persistence fix

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
