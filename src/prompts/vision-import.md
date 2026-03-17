# 门诊病历图片提取

从图片中提取患者信息和临床字段，输出 JSON。

## 规则

- 仔细阅读所有文字，包括手写内容
- 多页图片作为同一份病历合并提取
- 仅使用图片中明确出现的信息，不得推断或虚构
- 未提及的字段填 `""`
- 诊断只填名称，不附编码

## 输出格式（严格JSON）

{
  "patient": {"name": "...", "gender": "男|女", "age": 45},
  "department": "",
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

## patient

从病历抬头提取：
- name：患者姓名（未出现 → null）
- gender："男" 或 "女"（未出现 → null）
- age：整数（未出现 → null）

## 字段定义

- department：科别
- chief_complaint：主诉（症状+时间）
- present_illness：现病史
- past_history：既往史/手术史（不含过敏）
- allergy_history：过敏史（无过敏 → "否认药物、食物过敏史"）
- personal_history：吸烟/饮酒/职业
- marital_reproductive：婚育史
- family_history：家族史
- physical_exam：生命体征/体格检查
- specialist_exam：专科查体
- auxiliary_exam：化验/影像/心电图
- diagnosis：初步诊断
- treatment_plan：用药/治疗措施
- orders_followup：医嘱/随访/复诊

仅输出 JSON，不添加解释或 Markdown 标记。
