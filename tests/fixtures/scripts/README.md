# E2E Fixture Generation — LLM Test Cases

## `generate_llm_cases.py`

Generates diverse Chinese doctor-agent conversation test cases using LLMs.
Output is auto-versioned: `_v1.json`, `_v2.json`, … (never overwrites existing files).

### Prerequisites

- Run from a **normal terminal** (not inside a Claude Code session) — `claude -p` is blocked inside Claude Code
- Python env: `.venv` at project root
- Optional: `codex` CLI in PATH for dual-model generation

---

### Commands

**Most common — Claude CLI + Codex (200 cases):**
```bash
cd /Users/jingwuxu/Documents/Code/doctor-ai-agent-benchmark
  .venv/bin/python tests/fixtures/scripts/generate_llm_cases.py --claude-cli
```

**Claude CLI only (100 cases):**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --no-codex
```

**Codex only:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --no-claude
```

**Claude API (requires key):**
```bash
ANTHROPIC_API_KEY=sk-ant-... python tests/fixtures/scripts/generate_llm_cases.py --no-codex
```

**Dry-run — print prompt without calling any LLM:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --dry-run --claude-cli --no-codex
```

**Custom output path:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --out /tmp/test_cases.json
```

**More cases per batch (default 10):**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --cases-per-batch 20
```

**More total data by repeating all theme batches 3 times:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --rounds 3
```

**Append 2 dedicated 神经/脑血管专科 batches:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --extra-neuro-specialty-batches 2
```

**Append all 10 神经/脑血管专科 batches:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --extra-neuro-specialty-batches 10
```

**Use only 神经/脑血管专科 batches:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --neuro-cerebro-only
```

**Use only the first 4 神经/脑血管专科 batches:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --neuro-cerebro-only --extra-neuro-specialty-batches 4
```

**Larger run example (10 batches × 20 cases × 3 rounds × 2 models = 1200 cases):**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --cases-per-batch 20 --rounds 3
```

**Larger neuro-focused run example:**
```bash
python tests/fixtures/scripts/generate_llm_cases.py --claude-cli --cases-per-batch 20 --rounds 2 --extra-neuro-specialty-batches 7
```

---

### How it works

| Step | Detail |
|------|--------|
| **Batches** | 10 base clinical themes |
| **Specialty add-on** | `--extra-neuro-specialty-batches N` appends up to 10 神经/脑血管专科 batches |
| **Specialty-only mode** | `--neuro-cerebro-only` skips `BASE_BATCHES` and uses only `NEURO_CEREBRO_SPECIALTY_BATCHES` |
| **Per batch** | `--cases-per-batch` cases requested from each active model |
| **Rounds** | `--rounds` repeats the full 10-batch theme set with a stronger non-overlap prompt |
| **Total** | `(10 + extra_specialty_batches) × rounds × cases-per-batch × num_models` |
| **Grounding** | Each prompt embeds real CHIP-CDEE discharge record fragments (randomly sampled per run) to anchor clinical vocabulary |
| **Diversity** | Prompt describes 4 orthogonal axes (message length, formality, language mix, rhythm) — no fixed style templates |
| **Output** | One JSON file, array of case objects |

---

### Output format

Each case in the output array:

```json
{
  "case_id": "LLM-GEN-CLAUDE-001",
  "title": "LLM-generated (claude) batch 1: cardiology",
  "source": "claude",
  "batch": 0,
  "intent_sequence": ["create_patient", "add_record"],
  "clinical_domain": "cardiology",
  "chatlog": [
    {"speaker": "doctor", "text": "58岁男，胸痛2小时，先创建"},
    {"speaker": "doctor", "text": "hs-cTnI 2.8，心电图下壁ST抬高，确诊STEMI"}
  ],
  "expectations": {
    "must_not_timeout": true,
    "expected_table_min_counts_global": {"system_prompts": 1},
    "expected_table_min_counts_by_doctor": {"patients": 1, "medical_records": 1},
    "must_include_any_of": [["BNP", "胸痛", "STEMI"]]
  }
}
```

---

### Grounding data

If the external drive `/Volumes/ORICO/doctor-ai-agent/train/data` is mounted,
8 additional CHIP-CDEE sentences are randomly sampled and added to the prompt each run.
If the drive is absent the script falls back to the curated built-in examples — no error.

---

### Adding new batch themes

Edit the `BATCHES` list in `generate_llm_cases.py`:

```python
{
    "theme": "主题描述（中文）",
    "domains": "科室1、科室2、科室3",
    "ops": "add_record, create_patient+add_record, query_records+add_record",
},
```
