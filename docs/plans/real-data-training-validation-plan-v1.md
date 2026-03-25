# ChatGPT-Based Data: Real-Data Training / Validation Plan v1

## Goal

用真实门诊输入风格验证端到端能力：结构化病历、去重创建、风险分层、任务生成与通知。

## Data provenance

- `data_source`: `chat-gpt-based-data`

## Affected files

- `train/data/real_data_multimodal_training_validation_v1.md`
- `tests/integration/test_text_pipeline.py`（复用）
- `tests/integration/test_image_pipeline.py`（复用）
- `tests/integration/test_manage_tasks_pipeline.py`（复用）

## Steps

1. 准备环境  
   - 启动服务：`uvicorn main:app --reload`  
   - 启动 Ollama：`ollama serve`  
   - 建议模型：`qwen2.5:7b`（文本），`qwen2.5vl:7b`（图片）  
   - 需要验证自动随访任务时：`export AUTO_FOLLOWUP_TASKS_ENABLED=true`

2. 训练样本执行（文本）  
   - 按 `RD-001 / RD-002 / RD-005` 逐条发送 `/api/records/chat`  
   - 断言：返回 `record` 非空且 `chief_complaint` 非空  
   - 断言：同名同 `doctor_id` 第二次录入不会新增 `patients` 行

3. 训练样本执行（图片）  
   - 上传图片到 `/api/records/from-image`（对应 RD-003）  
   - 断言：`chief_complaint`、`diagnosis`、`treatment_plan` 非空  
   - 断言：数值信息（如 `BP 150/90`）保留在结构化字段

4. 访谈模式验证（RD-004）  
   - 微信入口发送 `开始访谈`  
   - 完成 7 步输入，检查病历写入成功  
   - 若有随访描述，检查是否创建 `follow_up` 任务

5. 风险分层验证  
   - 查询患者管理接口：`/api/manage/patients?doctor_id=<id>`  
   - 对比 `primary_risk_level`：  
     - RD-001 预期 `high`（含急危词时可到 `critical`）  
     - RD-002 预期 `medium/high`（规则包含肿瘤关键词）  
     - RD-005 预期 `low`

6. 任务与通知验证  
   - 查询任务：`/api/tasks?doctor_id=<id>`  
   - RD-002/RD-005：验证 `follow_up` 与 `due_at`（约 90 天/30 天）  
   - RD-001：仅微信路由在 `is_emergency=true` 下创建 `emergency`  
   - 等待调度器周期（1 分钟）后验证 `notified_at` 更新

7. 回归测试  
   - 单元测试：`.venv/bin/python -m pytest tests/ -v`  
   - 需要时再跑集成：`pytest tests/integration/ -v`

## SQL spot checks

```sql
-- 1) 同名去重（doctor_id + name）
SELECT doctor_id, name, COUNT(*) c
FROM patients
GROUP BY doctor_id, name
HAVING c > 1;

-- 2) 8字段落库检查（示例看最近一条）
SELECT chief_complaint, history_of_present_illness, past_medical_history,
       physical_examination, auxiliary_examinations, diagnosis,
       treatment_plan, follow_up_plan
FROM medical_records
ORDER BY id DESC LIMIT 1;

-- 3) 风险结果
SELECT name, primary_risk_level, risk_score, risk_tags
FROM patients
ORDER BY id DESC LIMIT 20;

-- 4) 任务结果
SELECT task_type, title, status, due_at, notified_at, trigger_source, trigger_reason
FROM doctor_tasks
ORDER BY id DESC LIMIT 20;
```

## Pass criteria

- 结构化：5/5 用例输出可用 8 字段（允许 `null` 的字段符合临床缺失）
- 去重：无重复 `doctor_id + name` 患者行
- 风险：3 个代表病例风险等级符合预期区间
- 任务：随访任务按计划生成，调度后可看到通知时间

## Risks / open questions

- 当前 `/api/records/chat` 不自动创建 `emergency` 任务，微信路由才会创建（行为差异需统一）
- 肿瘤病例在现有风险规则中常被提到 `high`，与“稳定复查=medium”目标可能不一致
- 图片链路受 OCR/视觉模型波动影响，需要容错断言（包含关键词而非完全等值）
