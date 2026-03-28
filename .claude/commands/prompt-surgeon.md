# /prompt-surgeon — Edit prompts with eval coverage

Use when editing prompt files under `src/agent/prompts/`, fixing routing drift,
extraction quality, or Chinese phrasing in LLM output.

## Workflow

### Step 1: Identify the prompt

Determine which prompt file is being edited. Map it to its eval artifacts:

| Prompt file | Wrapper | Cases | Has eval |
|-------------|---------|-------|----------|
| `intent/routing.md` | `wrappers/routing.md` | `cases/routing.yaml` | Yes |
| `intent/query.md` | `wrappers/query.md` | `cases/query.yaml` | Yes |
| `intent/interview.md` | `wrappers/interview.md` | `cases/interview.yaml` | Yes |
| `intent/diagnosis.md` | `wrappers/diagnosis.md` | `cases/diagnosis.yaml` | Yes |
| `intent/general.md` | `wrappers/general.md` | `cases/general.yaml` | Yes |
| `intent/vision-ocr.md` | `wrappers/vision-ocr.md` | `cases/vision-ocr.yaml` | Yes |
| `intent/patient-interview.md` | `wrappers/patient-interview.md` | `cases/patient-interview.yaml` | Yes |
| `intent/triage-classify.md` | — | — | **No** |
| `intent/triage-escalation.md` | — | — | **No** |
| `intent/triage-informational.md` | — | — | **No** |
| `knowledge_ingest.md` | — | — | **No** |
| `common/base.md` | (used by all) | — | **No** (system-level) |
| `domain/neurology.md` | (used by all domain) | — | **No** (domain-level) |

### Step 2: Capture the before state

Before making any edits, read the current prompt file content and save it mentally
as the "before" version. You'll need this for the diff in Step 4.

### Step 3: Make the edit

Edit the prompt file. Follow these rules from AGENTS.md and project feedback:
- **Show the diff to the user and get explicit approval** before finalizing
- Use Chinese (中文) for user-facing strings and medical terminology
- Preserve medical abbreviations (STEMI, BNP, PCI, EGFR, etc.)
- If the prompt uses `structured_call()` → no output format section needed (Pydantic enforces)
- If the prompt uses `llm_call()` → prompt MUST define `## 输出格式` since no code enforcement

### Step 4: Show diff and get approval

Present a clear before/after comparison to the user. Highlight:
- What changed (added rules, removed constraints, rephrased instructions)
- Why it changed (what problem this fixes)
- Any risk (could this break other intents? change output format?)

**Wait for user approval before proceeding.**

### Step 5: Run eval (if coverage exists)

If the prompt has eval coverage (see table in Step 1), run the eval:

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/tests/prompts && bash run.sh <prompt-name>
```

Where `<prompt-name>` matches the wrapper/cases filename (e.g., `routing`, `query`, `diagnosis`).

**Important:**
- This requires `GROQ_API_KEY` in `config/runtime.json`
- Each eval takes 10-30 seconds per prompt
- Report results: X passed, Y failed
- If any cases failed, show which ones and why

If the prompt has **no eval coverage**, warn:
"This prompt has no eval cases. Consider adding `tests/prompts/wrappers/<name>.md` and
`tests/prompts/cases/<name>.yaml` before shipping. Skipping eval."

### Step 6: Check README sync

Read `src/agent/prompts/README.md`. Check if the edit changed any of:
- Intent count or names
- Which LLM call type is used (`structured_call` vs `llm_call`)
- Prompt workflow (new stages, removed stages)
- Layer assignments in the prompt composer

If any of these changed, update the README. If not, skip.

### Step 7: Summary

Report:
```
Prompt: intent/<name>.md
Change: <one-line description>
Eval: X/Y passed (or "no coverage")
README: updated / no update needed
Status: DONE
```

## When NOT to use this skill

- Editing `common/base.md` or `domain/neurology.md` — these affect all prompts,
  run the full eval suite instead: `cd tests/prompts && bash run.sh`
- Adding brand new prompt files — create the wrapper + cases first, then use this skill
- Fixing typos only — just edit directly, no eval needed
