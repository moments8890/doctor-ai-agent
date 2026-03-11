# AI Context and Prompt Contract

This document defines the current engineering contract for AI-facing inputs and
outputs in `doctor-ai-agent`.

Use it when changing:

- prompt text
- routing context assembly
- structuring context assembly
- memory/context compression
- any write path that depends on LLM output

This is a normative document. Reviews may discuss alternatives, but code changes
should follow this contract unless a new ADR explicitly changes it.

## Goals

- keep patient-binding and write decisions deterministic where possible
- separate authoritative state from advisory context
- prevent prompt/context drift from silently changing product behavior
- make prompt changes testable and reviewable

## Core Rules

### 1. Authoritative state is not advisory context

Authoritative state controls routing and persistence decisions. It must not be
cached as a stale hint or overridden by LLM interpretation.

Current authoritative state includes:

- current patient binding
- pending draft / pending record state
- active interview or specialist workflow state
- explicit session cursor state needed for confirmation or recovery

Advisory context includes:

- recent conversation history
- compressed long-term memory
- doctor knowledge snippets
- doctor profile / specialty hints

Advisory context may inform the LLM. It must not silently decide patient binding
or write-path approval.

### 2. Prompt quality cannot compensate for dirty context

If context assembly is wrong, prompt tuning is not the first-line fix.

Before expanding prompt rules, check:

- message roles
- context source ordering
- history trimming
- clinical-context filtering
- prompt-injection sanitization

### 3. The final doctor message is the only final `user` message for routing

Routing must preserve a clean distinction between:

- system instructions
- system-supplied context
- prior history
- the doctor's current input

Background knowledge must not be injected as fake doctor input.

### 4. LLM output is never permission to skip safety gates

LLM output may classify, extract, summarize, or draft.
It does not authorize:

- silent patient switching
- silent draft persistence
- destructive actions without explicit product rules
- treating advisory context as authoritative truth

## AI Surfaces

### Routing

Primary code:

- `services/ai/agent.py`
- `services/ai/turn_context.py`
- `services/knowledge/doctor_knowledge.py`

Purpose:

- classify current doctor intent
- extract tool-call parameters or fallback intent fields
- produce a safe, minimal routing result

Allowed inputs:

- routing system prompt
- current patient context
- candidate patient context
- recent patient-not-found context
- filtered / trimmed recent history
- doctor knowledge snippet
- current doctor message

Required role behavior:

- prompt and system-supplied context -> `system`
- preserved prior conversation -> original history roles
- current doctor turn -> final `user` message

Forbidden patterns:

- injecting knowledge or summaries as fake user messages
- letting compressed memory decide patient binding
- relying only on raw last-N history when higher-value context is available

### Structuring

Primary code:

- `services/domain/record_ops.py`
- `services/ai/structuring.py`

Purpose:

- convert clinical dictation or structured intent fields into a readable medical record

Allowed inputs:

- current clinical text
- filtered clinical-only recent history
- encounter type
- sanitized prior-visit summary for follow-up context

Forbidden patterns:

- mixing task commands, admin chatter, greetings, or record-query language into clinical input
- injecting unsanitized prior summaries or imported text blocks as trusted instructions
- treating structuring output as approval to persist without existing product gates

### Memory Compression

Primary code:

- `services/ai/memory.py`

Purpose:

- summarize longer-term conversational context into a compact advisory memory block

Contract:

- compression output is advisory only
- compression must not become the source of truth for current patient binding
- compression failures must prefer preserving raw context over silently truncating critical state

## Context Ordering Contract

When building routing messages, preserve this conceptual order:

1. system prompt
2. authoritative routing hints
3. advisory system context
4. trimmed prior conversation
5. current doctor message

Current examples of authoritative routing hints:

- current patient
- candidate patient
- recent patient-not-found context

Current examples of advisory system context:

- doctor knowledge snippet
- compressed memory summary

## Input Filtering Rules

### Routing history

Routing history should prefer information value over raw recency alone.

Minimum expectations:

- keep the most recent exchange
- preserve clarification turns when relevant
- preserve patient-binding turns when relevant
- preserve recent clinical decision context when relevant

### Structuring history

Structuring input should include only clinical turns.

Exclude:

- greetings
- task management commands
- patient list / record query commands
- admin and help chatter
- confirmation words that are not part of the clinical note

## Prompt Editing Rules

Prompt text is stored in `system_prompts`. Prompt edits are allowed, but they
must preserve the contract above.

When editing prompts:

1. Do not use prompts to redefine product safety policy that belongs in code.
2. Do not rely on prompts to infer authoritative state that the system already knows.
3. Keep routing prompts focused on intent/tool selection and clarification behavior.
4. Keep structuring prompts focused on faithful clinical normalization and extraction.
5. Preserve medical abbreviations and non-hallucination rules.

## Output Contract

### Routing output

Routing output may contain:

- intent
- patient name candidates
- structured fields
- chat reply
- confidence
- tool arguments / extra data

Routing output must not be treated as proof that:

- the patient match is correct
- the action is approved
- the note may bypass pending-draft flow

### Structuring output

Structuring output is derived data.

Current persistence contract:

- `medical_records.content` is the primary readable source of truth
- tags, specialty scores, or future structured payloads are derived support data
- if derived fields disagree with readable content, readable content wins unless a
  future ADR changes that rule

## Change Checklist

Use this checklist when changing AI behavior:

### Prompt-only change

- update or add direct unit tests for the affected prompt path
- run integration tests for the affected route
- run chatlog replay if routing or wording may materially shift

### Routing context change

- add direct tests for message order, roles, and trimming
- verify advisory context cannot override authoritative state
- run unit + integration coverage

### Structuring context change

- add direct tests for clinical-context filtering and prior-summary handling
- verify non-clinical text is excluded
- run unit + integration coverage

### Memory/compression change

- verify compressed output remains advisory
- add tests for failure handling and non-destructive fallback behavior

## Related Docs

- [Prompt Inventory](AI提示词文档.md)
- [Architecture Overview](../review/architecture-overview.md)
- [LLM Context Review and Plan](../review/03-11/llm-context-architecture-review-and-plan.md)
- [ADR Log](../adr/README.md)
