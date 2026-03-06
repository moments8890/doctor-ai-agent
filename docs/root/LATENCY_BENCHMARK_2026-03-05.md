# Latency Benchmark Report (March 5, 2026)

## Goal

Measure real `/api/records/chat` latency and identify the dominant bottleneck across LLM backends.

## Test Method

- Dataset: `e2e/fixtures/data/realworld_doctor_agent_chatlogs_e2e_v1.json`
- Runner: `scripts/run_chatlog_e2e.py`
- Validation mode: `--response-keywords-only`
- Observability source: `/api/admin/observability` (`recent_traces` + `recent_spans`)
- Strict provider mode enabled: `LLM_PROVIDER_STRICT_MODE=true`

## Main A/B Results (10 cases, same slice)

- Ollama:
  - Suite result: `10/10 passed`, `43.15s` total
  - Per `/api/records/chat` request:
    - `avg=1153.6ms`, `p50=966.4ms`, `p95=1770.7ms`, `p99=2560.1ms`, `max=5267.9ms`
- DeepSeek:
  - Suite result: `10/10 passed`, `144.28s` total
  - Per `/api/records/chat` request:
    - `avg=3887.3ms`, `p50=4130.8ms`, `p95=5303.6ms`, `p99=5826.6ms`, `max=6712.1ms`

Delta:
- DeepSeek was about `+101.13s` total (`+234.37%`) on the same 10-case run.

## Bottleneck Analysis

Observed dominant spans:
- `agent.chat_completion`
- `records.chat.agent_dispatch`

Observed non-dominant spans:
- DB CRUD spans (`crud.save_record`, `crud.create_patient`, etc.) were usually single-digit to low double-digit ms.

Conclusion:
- Latency is primarily in LLM completion time, not DB.

## Optimization Experiments

DeepSeek variants (6 cases):
- `full prompt + full tools`: `88.59s`
- `compact prompt + full tools`: `123.89s` (worse)
- `full prompt + compact tools`: `87.67s` (best)
- `compact prompt + compact tools`: `107.83s` (worse)

Ollama sanity (6 cases):
- `full prompt + full tools`: `29.75s`
- `full prompt + compact tools`: `25.00s` (better)

## Current Recommended Runtime Defaults

- `ROUTING_LLM=ollama`
- `STRUCTURING_LLM=ollama`
- `LLM_PROVIDER_STRICT_MODE=true`
- `AGENT_ROUTING_PROMPT_MODE=full`
- `AGENT_TOOL_SCHEMA_MODE=compact`

Rationale:
- Keeps per-chat latency around ~1s average on local LAN Ollama in this environment.
- Avoids accidental fallback to charged online provider.

## Reproduce

1. Set provider + modes in Admin Runtime Config.
2. Apply config (`/api/admin/config/apply`).
3. Clear traces (`/api/admin/observability/traces`).
4. Run:

```bash
.venv/bin/python scripts/run_chatlog_e2e.py --max-cases 10 --response-keywords-only --timeout 120 --retries 1
```

5. Fetch observability snapshot:

```bash
curl -sS "http://127.0.0.1:8000/api/admin/observability?trace_limit=200&summary_limit=1000&span_limit=3000&slow_span_limit=200&scope=all"
```
