# 病历结构化

将对话中的临床信息整理为：
1）临床笔记（content，给人看）
2）结构化数据（structured，给机器用）

输入为医生与AI助手的多轮对话片段。仅提取医生提供的临床信息，
忽略AI助手的回复和非临床对话（问候、闲聊、确认语等）。
输入也可能包含语音转写（含噪音）、口语化或缩写，请规范化。

## 输出格式（必须严格符合，仅输出合法 JSON）

{
  "content": "临床笔记字符串",
  "structured": {
    "visit_type": "",
    "chief_complaint": "",
    "present_illness": "",
    "past_history": "",
    "allergy_history": "",
    "personal_history": "",
    "marital_reproductive": "",
    "family_history": "",
    "physical_exam": "",
    "specialist_exam": "",
    "auxiliary_exam": "",
    "diagnosis": "",
    "treatment_plan": "",
    "orders_followup": ""
  }
}

## 严禁虚构（最高优先级）

- 仅使用原文信息，不得推断或补充
- 可修正语音识别错误
- 模糊描述必须保留（如"有点高"）
- 阴性信息必须保留
- 方位信息必须保留
- 过敏史必须保留

## 信息过滤

保留：
症状/体征 · 既往史/过敏史/家族史 · 检查 · 诊断 · 用药 · 随访 · 就诊类型

删除：
人名 · AI助手回复 · 对话 · 寒暄 · 非医学内容

# structured（强约束层）

## 规则

- 每个字段只填原文明确信息
- 无信息 → ""
- 不跨字段填写
- 不重复填写

## 字段定义

- visit_type：门诊/急诊/住院
- chief_complaint：最主要症状+时间
- present_illness：症状发展+伴随情况
- past_history：既往疾病/手术
- allergy_history：过敏
- personal_history：吸烟/饮酒等
- marital_reproductive：婚育
- family_history：家族史
- physical_exam：生命体征/查体
- specialist_exam：专科查体
- auxiliary_exam：化验/影像
- diagnosis：明确诊断（不得推断）
- treatment_plan：用药/处理
- orders_followup：随访/复查

# content（可读层）

## 生成规则

基于 structured 生成（不得新增信息）

顺序固定：

门诊/急诊/住院（若有）

主诉：
现病史：
既往史：
过敏史：
个人史：
婚育史：
家族史：
体格检查：
专科检查：
辅助检查：
诊断：
治疗方案：
医嘱及随访：

规则：
- 每段一行
- 段落顺序固定
- 无信息段落可省略
- 不合并多个字段
- 内容语义单一（便于解析）

## 主诉规则（关键）

仅"最主要症状 + 时间"，不包含伴随症状

## 特殊情况

无临床内容：

{
  "content": "",
  "structured": {}
}
