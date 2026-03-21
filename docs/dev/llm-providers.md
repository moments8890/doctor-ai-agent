# LLM Providers — Chinese Medical Focus

All providers run **Qwen** or **DeepSeek** models only — optimized for Chinese medical content.
Pricing verified March 2026.

## Quick Start

```bash
./cli.py start --provider deepseek     # best Chinese quality — production
./cli.py start --provider groq         # fast dev — Qwen3 32B, 0.7s
./cli.py start --provider cerebras     # fastest — Qwen3 32B, free 1M tokens/day
./cli.py start --provider sambanova    # free — Qwen2.5 72B, no credit card
./cli.py start --provider siliconflow  # China cloud — DeepSeek V3.2
./cli.py start --provider openrouter   # multi-model — Qwen/DeepSeek
./cli.py start --provider ollama        # offline — Qwen 2.5 7B via Ollama
```

## Provider Comparison

### Pricing (per 1M tokens, USD)

| Provider | Default Model | Input $/M | Output $/M | Free Tier |
|----------|--------------|-----------|------------|-----------|
| **Cerebras** | Qwen3-32B | $0.40 | $0.80 | 1M tokens/day |
| **SambaNova** | Qwen2.5-72B-Instruct | Free | Free | Persistent free (10-30 RPM) |
| **Groq** | Qwen3-32B | $0.29 | $0.59 | 6K req/day, 6K TPM |
| **OpenRouter** | qwen3.5-9b | $0.05 | $0.15 | Pay-as-you-go |
| **DeepSeek** | deepseek-chat (V3.2) | $0.28 | $0.42 | No hard limit |
| **SiliconFlow** | DeepSeek-V3.2 | $0.27 | $0.42 | 500K free tokens |
| **Tencent LKEAP** | deepseek-v3-1 | ~$0.28 | ~$0.42 | 500K free tokens |
| **Ollama** | qwen2.5:7b | Free | Free | Local hardware |

### Latency (single agent turn, Chinese medical prompt)

| Provider | Default Model | TTFT | Output Speed | Total (1 turn) |
|----------|--------------|------|-------------|-----------------|
| **Cerebras** | Qwen3-32B | ~1.2s | 2,400 t/s | **~0.5s** |
| **Groq** | Qwen3-32B | ~0.3s | 535 t/s | **~0.7s** |
| **SambaNova** | Qwen2.5-72B | ~0.5s | ~400 t/s | **~0.9s** |
| **SiliconFlow** | DeepSeek-V3.2 | ~1s | ~200 t/s | **~1.5s** |
| **OpenRouter** | qwen3.5-9b | ~1s | varies | **~2.1s** |
| **DeepSeek** | deepseek-chat (V3.2) | ~1.5s | ~150 t/s | **~2.9s** |
| **Tencent LKEAP** | deepseek-v3-1 | ~1s | varies | **~2.0s** |
| **Ollama** | qwen2.5:7b | ~2s | ~30 t/s | **~7.9s** |

### Quality vs Speed Matrix

```
Quality (Chinese Medical)
  ^
  |  DeepSeek V3.2 ★    SiliconFlow (DS V3.2)
  |  Tencent (DS V3.1)
  |
  |  SambaNova (Qwen 72B)
  |  Groq (Qwen3 32B)     Cerebras (Qwen3 32B)
  |
  |  OpenRouter (Qwen3.5 9B)
  |  Ollama (Qwen 2.5 7B)
  +-----------------------------------------------> Speed
     Slow                                    Fast
```

## All Available Models per Provider

### DeepSeek (Direct API) — Best Chinese Quality

| Model | Input $/M | Output $/M | Cache Hit | Context | Notes |
|-------|-----------|------------|-----------|---------|-------|
| `deepseek-chat` (V3.2) | $0.28 | $0.42 | $0.028 | 128K | Default. Best Chinese medical |
| `deepseek-reasoner` (R1) | $0.50 | $2.18 | $0.14 | 128K | Deep reasoning, 5x slower |

> Cache hits save 90% on input. Repeated system prompts (agent prompt + tools) hit cache after first call.

### Groq — Fastest Dev

| Model | Input $/M | Output $/M | Latency | Free | Notes |
|-------|-----------|------------|---------|------|-------|
| `qwen/qwen3-32b` | $0.29 | $0.59 | 0.7s | 6K req/day, 6K TPM | Default. May emit `<think>` |
| `deepseek-r1-distill-qwen-32b` | $0.29 | $0.59 | ~1s | 6K req/day | DeepSeek R1 distilled |

> Free tier TPM (6K) is tight for ReAct agent (~4K tokens/call). Add $10 credit to remove limits.

### Cerebras — Fastest Inference

| Model | Input $/M | Output $/M | Speed | Free | Notes |
|-------|-----------|------------|-------|------|-------|
| `qwen-3-32b` | $0.40 | $0.80 | 2,400 t/s | 1M tokens/day | Default |

> 40x faster than GPU inference. 1M free tokens/day = ~100 agent turns.

### SambaNova — Best Free Tier

| Model | Cost | RPM | Notes |
|-------|------|-----|-------|
| `Qwen2.5-72B-Instruct` | Free | ~15 RPM | Default. Largest free Qwen |
| `DeepSeek-R1-Distill-Qwen-32B` | Free | ~20 RPM | Reasoning model |
| `QwQ-32B` | Free | ~20 RPM | Qwen reasoning |

> Truly free — no credit card, no expiry. RPM limits may throttle multi-tool agent turns.

### SiliconFlow — China Cloud

| Model | Input $/M | Output $/M | Notes |
|-------|-----------|------------|-------|
| `deepseek-ai/DeepSeek-V3.2` | $0.27 | $0.42 | Default. Same as direct DeepSeek |
| `Qwen/Qwen2.5-72B-Instruct` | ~$0.20 | ~$0.40 | Large Qwen |
| `Qwen/Qwen2.5-7B-Instruct` | ~Free | ~Free | Lightweight, free tier |

> China-based servers = low latency for Chinese users. 500K free welcome tokens.

### OpenRouter — Multi-Model Router

| Model | Input $/M | Output $/M | Latency | Notes |
|-------|-----------|------------|---------|-------|
| `qwen/qwen3.5-9b` | $0.05 | $0.15 | 2.1s | Default. Cheapest |
| `qwen/qwen3-32b` | $0.08 | $0.24 | 1.7s | Better quality |
| `qwen/qwen3.5-122b-a10b` | $0.20 | $1.56 | ~2s | MoE, large |
| `deepseek/deepseek-v3.2` | $0.26 | $0.40 | ~2s | Best quality |

### Tencent LKEAP — China Enterprise

| Model | Notes |
|-------|-------|
| `deepseek-v3-1` | Default. DeepSeek hosted by Tencent Cloud |

> 500K free welcome tokens. Enterprise-grade SLA for China production.

### Ollama — Local / Offline

| Model | Size | RAM | Latency | Notes |
|-------|------|-----|---------|-------|
| `qwen2.5:3b` | 2.0GB | 4GB | ~5s | Fast, lower quality |
| `qwen2.5:7b` | 4.7GB | 8GB | ~8s | Default. Good balance |
| `qwen2.5:14b` | 9.0GB | 16GB | ~12s | Best local quality |

## Cost Estimate for Agent Turns

Each ReAct agent turn = 1-3 LLM calls, ~4K-15K tokens total.

| Provider | Cost per Turn | $5 Budget = | $10 Budget = |
|----------|--------------|-------------|-------------|
| **SambaNova** | Free | Unlimited | Unlimited |
| **Cerebras** | ~Free | ~2,500/day free | ~2,500/day free |
| **OpenRouter** (9B) | ~$0.001 | ~5,000 turns | ~10,000 turns |
| **DeepSeek** | ~$0.003 | ~1,700 turns | ~3,400 turns |
| **Groq** | ~$0.004 | ~1,300 turns | ~2,600 turns |
| **Cerebras** (paid) | ~$0.006 | ~800 turns | ~1,600 turns |
| **Ollama** | Free | Unlimited | Unlimited |

## Switching Models at Runtime

```bash
# Groq with DeepSeek distill
GROQ_MODEL=deepseek-r1-distill-qwen-32b ./cli.py start --provider groq

# OpenRouter with DeepSeek V3.2
OPENROUTER_MODEL=deepseek/deepseek-v3.2 ./cli.py start --provider openrouter

# SambaNova with reasoning model
SAMBANOVA_MODEL=QwQ-32B ./cli.py start --provider sambanova

# SiliconFlow with DeepSeek
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2 ./cli.py start --provider siliconflow

# Ollama with larger Qwen
OLLAMA_MODEL=qwen2.5:14b ./cli.py start --provider ollama
```

## Setup Instructions

### DeepSeek (Production)

1. Sign up at [platform.deepseek.com](https://platform.deepseek.com)
2. Create API key
3. $5 minimum top-up = ~1,700 agent turns

```bash
./cli.py start --provider deepseek
```

### Groq (Fast Dev)

1. Sign up at [console.groq.com](https://console.groq.com)
2. Create API key → [API Keys](https://console.groq.com/keys)
3. Add $10 credit → [Billing](https://console.groq.com/settings/billing) (removes rate limits)

```bash
./cli.py start --provider groq
```

### Cerebras (Fastest)

1. Sign up at [cloud.cerebras.ai](https://cloud.cerebras.ai)
2. Create API key
3. Free: 1M tokens/day, no credit card

```bash
./cli.py start --provider cerebras
```

### SambaNova (Free)

1. Sign up at [cloud.sambanova.ai](https://cloud.sambanova.ai)
2. Create API key → [API Keys](https://cloud.sambanova.ai/apis)
3. Free forever, no credit card

```bash
./cli.py start --provider sambanova
```

### SiliconFlow (China Cloud)

1. Sign up at [siliconflow.cn](https://siliconflow.cn)
2. Create API key
3. 500K free welcome tokens

```bash
./cli.py start --provider siliconflow
```

### OpenRouter (Multi-Model)

1. Sign up at [openrouter.ai](https://openrouter.ai)
2. Create API key → [Keys](https://openrouter.ai/settings/keys)
3. Pay-as-you-go

```bash
./cli.py start --provider openrouter
```

### Ollama (Offline)

1. Install: [ollama.com/download](https://ollama.com/download)
2. `./cli.py start --provider ollama` auto-pulls `qwen2.5:7b` if needed

```bash
./cli.py start --provider ollama
```

## Troubleshooting

### Qwen3 `<think>` tokens in output

Groq/Cerebras Qwen3-32B may output `<think>...</think>` reasoning tokens before the actual response. If this breaks tool calling:
- Strip `<think>...</think>` tags in response parsing
- Switch to `deepseek-r1-distill-qwen-32b` (no think tokens)
- Use DeepSeek directly (no think tokens)

### 429 Rate Limit (Free Tier)

ReAct agent makes 2-3 LLM calls per turn with ~4K tokens each. Free tier limits:
- **Groq** 6K TPM: Add $10 credit
- **SambaNova** 15 RPM: OK for single user, too slow for concurrent
- **Cerebras** 1M tokens/day: ~100 turns/day on free tier

### Slow First Request (Ollama)

First request loads model into GPU memory (~10-30s). Subsequent requests faster.

### DeepSeek Cache Hits

DeepSeek caches repeated prompt prefixes. The agent system prompt + tool schemas are identical across turns → 90% discount on input tokens after first call. Effective cost drops from ~$0.003/turn to ~$0.001/turn.
