/no_think

## Task

分析医生对AI草稿的修改，判断修改类型（风格偏好 / 事实纠正 / 场景特定），并归类到对应的个性化字段；若为事实纠正，额外输出可复用的临床规则与分类。

## Input

<original_text>
{original}
</original_text>

<edited_text>
{edited}
</edited_text>

## Rules

### 类型判断（按此顺序检查）
1. **factual** — 医生纠正了医学事实（药名、剂量、检查项目、诊断、治疗方案）。输出 kb_category + proposed_kb_rule
2. **context_specific** — 修改仅适用于该特定患者的情况（如针对某患者的特殊叮嘱、个体化用药调整）
3. **style** — 医生改变了语气、称呼、结构、删除/增加了某类内容。输出 persona_field

### 字段归类（仅 type=style 时必填）
4. **reply_style** — 语气/称呼/正式程度的变化
5. **closing** — 结尾用语/随访叮嘱的改变
6. **structure** — 内容组织方式的改变
7. **avoid** — 删除某类内容
8. **edits** — 语言修辞习惯
9. type=factual 或 type=context_specific 时，persona_field 填 ""

### KB 分类（仅 type=factual 时必填）
10. **diagnosis** — 诊断逻辑、鉴别要点、红旗识别
11. **medication** — 药物选择、剂量、禁忌
12. **followup** — 随访时间、复查频率、监测指标
13. **custom** — 不在上面三类中的临床规则
14. type 非 factual 时，kb_category 填 "" 且 proposed_kb_rule 填 ""

### proposed_kb_rule 要求（type=factual 时）
15. 必须是去情境化的通用规则（不带患者姓名、日期、具体病情细节）
16. 长度 ≤ 300 字符，中文
17. 完整自包含（读者不需要看 original/edited 就能理解）
18. 不得包含 PII（姓名、手机号、身份证号、住院号、具体日期）

### confidence 定义
19. **high** — 修改模式非常明确：删除整段、系统性改变称呼、统一缩短所有句子
20. **medium** — 有一定规律但不完全确定
21. **low** — 修改很小或意图模糊

### summary 要求
22. summary 必须是结构性描述，描述修改**模式**而非具体内容
23. summary 中不得包含患者姓名、日期、具体病情等个人信息

## Output

输出 JSON，不要输出其他内容：

```
{{"type": "style|factual|context_specific", "persona_field": "reply_style|closing|structure|avoid|edits|", "summary": "一句话结构性描述", "confidence": "low|medium|high", "kb_category": "diagnosis|medication|followup|custom|", "proposed_kb_rule": "去情境化临床规则或空字符串"}}
```

- 所有 JSON key 使用英文
- 不使用 null — 空值用 ""
- proposed_kb_rule 为 "" 时，kb_category 也必须为 ""

## Constraints

- 只输出 JSON，不要解释推理过程
- type 只能是 style / factual / context_specific 三选一
- persona_field 只能是 reply_style / closing / structure / avoid / edits / ""
- kb_category 只能是 diagnosis / medication / followup / custom / ""
- confidence 只能是 low / medium / high 三选一
- 不得在 summary / proposed_kb_rule 中泄露患者个人信息

## Examples

**示例1：风格修改 — 删除结尾祝福语（高置信度）**

<original_text>
张阿姨您好，您的血压控制得不错，继续目前的用药方案即可。建议每周测量血压2-3次并记录。祝您身体健康，早日康复！
</original_text>

<edited_text>
张阿姨你好，血压还行，继续吃药就好。每周量2-3次血压记录下。
</edited_text>

→ {{"type": "style", "persona_field": "closing", "summary": "删除结尾祝福语，整体语气改为口语化简短风格", "confidence": "high", "kb_category": "", "proposed_kb_rule": ""}}

**示例2：事实纠正 — 修改药物名称**

<original_text>
建议继续服用氨氯地平控制血压，同时注意低盐饮食。
</original_text>

<edited_text>
建议继续服用硝苯地平控制血压，同时注意低盐饮食。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "纠正了降压药名称（氨氯地平→硝苯地平）", "confidence": "high", "kb_category": "medication", "proposed_kb_rule": "对本医生而言，该类高血压患者首选硝苯地平而非氨氯地平控制血压"}}

**示例3：场景特定 — 针对特定患者的调整**

<original_text>
术后请注意伤口护理，按时换药，有异常及时就诊。
</original_text>

<edited_text>
术后请注意伤口护理，按时换药，有异常及时就诊。因为您有糖尿病，伤口愈合可能较慢，请特别注意血糖控制。
</edited_text>

→ {{"type": "context_specific", "persona_field": "", "summary": "针对患者合并症添加了个体化叮嘱", "confidence": "high", "kb_category": "", "proposed_kb_rule": ""}}

**示例4：风格修改 — 调整回复结构（中等置信度）**

<original_text>
您的检查结果显示甲状腺功能正常，TSH和T3T4均在正常范围内。甲状腺超声也未见明显异常。综合来看，目前不需要特殊处理，建议半年后复查。
</original_text>

<edited_text>
结论：甲状腺没问题，半年后复查。

检查结果：TSH、T3T4正常，超声未见异常。
</edited_text>

→ {{"type": "style", "persona_field": "structure", "summary": "将回复改为结论前置的结构，先给结论再列支持数据", "confidence": "medium", "kb_category": "", "proposed_kb_rule": ""}}

**示例5：微小修改 — 意图模糊（低置信度）**

<original_text>
建议您近期复查一下血常规。
</original_text>

<edited_text>
建议近期复查血常规。
</edited_text>

→ {{"type": "style", "persona_field": "edits", "summary": "删除了冗余的'您'和'一下'", "confidence": "low", "kb_category": "", "proposed_kb_rule": ""}}

**示例6：事实纠正 — 诊断条件修正**

<original_text>
颅脑术后头痛患者可以使用布洛芬止痛。
</original_text>

<edited_text>
颅脑术后头痛患者在排除脑脊液漏之前不建议使用NSAIDs，首选对乙酰氨基酚。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了颅脑术后头痛的止痛药选择", "confidence": "high", "kb_category": "diagnosis", "proposed_kb_rule": "颅脑术后头痛患者在排除脑脊液漏之前不建议使用 NSAIDs（包括布洛芬），首选对乙酰氨基酚"}}

**示例7：事实纠正 — 随访时间调整**

<original_text>
颅内动脉瘤夹闭术后3个月复查CTA即可。
</original_text>

<edited_text>
颅内动脉瘤夹闭术后2周首次复查CTA，之后3个月、1年各复查一次。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了动脉瘤夹闭术后的复查时点", "confidence": "high", "kb_category": "followup", "proposed_kb_rule": "颅内动脉瘤夹闭术后首次 CTA 复查时间为术后 2 周，而非 3 个月；之后分别在 3 个月、1 年复查"}}

**示例8：事实纠正 — 药物联用禁忌**

<original_text>
血压仍偏高，可以加用ARB类药物联合治疗。
</original_text>

<edited_text>
患者已在用ACEI，不要联用ARB，可换为钙通道阻滞剂。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "纠正了 ACEI 与 ARB 的联用建议", "confidence": "high", "kb_category": "medication", "proposed_kb_rule": "ACEI 与 ARB 不可联用；已使用 ACEI 的患者血压控制不佳时，优先加用钙通道阻滞剂"}}

**示例9：事实纠正 — 通用临床规则**

<original_text>
糖尿病患者伤口一般一周愈合。
</original_text>

<edited_text>
糖尿病患者伤口愈合较慢，需要额外 1-2 周观察，并严格控制血糖在 7 mmol/L 以下。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "修正了糖尿病患者伤口愈合预估", "confidence": "high", "kb_category": "custom", "proposed_kb_rule": "糖尿病患者伤口愈合较非糖尿病患者慢 1-2 周，期间需严格控制血糖在 7 mmol/L 以下"}}
