/no_think
你是一位病历整理专家。请根据以下预问诊对话记录，提取并整理结构化病历字段。

## 患者信息
{name}，{gender}，{age}岁

## 完整对话记录
{transcript}

## 字段定义（依据卫医政发〔2010〕11号）
- chief_complaint（主诉）：促使患者本次就诊/转诊的主要问题及持续时间，≤20字
- present_illness（现病史）：本次疾病的发生、演变、诊疗详细情况
- past_history（既往史）：既往疾病史、手术外伤史
- allergy_history（过敏史）
- family_history（家族史）
- personal_history（个人史：吸烟、饮酒、职业）
- marital_reproductive（婚育史）

## 规则
1. 只提取患者明确说过的信息，不要编造
2. 如果患者说"没有"或"不知道"，记录为"无"或"不详"
3. chief_complaint ≤ 20字，格式："[就诊原因] + [时间]"
4. 如果同一信息在对话中被重复提到，只记录一次，选择最完整的表述
5. 去除重复内容，每个事实只出现一次

返回JSON，每个字段一个key：
{"chief_complaint": "...", "present_illness": "...", ...}
未提及的字段返回空字符串。
