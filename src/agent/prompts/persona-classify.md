/no_think

## Task

分析医生对AI草稿的修改，判断修改类型（风格偏好 / 事实纠正 / 场景特定），并归类到对应的个性化字段。
目的：将医生的风格偏好自动学习为个性化规则，提升后续AI草稿的匹配度。

## Input

<original_text>
{original}
</original_text>

<edited_text>
{edited}
</edited_text>

## Rules

### 类型判断（按此顺序检查）
1. **factual** — 医生纠正了医学事实（药名、剂量、检查项目、诊断、治疗方案）。原因：事实纠正不应学习为风格规则，否则会污染个性化模型
2. **context_specific** — 修改仅适用于该特定患者的情况（如针对某患者的特殊叮嘱、个体化用药调整）。原因：个体化修改不具有泛化价值，不应提取为通用规则
3. **style** — 医生改变了语气、称呼、结构、删除/增加了某类内容。原因：这类修改反映医生的沟通偏好，应学习为个性化规则

### 字段归类（仅 type=style 时必填）
4. **reply_style** — 语气/称呼/正式程度的变化（如：把"您"改成"你"，删除敬语，加口语化表达）
5. **closing** — 结尾用语/随访叮嘱的改变（如：删除"祝您早日康复"，改为"有问题随时来"）
6. **structure** — 内容组织方式的改变（如：把详细解释删到一句话，调整段落顺序，先给结论再解释）
7. **avoid** — 删除某类内容（如：删除所有用药提醒，删除情绪安抚语句，去掉注意事项列表）
8. **edits** — 语言修辞习惯（如：缩短长句，去掉感叹号，医学术语替代通俗说法）
9. type=factual 或 type=context_specific 时，persona_field 填 ""

### confidence 定义
10. **high** — 修改模式非常明确：删除整段、系统性改变称呼、统一缩短所有句子。原因：明确模式可直接生成规则
11. **medium** — 有一定规律但不完全确定：改了部分表述但保留了其他类似表述
12. **low** — 修改很小或意图模糊：改了个别词、无法确定是有意还是随手修改

### summary 要求
13. summary 必须是结构性描述，描述修改**模式**而非具体内容（如"删除了结尾的祝福语"而非"删除了祝您早日康复"）
14. summary 中不得包含患者姓名、日期、具体病情等个人信息。原因：summary 会被存储为通用规则模板

## Output

输出 JSON，不要输出其他内容：

```
{{"type": "style/factual/context_specific", "persona_field": "reply_style/closing/structure/avoid/edits/（空字符串）", "summary": "一句话结构性描述", "confidence": "low/medium/high"}}
```

- 所有 JSON key 使用英文，所有值使用中文或英文枚举值
- 不使用 null，persona_field 无值时用 ""

## Constraints

- 只输出 JSON，不要解释推理过程
- type 只能是 style / factual / context_specific 三选一
- persona_field 只能是 reply_style / closing / structure / avoid / edits / ""
- confidence 只能是 low / medium / high 三选一
- 不得在 summary 中泄露患者个人信息

## Examples

**示例1：风格修改 — 删除结尾祝福语（高置信度）**

<original_text>
张阿姨您好，您的血压控制得不错，继续目前的用药方案即可。建议每周测量血压2-3次并记录。祝您身体健康，早日康复！
</original_text>

<edited_text>
张阿姨你好，血压还行，继续吃药就好。每周量2-3次血压记录下。
</edited_text>

→ {{"type": "style", "persona_field": "closing", "summary": "删除结尾祝福语，整体语气改为口语化简短风格", "confidence": "high"}}
（删除了整段祝福、把"您"改成"你"、多处缩短 — 模式明确，高置信度）

**示例2：事实纠正 — 修改药物名称**

<original_text>
建议继续服用氨氯地平控制血压，同时注意低盐饮食。
</original_text>

<edited_text>
建议继续服用硝苯地平控制血压，同时注意低盐饮食。
</edited_text>

→ {{"type": "factual", "persona_field": "", "summary": "纠正了降压药名称", "confidence": "high"}}
（只改了药名，属于医学事实纠正，不是风格偏好）

**示例3：场景特定 — 针对特定患者的调整**

<original_text>
术后请注意伤口护理，按时换药，有异常及时就诊。
</original_text>

<edited_text>
术后请注意伤口护理，按时换药，有异常及时就诊。因为您有糖尿病，伤口愈合可能较慢，请特别注意血糖控制。
</edited_text>

→ {{"type": "context_specific", "persona_field": "", "summary": "针对患者合并症添加了个体化叮嘱", "confidence": "high"}}
（添加的内容仅适用于该患者的糖尿病情况，不具有泛化价值）

**示例4：风格修改 — 调整回复结构（中等置信度）**

<original_text>
您的检查结果显示甲状腺功能正常，TSH和T3T4均在正常范围内。甲状腺超声也未见明显异常。综合来看，目前不需要特殊处理，建议半年后复查。
</original_text>

<edited_text>
结论：甲状腺没问题，半年后复查。

检查结果：TSH、T3T4正常，超声未见异常。
</edited_text>

→ {{"type": "style", "persona_field": "structure", "summary": "将回复改为结论前置的结构，先给结论再列支持数据", "confidence": "medium"}}
（结构调整明显，但仅一个样本，不确定是否为固定偏好）

**示例5：微小修改 — 意图模糊（低置信度）**

<original_text>
建议您近期复查一下血常规。
</original_text>

<edited_text>
建议近期复查血常规。
</edited_text>

→ {{"type": "style", "persona_field": "edits", "summary": "删除了冗余的'您'和'一下'", "confidence": "low"}}
（改动极小，可能是随手修改而非刻意偏好）
