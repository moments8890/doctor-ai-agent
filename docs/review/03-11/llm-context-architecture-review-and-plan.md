# Goal
Summarize the current LLM context architecture risks and define an execution plan to improve routing/structuring accuracy by cleaning context assembly instead of only tuning prompts.

# Summary

## Current assessment
- The current agent prompt is usable, but it is not the primary accuracy bottleneck.
- The main problem is the context assembly layer: knowledge injection, history trimming, and structuring input construction are mixing the wrong information together.
- The routing LLM and structuring LLM are consuming context with different needs, but the current system does not model those needs separately.

## Key findings
1. Knowledge context is cached by `doctor_id` instead of `doctor_id + query`, so irrelevant knowledge can leak into later unrelated requests.
2. Routing LLM message assembly treats retrieved knowledge as a `user` message, which can blur the line between true user input and background context.
3. Routing history is trimmed by raw message count, not by information value, so important clarification/patient-binding context is easy to lose.
4. Structuring LLM input is built from raw recent user turns, which allows task/query/export/control language to contaminate the clinical note.
5. The current prompt set is overloaded: one prompt is trying to do intent selection, tool choice, field extraction, clarification policy, and response style all at once.
6. The compact routing prompt is materially weaker than the full prompt, but compact mode is the likely default in practice.

## Bottom-line conclusion
- The current prompt is "good enough to operate" but not "good enough to carry the architecture."
- Accuracy gains are more likely to come from separating and cleaning context inputs than from adding more prompt rules.

# Affected files
- docs/review/03-11/llm-context-architecture-review-and-plan.md
- services/knowledge/doctor_knowledge.py
- services/ai/agent.py
- services/domain/record_ops.py
- tests/test_agent.py
- tests/test_llm_context.py (new — 26 tests)

# Steps

## Done

1. ~~Fix knowledge context caching.~~
   - Changed `_KNOWLEDGE_CACHE` from caching the rendered string (stale across queries) to caching raw items by `doctor_id` (`_KNOWLEDGE_ITEMS_CACHE`).
   - `render_knowledge_context(query=..., items=...)` is now called fresh on every request, so per-query scoring always reflects the current query.
   - DB reads are still cached (5-min TTL by doctor_id) to avoid repeated queries.

3. ~~Change routing LLM message roles.~~
   - Knowledge context is now injected as `{"role": "system", ...}` instead of `{"role": "user", ...}` in `_build_messages()`.
   - True user input remains the only `user` message, preventing the LLM from confusing background knowledge with the doctor's actual request.
   - Test `test_dispatch_injects_knowledge_context_as_system_message` updated to assert `system` role.

4. ~~Replace raw history trimming with information-aware trimming.~~
   - Added `_trim_history_by_value()` in `agent.py` which:
     - Always keeps the last 2 turns (immediate context).
     - Among older turns, prioritizes high-value turns (patient binding, clarification questions, clinical decisions, scale scores, follow-up context) via `_HIGH_VALUE_RE`.
     - Fills remaining budget with low-value turns newest-first.
     - Result is always in chronological order.
   - Replaces the old "newest-first, drop when over char budget" approach.

8. ~~Add validation coverage.~~ (unit tests complete; E2E follow-up optional)
   - `tests/test_llm_context.py` — 26 new tests covering:
     - **Knowledge cache** (3 tests): items cached by doctor_id, re-rendered per query with different rankings; DB hit skipped on cache; invalidation forces re-fetch.
     - **Message roles** (3 tests): knowledge injected as `system`; no `user` messages contain background knowledge; injection keywords blocked.
     - **History trimming** (7 tests): empty history; short history intact; last 2 always kept; high-value preserved over low-value; `_is_high_value_turn` detects patient binding, scores, clinical decisions; long turns counted as high-value; chronological order preserved.
     - **Clinical context filtering** (6 tests): short commands excluded; admin prefixes excluded; greetings/task turns excluded; clinical history included; deduplication; `_is_clinical_turn` boundary cases.
     - **Record assembly** (7 tests): `_sanitize_prior_summary` only for follow_up; injection lines blocked; truncation; `assemble_record` passes encounter_type; prior summary injected for follow_up; no prior summary for first_visit.
   - E2E cases (unrelated specialties, clarification turns, mixed task+clinical, follow-up flows) are optional follow-up.

## Satisfied by existing implementation

5. ~~Split structuring context assembly into a dedicated builder.~~
   - `record_ops.build_clinical_context()` already filters history to clinical-only turns.
   - Excludes commands, greetings, task operations, queries, and admin chatter via `_is_clinical_turn()`.
   - No changes needed — this was already implemented correctly.

6. ~~Tighten the structuring input protocol.~~
   - `assemble_record()` in `record_ops.py` already:
     - Builds clinical-only context via `build_clinical_context()`.
     - Detects encounter type (first_visit / follow_up / unknown).
     - Injects sanitized prior-visit summary for follow-up encounters.
   - No changes needed — this was already implemented correctly.

## Deferred — follow-up task

2. Split routing context assembly into a dedicated `RoutingContextBuilder`.
   - Currently `_build_messages()` in `agent.py` handles this inline. Extracting it into a separate class would improve testability and make the assembly order explicit.
   - Deferred: the inline implementation is clear enough for now; value is incremental.

7. Re-evaluate prompt modes after context cleanup.
   - Compare full vs compact routing prompts with the new context assembly in place.
   - Do not treat prompt tuning as the first-line fix.

# Risks / open questions
- If compact prompt mode remains default, gains from context cleanup may be partially masked by prompt compression loss.
- Clarification state is not yet modeled as a first-class context object; introducing it may require small workflow changes beyond pure prompt assembly.
- The `RoutingContextBuilder` refactor (step 2) is deferred — current inline `_build_messages()` is functional but would benefit from extraction for testability.
