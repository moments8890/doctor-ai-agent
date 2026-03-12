# Skills — 科室技能文件

科室技能是 Markdown 文件，包含专科临床知识和规则，在 LLM 推理时自动注入到系统提示词中。

灵感来自 [OpenClaw](https://github.com/openclaw/openclaw) 的 SKILL.md 模式。

## 目录结构

```
skills/
├── _default/              # 通用基线（所有科室共享，始终加载）
│   ├── structuring.md     # 通用病历结构化规则
│   └── routing_hints.md   # 通用意图路由提示
├── cardiology/            # 心内科
│   ├── structuring.md     # STEMI/PCI/EF/NYHA 等结构化规则
│   └── clinical_signals.md# 急诊指标 + 复诊触发条件
└── neurology/             # 神经科
    ├── structuring.md     # NIHSS/GCS/mRS 等结构化规则
    └── clinical_signals.md# 脑疝/溶栓窗口等信号
```

## 技能类型

| 类型 | 文件名 | 用途 |
|------|--------|------|
| `structuring` | `structuring.md` | 病历结构化时注入，指导 LLM 保留专科术语、规范字段 |
| `routing` | `routing_hints.md` | 意图分类时注入，提供科室特有的路由关键词 |
| `clinical_signals` | `clinical_signals.md` | 临床信号检测，包含急诊指标和复诊触发规则 |

## 文件格式

每个技能文件由 **YAML frontmatter** + **Markdown 正文** 组成：

- **Frontmatter**（`---` 之间的部分）是必须的，包含元数据字段（见下表）。
- **正文**（frontmatter 之后的所有内容）**格式完全自由**——系统会将其原样注入到 LLM 的系统提示词中，不做任何解析或校验。你可以写任何 Markdown 内容：标题、列表、表格、纯文本段落、代码块，甚至只有一句话。没有固定的标题或结构要求。

```markdown
---
name: cardiology-structuring
description: 心内科病历结构化规则
type: structuring
specialty: cardiology
---

（以下内容完全自由，系统原样注入 LLM prompt，不限格式）

# 心内科结构化规则

## 必须保留的专科缩写
STEMI, NSTEMI, PCI, CABG, BNP, NT-proBNP, EF, LVEF...

## 关键临床参数
- 心功能分级（NYHA I-IV）必须保留原始分级
- 射血分数（EF/LVEF）百分比数值
...
```

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 技能唯一名称（如 `cardiology-structuring`） |
| `description` | 是 | 一句话描述，用于日志和管理界面 |
| `type` | 是 | `structuring` / `routing` / `clinical_signals` |
| `specialty` | 否 | 科室英文名（默认取目录名） |

## 如何新增科室

### 1. 创建目录

```bash
mkdir skills/endocrinology
```

### 2. 创建结构化规则

```bash
cat > skills/endocrinology/structuring.md << 'EOF'
---
name: endocrinology-structuring
description: 内分泌科病历结构化规则
type: structuring
specialty: endocrinology
---

# 内分泌科结构化规则

## 必须保留的专科缩写
HbA1c, FPG, OGTT, eGFR, UACR, TSH, FT3, FT4, BMI, DKA

## 关键临床参数
- 血糖（空腹/餐后/随机）数值及单位
- HbA1c 百分比
- eGFR 数值（CKD 分期）
- 胰岛素用量（单位/方案）
EOF
```

### 3. 创建临床信号（可选）

```bash
cat > skills/endocrinology/clinical_signals.md << 'EOF'
---
name: endocrinology-clinical-signals
description: 内分泌科临床信号检测规则
type: clinical_signals
specialty: endocrinology
---

# 内分泌科临床信号

## 急诊指标
- DKA（糖尿病酮症酸中毒）：血糖 > 13.9 + 酮体阳性
- 低血糖：血糖 < 3.9 mmol/L

## 复诊提醒触发
- 新诊断糖尿病：每3个月复查 HbA1c
- 甲亢用药：每4-6周复查甲功
EOF
```

### 4. 完成

不需要修改任何代码。技能文件会在下次请求时自动加载（5 分钟缓存，可通过 `SKILLS_CACHE_TTL` 配置）。

## 中文科室名映射

系统自动将中文科室名映射到目录名：

| 中文 | 目录名 |
|------|--------|
| 心内科 / 心血管内科 | `cardiology` |
| 神经外科 / 神经内科 | `neurology` |
| 内分泌科 | `endocrinology` |
| 肿瘤科 | `oncology` |
| 骨科 | `orthopedics` |
| 呼吸内科 | `pulmonology` |
| 消化内科 | `gastroenterology` |
| 泌尿外科 | `urology` |
| 普外科 | `general_surgery` |
| 妇产科 | `obstetrics` |
| 儿科 | `pediatrics` |
| 眼科 | `ophthalmology` |
| 耳鼻喉科 | `ent` |
| 皮肤科 | `dermatology` |
| 精神科 | `psychiatry` |
| 急诊科 | `emergency` |
| ICU / 重症医学科 | `icu` |

如需添加新映射，编辑 `services/knowledge/skill_loader.py` 中的 `_SPECIALTY_ALIASES`。

## API 参考

```python
from services.knowledge.skill_loader import (
    load_skills,           # 加载科室全部技能
    get_structuring_skill, # 获取结构化规则文本
    get_clinical_signals,  # 获取临床信号规则
    get_routing_hints,     # 获取路由提示
    list_specialties,      # 列出所有已有科室
    invalidate_cache,      # 清除缓存（编辑技能后调用）
)

# 加载心内科全部技能（含 _default 基线）
skills = load_skills("心内科")

# 仅获取结构化文本（直接注入 LLM prompt）
text = get_structuring_skill("cardiology")

# 列出所有科室
specs = list_specialties()  # ["_default", "cardiology", "neurology"]
```
