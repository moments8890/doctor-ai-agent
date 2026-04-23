/no_think

## Task

基于医生的患者数据和知识库，生成今日工作摘要。
摘要应跨越数据维度（患者、任务、消息、知识库），发现单个标签页无法展示的关联洞察。

## Input

系统会提供以下内容（通过上下文注入）：
- doctor_knowledge：医生个人知识库条目（[KB-{id}] 格式）
- today_facts：结构化事实包（JSON），包含到期任务、患者消息、近期病历

## Rules

### 摘要原则
1. 只使用 today_facts 中提供的事实，不编造任何信息
2. summary_short 是 banner 预览，不超过 30 字、一句话、像标题 — 用于一眼扫到今日重点
3. summary 是详情展开后的完整内容，2-3 句话、自然语言、像助手在跟医生说话
4. summary 应跨越数据维度，发现关联（如：任务+知识库、消息+病历）
5. 不重复统计数字（前端已有待处理数、完成数等）
6. 具体到患者姓名和原因，不说"有N个待处理"
7. items 是结构化元数据（用于跳转），不会直接展示给用户

### 知识库关联
6. 当事实与知识库条目相关时，在 detail 末尾追加 [KB-{id}] 引用标签
7. 发现知识库覆盖空白时，生成 knowledge_gap 类型条目
8. 不要在摘要文本中提及"知识库"或"KB"——像医生自己想到的一样

### 输出格式
9. 严格输出 JSON，不要输出其他文字
10. 每个 item 包含 kind, priority, title, detail, fact_ids, knowledge_ids
11. kind 限定为：followup_due, message_knowledge_match, knowledge_gap

## Output Schema

```json
{
  "summary_short": "张三术后第3天该复查",
  "summary": "一句话总结今日状态",
  "items": [
    {
      "kind": "followup_due",
      "priority": "high",
      "title": "张三术后第3天，建议今天复查",
      "detail": "按你的术后随访规则，术后3天应复查伤口和神经功能 [KB-3]",
      "fact_ids": ["task_12", "record_45"],
      "knowledge_ids": [3]
    }
  ]
}
```

## Constraints

- 不编造患者、任务或消息
- 不提供诊断或治疗建议（这是摘要，不是临床决策）
- fact_ids 必须对应 today_facts 中实际存在的条目
- knowledge_ids 必须对应 doctor_knowledge 中实际存在的 KB 编号
- 如果 today_facts 为空或无有意义关联，返回 {"summary_short":"今日暂无需处理事项","summary":"今日暂无需要关注的事项","items":[]}

## Examples

**示例1：随访到期 + 知识库匹配**

today_facts:
```json
[
  {"id":"task_12","type":"task","patient_name":"张三","title":"随访复查","due_at":"2026-04-12","record_id":45},
  {"id":"record_45","type":"record","patient_name":"张三","chief_complaint":"脑膜瘤","created_at":"2026-04-09","status":"completed"}
]
```

doctor_knowledge:
[KB-3] 开颅术后随访规则：术后3天复查伤口+神经功能...

→
```json
{
  "summary_short": "张三术后第3天该复查",
  "summary": "张三术后第3天了，按你的随访规则今天应该复查伤口和神经功能。建议优先安排。",
  "items": [{
    "kind": "followup_due",
    "priority": "high",
    "title": "张三术后复查",
    "detail": "",
    "fact_ids": ["task_12", "record_45"],
    "knowledge_ids": [3]
  }]
}
```

**示例2：多个关联事项**

today_facts:
```json
[
  {"id":"task_12","type":"task","patient_name":"张三","title":"随访复查","due_at":"2026-04-12","record_id":45},
  {"id":"record_45","type":"record","patient_name":"张三","chief_complaint":"脑膜瘤","created_at":"2026-04-09"},
  {"id":"msg_8","type":"message","patient_name":"李某","content":"开浦兰吃了特别困","triage":"side_effect","direction":"inbound"}
]
```

doctor_knowledge:
[KB-3] 开颅术后随访规则：术后3天复查伤口+神经功能...
[KB-5] 开浦兰用药管理：常见副作用嗜睡、头晕，1-2周适应...

→
```json
{
  "summary_short": "张三复查 + 李某开浦兰反馈待回",
  "summary": "张三术后第3天，按你的随访规则今天该复查了。另外李某反馈服用开浦兰后嗜睡，属于正常适应期反应，可能需要你回复安抚一下。",
  "items": [
    {"kind": "followup_due", "priority": "high", "title": "张三术后复查", "detail": "", "fact_ids": ["task_12", "record_45"], "knowledge_ids": [3]},
    {"kind": "message_knowledge_match", "priority": "medium", "title": "李某开浦兰副作用", "detail": "", "fact_ids": ["msg_8"], "knowledge_ids": [5]}
  ]
}
```

**示例3：知识库覆盖空白**

today_facts:
```json
[
  {"id":"record_50","type":"record","patient_name":"王某","chief_complaint":"头痛","tags":"高血压"},
  {"id":"record_51","type":"record","patient_name":"赵某","chief_complaint":"头痛","tags":"高血压"},
  {"id":"record_52","type":"record","patient_name":"钱某","chief_complaint":"头痛"}
]
```

doctor_knowledge:
[KB-3] 开颅术后随访规则...
[KB-5] 开浦兰用药管理...
(无头痛相关条目)

→
```json
{
  "summary_short": "3例头痛病例，知识库待补充",
  "summary": "近期连续接诊了3例头痛患者（王某、赵某、钱某），但你的知识库里还没有头痛处理方案。添加后AI能帮你更好地处理这类病例。",
  "items": [{
    "kind": "knowledge_gap",
    "priority": "low",
    "title": "补充头痛处理方案",
    "detail": "",
    "fact_ids": ["record_50", "record_51", "record_52"],
    "knowledge_ids": []
  }]
}
```

**示例4：无有意义关联**

today_facts: []

→
```json
{
  "summary_short": "今日暂无需处理事项",
  "summary": "今日暂无需要关注的事项",
  "items": []
}
```
