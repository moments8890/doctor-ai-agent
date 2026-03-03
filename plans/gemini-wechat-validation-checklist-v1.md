# Gemini WeChat Validation Checklist v1

## Goal

验证 Gemini 模式下 WeChat-native 助手在意图识别、结构化提取、状态机和任务生成的正确性。

## Scope

- 场景 1：心内 STEMI 新患者建档
- 场景 2：肿瘤影像+化疗随访
- 场景 3：7 步引导问诊（Interview Mode）

## DB checks (project-accurate fields)

1. `patients.primary_risk_level`  
   - 场景 1 目标：`critical`（或至少 `high`，取决于诊断关键词）

2. `medical_records` 8 字段  
   - 场景 2 重点：  
     - `auxiliary_examinations` 包含 CT 结论 + WBC 3.2  
     - `treatment_plan` / `follow_up_plan` 包含第4周期化疗与化疗前复查

3. `doctor_tasks`  
   - 场景 1：仅 WeChat 路由且 `is_emergency=true` 时创建 `task_type='emergency'`  
   - 场景 2：有 `follow_up_plan` 且 `AUTO_FOLLOWUP_TASKS_ENABLED=true` 时创建 `task_type='follow_up'`，检查 `due_at`

4. `doctor_contexts.summary`  
   - 场景 3 完成后，检查是否生成压缩摘要（依赖会话轮次/空闲触发）

## Commands

```bash
export ROUTING_LLM=gemini
export STRUCTURING_LLM=gemini
export GEMINI_API_KEY=...
export AUTO_FOLLOWUP_TASKS_ENABLED=true

# 自动化（chat 路由）
.venv/bin/python tools/train_gemini.py --clean --check-follow-up-tasks

# 集成模板
export RUN_GEMINI_TEMPLATE=1
pytest tests/integration/test_gemini_wechat_template.py -v
```

## Manual WeChat-only checks

- Interview 7-step：发送 `开始访谈`，确认逐步提问与结束写库
- Emergency async push：验证 `create_emergency_task` 的即时通知文案
- OCR + 语音融合：先图后语音，确认同一患者时间轴记录连续
