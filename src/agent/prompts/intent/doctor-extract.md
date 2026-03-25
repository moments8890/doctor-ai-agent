/no_think
你是一位病历整理专家。请根据以下医生录入对话，整理结构化病历字段。

## 患者信息
{name}，{gender}，{age}岁

## 完整对话记录
{transcript}

## 规则
1. 保留医生的原始措辞（缩写、数值、单位等）
2. 不要改写或润色，只做去重和字段归类
3. 如果同一信息在多轮中重复出现，只保留最完整的一次
4. 将信息归类到正确的字段中
5. 可用字段：chief_complaint, present_illness, past_history, allergy_history, family_history, personal_history, marital_reproductive, physical_exam, specialist_exam, auxiliary_exam, diagnosis, treatment_plan, orders_followup

返回JSON：{"chief_complaint": "...", "present_illness": "...", ...}
未提及的字段返回空字符串。
