# Tests

## Test Suites

| Suite | Location | What it tests | LLM calls | How to run |
|-------|----------|---------------|-----------|------------|
| **Regression** | `tests/regression/` | Deterministic extraction + workflow tests | Yes (Groq) | `RUN_REGRESSION=1 PYTHONPATH=src pytest tests/regression/ -v` |
| Integration | `tests/integration/` | Live API smoke tests | Yes | `RUN_E2E_FIXTURES=1 pytest tests/integration/ -v` |
| Core | `tests/core/` | App-level unit tests | Mocked | `pytest tests/core/ -v` |
| WeChat | `tests/wechat/` | WeChat/WeCom endpoint tests | Mocked | `pytest tests/wechat/ -v` |

**All tests requiring a live server MUST use port 8001** (test server), never 8000 (dev server with real data).

```bash
# Start test server
PYTHONPATH=src uvicorn main:app --host 127.0.0.1 --port 8001

# Run regression suite
RUN_REGRESSION=1 PYTHONPATH=src pytest tests/regression/ -v
```

---

## Regression Suite (86 tests)

The regression suite is the primary quality gate. All tests are deterministic (no LLM judges). Each test calls the real LLM through the live server, then asserts on DB state, HTTP responses, or extracted field content.

**Cost:** ~$0.10 per run (86 LLM calls via Groq)
**Time:** ~2.5 minutes
**Markers:** `pytest -m regression` (all), `-m extraction` (Kind A), `-m workflow` (Kind B)

### Kind B: Doctor Interview Workflow (16 tests)

Tests the doctor interview API — session lifecycle, confirm behavior, edge cases.

#### Session Lifecycle (5 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_cancel` | Start interview for "张三 男 56岁 头痛3天", then cancel | No medical record saved in DB |
| `test_resume` | Send 2 turns, then GET session state | Collected fields preserved; confirm creates record |
| `test_confirm_empty_rejected` | Send "你好" (no clinical data), then confirm | HTTP 400 — can't save empty record |
| `test_confirm_double_rejected` | Confirm, then confirm again | First → 200, second → 400 |
| `test_deferred_patient_creation` | Send clinical text, check DB before/after confirm | Patient + record both created at confirm time, not during turns |

#### Confirm Status (2 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_minimal_pending_review` | Only chief complaint + present illness | status = `pending_review` |
| `test_confirm_complete` | All fields filled (CC, HPI, history, exam, diagnosis, treatment, follow-up) | status = `completed` |

#### Edge Cases (3 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_duplicate_message` | Same text sent twice | Chief complaint not duplicated |
| `test_5_turn_incremental` | 5 turns, each adding 2-3 fields | ≥4 fields merged correctly |
| `test_empty_input` | Whitespace-only input | No crash (400 or graceful response) |

#### Carry-Forward (2 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_carry_forward_confirm` | Returning patient — system offers history from prior visit, doctor confirms | Field injected into collected |
| `test_carry_forward_dismiss` | Same, but doctor dismisses | Field NOT injected |

#### Auto Tasks (1 test)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_auto_task_generation` | orders_followup has "2周后复查 1个月后随访" | ≥1 follow-up task auto-created |

#### Patient Workflows via Doctor API (2 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_patient_self_contradict` | "没有过敏" then "哦对了我对青霉素过敏" | allergy_history has "青霉素" — later correction wins |
| `test_patient_checkup_only` | "体检 无不适 否认既往病史" | Valid record created from minimal/negative content |

#### Doctor Chat (1 test)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_query_task_empty` | "查看我的任务" when no tasks exist | Non-empty reply (graceful empty state) |

---

### Kind B: Patient Interview Workflow (10 tests)

Tests the patient-facing API — registration, JWT auth, interview flow.

#### Full Flow (2 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_simple_headache` | Register → start → 5 turns ("我头疼", "三天了", ...) → confirm | ≥3 fields filled; record_id returned; DB row exists |
| `test_abdominal_pain_with_history` | Register → 6 turns including surgical history + allergy → confirm | ≥4 fields filled |

#### Session Management (2 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_resume_interrupted` | Start → 2 turns → start again (simulating app restart) | Same session_id; `resumed=true`; collected preserved |
| `test_cancel_and_restart` | Start → 1 turn → cancel → start again | New session_id (different from cancelled one) |

#### Registration (3 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_register_links_existing_patient` | Doctor creates patient, then patient self-registers with same name | Links to existing (no duplicate); patients count = 1 |
| `test_register_rejects_mismatched_yob` | Register with YOB=1990, then try same name with YOB=1985 | HTTP 400 |
| `test_wrong_yob_login_rejected` | Register with YOB=1992, login with YOB=1988 | HTTP 401 |

#### Extraction Quality (3 tests)

| Test | What it does | What it verifies |
|------|-------------|-----------------|
| `test_negatives_captured` | Patient says "没有头痛", "没有过敏", "不抽烟" | Record created; chief_complaint filled |
| `test_combined_multi_field_answers` | "以前有高血压，吃氨氯地平，对青霉素过敏" (one message, multiple fields) | ≥4 fields filled from split answer |
| `test_history_injection` | "我对磺胺类药物和海鲜过敏" | allergy_history contains "磺胺" or "海鲜" |

---

### Kind A: Doctor Extraction D1-D8 (8 tests)

Each sends a complete doctor dictation → confirms → checks if ≥65% of expected clinical facts appear in the correct DB fields. Tests the full extraction pipeline: `interview.md` (per-turn) + `doctor-extract.md` (batch at confirm).

| Test | Input Style | Key Challenge | Facts |
|------|------------|---------------|-------|
| `D1` verbose_attending | Long formal narrative, standard terminology | Volume — 37 facts from dense admission note | 37 |
| `D2` telegraphic_surgeon | Terse shorthand, no labels, arrows (`NIHSS 8→术后4`) | Field routing without section headers | 30 |
| `D3` ocr_paste | OCR'd referral letter with spacing/typos (`搪尿病`) | Noise cleanup + extraction | 35 |
| `D4` multi_turn | 3 turns: CC/HPI → history/exam → diagnosis/plan | Multi-turn merge | 30 |
| `D5` bilingual_mix | English/Chinese mix (`R-ICA stenosis 70%`, `HTN 15y`) | Bilingual term handling | 39 |
| `D6` negation_cluster | 40+ negations (`否认头晕头痛恶心呕吐肢体麻木无力`) | Compound negation preservation | 40 |
| `D7` copy_paste_conflict | Two visits pasted — old vs current values | Conflict resolution (prefer latest) | 29 |
| `D8` template_fill | `【主诉】`, `【既往史】` labels | Label-guided field mapping | 43 |

**Matching strategy** (4 layers, all deterministic):
1. Exact substring
2. Token-based with gaps (tolerates inserted words like `行`, `约`)
3. Core-term extraction (strips `否认`/`无` prefix for compound negations)
4. Jieba anchor matching (segments fact into words, checks all appear in field)

---

### Kind A: MVP Chat Scenarios (52 tests)

Tests the chat pipeline (routing → intent handler → DB effects). No extraction fact-checking — only structural assertions (patient created, session created, DB counts).

| Category | Count | Examples |
|----------|-------|---------|
| Record creation | 28 | `stemi_emergency_intake`, `copd_exacerbation`, `depression_intake`, `ds_cardiology_new_intake`, `gm_oncology_ct_chemo` |
| Query | 7 | `cardiology_followup_query`, `query_nonexistent_patient`, `list_all_patients`, `query_no_write_side_effects` |
| Clarification | 5 | `clarify_missing_name`, `clarify_ambiguous_patient`, `noname_blocked_write` |
| Correction | 4 | `correct_troponin_value`, `same_turn_correction`, `correction_saves_corrected` |
| Edge cases & safety | 5 | `numeric_only_input`, `special_chars_parens`, `repeated_greeting`, `help_request` |
| Task & compound | 3 | `schedule_followup`, `note_wins_over_schedule`, `create_with_clinical_content` |

---

## File Structure

```
tests/
├── README.md                    ← this file
├── regression/                  ← deterministic regression suite (86 tests)
│   ├── conftest.py              # fixtures, cleanup, skip guard, port 8001 safety
│   ├── models.py                # ScenarioSpec, FactRule, MatchResult dataclasses
│   ├── normalizer.py            # Chinese text normalization + alias tables
│   ├── matchers.py              # 4-layer deterministic matcher (substring → token → core-term → jieba)
│   ├── helpers.py               # Doctor API wrappers + DB helpers
│   ├── helpers_patient.py       # Patient API wrappers (registration, auth, interview)
│   ├── loader.py                # Auto-detect JSON format (v2, D1-D8 legacy, MVP legacy)
│   ├── test_extraction.py       # Kind A: parametrized from 60 JSON scenario files
│   ├── test_doctor_interview.py # Kind B: 16 doctor workflow tests
│   └── test_patient_interview.py# Kind B: 10 patient workflow tests
├── fixtures/
│   ├── doctor_sim/scenarios/    # 60 doctor scenario JSON files (v2 format)
│   └── patient_sim/scenarios/   # 11 patient scenario JSON files (v2 format)
├── integration/                 # Legacy integration tests
├── core/                        # Unit tests (mocked I/O)
└── wechat/                      # WeChat endpoint tests
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RUN_REGRESSION` | (unset) | Set to `1` to enable regression tests |
| `INTEGRATION_SERVER_URL` | `http://127.0.0.1:8001` | Test server URL |
| `PATIENTS_DB_PATH` | From `config/runtime.json` | DB path for assertions |
