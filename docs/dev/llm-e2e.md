# E2E Test Report — ReAct Agent Architecture

> Updated: 2026-03-20 | Architecture: LangGraph ReAct agent (`src/agent/`)
> Test suite: `tests/integration/test_e2e_fixtures.py` (52 cases)
> Fixture: `tests/fixtures/data/mvp_accuracy_benchmark.json`

## Current Status

| Provider | Model | Client | Passed | Rate | Time |
|----------|-------|--------|--------|------|------|
| **Groq** | **Qwen3-32B** | ChatGroq | **52/52** | **100%** | **3.1 min** |
| **DeepSeek** | **V3 (beta+strict)** | ChatDeepSeek | **49/52** | **94%** | **12.8 min** |

DeepSeek's 3 remaining failures (010, 024, 025) are non-deterministic
model behavior on edge cases — not fixable from our side.

## Changes That Got Us Here

| Change | DeepSeek | Qwen3-32B |
|--------|----------|-----------|
| Starting point (ChatOpenAI, old prompt) | 18/52 (35%) | 22/52 (42%) |
| + session.py history fix | — | 52/52 (100%) |
| + ChatDeepSeek / ChatGroq clients | 23/52 (44%) | 52/52 (100%) |
| + Pydantic Field descriptions | 32/52 (62%) | — |
| + beta endpoint + strict bind_tools | 31/52 (60%) | — |
| + tool-first prompt (v2) | 49/52 (94%) | 50/52 (96%) |
| + **create-intent prompt (v3)** | **49/52 (94%)** | **52/52 (100%)** |

### Key fixes (in order of impact)

1. **session.py history fix** — append `HumanMessage` before `ainvoke()`
   so tools can see the current turn. Fixed Qwen3 from 42% → 100%.

2. **Prompt rewrite (v3)** — "创建意图优先" framing, tool-first judgment
   order, explicit "禁止行为" section. Fixed DeepSeek from 35% → 94%.

3. **Provider-specific LangChain clients** — `ChatDeepSeek` (beta+strict),
   `ChatGroq`, `ChatOllama` instead of generic `ChatOpenAI`. Proper
   tool-calling protocol per provider.

4. **Pydantic Field descriptions** — Chinese descriptions on every tool
   parameter. Prevents DeepSeek from inventing extra fields.

5. **`clinical_text` param on `create_record`** — accepts LLM-provided
   clinical text, falls back to history scan. Works for both models.

6. **Fixtures consolidated** — merged `deepseek_conversations_v1.json`
   and `gemini_wechat_scenarios_v1.json` into `mvp_accuracy_benchmark.json`.

## DeepSeek Failure Analysis

DeepSeek V3's tool-calling has 3 known weaknesses:

1. **Invents extra parameters** — adds `instruction`, `department`,
   `chief_complaint` etc. to `create_record`. Mitigated by beta+strict
   endpoint and Pydantic schemas, but not fully eliminated.

2. **Prefers conversational replies** — when uncertain, defaults to text
   reply instead of tool call. The v3 prompt reduced this significantly.

3. **Infinite retry loops** — on API rejection, repeats the same malformed
   call 30+ times in one generation. `max_retries=0` limits impact.

## Provider Recommendation

- **Dev/testing:** Groq Qwen3-32B — free, fast (3 min), 100% pass rate
- **Production:** DeepSeek V3 — best Chinese text quality, 94% tool accuracy
- **Hybrid:** Groq for agent routing + DeepSeek for structuring
- **Offline/local:** Qwen3.5:9b via Ollama — not benchmarked yet

## How to Run

```bash
# Start server with a provider
PORT=8001 ./.dev.sh groq   # or deepseek

# Run E2E tests (in another terminal)
RUN_E2E_FIXTURES=1 ROUTING_LLM=groq STRUCTURING_LLM=groq \
PYTHONPATH=src .venv/bin/python -m pytest \
tests/integration/test_e2e_fixtures.py -v --tb=line
```
