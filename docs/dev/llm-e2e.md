# E2E Failure Investigation — ReAct Agent Architecture

> Date: 2026-03-19 | Architecture: LangGraph ReAct agent (`src/agent/`)
> Test suite: `tests/integration/test_e2e_fixtures.py` (52 cases)
> Best result: Groq Qwen3-32B — 22/52 (42%)

## Summary

| Provider | Model | Passed | Rate | Time | Cost |
|----------|-------|--------|------|------|------|
| **Groq** | **Qwen3-32B** | **22/52** | **42%** | **9.5 min** | Free (6K req/day) |
| DeepSeek | deepseek-chat (V3) | 21/52 | 40% | 18 min | ~$0.14/M tokens |
| SambaNova | Llama-3.3-70B | 16/52 | 31% | ~1 min | Free |
| Groq | Llama-3.1-8B | 13/52 | 25% | 7.5 min | Free (6K req/day) |

## Per-Case Results

| Case | Group | Title | Groq Qwen3-32B | DeepSeek | SambaNova Llama70B | Groq Llama8B |
|------|-------|-------|:-:|:-:|:-:|:-:|
| MVP-ACC-001 | create_save | STEMI emergency | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-002 | create_save | Acute stroke | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-003 | create_save | COPD exacerbation | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-004 | create_save | Diabetic ketoacidosis | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-005 | create_save | Acute MI | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-006 | create_save | Pneumonia | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-007 | create_save | Heart failure | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-008 | create_save | GI bleeding | PASS | PASS | FAIL | FAIL |
| MVP-ACC-009 | create_save | Renal failure | PASS | PASS | FAIL | FAIL |
| MVP-ACC-010 | create_save | Asthma exacerbation | PASS | FAIL | FAIL | FAIL |
| MVP-ACC-011 | query | Query records | PASS | PASS | PASS | PASS |
| MVP-ACC-012 | query | Query patient list | PASS | PASS | PASS | PASS |
| MVP-ACC-013 | update | Update record | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-014 | chitchat | Greeting | PASS | PASS | PASS | FAIL |
| MVP-ACC-015 | chitchat | Medical question | PASS | PASS | PASS | PASS |
| MVP-ACC-016 | chitchat | Off-topic | PASS | PASS | PASS | PASS |
| MVP-ACC-017 | multi_turn | Multi-turn create | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-018 | multi_turn | Collect then create | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-019 | multi_turn | Supplement info | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-020 | multi_turn | Correct and update | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-023 | task | Create follow-up | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-024 | task | Create appointment | PASS | FAIL | FAIL | FAIL |
| MVP-ACC-025 | task | Create reminder | PASS | PASS | FAIL | FAIL |
| MVP-ACC-026 | task | Query tasks | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-027 | task | Task for existing patient | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-030 | edge | Empty input | PASS | PASS | PASS | PASS |
| MVP-ACC-031 | edge | Very long input | PASS | PASS | FAIL | PASS |
| MVP-ACC-032 | edge | Special characters | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-033 | edge | Ambiguous name | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-034 | edge | Minimal info create | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-035 | compound | Create + task | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-036 | compound | Query + update | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-037 | compound | Create + query | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-038 | confirm | Confirm pending | PASS | PASS | PASS | PASS |
| MVP-ACC-039 | confirm | Abandon pending | PASS | PASS | PASS | PASS |
| MVP-ACC-041 | safety | Refuse fabrication | PASS | PASS | PASS | PASS |
| MVP-ACC-042 | safety | Refuse unknown patient | PASS | PASS | PASS | PASS |
| MVP-ACC-043 | dedup | Patient dedup | FAIL | FAIL | FAIL | FAIL |
| MVP-ACC-044 | i18n | Chinese medical terms | PASS | PASS | PASS | PASS |
| MVP-ACC-045 | i18n | Mixed CN/EN | PASS | PASS | PASS | FAIL |
| MVP-ACC-046 | i18n | Drug names preserved | PASS | PASS | PASS | PASS |
| MVP-ACC-047 | perf | Timeout compliance | PASS | PASS | PASS | PASS |
| MVP-ACC-048 | robustness | Typo tolerance | PASS | PASS | PASS | FAIL |
| MVP-ACC-049 | robustness | Abbreviation handling | PASS | PASS | PASS | FAIL |
| DS-001 | deepseek | Create record | FAIL | FAIL | FAIL | FAIL |
| DS-002 | deepseek | Create record | FAIL | FAIL | FAIL | FAIL |
| DS-003 | deepseek | Create record | FAIL | FAIL | FAIL | FAIL |
| DS-004 | deepseek | Create record | FAIL | PASS | FAIL | FAIL |
| DS-005 | deepseek | Create record | FAIL | FAIL | FAIL | FAIL |
| GM-001 | gemini | Create record | FAIL | FAIL | FAIL | FAIL |
| GM-002 | gemini | Create record | FAIL | FAIL | FAIL | FAIL |
| GM-003 | gemini | Create record | FAIL | FAIL | FAIL | FAIL |

## Failure Root Cause Analysis

All 30 failures fall into 4 root causes. Ordered by impact.

---

### Issue 1: Current turn not in history when tool runs (create_save 001–007)

**Symptom:** Patient created, but `medical_records = 0`. Pending record
never written because `_create_pending_record()` returns early with
"没有找到临床信息".

**Root cause:** `_create_pending_record()` in `agent/tools/doctor.py:108-120`
collects clinical text by scanning `agent.history` for messages containing
`patient_name`. But the current turn's message is **not yet in history**
when the tool runs — `_add_turn()` only appends *after* `agent.handle()`
returns.

```
Timeline:
  1. Doctor sends "创建患者赵强，男61岁，胸痛90分钟..."
  2. LLM sees input → calls create_record(patient_name="赵强")
  3. Tool runs _create_pending_record()
  4. Scans agent.history for messages containing "赵强"
  5. History is EMPTY (this is turn 1, no prior messages)
     → clinical_text = ""
     → Returns {"status": "error", "message": "没有找到临床信息"}
  6. Agent replies with error, no pending record created
  7. Doctor sends "确认" → nothing to confirm → FAIL
```

**Why 008/009 sometimes pass:** Non-deterministic — the LLM may retry,
or the structuring call gets clinical text through a different path.

**Fix:** In `src/agent/session.py`, append the human message *before*
invoking the agent so tools can see the current turn:

```python
async def handle(self, text: str) -> str:
    # Add current message BEFORE invoke so tools can scan it
    self.history.append(HumanMessage(content=text))

    result = await self.agent.ainvoke(
        {"messages": self.history},
        config={"recursion_limit": 25},
    )
    reply_messages = result.get("messages", [])
    reply = ""
    if reply_messages:
        last = reply_messages[-1]
        reply = last.content if hasattr(last, "content") else str(last)

    # Only append AI reply (human already added above)
    self.history.append(AIMessage(content=reply))
    if len(self.history) > MAX_HISTORY * 2:
        self.history = self.history[-(MAX_HISTORY * 2):]
    return reply
```

And guard `_add_turn` in `handle_turn.py` for fast-path calls:

```python
def _add_turn(self, text: str, reply: str) -> None:
    # Fast-path: human msg may already be in history from handle()
    if not self.history or not isinstance(self.history[-1], HumanMessage) \
       or self.history[-1].content != text:
        self.history.append(HumanMessage(content=text))
    self.history.append(AIMessage(content=reply))
    ...
```

**Impact:** Fixes ~28 cases (001–010, 013, 031–037, DS-*, GM-*).

---

### Issue 2: Multi-turn collection rules missing from agent prompt (017–020)

**Symptom:** Patient not created in multi-turn cases where turn 1
provides partial info and turn 2 completes it.

**Root cause:** The agent prompt (`prompts/agent-doctor.md`) may not
include explicit rules for:
- Accumulating clinical fields across messages
- Maximum follow-up count before auto-creating
- When to auto-trigger `create_record` vs ask for more info

**Fix:** Add to `prompts/agent-doctor.md`:

```markdown
## 临床信息收集规则
- 当医生提供部分患者信息时，询问缺少的关键字段（姓名、主诉）
- 最多追问 2 次，之后用已有信息自动调用 create_record
- 当单条消息包含姓名 + 主诉 + 任意临床数据时，立即调用 create_record
- 不要等待医生说"创建"——临床内容本身就是创建信号
```

**Impact:** Fixes 4 cases (017–020).

---

### Issue 3: Cascading failures from issue #1 (023–027, 035–037)

**Symptom:** Task and compound cases fail because they depend on a
patient/record being created in an earlier turn within the same test case.

**Root cause:** When `create_record` fails (issue #1), the patient may
exist (resolve auto-creates it), but no record or pending draft exists.
Subsequent turns that need records/tasks fail.

**Fix:** Resolves automatically when issue #1 is fixed.

**Impact:** ~8 cases.

---

### Issue 4: DS/GM fixtures assume provider-specific behavior

**Symptom:** `deepseek_conversations_v1.json` and
`gemini_wechat_scenarios_v1.json` fixtures fail across all providers.

**Root cause:** Written for the old UEC pipeline with provider-tuned
routing. The new ReAct agent has different tool-calling behavior.

**Fix options:**
- Re-generate fixtures for the ReAct agent
- Merge into `mvp_accuracy_benchmark.json` with provider-agnostic assertions
- Skip with `"skip_react": true` flag in fixture JSON

**Impact:** 8 cases (DS-001–005, GM-001–003).

---

## Fix Priority

| # | Issue | Impact | Effort | Cases Fixed |
|---|-------|--------|--------|-------------|
| 1 | History missing current turn | **Critical** | Small (10 lines) | ~28 cases |
| 2 | Multi-turn prompt rules | Medium | Medium (prompt tuning) | 4 cases |
| 3 | Cascading from #1 | Auto | — | ~8 cases |
| 4 | Provider-specific fixtures | Low | Small | 8 cases |

**Fix #1 alone could bring pass rate from 42% to ~75%+.**

---

## What Passes Reliably (all providers)

- **Query / list** (011, 012) — read-only, no writes
- **Chitchat** (015, 016) — off-topic / medical questions
- **Confirm / abandon** (038, 039) — deterministic fast path, 0 LLM
- **Safety** (041, 042) — refuse fabrication / unknown patient
- **i18n** (044, 046) — Chinese medical terms, drug name preservation
- **Perf** (047) — timeout compliance

## Chinese-Native Models Dominate

Qwen3-32B and DeepSeek V3 are significantly better than Llama at Chinese
clinical intent classification. Llama models misclassify `action_type` on
create/task intents in Chinese.

## Provider Recommendation

- **Dev/testing:** Groq Qwen3-32B — free, fast (9.5 min), best pass rate
- **Production:** DeepSeek V3 — reliable, best Chinese quality, low cost
- **Offline/local:** Qwen3.5:9b via Ollama — not benchmarked (LAN down)

## How to Run

```bash
# Start server with a provider
PORT=8001 ./.dev.sh deepseek   # or groq, sambanova, etc.

# Run E2E tests (in another terminal)
RUN_E2E_FIXTURES=1 ROUTING_LLM=deepseek STRUCTURING_LLM=deepseek \
PYTHONPATH=src .venv/bin/python -m pytest \
tests/integration/test_e2e_fixtures.py -v --tb=line
```

## How to Validate Fix #1

After applying the `session.py` change:
```bash
PORT=8001 ./.dev.sh groq
# then:
RUN_E2E_FIXTURES=1 ROUTING_LLM=groq STRUCTURING_LLM=groq \
PYTHONPATH=src .venv/bin/python -m pytest \
tests/integration/test_e2e_fixtures.py -v --tb=line
```
Expected: create_save 001–010 should start passing.
