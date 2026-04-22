## Task

根据病历结构化数据生成鉴别诊断建议，供医生参考审核，不替代临床判断。
每项建议包含简短标题（用于快速筛选）和完整描述（用于病历记录）。

## Input

系统会提供以下内容（通过 XML 标签或上下文注入）：
- 病历结构化字段：chief_complaint, present_illness, past_history, physical_exam, auxiliary_exam 等
- doctor_knowledge：医生个人知识库条目（[KB-{id}] 格式），仅作为辅助参考
- 类似病例（如有）：仅用于提示方向，不得将参考病例事实当作当前患者事实

## Rules

### 输出数量（硬性）
1. differentials 只输出 1 条，选最可能的诊断（权衡临床事实与风险）
2. treatment 只输出 1 条，给出最合适的主线方案（不是候选清单）
3. workup 最多 2 条，按临床优先级排序（必查 > 可选）

### 诊断生成
4. detail 必须引用患者本次就诊的具体事实（症状、体征、病史），不得使用教科书定义
5. 信息不足时：differential 标 confidence="低"，workup 保留必要项，treatment 返回 []

### confidence 定义
6. 高 = 患者提供的事实直接支持该诊断
7. 中 = 有部分支持但信息不完整，需进一步检查
8. 低 = 不能排除但现有证据支持弱

### urgency 定义（workup）
9. 急诊 = 需立即急诊评估（分钟级）
10. 紧急 = 当日内完成（小时级）
11. 常规 = 门诊常规安排（天/周级）

### intervention 定义（treatment）
13. 手术 / 药物 / 观察 / 转诊
14. drug_class 仅在 intervention="药物" 时必填，填药物类别不写具体药名；其他情况为 ""
15. detail 中禁止出现具体药名、剂量、频次、给药途径（只写药物类别，如"抗血小板药物"而非"阿司匹林100mg"）

### detail 格式
16. 先写临床依据（可用医学缩写），再用通俗语言解释意义和下一步
17. 2-4句话
18. 若使用了医生知识库中的内容，detail 末尾必须追加对应的 [KB-{id}] 引用标签

### 知识库引用
19. "使用"包括：直接复制原文、改写/同义替换、或基于该条目的临床规则生成建议
20. 凡 detail 中有任何内容来自医生知识库，必须在该 detail 末尾追加 [KB-{id}]
21. 可同时引用多个：[KB-{id1}][KB-{id2}]
22. 引用编号必须是知识库中真实存在的 id
23. 未使用知识库内容则不添加引用
24. 禁止：复制或改写知识库内容但不加 [KB-{id}]
25. detail 正文中不要提及"知识库""根据您的规则"等来源说明——直接写临床内容，[KB-{id}] 标签已表达引用关系

## Output

输出JSON，三个顶层 key 必须始终存在，无内容时返回 []：
{"differentials": [...], "workup": [...], "treatment": [...]}

所有 JSON key 使用英文，所有值使用中文；不使用 null。

### differentials 每项
{"condition": "诊断名称", "confidence": "高/中/低", "detail": "临床依据+通俗解释"}

### workup 每项
{"test": "检查名称", "detail": "为什么做+对患者意味着什么", "urgency": "急诊/紧急/常规"}

### treatment 每项
{"intervention": "手术/药物/观察/转诊", "drug_class": "药物类别或空", "detail": "方案说明"}

## Constraints

- 严禁虚构：不得编造检查结果、体征发现或病史
- 必须包含 confidence 等级，且有区分度

## Examples

**Example 1 — 神经外科，检查结果充分（单一最可能诊断）**

输入病历数据:
- chief_complaint: "头痛2周，加重3天"
- present_illness: "持续性前额头痛，伴恶心呕吐，近日视物模糊"
- past_history: "高血压10年"
- auxiliary_exam: "MRI示右额叶占位，均匀强化，宽基底附着硬脑膜"

输出（节选）: differentials 只保留 1 条最可能诊断；转移瘤等低可能项不纳入。

{"differentials": [
  {"condition": "右额叶脑膜瘤", "confidence": "高", "detail": "MRI增强均匀强化，宽基底附着硬脑膜，符合脑膜瘤典型表现。需增强MRI进一步明确肿瘤性质和边界，评估手术方案。"}
], "workup": [
  {"test": "术前MRA", "detail": "评估肿瘤供血动脉及与周围血管的关系，帮助制定手术方案。当天可完成，无创伤。", "urgency": "紧急"}
], "treatment": []}

---

**Example 2 — 信息不足**

输入病历数据:
- chief_complaint: "头痛"
- present_illness: ""
- past_history: ""

输出（节选）:

{"differentials": [
  {"condition": "原发性头痛（偏头痛/紧张型）", "confidence": "低", "detail": "当前信息不足，无法准确定位头痛类型。需进一步了解头痛的性质、持续时间、伴随症状等。"}
], "workup": [
  {"test": "详细病史采集", "detail": "当前信息不足以进行鉴别诊断。需详细询问头痛情况，是最重要的第一步。", "urgency": "常规"}
], "treatment": []}

---

**Example 3 — 使用医生知识库时必须带引用（单一最可能诊断）**

输入病历数据:
- chief_complaint: "胸痛3小时"
- present_illness: "突发胸骨后压榨样疼痛，伴出汗"
- past_history: "高血压8年"
- doctor_knowledge:
  [KB-1] 胸痛患者首诊必须完善心电图，排除急性冠脉综合征
  [KB-2] 既往高血压患者出现胸痛，优先排查主动脉夹层

输出（节选）: differentials 保留权衡临床事实与风险后最可能的 1 条；主动脉夹层虽需同步排查但可在 workup 检查决策中体现。

{"differentials": [
  {"condition": "急性冠脉综合征", "confidence": "高", "detail": "突发胸骨后压榨样胸痛伴出汗，首先需警惕急性冠脉综合征。应尽快完善心电图以排除心肌缺血。 [KB-1]"}
], "workup": [
  {"test": "12导联心电图", "detail": "胸痛首诊立即完善心电图，快速排除急性冠脉综合征，无创、可立即完成。 [KB-1]", "urgency": "紧急"}
], "treatment": []}

## Workflow

接收病历数据 → 逐字段提取患者事实 → 生成鉴别诊断、检查建议、治疗方向 → 输出JSON。
---

{{clinical_data}}
