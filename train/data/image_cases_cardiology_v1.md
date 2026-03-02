# 图片病历识别测试计划 v1（手写门诊记录 — 心血管内科）

## 语料说明

- 每条用例对应一张**手写门诊记录照片**，模拟医生拍摄纸质病历的真实场景
- 测试目标：`POST /api/records/from-image` 全链路（视觉提取 → 结构化）
- 专科：心血管内科
- 跑法：`python tools/train_images.py train/data/image_cases_cardiology_v1.md`

## 断言语法（供 train_images.py 解析）

每个用例的 `### 字段验证` 块中，每行格式为：

```
<field>: <rule> [, contains=<substring>]
```

| rule | 含义 |
|------|------|
| `non-null` | 字段不得为空 |
| `null` | 字段必须为 null/空 |
| `any` | 不检查 |

------------------------------------------------------------------------

## Image Case 001

**医生**：测试医生\
**日期**：2026-05-12\
**患者**：刘某某\
**图片**：train/images/ChatGPT Image Mar 1, 2026, 05_00_42 PM.png

### 图片原始内容（人工转录）

```
刘某某 男 62岁                          2026.5.12

主诉：胸闷1周，活动后加重

HPI：高血压10年，糖尿病5年
     夜间有胸闷出汗

查体：BP 168/95mmHg，双下肢轻度水肿
     ?UA? CAD
     血糖 7.9mmol/L

建议：
  1. 心电图 + 心肌酶
  2. 冠脉CTA
  3. 住院观察
```

### 字段验证

```assertions
chief_complaint: non-null, contains=胸闷
history_of_present_illness: non-null, contains=高血压
past_medical_history: non-null
physical_examination: non-null, contains=168
auxiliary_examinations: non-null, contains=7.9
diagnosis: non-null
treatment_plan: non-null, contains=心电图
follow_up_plan: any
```

------------------------------------------------------------------------

## Image Case 002

**医生**：测试医生\
**日期**：2026-06-21\
**患者**：李某某\
**图片**：train/images/ChatGPT Image Mar 1, 2026, 05_02_49 PM.png

### 图片原始内容（人工转录）

```
李某某 男 58岁                          2026.6.21

主诉：胸痛2小时
     ?ACS?

查体：BP 182/110mmHg，110次/分
     ?NSTEMI? 大汗恶心

检查：心电图：T波倒置 V1-4
     肌钙蛋白：0.46 ng/ml
     BNP：385 pg/ml

建议：
  1. 立即送胸痛中心
  2. 普洛地尔 静推
  3. 硝酸甘油 保安定 吸氧
  4. 介入导管
```

### 字段验证

```assertions
chief_complaint: non-null, contains=胸痛
history_of_present_illness: non-null
past_medical_history: any
physical_examination: non-null, contains=182
auxiliary_examinations: non-null, contains=0.46
diagnosis: non-null
treatment_plan: non-null, contains=胸痛中心
follow_up_plan: any
```

------------------------------------------------------------------------
