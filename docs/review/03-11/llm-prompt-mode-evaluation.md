# Goal
Decide whether `full` or `compact` should be the default routing prompt mode after the 2026-03-11 context cleanup, using explicit evaluation instead of more prompt churn.

# Affected files
- docs/review/03-11/llm-prompt-mode-evaluation.md
- services/ai/agent.py
- services/ai/agent_tools.py
- config/runtime.json.sample
- tests/test_prompt_mode_eval.py

# Steps

## Done

1. ~~Freeze the baseline.~~
   - [`docs/review/03-11/llm-context-architecture-review-and-plan.md`](llm-context-architecture-review-and-plan.md) is the completed cleanup snapshot.
   - No prompt-mode evaluation mixed with context-assembly refactors.

2. ~~Define a compact evaluation set for routing.~~
   - Created [`tests/test_prompt_mode_eval.py`](../../tests/test_prompt_mode_eval.py) with 13 evaluation cases:
     - **Core routing (6):** note_capture, followup_note, patient_lookup, query_with_clinical_vocab, task_complete, followup_schedule
     - **Clarification (1):** clarification_name_reply (bare name after "请问这位患者叫什么名字？")
     - **Create patient (1):** create_patient_only
     - **Correction (1):** record_correction
     - **Edge cases (4):** greeting_no_tool, list_patients, list_tasks, delete_patient
   - Covers intent selection (13 cases × 2 modes = 26 tests) and patient binding (8 cases × 2 modes = 16 tests) — 42 total parametrized tests.
   - Auto-skips when no LLM is configured (`ROUTING_LLM` + API key).
   - Standalone runner (`python tests/test_prompt_mode_eval.py`) prints a comparison table with per-mode accuracy.

3. ~~Compare `compact` vs `full` under the same context assembly.~~
   - Evaluated on 2026-03-11 with `ROUTING_LLM=ollama` (qwen2.5:14b).
   - No external API keys (deepseek, gemini, etc.) available for cross-provider comparison.

### Results: ollama (qwen2.5:14b)

| Mode | Intent accuracy | Patient binding accuracy |
|------|----------------|------------------------|
| **compact** | **62% (8/13)** | **75% (6/8)** |
| full | 54% (7/13) | 62% (5/8) |

**Full-mode unique failures (4):** note_capture, query_with_clinical_vocab, task_complete, create_patient_only — all returned `unknown`. The verbose prompt appears to exhaust the model's attention budget, causing it to skip tool calls.

**Compact-mode unique failures (2):** followup_schedule (returned `unknown`), delete_patient (returned `unknown`).

**Shared failures (2):** record_correction (`update_record` not triggered by either mode), list_tasks (`待办任务` not recognized by either mode).

**Compact-mode wrong-tool (1):** create_patient_only → called `update_patient_info` instead of `create_patient`.

### Analysis
- Compact outperforms full by 8 percentage points on intent and 13 on patient binding.
- Full mode's extra verbosity hurts more than it helps on a 14B parameter model — the most basic case (note_capture) fails in full but succeeds in compact.
- Both modes share the same weak spots (record_correction, list_tasks), confirming these are tool/prompt gaps rather than mode-specific issues.
- The `create_patient` vs `update_patient` confusion in compact mode is a tool naming issue, not a prompt mode issue.

4. ~~Make one explicit default decision.~~
   - **Decision: keep `compact` as the default.**
   - Compact produces materially better routing on the available LLM (qwen2.5:14b).
   - Full mode's structured format does not compensate for its token cost on smaller models.
   - `config/runtime.json.sample` should set `AGENT_ROUTING_PROMPT_MODE=compact`.
   - If a future evaluation on a stronger model (deepseek, GPT-4) shows full is better, revisit.

## To do

5. Add regression coverage for the chosen default.
   - Update or add focused tests for the shared failure cases: `record_correction`, `list_tasks`.
   - Investigate `create_patient` vs `update_patient` tool confusion — may need tool name/description clarification.
   - Re-run evaluation after any prompt or tool fixes to confirm improvement.

6. Defer adjacent architecture work unless the evaluation proves it is necessary.
   - `RoutingContextBuilder` extraction is not part of this plan.
   - Shared failure cases (record_correction, list_tasks) are prompt/tool issues, not architecture issues — fix in prompt text or tool definitions.

# Prompt mode details

| Mode | Env var | Word count | Style |
|------|---------|-----------|-------|
| `full` | `AGENT_ROUTING_PROMPT_MODE=full` | ~607 words | Structured sections with numbered rules |
| `compact` | `AGENT_ROUTING_PROMPT_MODE=compact` | ~205 words | Semicolon-delimited single paragraph |

- Prompt text: `services/ai/agent_tools.py` (`_SYSTEM_PROMPT` / `_SYSTEM_PROMPT_COMPACT`)
- Mode selection: `services/ai/agent.py` → `_get_routing_prompt()` reads `AGENT_ROUTING_PROMPT_MODE`
- Code default: `compact` (hardcoded fallback in `_get_routing_prompt`)
- Config default: `config/runtime.json.sample` currently sets `full`

# Risks / open questions
- Provider variance may hide the real effect size between `compact` and `full`.
- A small evaluation set can overfit to known failures; the 13 cases include both obvious and boring routine cases to mitigate this.
- `config/runtime.json` is local-only and should not be treated as the committed default; use `config/runtime.json.sample` for repo defaults.
