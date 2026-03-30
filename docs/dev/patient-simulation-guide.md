# Patient Simulation Testing — How to Run

## Prerequisites

1. **Server running on port 8001:**
   ```bash
   cd src && python -m uvicorn main:app --port 8001 --reload
   ```

2. **LLM provider configured** — the system LLM (Groq/DeepSeek/Ollama) must be set in `config/runtime.json` or env vars. The patient LLM also needs an API key (same or different provider).

3. **Python venv active:**
   ```bash
   source .venv/bin/activate
   ```

## Quick Start

```bash
# Run all 10 personas, Groq as patient LLM, no quality scoring
PYTHONPATH=src python scripts/run_patient_sim.py --patients all --patient-llm groq --no-quality-score
```

Output:
```
Patient LLM: groq | Server: http://127.0.0.1:8001
Personas: ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10']
DB: /path/to/data/patients.db

Running P1 王明... PASS (7 turns)
Running P2 李秀兰... PASS (8 turns)
...

==================================================
Results: 7/10 passed
Report:  reports/patient_sim/sim-2026-03-20T210000.html
JSON:    reports/patient_sim/sim-2026-03-20T210000.json
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--patients` | `all` | Comma-separated persona IDs (`P1,P4,P7`) or `all` |
| `--patient-llm` | `groq` | LLM provider for patient simulation: `deepseek`, `groq`, `claude` |
| `--server` | `http://127.0.0.1:8001` | Server URL |
| `--no-quality-score` | off | Skip Tier 3 LLM quality scoring (faster) |

## Examples

```bash
# Single persona for debugging
PYTHONPATH=src python scripts/run_patient_sim.py --patients P1 --patient-llm groq

# Messy patients only (stress test)
PYTHONPATH=src python scripts/run_patient_sim.py --patients P4,P5,P6 --patient-llm groq --no-quality-score

# Use DeepSeek as patient (better Chinese, needs DEEPSEEK_API_KEY)
PYTHONPATH=src python scripts/run_patient_sim.py --patients all --patient-llm deepseek

# Against a remote server
PYTHONPATH=src python scripts/run_patient_sim.py --patients all --patient-llm groq --server https://staging.example.com
```

## Patient Personas

| ID | Name | Condition | Style |
|----|------|-----------|-------|
| P1 | 王明，男，58岁 | 未破裂脑动脉瘤（体检发现） | Cooperative |
| P2 | 李秀兰，女，65岁 | 缺血性脑卒中术后3个月 | Cooperative |
| P3 | 张建国，男，72岁 | 颈动脉狭窄，既往TIA | Cooperative |
| P4 | 赵小红，女，45岁 | 脑血管畸形 (AVM) | Messy — anxious |
| P5 | 陈大海，男，60岁 | 脑出血恢复期6个月 | Messy — minimal |
| P6 | 刘芳，女，55岁 | 慢性头痛待查 | Messy — vague |
| P7 | 王淑芬，女，68岁 | 动脉瘤弹簧圈术后，双抗 | Cooperative |
| P8 | 周国强，男，62岁 | Pipeline 术后双抗漏服 | Guarded — adherence risk |
| P9 | 孙丽，女，59岁 | 反复单眼发黑 / 颈动脉狭窄 | Cooperative — symptom specificity |
| P10 | 何静，女，48岁 | 搏动性耳鸣 / 疑似硬脑膜动静脉瘘 | Messy — atypical vascular symptom |

Persona files: `tests/fixtures/patient_sim/personas/*.json`

## What It Does

For each persona, the pipeline:

1. **Registers** a patient via `/api/patient/register`
2. **Logs in** via `/api/patient/login` → gets JWT token
3. **Starts interview** via `/api/patient/interview/start`
4. **Runs interview loop** (max 20 turns):
   - System asks a question
   - Patient LLM generates a response based on the persona
   - Response sent via `/api/patient/interview/turn`
   - Stops when 5+ fields collected or 20 turns reached
5. **Confirms** the interview via `/api/patient/interview/confirm`
6. **Validates** with 4 tiers:
   - **Tier 1 (DB):** record exists, structured JSON populated, review queue created
   - **Tier 2 (3-axis):** elicitation coverage, extraction fidelity (dialog-based: judges what patient actually said vs what record captured), NHC compliance. Uses LLM to extract patient's actual statements from conversation, then judges those against the structured record. Facts the patient never mentioned are excluded from scoring.
   - **Tier 3 (Quality):** LLM judge scores conversation 0-10 (optional)
   - **Tier 4 (Anomaly):** anomaly review checks
7. **Cleans up** test data (`intsim_*` rows)

## Reading the Report

Reports are saved to `reports/patient_sim/`:
- `sim-{timestamp}.html` — Detailed technical report (scorecard, DB checks, quality scores)
- `sim-{timestamp}-review.html` — Dialog review (persona background, chat history, structured record, fact assessment table with "患者实际表述" column). Passed personas collapsed, failed ones expanded.
- `sim-{timestamp}.json` — Machine-readable results

The markdown report includes:
- Summary table (pass/fail per persona)
- Extracted facts table (expected vs actual per field)
- Full conversation transcript (collapsible)
- Quality scores (if enabled)

## Running via Pytest

```bash
# Gated behind env var to avoid running on every test suite
RUN_PATIENT_SIM=1 PYTHONPATH=src python -m pytest tests/integration/test_patient_simulation.py -v -s
```

This runs the same pipeline but asserts pass/fail per persona as pytest test cases.

## Troubleshooting

**"Set GROQ_API_KEY to use groq as patient LLM"**
→ The API key must be in `config/runtime.json` or set as env var: `export GROQ_API_KEY=gsk_...`

**Patient responses contain `<think>...</think>` traces**
→ Already handled — the pipeline strips Qwen3 thinking tokens automatically.

**All personas hit 20 turns (timeout)**
→ The system interview may not be extracting enough fields. Check `progress.filled` in the JSON report. The stop condition is `filled >= 5`.

**Extraction validation fails but DB passes**
→ The `fact_catalog` entries in the persona JSON may not match what the system actually extracts. T2 uses 3 LLM judges with tiered matching (exact/partial/missed). A `partial` match (core concept present but details missing) counts as a pass. Only `missed` critical facts cause failure. Check the report for vote details and adjust facts in `tests/fixtures/patient_sim/personas/*.json`.

**Same persona passes/fails on different runs**
→ LLM non-determinism affects both the sim patient (what it says) and the interview AI (what it asks). Run 2-3 times to assess stability. Personas with `volunteer=false` facts that depend on the AI asking the right category question are inherently less stable.

**"Register failed: 404"**
→ The test doctor doesn't exist. The pipeline creates one automatically, but the DB must be writable. Check `data/patients.db` exists and is not locked.

---

# Doctor Simulation Testing

## Quick Start

```bash
# Start test server on 8001 (NOT 8000 — that's dev)
cd src && python -m uvicorn main:app --port 8001

# Run all 8 doctor personas
PYTHONPATH=scripts python scripts/run_doctor_sim.py --personas all
```

## Doctor Personas

| ID | Style | What it tests |
|----|-------|---------------|
| D1 | 详细主治医师 | Full sentences, baseline extraction |
| D2 | 简洁外科急诊 | Abbreviations (STEMI, PCI, EF) |
| D3 | OCR粘贴 | Noisy OCR text tolerance |
| D4 | 多轮口述 | Multi-turn merge + dedup |
| D5 | 中英混合 | Bilingual labs/drugs (波立维, LDL-C) |
| D6 | 否定为主 | Negative symptom clusters (无发热咳嗽咳痰) |
| D7 | 复制粘贴冲突 | Copy-paste duplicates + contradictions |
| D8 | 模板填空 | Template format (【主诉】...【现病史】...) |

Persona files: `tests/fixtures/doctor_sim/personas/*.json`

## Key Difference from Patient Sim

- Doctor turns are **scripted** (no LLM generation) — tests extraction accuracy, not conversation
- All 13 clinical fields in scope (not just 7 subjective)
- 3-dimension evaluation: extraction recall, field routing, record quality
- Drug brand→generic mapping tested (波立维→氯吡格雷)

## Reports

```
reports/doctor_sim/
├── docsim-{timestamp}.html    # HTML report
└── docsim-{timestamp}.json    # Machine-readable
```

---

## Important: Test Server Port

**Always use port 8001 for simulation testing.** Never run sims against 8000 (dev server).

```bash
# Test server (for simulations)
cd src && uvicorn main:app --port 8001

# Dev server (for development — do NOT run sims here)
cd src && uvicorn main:app --port 8000
```

## API Keys by Provider

| Provider | Env Var / runtime.json key | Where to get it |
|----------|---------------------------|-----------------|
| Groq | `GROQ_API_KEY` | https://console.groq.com/keys |
| DeepSeek | `DEEPSEEK_API_KEY` | https://platform.deepseek.com |
| OpenRouter | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| Claude | `ANTHROPIC_API_KEY` | https://console.anthropic.com |
