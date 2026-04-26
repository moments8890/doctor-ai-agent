# LLM Prompting Guide — Doctor AI Agent

> Internal reference for writing, editing, and reviewing LLM prompts in this
> project. Synthesized from Anthropic, OpenAI, and Google prompt engineering
> guides, adapted to our 6-layer prompt stack, Chinese-language medical domain,
> and Qwen/DeepSeek model family.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Universal Principles](#2-universal-principles)
3. [Structural Patterns](#3-structural-patterns)
4. [Output Control](#4-output-control)
5. [Few-Shot Examples](#5-few-shot-examples)
6. [Medical Domain Rules](#6-medical-domain-rules)
7. [Conversation vs Single-Turn](#7-conversation-vs-single-turn)
8. [Extraction Prompts (Pattern C)](#8-extraction-prompts-pattern-c)
9. [Thinking & Reasoning](#9-thinking--reasoning)
10. [Safety & Guardrails](#10-safety--guardrails)
11. [Testing & Iteration](#11-testing--iteration)
12. [Anti-Patterns](#12-anti-patterns)
13. [Prompt Checklist](#13-prompt-checklist)
14. [Quick Reference Card](#14-quick-reference-card)

---

## 1. Architecture Overview

### The 6-Layer Prompt Stack

Every LLM call in this project is assembled by `prompt_composer.py` from up to
6 layers. Understanding the layers is prerequisite to writing good prompts.

```
L1 Identity      — common/base.md      Role, safety, precedence, date     [system]
L2 Specialty     — domain/{spec}.md    Domain knowledge (neurology)       [system]
L3 Task          — intent/{intent}.md  Action-specific rules + format     [system]
L4 Doctor Rules  — DB (auto-loaded)    User-authored KB, scored           [user/system]
L5 Case Memory   — DB (diagnosis only) Similar past confirmed decisions   [system]
L6 Patient       — DB (per-request)    Records, demographics, state       [user/system]
L7 Input         — user message        Actual doctor/patient input        [user]
```

### Three Composition Patterns

| Pattern | When Used | Layer Placement |
|---------|-----------|-----------------|
| **A — Single-Turn** | routing, query, general, diagnosis | L1-L3 → system; L4-L7 → user with XML tags |
| **B — Conversation** | intake, patient-intake | L1-L6 → system; history turns; L7 Input → plain user |
| **C — Direct** | doctor-extract, patient-extract, vision-ocr | Standalone template with `{variables}`, no composer |

### File Locations

```
src/agent/prompts/
  common/base.md          ← L1 Identity (universal)
  domain/neurology.md     ← L2 Specialty
  intent/
    routing.md            ← Intent classification
    intake.md          ← Doctor-side record creation
    patient-intake.md  ← Patient pre-consultation
    query.md              ← Query result formatting
    general.md            ← Small talk, greetings
    diagnosis.md          ← Differential diagnosis pipeline
    doctor-extract.md     ← Structured extraction (doctor)
    patient-extract.md    ← Structured extraction (patient)
    vision-ocr.md         ← Image → text extraction
```

---

## 2. Universal Principles

These principles apply to **every prompt** in the project, regardless of pattern
or intent.

### 2.1 Be Explicit and Direct

Models respond best to clear, unambiguous instructions. Never rely on inference
when you can state what you want directly.

```markdown
# Bad
尽量详细地回复。

# Good
生成鉴别诊断，最多5个，按 confidence 从高到低排列。每项包含 condition、
confidence（高/中/低）和 detail（2-4句，先写临床依据再写通俗解释）。
```

**Why this matters for medical prompts:** Ambiguity in medical contexts can lead
to hallucinated diagnoses or fabricated patient data. Explicit constraints
prevent this.

### 2.2 Explain the Why, Not Just the What

Providing motivation behind a rule helps the model generalize correctly to edge
cases.

```markdown
# Bad
保留医学缩写原样。

# Good
保留医学缩写原样：STEMI、BNP、EF、CT、MRI 等。
原因：缩写是标准化的医学术语，改写会降低准确性，且医生习惯使用缩写快速阅读。
```

### 2.3 Numbered Priority + Sequential Steps

When order matters, use numbered lists. When rules conflict, explicit priority
resolves ambiguity.

```markdown
## 判断顺序（严格按此优先级执行）
1. create_record — 最高优先级
2. create_task
3. query_record
...
```

Our `common/base.md` already sets global precedence:
1. Safety rules (highest)
2. Intent instructions
3. Doctor knowledge base
4. Patient data (when conflicting with KB)

### 2.4 One Prompt, One Job

Each prompt file in `intent/` handles exactly one intent type. Avoid cramming
multiple responsibilities into a single prompt. If a new capability needs
different instructions, create a new intent file and add a `LayerConfig`.

---

## 3. Structural Patterns

### 3.1 Use XML Tags for Variable Content

XML tags are the **primary structural mechanism** for passing dynamic data to the
model. They prevent the model from confusing instructions with data.

**In Pattern A (single-turn)**, the composer wraps dynamic layers in XML:

```xml
<doctor_knowledge>
{KB items loaded from database}
</doctor_knowledge>

<patient_context>
{patient records, demographics}
</patient_context>

<doctor_request>
{the actual doctor message}
</doctor_request>
```

**When writing new prompts that need variable injection**, use XML tags:

```xml
<patient_records>
{records}
</patient_records>

<similar_cases>
{reference cases from KB}
</similar_cases>
```

**Rules for XML tags in this project:**
- Use lowercase_snake_case for tag names
- Use consistent tags across prompts (don't mix `<patient_data>` and
  `<patient_context>`)
- Nest when there's natural hierarchy:
  ```xml
  <documents>
    <document index="1">
      <source>CT_report.pdf</source>
      <content>...</content>
    </document>
  </documents>
  ```

### 3.2 Markdown Headers for Prompt Sections

All our prompt files use Markdown headers to organize sections:

```markdown
# Role: 医生AI临床助手

## Profile
## Task
## Rules
## Constraints
## Examples
## Workflow
```

**Standard section order for intent prompts:**

| Section | Purpose | Required |
|---------|---------|----------|
| `# Role` | Identity and persona | Yes |
| `## Profile` | Description, language, style | Yes |
| `## Task` | What the model should do | Yes |
| `## Rules` | Numbered behavioral rules | Yes |
| `## Constraints` | Hard boundaries (safety, format) | Yes |
| `## Examples` | Input/output pairs | Strongly recommended |
| `## Workflow` | Step-by-step execution flow | For complex prompts |
| `## Init` | First-turn behavior | For conversation prompts |

### 3.3 Role Assignment

Every prompt begins by assigning a role. This focuses the model's behavior and
establishes the domain.

```markdown
# Role: 医生AI临床助手

## Profile
- 定位：主治医生的智能临床工具，所有操作均在医生授权下进行
- 不独立提供医疗建议，不替代医生判断
- 语言：中文
- 风格：专业、简洁、循证
```

**Role design principles:**
- Specify the relationship to the user ("医生的工具", not "医生的替代")
- Include language and tone ("专业、简洁、循证")
- State what the role is **not** ("不独立提供医疗建议")

---

## 4. Output Control

### 4.1 JSON Output Specification

Most prompts in this project require JSON output. Be explicit about the schema.

**Good pattern (from `routing.md`):**

```markdown
输出：{"intent": "create_record", "patient_name": "赵强",
       "params": {"gender": "男", "age": 61}, "deferred": null}
```

**Better pattern (from `diagnosis.md`):**

```markdown
## Constraints
- 四个顶层 key 必须始终存在：differentials, workup, treatment, signal_flags
- 无内容时返回 []
- 所有 JSON key 使用英文，所有值使用中文；不使用 null
```

**Rules for JSON output in this project:**
1. Show the complete JSON schema in constraints, not just examples
2. Specify what to do when fields are empty (`[]` vs `""` vs omit)
3. Keys in English, values in Chinese (our standard)
4. State whether `null` is allowed (we generally prefer `""` or `[]`)

### 4.2 Tell the Model What TO Do

```markdown
# Bad (negative instruction)
不要在回复中使用 Markdown 表格。

# Good (positive instruction)
用自然语言描述查询结果，按时间倒序排列。突出诊断和治疗方案。
```

### 4.3 Control Response Length

For conversation prompts (Pattern B), specify length constraints:

```markdown
每次 2-3 句话        ← patient-intake.md
简单一句话确认       ← intake.md (nurse-like brevity)
2-4句话             ← diagnosis.md detail field
```

For extraction prompts (Pattern C), length is implicit — the output is
structured JSON, not prose.

### 4.4 Use the `/no_think` Directive

For extraction prompts where reasoning adds latency without value, prefix with
`/no_think` to suppress chain-of-thought:

```markdown
/no_think
你是一位病历整理专家。请根据以下医生录入内容...
```

We use this in `doctor-extract.md` and `patient-extract.md` because these are
pure extraction tasks — the model doesn't need to reason about the input, just
categorize it.

**When to use `/no_think`:**
- Extraction tasks (text → structured JSON)
- OCR post-processing
- Simple classification where examples are sufficient

**When NOT to use `/no_think`:**
- Diagnosis generation (requires clinical reasoning)
- Patient intakes (requires conversational planning)
- Complex queries (requires multi-step reasoning)

---

## 5. Few-Shot Examples

### 5.1 Why Examples Are Critical

Examples are the **single most effective** technique for steering LLM output
format, tone, and accuracy. Our medical domain makes this especially important
because:

- Medical terminology has precise meanings
- JSON schema compliance needs to be exact
- Edge cases (empty input, contradictory info, OCR noise) are common

### 5.2 Example Design Rules

**Include 3-5 examples per prompt** covering:

| Coverage Type | Purpose | Example |
|---------------|---------|---------|
| **Happy path** | Standard input | "张三，男55岁，头痛两周" |
| **Edge case** | Empty/minimal input | "头痛"（no demographics） |
| **Noise handling** | Irrelevant content | Filtering AI responses, greetings |
| **Correction** | Contradictory input | Doctor corrects previous statement |
| **Boundary** | Ambiguous intent | "王芳来复诊了"（query or create?) |

**Example structure (from our codebase):**

```markdown
## 示例

**示例1：标准门诊多轮对话**

对话记录：
医生：张三，男55岁，头痛两周加重三天。
AI助手：好的，记录了主诉信息。
医生：伴恶心呕吐，无发热...

→ {"chief_complaint": "头痛2周，加重3天", ...}

**示例2：重复信息去重**
...（第二次提到hs-cTnI为重复，只保留首次）

**示例3：过滤闲聊和AI回复**
...（忽略问候和AI回复）

**示例4：医生纠正之前的信息**
...（血压以纠正后的150/90为准）

**示例5：单段口述电报式录入**
...（所有信息在一段中，按内容归类）
```

### 5.3 Example Anti-Patterns

- **Too similar:** 5 examples of the same pattern teach nothing new
- **Too clean:** Real input has typos, abbreviations, mixed Chinese/English
- **Missing explanation:** Add parenthetical notes explaining the reasoning:
  `（第二次提到hs-cTnI为重复，只保留首次完整版本）`
- **Examples contradict rules:** Review examples against your rules section

### 5.4 Diverse Input Formats

Our prompts handle diverse input formats. Examples should cover all of them:

```
- Multi-turn dialogue (医生 → AI → 医生 → ...)
- Single-paragraph dictation ("刘芳 女 62 心内科 胸痛4h...")
- Template paste (structured forms from EMR)
- OCR text (noisy, possibly garbled)
- Voice transcription (filler words: "嗯", "那个", "就是说")
```

---

## 6. Medical Domain Rules

### 6.1 Terminology Preservation

```markdown
保留医学缩写原样：STEMI、BNP、EF、CT、MRI 等
```

This is a project-wide rule from `common/base.md`. Never instruct the model to
expand or translate medical abbreviations.

### 6.2 No Fabrication Rule

The most critical safety constraint across all prompts:

```markdown
- 绝不编造病历数据或患者信息
- 绝不猜测患者姓名
- AI建议仅供参考，最终诊断由医生决定
```

**Apply this rule in every prompt that touches patient data.** The `diagnosis.md`
prompt extends it:

```markdown
- 严禁虚构：不得编造检查结果、体征发现或病史
- 类似病例参考仅用于提示方向，不得将参考病例事实当作当前患者事实
```

### 6.3 Synonym Mapping

Standardize common patient expressions:

```markdown
同义词映射：
- "没有" / "未发现" / "未见" → "无"
- "不知道" / "不清楚" / "不确定" → "不详"
```

### 6.4 Confidence and Urgency Definitions

For diagnostic prompts, always define your rating scales explicitly:

```markdown
**confidence 定义**
- 高 = 患者提供的事实直接支持该诊断
- 中 = 有部分支持但信息不完整
- 低 = 不能排除但现有证据支持弱

**urgency 定义（workup）**
- 急诊 = 需立即急诊评估（分钟级）
- 紧急 = 当日内完成（小时级）
- 常规 = 门诊常规安排（天/周级）
```

**Why explicit definitions matter:** Without them, models use their own
heuristics for "高/中/低", which drift across calls. Definitions anchor the
scale.

### 6.5 Handling Insufficient Information

Every prompt that generates clinical content must specify how to handle missing
data:

```markdown
信息不足时：
- 降低 confidence
- 保持鉴别诊断宽泛
- workup 保留必要项
- treatment 返回 []
- 不虚构危险信号，signal_flags 返回 []
```

---

## 7. Conversation vs Single-Turn

### 7.1 Pattern A — Single-Turn

Used for: routing, query, general, diagnosis, create_task

```
system: [L1 Identity + L2 Specialty + L3 Task]
user:   <doctor_knowledge>...</doctor_knowledge>
        <patient_context>...</patient_context>
        <doctor_request>...</doctor_request>
```

**Prompt writing rules for Pattern A:**
- Intent prompt is self-contained — no state from previous turns
- All context arrives via XML tags in the user message
- Output is a single JSON response

### 7.2 Pattern B — Conversation

Used for: intake (create_record), patient-intake

```
system: [L1 Identity + L2 Specialty + L3 Task + L4 Doctor Rules + L6 Patient]
user/assistant: [conversation history]
user:   [latest message — plain text, no XML]
```

**Prompt writing rules for Pattern B:**
- KB and patient context go into the system message (not user)
- History turns are injected between system and the latest user message
- The latest user message is plain text — no wrapping
- State accumulates across turns (e.g., `present_illness` appends, not
  overwrites)
- Include a `## Init` section defining first-turn behavior

**Conversation-specific rules to include:**

```markdown
### 对话规则
1. 每次先回应患者/医生，再提问
2. 不在回复中复述已收集的信息
3. present_illness 多轮累积（追加，不覆盖，避免重复）
```

### 7.3 Pattern C — Direct (No Composer)

Used for: doctor-extract, patient-extract, vision-ocr

These prompts bypass the composer. The calling code loads the template directly
and substitutes `{variables}`.

```markdown
/no_think
你是一位病历整理专家。请根据以下医生录入内容...

## 患者信息
{name}，{gender}，{age}岁

## 医生录入内容
{transcript}
```

**Prompt writing rules for Pattern C:**
- Use `{variable}` placeholders (not `{{double_brace}}`)
- Always prefix with `/no_think` for extraction tasks
- The prompt is the **entire message** — no layer composition
- Include `common/base.md` content as a system message prefix separately
  (handled by calling code)

---

## 8. Extraction Prompts (Pattern C)

Extraction prompts are the workhorses of the project. They convert unstructured
clinical text into structured JSON. Special rules apply.

### 8.1 Field Definitions

List every field with a brief description and classification guide:

```markdown
## 可用字段及归类指引
- chief_complaint: 主诉（≤20字，促使就诊的主要问题+时间）
- present_illness: 现病史（起病经过、症状演变、诊疗经过）
- past_history: 既往病史、手术史、用药史
- allergy_history: 过敏史（药物/食物）
...
```

### 8.2 Deduplication Rules

Real clinical input contains repetition. Always include dedup rules:

```markdown
- 如果同一信息在多轮中重复出现，只保留最完整的一次
- 同一字段前后矛盾 → 以最后一次表述为准
```

### 8.3 Noise Filtering

Voice transcription and OCR produce noise. Include specific filters:

```markdown
- 过滤语音转写噪音词（"嗯""呃""那个""就是说"等）
- 不要从AI助手的回复中提取信息
- 语音转写不清 → 原样保留，无法辨认标注[?]
```

### 8.4 Abnormal Input Handling

Always define behavior for edge cases:

```markdown
## 异常处理
- 空输入或全是闲聊 → 所有字段返回空字符串
- 同一字段前后矛盾 → 以最后一次表述为准
- 语音转写不清 → 原样保留，无法辨认的部分标注[?]
- 信息不足 → 提取已有内容，不要补充猜测
```

---

## 9. Thinking & Reasoning

### 9.1 When to Enable Thinking

| Prompt | Thinking | Reason |
|--------|----------|--------|
| routing.md | Off (fast) | Simple classification, examples sufficient |
| doctor-extract.md | Off (`/no_think`) | Pure extraction, no reasoning needed |
| patient-extract.md | Off (`/no_think`) | Pure extraction |
| vision-ocr.md | Off | OCR transcription, no reasoning |
| intake.md | Light | Needs to plan next question |
| patient-intake.md | Light | Needs conversational planning |
| diagnosis.md | On | Clinical reasoning, differential diagnosis |
| general.md | Off | Simple responses |
| query.md | Off | Formatting results |

### 9.2 Guiding Reasoning (When Thinking Is On)

For prompts where reasoning matters (like `diagnosis.md`), structure the
workflow explicitly:

```markdown
## Workflow
接收病历数据 → 逐字段提取患者事实 → 生成鉴别诊断、检查建议、治疗方向、危险信号
```

For more complex reasoning, break it into explicit steps:

```markdown
## 推理步骤
1. 提取当前病历中的关键事实（症状、体征、检查结果）
2. 逐一评估每个可能的诊断
3. 对每个诊断评估 confidence（高/中/低）
4. 生成对应的检查建议和治疗方向
5. 识别需要立即处理的危险信号
```

### 9.3 Self-Verification Prompts

For high-stakes outputs, add a verification step:

```markdown
输出前检查：
- 每个 differential 的 detail 是否引用了患者本次就诊的具体事实？
- confidence 是否有区分度（不全是"高"）？
- signal_flags 非空时 workup 是否有紧急/急诊项？
```

---

## 10. Safety & Guardrails

### 10.1 The Precedence Hierarchy

From `common/base.md` — this is the project's master safety rule:

```
1. 遵守安全规则（最高优先级）
2. 遵守意图指令（intent instructions）
3. 参考医生知识库，但不优先于实际病历数据
4. 如果相似病例与当前病历数据冲突，以当前病历为准
```

Every new prompt must be compatible with this hierarchy.

### 10.2 Safety Rules for All Prompts

Include in every prompt that touches patient data:

```markdown
- 绝不编造病历数据或患者信息
- 绝不猜测患者姓名（must come from doctor's message）
- AI建议仅供参考，最终诊断由医生决定
```

### 10.3 Patient-Facing Safety

For patient-facing prompts (`patient-intake.md`):

```markdown
1. 所有症状均按常规病史采集流程处理，不做紧急分诊判断
2. 不独立提供医疗建议，不做诊断
3. 不捏造信息；未经患者确认不填入字段
```

### 10.4 Knowledge Base Safety

When the prompt includes KB data (L4 Doctor Rules):

```markdown
- 知识库仅供参考，不优先于当前病历事实
- 类似病例参考仅用于提示方向
- 不得将参考病例事实当作当前患者事实
```

---

## 11. Testing & Iteration

### 11.1 Prompt Regression Tests

All prompts have wrapper copies in `tests/prompts/wrappers/` for regression
testing. When editing a prompt:

1. Edit the source in `src/agent/prompts/intent/`
2. Run regression tests to verify no behavioral change
3. Update wrappers if the change is intentional

### 11.2 Evaluation Dimensions

Test each prompt change against these dimensions:

| Dimension | What to Check |
|-----------|---------------|
| **Format compliance** | Does output match JSON schema exactly? |
| **Field accuracy** | Are extracted fields correct and complete? |
| **Deduplication** | Is repeated info properly deduplicated? |
| **Safety** | Does the model refuse to fabricate? |
| **Edge cases** | Empty input, contradictory info, off-topic |
| **Terminology** | Are medical abbreviations preserved? |
| **Tone** | Professional for doctors, warm for patients? |

### 11.3 A/B Testing Prompt Changes

When making non-trivial prompt changes:

1. Prepare 10-20 test inputs covering happy paths and edge cases
2. Run both old and new prompts against the same inputs
3. Compare outputs side-by-side
4. Check for regressions in any of the evaluation dimensions above
5. **Show diff and get user approval before committing** (per project policy)

### 11.4 Common Failure Modes

| Failure | Symptom | Fix |
|---------|---------|-----|
| Schema drift | Extra keys, missing keys in JSON | Add explicit schema in constraints |
| Hallucination | Fabricated exam results | Strengthen no-fabrication rules + add negative example |
| Over-extraction | Extracting info from AI responses | Add "不要从AI助手的回复中提取信息" |
| Under-extraction | Missing info from patient message | Add more diverse examples |
| Tone mismatch | Medical jargon in patient prompts | Add "使用日常语言，不使用医学术语" |
| Priority confusion | Wrong intent classification | Add more boundary examples + strengthen priority rules |

---

## 12. Anti-Patterns

### Things to Avoid in Prompt Files

| Anti-Pattern | Why It's Bad | Do This Instead |
|---|---|---|
| Vague instructions ("尽量做好") | No measurable criteria | Specify exact constraints |
| Negative-only rules ("不要做X") | Doesn't tell model what TO do | "Do X instead of Y" |
| Duplicating base.md rules | Maintenance burden, conflicts | Reference layer 1 |
| Giant monolithic prompts | Hard to test, debug, iterate | One intent per file |
| Examples without explanation | Model copies pattern without understanding | Add parenthetical reasoning |
| Overly detailed step-by-step | Models reason better with general guidance | State goal + constraints |
| Instructions in user message | Confused with data | Instructions in system, data in user |
| Mixed language keys | Inconsistent parsing | Keys in English, values in Chinese |
| Using `null` in JSON output | Inconsistent across models | Use `""` or `[]` |
| Temperature/model in prompt | These are API parameters | Set in code, not prompt |

### Things to Avoid in Prompt Composition

| Anti-Pattern | Why It's Bad | Do This Instead |
|---|---|---|
| Hardcoding KB in prompt file | Stale data, can't personalize | Use L4 Doctor Rules (auto-loaded from DB) |
| Putting patient data in system msg (Pattern A) | Violates layer separation | Use XML tags in user message |
| String concatenation for messages | Injection risk, fragile | Use `compose_messages()` |
| Skipping `_inject_date()` | `{current_date}` appears literally | Always go through composer |

---

## 13. Prompt Checklist

Use this checklist when writing or reviewing any prompt.

### Structure
- [ ] Starts with `# Role` and `## Profile` (identity, language, style)
- [ ] Has a clear `## Task` section
- [ ] Rules are numbered and prioritized
- [ ] Constraints are explicit (not implied)
- [ ] Uses Markdown headers for sections
- [ ] Uses XML tags for variable/dynamic content

### Content
- [ ] Includes 3-5 diverse examples (happy path + edge cases)
- [ ] Examples include parenthetical explanations
- [ ] Specifies output format (JSON schema, field definitions)
- [ ] Defines behavior for empty/missing/invalid input
- [ ] Includes synonym mapping where relevant
- [ ] Medical abbreviations preservation rule included

### Safety
- [ ] No-fabrication rule present
- [ ] Patient name extraction rule (from doctor's words only)
- [ ] "AI建议仅供参考" included for diagnostic content
- [ ] Compatible with `common/base.md` precedence hierarchy

### Integration
- [ ] Added to `prompt_config.py` with correct `LayerConfig`
- [ ] Layer placement is correct (system vs user)
- [ ] `{current_date}` placeholder if date-sensitive
- [ ] Template variables documented if Pattern C
- [ ] Regression test wrapper created in `tests/prompts/wrappers/`

---

## 14. Quick Reference Card

### Prompt Template (New Intent)

```markdown
# Role: 医生AI临床助手

## Profile
- 定位：{role description}
- 语言：中文
- 风格：{style}

## Task
{what the model should do}

## Rules
1. {numbered rules in priority order}
2. ...

## Constraints
- {hard boundaries}
- 所有 JSON key 使用英文，所有值使用中文
- {output schema specification}

## Examples

**示例1：{happy path}**
输入：...
输出：...

**示例2：{edge case}**
输入：...
输出：...
（解释）

**示例3：{error handling}**
输入：...
输出：...

## Workflow
{input} → {step 1} → {step 2} → {output}
```

### LayerConfig Template (New Intent)

```python
IntentType.new_intent: LayerConfig(
    system=True,          # Include common/base.md (almost always True)
    domain=False,         # Include domain/{specialty}.md
    intent="new-intent",  # Maps to intent/new-intent.md
    knowledge_categories=[KnowledgeCategory.custom],
    patient_context=False,
    conversation_mode=False,
),
```

### Industry Sources

This guide synthesizes best practices from:

- **Anthropic** — Prompt engineering best practices (2025): clarity, XML tags,
  examples, role prompting, thinking control, output formatting
- **OpenAI** — Prompt engineering guide: task decomposition, reference text,
  systematic testing, giving the model time to think
- **Google** — Gemini prompting strategies: few-shot examples, structured output,
  parameter optimization, prompt decomposition

---

*Last updated: 2026-03-27*
