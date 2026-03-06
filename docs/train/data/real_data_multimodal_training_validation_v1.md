# ChatGPT-Based Data：真实临床多模态训练/验证集 v1（心内 + 肿瘤 + 访谈）

## 目的

- 将真实门诊输入风格（语音转写、文本、图片、访谈）整理为统一训练/验证样本
- 对齐当前系统 8 字段结构化输出 + 风险分层 + 任务生成 + 数据库落库行为

## 数据来源标记

- `data_source`: `chat-gpt-based-data`

## 字段映射（本项目实际 schema）

- `chief_complaint` <- 主诉
- `history_of_present_illness` <- 现病史
- `past_medical_history` <- 既往史
- `physical_examination` <- 生命体征/查体
- `auxiliary_examinations` <- 辅助检查
- `diagnosis` <- 评估/诊断
- `treatment_plan` <- 诊疗计划
- `follow_up_plan` <- 随访计划

注：
- 本项目患者风险字段为 `patients.primary_risk_level`（不是 `risk_level`）。
- 风险等级合法值：`low|medium|high|critical`。
- `DoctorTask.task_type` 当前支持：`follow_up|emergency|appointment`。

---

## Case RD-001（心内科：高危不稳定心绞痛）

**输入通道**：微信语音转写文本  
**医生输入**：

> 记录一下。王建国，男，68岁。主诉：反复胸痛3天，加重2小时。既往高血压15年，糖尿病8年。今晚静息状态也痛，持续十几分钟，出冷汗。血压170/95，心率102。心电图ST段压低。考虑不稳定心绞痛，收入院观察。

**预期 intent/tool**：`add_medical_record`（`is_emergency=false`，可选转 `true` 视路由策略）  
**预期结构化 8 字段**：

```json
{
  "chief_complaint": "反复胸痛3天，加重2小时",
  "history_of_present_illness": "静息胸痛，持续十余分钟，伴冷汗",
  "past_medical_history": "高血压15年，糖尿病8年",
  "physical_examination": "BP 170/95 mmHg, HR 102 bpm",
  "auxiliary_examinations": "心电图ST段压低",
  "diagnosis": "不稳定心绞痛",
  "treatment_plan": "住院观察，完善心肌酶及冠脉评估",
  "follow_up_plan": null
}
```

**预期风险**：
- `patients.primary_risk_level = "high"`（若诊断含 `急诊PCI/休克/心跳骤停` 等可升至 `critical`）
- `patients.risk_tags` 建议包含：`high_risk_keyword`

**预期任务**：
- 如走微信路由且 `is_emergency=true`：创建 `task_type="emergency"`，即时通知
- 如走 `/api/records/chat`：默认不自动创建 emergency 任务（当前实现差异点）

---

## Case RD-002（肿瘤专科：稳定复查）

**输入通道**：文本  
**医生输入**：

> 李梅，女，52岁。乳腺癌术后两年，ER阳性。今日复查，无明显不适。CA153正常。继续口服他莫昔芬。三个月后复查。

**预期 intent/tool**：`add_medical_record`  
**预期结构化 8 字段**：

```json
{
  "chief_complaint": "乳腺癌术后复查",
  "history_of_present_illness": "无明显不适",
  "past_medical_history": "乳腺癌术后两年，ER阳性",
  "physical_examination": null,
  "auxiliary_examinations": "CA153正常",
  "diagnosis": "术后稳定期",
  "treatment_plan": "继续他莫昔芬",
  "follow_up_plan": "三个月后复查"
}
```

**预期风险**：
- `patients.primary_risk_level = "medium"` 或 `"high"`（当前规则命中 `肿瘤` 关键词倾向高风险）

**预期任务**：
- 开启 `AUTO_FOLLOWUP_TASKS_ENABLED=true` 时：自动创建 `follow_up`，`due_at≈90天`
- 微信路由会额外创建一条 `follow_up`（需去重策略验证）

---

## Case RD-003（图片输入：手写门诊记录）

**输入通道**：图片 -> `qwen2.5vl` -> 文本 -> `agent_dispatch()`  
**OCR 参考文本**：

> 赵强 60y M，HTN 10y，主诉：胸闷半月，BP 150/90，ECG 正常，考虑稳定型心绞痛，建议做冠脉CTA

**预期结构化 8 字段**：

```json
{
  "chief_complaint": "胸闷半月",
  "history_of_present_illness": null,
  "past_medical_history": "高血压10年",
  "physical_examination": "BP 150/90",
  "auxiliary_examinations": "ECG正常",
  "diagnosis": "稳定型心绞痛",
  "treatment_plan": "冠脉CTA检查",
  "follow_up_plan": null
}
```

**预期风险**：
- `patients.primary_risk_level = "medium"`（依赖诊断关键词/分类联动）

---

## Case RD-004（访谈模式：7-step intake）

**输入通道**：微信访谈  
**触发词**：`开始访谈`  
**7 步字段**：姓名、主诉、持续时间、严重程度、伴随症状、既往史、查体  

**预期行为**：
- 完成 7 步后自动生成 `compiled_text`
- `structure_medical_record(compiled_text)` 成功写入 `medical_records`
- 自动关联/创建患者并更新风险评分
- 若提及随访时间，触发 `follow_up` 任务

---

## Case RD-005（低风险慢病管理）

**输入通道**：语音转写文本  
**医生输入**：

> 陈志远，男，45岁。高血压控制一般。最近血压在140左右。无胸痛。建议调整氨氯地平剂量。一个月后复查。

**预期结构化 8 字段**：

```json
{
  "chief_complaint": "高血压控制一般",
  "history_of_present_illness": "近期血压约140，无胸痛",
  "past_medical_history": "高血压",
  "physical_examination": "血压约140",
  "auxiliary_examinations": null,
  "diagnosis": "高血压",
  "treatment_plan": "调整氨氯地平剂量",
  "follow_up_plan": "一个月后复查"
}
```

**预期风险**：
- `patients.primary_risk_level = "low"`

**预期任务**：
- 自动 `follow_up`，`due_at≈30天`
- 任务轮询通知由 APScheduler 每 1 分钟触发

---

## 验证重点（对应你的 4 个关键问题）

1. 单 LLM 输出一致性：`intent + 8字段 + 自然回复` 是否同轮给出  
2. 去重建档：同 `doctor_id + patient_name` 是否复用患者行  
3. 风险模型触发：`primary_risk_level` 是否与输入严重度一致  
4. 任务轮询：`check_and_send_due_tasks` 是否按分钟扫描并发送

---

## 最小执行命令（本地）

```bash
# 文本链路（需服务已启动）
python scripts/train.py train/data/clinic_raw_cases_cardiology_v2.md

# 图片链路
python scripts/train_images.py train/data/image_cases_cardiology_v1.md

# 若要验证自动随访任务（chat 路由）
export AUTO_FOLLOWUP_TASKS_ENABLED=true
```
