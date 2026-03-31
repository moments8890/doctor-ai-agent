# LLM Providers — Chinese Medical Focus

All providers run **Qwen** or **DeepSeek** models — optimized for Chinese medical content.
Pricing verified March 2026. Benchmarks run from Tencent Cloud (Beijing).

## Production Config

```bash
# Current production (runtime.json on server)
ROUTING_LLM=siliconflow
STRUCTURING_LLM=siliconflow
DIAGNOSIS_LLM=siliconflow
SILICONFLOW_MODEL=Qwen/Qwen2.5-32B-Instruct
```

## Benchmark Results (2026-03-30)

### Accuracy — 8 scenarios (4 routing, 2 extraction, 2 diagnosis)

| Provider | Model | Score | Avg Latency |
|----------|-------|:-----:|------------:|
| **siliconflow** | **Qwen2.5-32B-Instruct** | **8/8** | **1,239ms** |
| siliconflow | Qwen2.5-72B-Instruct | 8/8 | 4,001ms |
| dashscope | qwen-turbo | 8/8 | 1,412ms |
| dashscope | qwen-plus | 8/8 | 2,598ms |
| deepseek | deepseek-chat | 8/8 | 4,487ms |
| tencent_lkeap | deepseek-v3 | 8/8 | 4,497ms |
| siliconflow | Qwen2.5-7B-Instruct | 7/8 | 1,212ms |
| dashscope | qwen-max | 7/8 | 7,256ms |
| tencent_lkeap | deepseek-v3.2 | 6/8 | 6,039ms |
| siliconflow | Qwen3.5-35B-A3B | 8/8 | 3,457ms |

### Latency — minimal prompt, 3 runs after warmup

| Provider | Model | Avg Latency | < 500ms? |
|----------|-------|------------:|:--------:|
| siliconflow | Pro/Qwen2.5-7B | 211ms | ✅ |
| siliconflow | Qwen2.5-7B | 224ms | ✅ |
| **siliconflow** | **Qwen2.5-32B** | **247ms** | **✅** |
| dashscope | qwen-turbo | 379ms | ✅ |
| siliconflow | Qwen2.5-14B | 388ms | ✅ |
| dashscope | qwen-plus | 863ms | ❌ |
| dashscope | qwen3.5-plus | 1,027ms | ❌ |
| tencent_lkeap | deepseek-v3.1 | 1,593ms | ❌ |
| tencent_lkeap | deepseek-v3 | 1,874ms | ❌ |
| tencent_lkeap | deepseek-v3.2 | 1,976ms | ❌ |

### Why Qwen2.5-32B on SiliconFlow?

- **247ms latency** — sub-500ms target met
- **8/8 accuracy** — perfect on routing, extraction, and diagnosis
- **¥1.26/M tokens** — reasonable cost
- **Non-thinking model** — no `enable_thinking` workaround needed
- **Dense 32B** — consistent quality vs MoE models with cold-start issues

## China Production Providers

### SiliconFlow — Primary (Production)

| Model | Input ¥/M | Output ¥/M | Latency | Notes |
|-------|----------:|----------:|---------:|-------|
| **Qwen/Qwen2.5-32B-Instruct** | **1.26** | **1.26** | **247ms** | **Current prod** |
| Qwen/Qwen2.5-72B-Instruct | 4.13 | 4.13 | 532ms | Larger, slower |
| Qwen/Qwen2.5-14B-Instruct | 0.70 | 0.70 | 388ms | Mid-range |
| Qwen/Qwen2.5-7B-Instruct | Free | Free | 224ms | 7/8 accuracy — routing only |
| Pro/Qwen/Qwen2.5-7B-Instruct | 0.35 | 0.35 | 211ms | Dedicated SLA |
| Qwen/Qwen3.5-35B-A3B | varies | varies | 2,200ms+ | MoE, needs `enable_thinking: false` |
| Qwen/Qwen3-32B | varies | varies | 30s+ | Thinking model, avoid |

> Sign up: [siliconflow.cn](https://siliconflow.cn). 500K free welcome tokens.

### DashScope (Alibaba) — Backup

| Model | Input ¥/M | Output ¥/M | Latency | Notes |
|-------|----------:|----------:|---------:|-------|
| **qwen-turbo** | **0.30** | **0.60** | **379ms** | Cheapest accurate option |
| qwen-plus | 0.80 | 2.00 | 863ms | Good all-rounder |
| qwen-max | 2.00 | 6.00 | 7,256ms | Largest, timeout issues |
| qwen3-32b | varies | varies | >5s | Thinking model, avoid |

> Sign up: [百炼](https://bailian.console.aliyun.com). 1M free tokens (90 days).

### Tencent LKEAP — Backup

| Model | Input ¥/M | Output ¥/M | Latency | Notes |
|-------|----------:|----------:|---------:|-------|
| deepseek-v3.2 | 2.00 | 3.00 | 1,976ms | Newest, but slowest |
| deepseek-v3.1 | 4.00 | 12.00 | 1,593ms | |
| deepseek-v3 | 2.00 | 8.00 | 1,874ms | 8/8 accuracy |
| deepseek-r1 | varies | varies | very slow | Reasoning model, avoid |

> Sign up: [腾讯云](https://cloud.tencent.com/product/lkeap). 1M free tokens (2 months).

### DeepSeek (Direct) — Backup

| Model | Input ¥/M | Output ¥/M | Latency | Notes |
|-------|----------:|----------:|---------:|-------|
| deepseek-chat | 2.00 | 8.00 | 847ms | Cache hit: 0.1 input |
| deepseek-reasoner | 4.00 | 16.00 | very slow | Reasoning, avoid |

> Sign up: [platform.deepseek.com](https://platform.deepseek.com).

## Local Dev Providers (US-based, free tier)

These are for local development only — not accessible from China prod.

| Provider | Model | Cost | Notes |
|----------|-------|------|-------|
| **Groq** | qwen/qwen3-32b | Free (6K req/day) | Default local dev provider |
| Cerebras | qwen-3-32b | Free (1M tokens/day) | Fastest inference |
| SambaNova | Qwen2.5-72B | Free (10-30 RPM) | Largest free model |
| OpenRouter | qwen/qwen3.5-9b | $0.05/$0.15 per M | Multi-model |
| Ollama | qwen2.5:7b | Free (local) | Offline, needs GPU |

```bash
# Local dev (uses GROQ_API_KEY from .env)
./cli.py start --provider groq
```

## Thinking Models — `/no_think` Policy

All prompts include `/no_think` as the first line. This disables thinking mode on
Qwen3+ models that recognize the in-prompt flag.

For providers that require API-level control, the benchmark and eval endpoints
pass `extra_body={"enable_thinking": False}` for any model matching `qwen3*`.

**Avoid thinking models for production** — they add 5-30s latency with no accuracy
benefit on our structured-output tasks.

## Cost Estimate

Each user interaction = 1-3 LLM calls, ~1K-5K tokens total.

| Provider + Model | Cost per Interaction | ¥100 Budget = |
|-----------------|--------------------:|-------------:|
| SiliconFlow Qwen2.5-7B | Free | Unlimited |
| DashScope qwen-turbo | ~¥0.0004 | ~250K calls |
| SiliconFlow Qwen2.5-32B | ~¥0.0014 | ~71K calls |
| DashScope qwen-plus | ~¥0.002 | ~50K calls |
| DeepSeek deepseek-chat | ~¥0.005 | ~20K calls |
| Tencent deepseek-v3.2 | ~¥0.003 | ~33K calls |

## Runtime Model Switching

```bash
# Override model via env var
SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct ./cli.py start --provider siliconflow

# Or edit config/runtime.json on server:
# categories.llm.settings.SILICONFLOW_MODEL.value = "Qwen/Qwen2.5-72B-Instruct"
# Then: sudo systemctl restart doctor-ai-backend
```

## Debug Dashboard

The benchmark and eval tools are available at:

```
/api/debug/dashboard?token=<UI_DEBUG_TOKEN>#benchmark
```

- **Benchmark tab**: Latency test with model dropdown per provider
- **Eval tab**: 8-scenario accuracy test (routing + extraction + diagnosis)
- All providers run in parallel, 5s timeout per benchmark call, 15s per eval call
