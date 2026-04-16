# Voice → Rule Extraction

You receive a Chinese voice-memo transcript from a specialist doctor. Your job is to extract AT MOST ONE clinical rule from the transcript and output strict JSON.

## Input

Transcript (ASR output, may contain filler words or minor ASR noise):
{{transcript}}

Doctor specialty (may be empty):
{{specialty}}

## Output

Return a single JSON object with this exact shape:

```json
{
  "content": "<rule text in Chinese>" | null,
  "category": "custom" | "diagnosis" | "followup" | "medication" | null,
  "error": null | "no_rule_found" | "multi_rule_detected"
}
```

On success: `content` is the rule, `category` is one of the four values, `error` is null.
On handled failure: `content` and `category` are null, `error` is one of the two error codes.

### Error codes

- `no_rule_found` — transcript is a story, general observation, or question with no extractable clinical rule.
- `multi_rule_detected` — transcript clearly contains TWO OR MORE distinct clinical rules. Do NOT silently pick one.

### Category guide

- `diagnosis` — rules for diagnosing/assessing conditions (e.g., "当 X 症状出现时，考虑 Y")
- `followup` — rules for follow-up schedules and monitoring (e.g., "术后 X 天复查 Y")
- `medication` — rules for drug choice, dosing, contraindications
- `custom` — anything else (patient communication style, red flags, operational rules)

## Few-shot examples

### Example 1: clean followup rule
Transcript: "前交通动脉瘤术后第二周要关注记忆问题"
Specialty: "神经外科"
Output:
```json
{
  "content": "前交通动脉瘤术后第二周关注患者记忆变化，复诊时询问近期记忆清晰度",
  "category": "followup",
  "error": null
}
```

### Example 2: diagnosis rule with drug context
Transcript: "嗯那个服用抗凝药的患者如果出现新发头痛加重要警惕脑出血"
Specialty: "神经外科"
Output:
```json
{
  "content": "服用抗凝药的患者出现新发头痛或头痛加重时，警惕脑出血，建议立即影像学检查",
  "category": "diagnosis",
  "error": null
}
```

### Example 3: medication rule
Transcript: "阿托伐他汀二十毫克晚上睡前吃"
Specialty: ""
Output:
```json
{
  "content": "阿托伐他汀 20mg 晚上睡前服用",
  "category": "medication",
  "error": null
}
```

### Example 4: long story, no rule
Transcript: "今天遇到一个很有意思的病例啊患者五十多岁男性来的时候就是说头痛我就觉得可能是..."
Specialty: "神经外科"
Output:
```json
{
  "content": null,
  "category": null,
  "error": "no_rule_found"
}
```

### Example 5: multi-rule memo
Transcript: "前交通术后两周看记忆，另外如果患者有高血压要控制收缩压在140以下"
Specialty: "神经外科"
Output:
```json
{
  "content": null,
  "category": null,
  "error": "multi_rule_detected"
}
```

### Example 6: ambiguous (short, barely a rule)
Transcript: "注意观察"
Specialty: ""
Output:
```json
{
  "content": null,
  "category": null,
  "error": "no_rule_found"
}
```

## Constraints

- Output ONLY the JSON object. No prose before or after. A ```json fence is fine; your response must contain no other text.
- `content` must be in Chinese, clinically precise, ≤500 characters.
- Filter out filler words ("嗯", "那个", "就是说") and ASR noise.
- If in doubt between extracting and rejecting, prefer `no_rule_found`.
- Do NOT invent content not present in the transcript.
