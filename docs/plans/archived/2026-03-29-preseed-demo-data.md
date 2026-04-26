# Preseed Demo Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After onboarding, seed each doctor's account with 5 LVB-for-AD patients (13 records, 18 AI suggestions, 16 messages, 13 tasks) demonstrating every core feature.

**Architecture:** JSON content file → Pydantic validation → single-transaction service → 3 REST endpoints (create/reset/delete). Provenance via `seed_source` column on 7 tables. Timestamps staggered via `days_ago` fields for realism.

**Tech Stack:** Python/FastAPI, SQLAlchemy (async), Pydantic v2, React (frontend trigger)

**Spec:** `docs/specs/2026-03-29-preseed-demo-data-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/db/models/doctor.py:37` | Add `seed_source` to `DoctorKnowledgeItem` |
| Modify | `src/db/models/patient.py:25` | Add `seed_source` to `Patient` |
| Modify | `src/db/models/records.py:32` | Add `seed_source` to `MedicalRecordDB` |
| Modify | `src/db/models/patient_message.py:50` | Add `seed_source` to `PatientMessage` |
| Modify | `src/db/models/message_draft.py:48` | Add `seed_source` to `MessageDraft` |
| Modify | `src/db/models/ai_suggestion.py:49` | Add `seed_source` to `AISuggestion` |
| Modify | `src/db/models/tasks.py:70` | Add `seed_source` to `DoctorTask`, update CHECK |
| Create | `src/channels/web/ui/preseed_schema.py` | Pydantic models for JSON validation |
| Create | `src/channels/web/ui/preseed_data.json` | All seed content (5 patients, 2 KB items) |
| Create | `src/channels/web/ui/preseed_service.py` | Seed/reset/cleanup orchestration |
| Modify | `src/channels/web/ui/doctor_profile_handlers.py` | 3 new endpoints |
| Modify | `frontend/web/src/api.js` | Add `seedDemo` API call |
| Modify | `frontend/web/src/pages/doctor/OnboardingWizard.jsx` | Call seed on completion |

---

### Task 1: Add `seed_source` column to all 7 models

**Files:**
- Modify: `src/db/models/doctor.py:37`
- Modify: `src/db/models/patient.py:25`
- Modify: `src/db/models/records.py:32`
- Modify: `src/db/models/patient_message.py:50`
- Modify: `src/db/models/message_draft.py:48`
- Modify: `src/db/models/ai_suggestion.py:49`
- Modify: `src/db/models/tasks.py:61-72`

- [ ] **Step 1: Add `seed_source` to `DoctorKnowledgeItem`**

In `src/db/models/doctor.py`, after line 37 (`updated_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 2: Add `seed_source` to `Patient`**

In `src/db/models/patient.py`, after line 25 (`last_activity_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 3: Add `seed_source` to `MedicalRecordDB`**

In `src/db/models/records.py`, after the `updated_at` line (line 32), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 4: Add `seed_source` to `PatientMessage`**

In `src/db/models/patient_message.py`, after line 50 (`created_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 5: Add `seed_source` to `MessageDraft`**

In `src/db/models/message_draft.py`, after line 48 (`updated_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 6: Add `seed_source` to `AISuggestion`**

In `src/db/models/ai_suggestion.py`, after line 49 (`created_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 7: Add `seed_source` to `DoctorTask` and update CHECK constraint**

In `src/db/models/tasks.py`, after line 61 (`completed_at`), add:

```python
    seed_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

Also update the `source_type` CHECK constraint (line 70-73) to allow `"onboarding_preseed"`:

```python
        CheckConstraint(
            "source_type IS NULL OR source_type IN ('manual','rule','diagnosis_auto','onboarding_preseed')",
            name="ck_doctor_tasks_source_type",
        ),
```

- [ ] **Step 8: Verify models load**

Run: `.venv/bin/python -c "from db.models.doctor import DoctorKnowledgeItem; from db.models.patient import Patient; from db.models.records import MedicalRecordDB; from db.models.patient_message import PatientMessage; from db.models.message_draft import MessageDraft; from db.models.ai_suggestion import AISuggestion; from db.models.tasks import DoctorTask; print('all models OK')"`

Expected: `all models OK`

---

### Task 2: Create `preseed_schema.py` — Pydantic validation models

**Files:**
- Create: `src/channels/web/ui/preseed_schema.py`

- [ ] **Step 1: Create the schema file**

```python
"""Pydantic models for validating preseed_data.json at load time."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class SeedSuggestion(BaseModel):
    section: str  # differential | workup | treatment
    content: str
    detail: str  # may contain [KB-1] / [KB-2] placeholders
    confidence: str  # 高 | 中 | 低
    urgency: Optional[str] = None
    intervention: Optional[str] = None


class SeedRecord(BaseModel):
    key: str
    record_type: str  # visit | intake_summary
    status: str  # completed | pending_review
    days_ago: int  # relative timestamp
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    past_history: Optional[str] = None
    allergy_history: Optional[str] = None
    family_history: Optional[str] = None
    personal_history: Optional[str] = None
    physical_exam: Optional[str] = None
    auxiliary_exam: Optional[str] = None
    content: Optional[str] = None
    suggestions: List[SeedSuggestion] = []


class SeedMessage(BaseModel):
    content: str  # patient's message
    triage: str  # routine | info | question | urgent | concern
    auto_send: bool  # True → AI auto-replied, False → draft for doctor
    ai_reply: str  # AI reply text (may contain [KB-N] placeholders)
    days_ago: int = 0


class SeedTask(BaseModel):
    title: str
    task_type: str  # follow_up | checkup | general
    due_days: int  # days from now until due
    content: Optional[str] = None


class SeedPatient(BaseModel):
    key: str
    name: str
    gender: str  # male | female
    age: int
    records: List[SeedRecord]
    messages: List[SeedMessage]
    tasks: List[SeedTask]


class SeedKnowledgeItem(BaseModel):
    key: str
    title: str
    content: str


class SeedSpec(BaseModel):
    knowledge_items: List[SeedKnowledgeItem]
    patients: List[SeedPatient]
```

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python -c "from channels.web.ui.preseed_schema import SeedSpec; print('OK')"`

Expected: `OK`

---

### Task 3: Create `preseed_data.json` — seed content

**Files:**
- Create: `src/channels/web/ui/preseed_data.json`

This is a large file (~800+ lines) containing all 5 patients' medical content. The content comes from the design preview at `docs/dev/preseed-demo-preview.html`.

- [ ] **Step 1: Create the JSON file**

Create `src/channels/web/ui/preseed_data.json` with the full content. Structure:

```json
{
  "knowledge_items": [
    {
      "key": "kb_lvb_postop",
      "title": "LVB术后管理规范",
      "content": "颈深淋巴-静脉分流术（LVB）术后管理规范\n\n一、术后监测\n1. 术后2周、1月、3月、6月定期复查\n2. 每次复查行ICG荧光检查评估吻合口通畅性\n3. 认知评估：MMSE + MoCA，术后2周/3月/6月\n4. 影像学：术后3月复查MRI黑血序列，6月复查PET-CT\n\n二、危险信号\n1. 颈部肿胀：可能为淋巴漏或淋巴囊肿，需急查颈部超声\n2. 头痛加重：排除高灌注综合征或颅内出血\n3. 吻合口血栓：术后静脉压力变化可致血液返流形成血栓\n4. 认知突然下降：若术后曾改善后回退，首先排除吻合口狭窄\n\n三、用药\n1. 继续原有AD药物（多奈哌齐/美金刚），不自行停药\n2. 降压降糖等基础疾病药物不变\n3. 术后抗生素预防感染3天\n\n四、活动\n1. 术后1-2周避免剧烈运动和重体力劳动\n2. 日常轻度活动如散步可正常进行\n3. 颈部避免大幅度转动，保持切口清洁干燥\n\n五、手术要点（供AI参考）\n1. 鼻黏膜ICG注射法：双侧下鼻甲区域及鼻腔底部各注射2-3ml ICG\n2. 30分钟后颈深淋巴系统显影\n3. 选择管径≥0.3mm的淋巴管进行吻合\n4. 蔡司KINEVO 900机器人显微镜，15-25倍放大\n5. 淋巴结静脉吻合放大至10-15倍即可\n\n六、临床发现\n1. 部分患者术后视物模糊和头晕症状改善\n2. 推测LVB可能减轻眶内和内听道的颅神经相关性淋巴水肿\n3. 认知改善通常先于影像学改变\n4. MMSE≥15分的患者术后改善概率较高"
    },
    {
      "key": "kb_ad_diagnosis",
      "title": "AD诊断与鉴别标准",
      "content": "阿尔茨海默病（AD）诊断与鉴别标准\n\n一、典型AD\n1. 隐匿起病，进行性加重\n2. 以近事遗忘为首发，逐渐出现找词困难、计算力下降、空间定向障碍\n3. MRI示海马萎缩（Scheltens分级）\n4. PET-CT确认Aβ沉积\n\n二、非典型AD亚型\n1. 后皮质萎缩型（PCA）：以视空间功能障碍为主，枕叶皮层萎缩\n2. 词汇性失语型：以命名和找词困难为主\n3. 额叶型：以执行功能和行为异常为主\n\n三、鉴别诊断\n1. 血管性认知障碍（VCI）：阶梯样下降，有卒中史，MRI白质病变\n2. 正常压力脑积水（NPH）：三联征（步态异常+认知下降+尿失禁），脑室不成比例扩大\n3. 路易体痴呆（DLB）：波动性认知障碍，视幻觉，帕金森样症状，REM睡眠行为障碍\n4. 额颞叶痴呆（FTD）：人格改变，社交行为异常，语义性痴呆\n\n四、关键检查\n1. PET-CT（Aβ显像）：确认淀粉样蛋白沉积\n2. FDG-PET：评估脑代谢模式\n3. MRI黑血序列：评估脑淋巴/脑膜淋巴基线\n4. 腰穿CSF：Aβ42↓、p-tau↑、t-tau↑支持AD\n5. DAT-SPECT：排除路易体痴呆\n\n五、LVB手术适应证\n1. MMSE≥15分（文献提示术后改善概率较高）\n2. PET-CT确认Aβ阳性\n3. 药物治疗效果有限\n4. 患者及家属知情同意，配合度好"
    }
  ],
  "patients": [
    {
      "key": "zhang_xiulan",
      "name": "张秀兰",
      "gender": "female",
      "age": 72,
      "records": [
        {
          "key": "initial_visit",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 30,
          "chief_complaint": "记忆力进行性下降3年，加重半年",
          "present_illness": "3年前开始出现近事遗忘，逐渐不认识亲人名字。半年前加重，在熟悉地方迷路，不能管理财务。MMSE 18/30，MoCA 14/30。",
          "past_history": "高血压15年（氨氯地平5mg/日），2型糖尿病8年（二甲双胍），口服多奈哌齐5mg/日2年。",
          "allergy_history": "无药物过敏史",
          "family_history": "无特殊",
          "personal_history": "无吸烟饮酒史",
          "auxiliary_exam": "头颅MRI示双侧海马萎缩；PET-CT示双侧颞顶叶Aβ沉积阳性。",
          "content": "记忆力下降3年加重半年，MMSE 18，MoCA 14，PET阳性。高血压15年，糖尿病8年。",
          "suggestions": []
        },
        {
          "key": "surgery",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 16,
          "chief_complaint": "双侧颈深淋巴-静脉分流术（LVB）",
          "present_illness": "鼻黏膜ICG注射法（双侧下鼻甲各注射3ml），30分钟后颈深淋巴系统清晰显影。蔡司KINEVO 900机器人显微镜下操作，20倍放大，吻合3根淋巴管（管径0.3-0.5mm）至颈外静脉分支。ICG荧光确认吻合口通畅。",
          "content": "双侧颈深LVB，吻合3根淋巴管，ICG确认通畅。",
          "suggestions": []
        },
        {
          "key": "postop_2w",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "双侧颈深LVB术后2周复查",
          "present_illness": "术后恢复顺利，无发热，切口愈合好。家属反映近日能记住早餐内容，情绪较术前稳定。MMSE 20/30（↑2分），MoCA 16/30（↑2分）。",
          "physical_exam": "双侧颈部切口Ⅰ期愈合，无红肿渗出。ICG荧光复查示双侧吻合口通畅。",
          "content": "LVB术后2周，MMSE↑2，切口愈合好，吻合口通畅。",
          "suggestions": [
            {"section": "differential", "content": "术后恢复顺利，认知功能早期改善", "detail": "MMSE较术前提升2分，属于术后早期改善范围内。部分患者术后2周即出现记忆、情绪改善。建议继续观察。 [KB-1]", "confidence": "高"},
            {"section": "workup", "content": "3个月后复查PET-CT及认知评估", "detail": "术后早期影像学变化不明显，认知改善通常先于影像学改变。建议术后3个月复查PET-CT评估Aβ清除情况，同时复查MRI黑血序列评估脑淋巴引流。 [KB-1]", "confidence": "高"},
            {"section": "treatment", "content": "维持现有药物方案 + 认知康复训练", "detail": "继续口服多奈哌齐5mg/日，维持降压降糖方案不变。建议增加认知康复训练（每日记忆练习、社交互动）。 [KB-1]", "confidence": "高"}
          ]
        }
      ],
      "messages": [
        {"content": "手术完了，什么时候可以正常活动？", "triage": "routine", "auto_send": true, "ai_reply": "术后建议休息1-2周，避免剧烈运动和重体力劳动。日常轻度活动如散步可正常进行。颈部避免大幅度转动，保持切口清洁干燥。如有不适请及时联系。 [KB-1]", "days_ago": 10},
        {"content": "多奈哌齐还要继续吃吗？", "triage": "routine", "auto_send": true, "ai_reply": "请继续按原方案每日服用多奈哌齐5mg，下次复诊时再评估药物方案。同时继续服用降压药和降糖药，不要自行停药。 [KB-1]", "days_ago": 7},
        {"content": "今天做了复查CT，结果都正常", "triage": "info", "auto_send": true, "ai_reply": "好的，复查结果已记录。术后早期影像学检查正常是好的信号，说明手术区域无异常。请继续保持随访计划。", "days_ago": 3},
        {"content": "最近能记住早上吃了什么了，是不是在好转？", "triage": "info", "auto_send": true, "ai_reply": "这是一个积极的信号！部分患者术后确实会出现近事记忆力的改善，说明手术可能正在发挥作用。请继续坚持认知康复训练，我们会在复诊时做详细评估。 [KB-1]", "days_ago": 1}
      ],
      "tasks": [
        {"title": "安排3个月后PET-CT复查（评估Aβ清除情况）", "task_type": "checkup", "due_days": 76},
        {"title": "术后3个月认知评估（MMSE + MoCA）", "task_type": "follow_up", "due_days": 76}
      ]
    },
    {
      "key": "li_jianguo",
      "name": "李建国",
      "gender": "male",
      "age": 68,
      "records": [
        {
          "key": "initial_visit",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 60,
          "chief_complaint": "记忆力下降伴步态不稳2年",
          "present_illness": "2年前起记忆力逐渐下降，伴行走不稳、小碎步，静止性震颤不明显。MMSE 16/30，MoCA 12/30。外院诊断"AD伴帕金森综合征"。",
          "auxiliary_exam": "MRI示全脑萎缩，以颞叶为著。PET示Aβ弥漫性沉积。DAT-SPECT示多巴胺转运体减低。",
          "past_history": "冠心病5年，阿司匹林100mg/日。高血压8年。",
          "content": "记忆力下降伴步态不稳2年，MMSE 16，AD伴帕金森综合征。",
          "suggestions": []
        },
        {
          "key": "surgery",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 35,
          "chief_complaint": "右侧颈深淋巴-静脉分流术（LVB）",
          "present_illness": "鼻黏膜ICG注射法，右侧颈深淋巴管扩张明显（管径0.4-0.6mm），吻合2根淋巴管至颈外静脉。术中见淋巴管内液体浑浊，流速缓慢，提示淋巴引流功能障碍。ICG确认吻合通畅。计划择期行左侧LVB。",
          "content": "右侧颈深LVB，吻合2根淋巴管，淋巴管扩张明显。",
          "suggestions": []
        },
        {
          "key": "postop_1m",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "右侧LVB术后1月，右颈肿胀伴头晕加重1天",
          "present_illness": "术后2周复查时恢复尚可。3天前开始右颈部隐痛，昨日出现右颈明显肿胀（约3×4cm），质软，伴头晕加重。无发热，无肢体无力。",
          "physical_exam": "右颈部可触及3×4cm肿物，质软，无压痛，皮肤无红热。双侧瞳孔等大等圆，四肢肌力V级。",
          "content": "LVB术后1月，右颈肿胀3×4cm，头晕加重，疑淋巴漏/血栓。",
          "suggestions": [
            {"section": "differential", "content": "术后淋巴漏 / 吻合口血栓", "detail": "LVB术后1月出现颈部肿胀，需首先排除：①淋巴漏导致淋巴囊肿形成 ②吻合口血栓导致淋巴回流障碍。术中已见淋巴管扩张、液体浑浊，术后静脉压力变化可能导致血液返流形成血栓。 [KB-1]", "confidence": "高", "urgency": "urgent"},
            {"section": "workup", "content": "急查颈部超声 + ICG荧光复查吻合口", "detail": "颈部超声评估肿物性质（囊性/实性）及与吻合口的关系。ICG荧光检查评估吻合口是否仍通畅。必要时头颅CT排除颅内异常。 [KB-1]", "confidence": "高", "urgency": "urgent"},
            {"section": "treatment", "content": "局部加压包扎，必要时穿刺引流", "detail": "若为淋巴囊肿，先行加压包扎观察，必要时超声引导下穿刺引流。若确认吻合口血栓，需评估是否需要修复吻合或二次手术。暂停阿司匹林需权衡冠心病风险。 [KB-1]", "confidence": "中", "urgency": "urgent"}
          ]
        }
      ],
      "messages": [
        {"content": "术后恢复还可以，就是脖子有点紧绷的感觉", "triage": "routine", "auto_send": true, "ai_reply": "术后早期颈部轻度紧绷感是正常的，随着切口愈合和局部消肿会逐渐缓解。请避免颈部大幅度活动，保持切口清洁。如果紧绷感持续加重或出现明显肿胀，请及时联系。", "days_ago": 20},
        {"content": "陆医生，我爸脖子那里肿了一块，还说头晕比之前重了", "triage": "urgent", "auto_send": false, "ai_reply": "LVB术后出现颈部肿胀伴头晕加重需要重视。请尽快带您父亲到医院就诊，需要做颈部超声检查明确肿胀原因。如果肿胀迅速增大或出现呼吸困难，请立即到急诊就诊。 [KB-1]", "days_ago": 1},
        {"content": "今天肿得更大了，要去急诊吗？", "triage": "urgent", "auto_send": false, "ai_reply": "颈部肿胀进行性增大建议立即到医院急诊就诊。需要紧急做颈部超声和头颅CT检查，排除淋巴漏或吻合口血栓等术后并发症。到达后请告知急诊医生是LVB术后患者。 [KB-1]", "days_ago": 0}
      ],
      "tasks": [
        {"title": "尽快安排颈部超声 + 头颅CT检查", "task_type": "checkup", "due_days": 1, "content": "紧急：术后颈部肿胀，排除淋巴漏/吻合口血栓"},
        {"title": "ICG荧光复查吻合口通畅性", "task_type": "checkup", "due_days": 3}
      ]
    },
    {
      "key": "wang_meihua",
      "name": "王美华",
      "gender": "female",
      "age": 65,
      "records": [
        {
          "key": "referral",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 14,
          "chief_complaint": "记忆力下降2年，由外院神经内科转入",
          "present_illness": "外院诊断"认知功能障碍待查"，口服多奈哌齐5mg/日1年，症状仍在进展。MRI示双侧海马轻度萎缩（Scheltens 2级）。未做PET-CT。",
          "past_history": "高血脂5年（瑞舒伐他汀10mg/日）。无高血压、糖尿病。无脑血管病史。",
          "family_history": "母亲70岁后出现"老糊涂"，未正式诊断。",
          "content": "外院转诊，认知障碍待查，MMSE 22，MoCA 18，海马轻度萎缩。",
          "suggestions": []
        },
        {
          "key": "first_visit",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "记忆力进行性下降2年，找词困难半年",
          "present_illness": "2年前开始出现近事遗忘——反复询问同一问题、忘记约定。近半年加重，出现找词困难（想说"钥匙"说成"那个开门的"），计算力下降（买菜算不清账），在熟悉的超市迷路2次。外院口服多奈哌齐1年余，自觉无明显效果。无肢体无力，无头痛，无尿失禁，无性格改变。",
          "physical_exam": "MMSE 22/30（回忆-3，计算-3，定向-2），MoCA 18/30。步态正常，无锥体外系征。",
          "auxiliary_exam": "外院MRI示双侧海马轻度萎缩。余缺。",
          "content": "记忆力下降2年伴找词困难，MMSE 22，步态正常，无尿失禁。需鉴别AD/VCI/NPH。",
          "suggestions": [
            {"section": "differential", "content": "阿尔茨海默病（AD）", "detail": "隐匿起病，进行性加重，以近事遗忘为首发，逐渐出现找词困难、计算力下降、空间定向障碍。符合AD典型临床表现。MRI示海马萎缩支持诊断。家族史阳性增加AD可能。需PET-CT确认Aβ沉积。 [KB-2]", "confidence": "高"},
            {"section": "differential", "content": "血管性认知障碍（VCI）— 需排除", "detail": "患者有高血脂病史，是脑血管病危险因素。但无明确卒中史、无局灶体征、起病方式为缓慢进展而非阶梯样下降，不支持典型血管性痴呆。需MRI排除静默性脑梗死和白质病变。 [KB-2]", "confidence": "中"},
            {"section": "differential", "content": "正常压力脑积水（NPH）— 需排除", "detail": "NPH经典三联征为步态异常、认知下降、尿失禁。该患者步态正常、无尿失禁，不支持NPH。但需MRI评估脑室是否不成比例扩大。NPH是可手术逆转的痴呆原因，需明确排除。 [KB-2]", "confidence": "中"},
            {"section": "workup", "content": "PET-CT + MRI黑血序列 + 腰穿", "detail": "①PET-CT（Aβ显像）：确认Aβ沉积，同时作为LVB手术适应证核心指标 ②头颅MRI（含黑血序列）：评估白质病变、脑室形态，并建立颈深淋巴基线 ③腰穿脑脊液检查（Aβ42/p-tau/t-tau）：辅助AD诊断。 [KB-2]", "confidence": "高"},
            {"section": "treatment", "content": "继续多奈哌齐 + 待确诊后评估LVB手术", "detail": "目前继续口服多奈哌齐5mg/日。若PET-CT确认Aβ阳性且排除NPH/VCI，MMSE 22分属轻度范围，文献提示MMSE≥15分的AD患者LVB术后改善概率较高，可考虑手术评估。 [KB-1]", "confidence": "高"}
          ]
        }
      ],
      "messages": [
        {"content": "陆医生，我这个病做手术真的能好吗？", "triage": "question", "auto_send": false, "ai_reply": "颈深淋巴-静脉分流术（LVB）是通过改善脑部淋巴引流来帮助清除导致阿尔茨海默病的有害蛋白。从目前的临床经验看，多数患者术后会有不同程度的认知改善，主要表现在记忆力、情绪和日常行为方面的好转。不过，我们需要先完善检查确认诊断，才能评估您是否适合手术。 [KB-1]", "days_ago": 7},
        {"content": "手术风险大吗？需要住几天院？", "triage": "question", "auto_send": false, "ai_reply": "LVB手术在显微镜下进行，切口在颈部，创伤较小。一般住院5-7天。主要风险包括淋巴漏、吻合口血栓等，发生率较低。手术时间约2-4小时。具体情况等检查结果出来后在门诊详细说明。 [KB-1]", "days_ago": 5},
        {"content": "检查报告都做完了，什么时候能安排手术？", "triage": "routine", "auto_send": true, "ai_reply": "好的，我们会尽快安排陆医生查看您的检查结果。确认手术适应证后会通知您住院时间，请保持电话畅通。", "days_ago": 1}
      ],
      "tasks": [
        {"title": "预约PET-CT（Aβ显像）— 确认AD诊断 + LVB手术评估", "task_type": "checkup", "due_days": 7},
        {"title": "预约头颅MRI（含黑血序列）— 排除NPH/VCI + 淋巴基线", "task_type": "checkup", "due_days": 7},
        {"title": "腰穿脑脊液检查（Aβ42/p-tau/t-tau）", "task_type": "checkup", "due_days": 14}
      ]
    },
    {
      "key": "chen_weiqiang",
      "name": "陈伟强",
      "gender": "male",
      "age": 71,
      "records": [
        {
          "key": "referral",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 21,
          "chief_complaint": "视物模糊伴记忆力下降1年，由外院眼科+神经内科联合转诊",
          "present_illness": "1年前开始视物模糊，眼科检查未见明确器质性病变，配镜后无改善。同期出现记忆力下降和反复头晕。外院MRI示双侧颞叶萎缩，枕叶皮层变薄。",
          "past_history": "高血压8年（缬沙坦80mg/日），高血脂（阿托伐他汀）。无糖尿病。无耳部疾病史。",
          "content": "外院转诊，视物模糊+记忆力下降+头晕1年，眼科无器质性病变，颞叶+枕叶萎缩。",
          "suggestions": []
        },
        {
          "key": "first_visit",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "视物模糊伴记忆力下降1年，反复头晕半年",
          "present_illness": "1年前开始视物模糊，"像隔了一层水汽"，看东西不清楚但眼科查不出问题。同期出现记忆力下降，忘记家人生日、重复购买相同物品。半年前开始反复头晕，非旋转性，与体位变化无关，持续数小时自行缓解。近3月加重——阅读困难（看不清字但并非视力问题），空间感差（停车困难、判断距离不准）。无幻视，无帕金森样症状。",
          "physical_exam": "MMSE 21/30（视空间-4，回忆-3，计算-2），MoCA 16/30（视空间/执行功能明显受损）。步态正常，无震颤。双侧瞳孔正常，视力矫正后0.8/0.6。",
          "auxiliary_exam": "外院MRI示双侧颞叶萎缩，枕叶皮层变薄。余缺。",
          "content": "视物模糊+记忆+头晕，MMSE 21（视空间-4），枕叶变薄。需鉴别PCA-AD/DLB。",
          "suggestions": [
            {"section": "differential", "content": "后皮质萎缩型阿尔茨海默病（PCA-AD）", "detail": "以视空间功能障碍为突出表现（视物模糊、阅读困难、空间感差），伴记忆力下降，MRI示枕叶皮层变薄。PCA是AD的非典型变异型，病理基础仍为Aβ沉积，但分布以顶枕叶为主。MMSE视空间项失分显著支持此诊断。 [KB-2]", "confidence": "高"},
            {"section": "differential", "content": "路易体痴呆（DLB）— 需排除", "detail": "DLB也可出现视觉症状和认知波动。但该患者无典型幻视、无帕金森运动症状、无REM睡眠行为障碍，不支持DLB核心诊断标准。DAT-SPECT可辅助排除。 [KB-2]", "confidence": "中"},
            {"section": "differential", "content": "颅神经相关性淋巴水肿（值得注意）", "detail": "临床发现部分LVB术后患者视物模糊和头晕症状获得改善。推测颈深LVB除加快脑淋巴循环外，可能减轻眶内和内听道的颅神经相关性淋巴水肿。该患者若确诊AD，视觉和眩晕症状可能从LVB中额外获益。 [KB-1]", "confidence": "中"},
            {"section": "workup", "content": "PET-CT（FDG+Aβ双示踪）+ 视觉诱发电位 + 前庭功能", "detail": "①PET-CT（Aβ显像）：确认Aβ沉积，尤其关注顶枕叶分布 ②FDG-PET：评估后部代谢减低（PCA特征）③视觉诱发电位（VEP）：排除视通路器质性病变 ④前庭功能检查：排除外周性眩晕 ⑤MRI黑血序列：建立颈深淋巴基线。 [KB-2]", "confidence": "高"}
          ]
        }
      ],
      "messages": [
        {"content": "陆医生，我看东西模糊到底是眼睛的问题还是脑子的问题？", "triage": "question", "auto_send": false, "ai_reply": "从您的检查来看，眼睛本身没有大问题。您的视物模糊可能与大脑处理视觉信息的区域有关——这在部分认知障碍患者中可以出现。我们安排的PET-CT和视觉诱发电位检查可以帮助明确原因。值得一提的是，有些类似症状的患者在LVB手术后视觉有所改善。 [KB-1]", "days_ago": 10},
        {"content": "头晕会不会是耳朵的问题？要不要去看耳鼻喉？", "triage": "routine", "auto_send": true, "ai_reply": "好问题。我们已经安排了前庭功能检查，可以评估内耳是否有问题。您的头晕特点（非旋转性、与体位无关）更可能与脑部有关，但我们会全面排查。检查完成后再综合判断。", "days_ago": 5},
        {"content": "检查要做好几项，能不能集中一两天做完？", "triage": "routine", "auto_send": true, "ai_reply": "我们会尽量协调安排集中检查。PET-CT需要提前预约，其他检查可以当天完成。预约确认后会通知您具体时间安排。", "days_ago": 2}
      ],
      "tasks": [
        {"title": "预约PET-CT（Aβ + FDG双示踪）— 确认AD亚型", "task_type": "checkup", "due_days": 7},
        {"title": "视觉诱发电位（VEP）— 排除视通路病变", "task_type": "checkup", "due_days": 7},
        {"title": "前庭功能检查 — 排除外周性眩晕", "task_type": "checkup", "due_days": 7},
        {"title": "头颅MRI（含黑血序列）— 淋巴基线评估", "task_type": "checkup", "due_days": 10}
      ]
    },
    {
      "key": "liu_shufen",
      "name": "刘淑芬",
      "gender": "female",
      "age": 70,
      "records": [
        {
          "key": "initial_visit",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 210,
          "chief_complaint": "记忆力下降4年，近1年加速恶化",
          "present_illness": "4年前出现记忆力下降，渐进性加重。近1年明显加速：不认识邻居，做饭忘记关火，曾走失1次。MMSE 15/30，MoCA 10/30。CDR 2分（中度痴呆）。",
          "past_history": "高血压20年，糖尿病10年，骨质疏松。多奈哌齐+美金刚联合治疗2年。",
          "auxiliary_exam": "PET-CT示双侧颞顶叶广泛Aβ沉积。MRI示双侧海马萎缩（Scheltens 3级），额叶萎缩。",
          "content": "AD 4年，MMSE 15，广泛Aβ沉积，海马+额叶萎缩。",
          "suggestions": []
        },
        {
          "key": "surgery_and_3m",
          "record_type": "visit",
          "status": "completed",
          "days_ago": 90,
          "chief_complaint": "双侧颈深LVB手术 + 术后3月随访",
          "present_illness": "手术：双侧颈深LVB，吻合3根淋巴管。术中未见明显淋巴管扩张，管径偏细（0.2-0.3mm），吻合技术要求高。术后3月：MMSE升至19分（↑4分），能认出家人，情绪好转。强迫性反复洗手行为消失。家属非常满意。",
          "content": "双侧LVB（管径偏细），术后3月MMSE↑4分，认知行为显著改善。",
          "suggestions": []
        },
        {
          "key": "postop_6m",
          "record_type": "intake_summary",
          "status": "pending_review",
          "days_ago": 0,
          "chief_complaint": "双侧LVB术后6月，认知功能部分回退2月",
          "present_illness": "术后3月时改善明显，但近2月家属反映记忆力再次下降，又开始不认识邻居，偶有走失倾向。MMSE回退至16/30（较3月时↓3分）。MoCA 11/30。情绪较前波动，强迫行为未复发。",
          "content": "LVB术后6月，MMSE从19回退至16。需鉴别吻合口狭窄vs AD进展。",
          "suggestions": [
            {"section": "differential", "content": "吻合口狭窄/血栓 vs AD自然进展", "detail": "术后3月改善后出现回退，需首先排除吻合口狭窄或血栓导致淋巴引流效果下降。该患者术中淋巴管管径偏细（0.2-0.3mm），是术后吻合口狭窄的高风险因素。同时不排除重度AD的自然进展。 [KB-1]", "confidence": "高", "urgency": "urgent"},
            {"section": "workup", "content": "ICG荧光复查 + PET-CT对比", "detail": "ICG荧光检查评估双侧吻合口通畅性（关键检查）。复查PET-CT与术前/术后3月对比Aβ清除趋势。如吻合口不通畅，需评估是否具备二次手术条件。 [KB-1]", "confidence": "高"},
            {"section": "treatment", "content": "维持药物 + 加强认知干预", "detail": "继续多奈哌齐+美金刚联合方案，不建议减药。加强认知康复训练频次。待检查结果明确后再讨论后续手术方案。 [KB-1]", "confidence": "高"}
          ]
        }
      ],
      "messages": [
        {"content": "陆医生，术后三个月的时候明显好多了，我们全家都很高兴", "triage": "info", "auto_send": true, "ai_reply": "很高兴听到改善的消息。术后3个月是观察疗效的重要节点，认知功能的改善说明淋巴引流在发挥作用。请继续保持规律服药和认知训练，定期来院复查。", "days_ago": 60},
        {"content": "陆医生，我妈最近又开始忘事了，是不是手术白做了？", "triage": "concern", "auto_send": false, "ai_reply": "术后出现症状波动并不罕见，不代表手术没有效果。之前3个月的改善说明手术本身是成功的。现在需要检查是否有吻合口狭窄等可纠正的原因。建议您尽快带母亲来医院做一次ICG荧光检查，评估淋巴引流情况，我们再根据结果制定下一步方案。 [KB-1]", "days_ago": 3},
        {"content": "需要再做一次手术吗？", "triage": "question", "auto_send": false, "ai_reply": "目前还不能确定是否需要再次手术。先完成检查评估吻合口情况，如果确认是吻合口狭窄导致的，有多种处理方案可以考虑。我们团队也在研发新的淋巴静脉分流装置，可以降低再手术的难度。等检查结果出来后，陆医生会和您详细讨论方案。 [KB-1]", "days_ago": 1}
      ],
      "tasks": [
        {"title": "安排ICG荧光复查吻合口通畅性", "task_type": "checkup", "due_days": 5, "content": "优先：术后6月认知回退，排除吻合口狭窄"},
        {"title": "复查PET-CT（与术前/术后3月对比）", "task_type": "checkup", "due_days": 14}
      ]
    }
  ]
}
```

Note: The JSON above is the complete content. Write it to `src/channels/web/ui/preseed_data.json`.

- [ ] **Step 2: Validate JSON is parseable**

Run: `.venv/bin/python -c "import json; d=json.load(open('src/channels/web/ui/preseed_data.json')); print(f'{len(d[\"patients\"])} patients, {len(d[\"knowledge_items\"])} KB items')"`

Expected: `5 patients, 2 KB items`

- [ ] **Step 3: Validate through Pydantic**

Run: `.venv/bin/python -c "import json; from channels.web.ui.preseed_schema import SeedSpec; d=json.load(open('src/channels/web/ui/preseed_data.json')); s=SeedSpec(**d); print(f'Valid: {len(s.patients)} patients'); [print(f'  {p.name}: {len(p.records)}r {len(p.messages)}m {len(p.tasks)}t') for p in s.patients]"`

Expected:
```
Valid: 5 patients
  张秀兰: 3r 4m 2t
  李建国: 3r 3m 2t
  王美华: 2r 3m 3t
  陈伟强: 2r 3m 4t
  刘淑芬: 3r 3m 2t
```

---

### Task 4: Create `preseed_service.py` — seed orchestration

**Files:**
- Create: `src/channels/web/ui/preseed_service.py`

- [ ] **Step 1: Create the service module**

```python
"""
Preseed demo data service — creates/resets/deletes demo data for onboarding.

All operations run in a single transaction. No intermediate commits.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ai_suggestion import AISuggestion, SuggestionSection
from db.models.doctor import DoctorKnowledgeItem
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB, RecordStatus
from db.models.tasks import DoctorTask

from .preseed_schema import SeedSpec

_SEED_SOURCE = "onboarding_preseed"
_DATA_FILE = Path(__file__).parent / "preseed_data.json"
_spec_cache: Optional[SeedSpec] = None


def _load_spec() -> SeedSpec:
    global _spec_cache
    if _spec_cache is None:
        with open(_DATA_FILE, encoding="utf-8") as f:
            _spec_cache = SeedSpec(**json.load(f))
    return _spec_cache


def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _resolve_kb_refs(text: str, kb_map: dict[str, int]) -> str:
    for placeholder, real_id in kb_map.items():
        text = text.replace(placeholder, f"[KB-{real_id}]")
    return text


class SeedPatientResult(BaseModel):
    id: int
    name: str
    record_count: int = 0
    message_count: int = 0
    task_count: int = 0


class SeedResult(BaseModel):
    status: str = "ok"
    already_seeded: bool = False
    knowledge_items: list[dict] = []
    patients: list[SeedPatientResult] = []


async def is_seeded(db: AsyncSession, doctor_id: str) -> bool:
    """Check if any preseed data exists for this doctor."""
    row = (await db.execute(
        select(Patient.id).where(
            Patient.doctor_id == doctor_id,
            Patient.seed_source == _SEED_SOURCE,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def cleanup_seed_data(db: AsyncSession, doctor_id: str) -> None:
    """Delete all preseed data for a doctor. Order respects FK relationships."""
    # 1. AI suggestions (FK → records)
    await db.execute(delete(AISuggestion).where(
        AISuggestion.doctor_id == doctor_id,
        AISuggestion.seed_source == _SEED_SOURCE,
    ))
    # 2. Message drafts (FK → messages)
    await db.execute(delete(MessageDraft).where(
        MessageDraft.doctor_id == doctor_id,
        MessageDraft.seed_source == _SEED_SOURCE,
    ))
    # 3. Tasks (FK → patients/records)
    await db.execute(delete(DoctorTask).where(
        DoctorTask.doctor_id == doctor_id,
        DoctorTask.seed_source == _SEED_SOURCE,
    ))
    # 4. Messages (FK → patients)
    await db.execute(delete(PatientMessage).where(
        PatientMessage.doctor_id == doctor_id,
        PatientMessage.seed_source == _SEED_SOURCE,
    ))
    # 5. Records (FK → patients)
    await db.execute(delete(MedicalRecordDB).where(
        MedicalRecordDB.doctor_id == doctor_id,
        MedicalRecordDB.seed_source == _SEED_SOURCE,
    ))
    # 6. Knowledge items
    await db.execute(delete(DoctorKnowledgeItem).where(
        DoctorKnowledgeItem.doctor_id == doctor_id,
        DoctorKnowledgeItem.seed_source == _SEED_SOURCE,
    ))
    # 7. Patients (last — others reference patient_id)
    await db.execute(delete(Patient).where(
        Patient.doctor_id == doctor_id,
        Patient.seed_source == _SEED_SOURCE,
    ))
    await db.flush()


async def seed_demo_data(db: AsyncSession, doctor_id: str) -> SeedResult:
    """Create all preseed demo data in one transaction.

    Non-destructive: if data already exists, returns existing counts.
    Caller must call db.commit() after this returns.
    """
    if await is_seeded(db, doctor_id):
        return await _build_existing_result(db, doctor_id)

    spec = _load_spec()
    now = datetime.now(timezone.utc)

    # Phase 1: Knowledge items
    kb_map: dict[str, int] = {}  # "[KB-1]" → real_id
    kb_results = []
    for i, kb_spec in enumerate(spec.knowledge_items, start=1):
        item = DoctorKnowledgeItem(
            doctor_id=doctor_id,
            title=kb_spec.title,
            content=json.dumps({"text": kb_spec.content}, ensure_ascii=False),
            category="custom",
            seed_source=_SEED_SOURCE,
            created_at=now - timedelta(hours=1),
        )
        db.add(item)
        await db.flush()
        kb_map[f"[KB-{i}]"] = item.id
        kb_results.append({"id": item.id, "title": kb_spec.title})

    # Phase 2: Patients + records + suggestions + messages + drafts + tasks
    patient_results = []
    for p_spec in spec.patients:
        # Create patient
        year_of_birth = now.year - p_spec.age
        patient = Patient(
            doctor_id=doctor_id,
            name=p_spec.name,
            gender=p_spec.gender,
            year_of_birth=year_of_birth,
            seed_source=_SEED_SOURCE,
            created_at=_ts(max((r.days_ago for r in p_spec.records), default=0)),
        )
        db.add(patient)
        await db.flush()

        p_result = SeedPatientResult(id=patient.id, name=patient.name)

        # Records + suggestions
        for r_spec in p_spec.records:
            record = MedicalRecordDB(
                patient_id=patient.id,
                doctor_id=doctor_id,
                record_type=r_spec.record_type,
                status=r_spec.status,
                chief_complaint=r_spec.chief_complaint,
                present_illness=_resolve_kb_refs(r_spec.present_illness or "", kb_map) or None,
                past_history=r_spec.past_history,
                allergy_history=r_spec.allergy_history,
                family_history=r_spec.family_history,
                personal_history=r_spec.personal_history,
                physical_exam=r_spec.physical_exam,
                auxiliary_exam=r_spec.auxiliary_exam,
                content=r_spec.content,
                seed_source=_SEED_SOURCE,
                created_at=_ts(r_spec.days_ago),
                updated_at=_ts(r_spec.days_ago),
            )
            db.add(record)
            await db.flush()
            p_result.record_count += 1

            for s_spec in r_spec.suggestions:
                suggestion = AISuggestion(
                    record_id=record.id,
                    doctor_id=doctor_id,
                    section=s_spec.section,
                    content=s_spec.content,
                    detail=_resolve_kb_refs(s_spec.detail, kb_map),
                    confidence=s_spec.confidence,
                    urgency=s_spec.urgency,
                    intervention=s_spec.intervention,
                    seed_source=_SEED_SOURCE,
                )
                db.add(suggestion)

        # Messages + drafts
        for m_spec in p_spec.messages:
            inbound = PatientMessage(
                patient_id=patient.id,
                doctor_id=doctor_id,
                content=m_spec.content,
                direction="inbound",
                source="patient",
                triage_category=m_spec.triage,
                ai_handled=m_spec.auto_send,
                seed_source=_SEED_SOURCE,
                created_at=_ts(m_spec.days_ago),
            )
            db.add(inbound)
            await db.flush()
            p_result.message_count += 1

            reply_text = _resolve_kb_refs(m_spec.ai_reply, kb_map)

            if m_spec.auto_send:
                outbound = PatientMessage(
                    patient_id=patient.id,
                    doctor_id=doctor_id,
                    content=reply_text,
                    direction="outbound",
                    source="ai",
                    reference_id=inbound.id,
                    seed_source=_SEED_SOURCE,
                    created_at=_ts(m_spec.days_ago) + timedelta(minutes=2),
                )
                db.add(outbound)
            else:
                draft = MessageDraft(
                    doctor_id=doctor_id,
                    patient_id=str(patient.id),
                    source_message_id=inbound.id,
                    draft_text=reply_text,
                    cited_knowledge_ids=json.dumps(
                        list(kb_map.values()), ensure_ascii=False
                    ),
                    status=DraftStatus.generated.value,
                    seed_source=_SEED_SOURCE,
                )
                db.add(draft)

        # Tasks
        for t_spec in p_spec.tasks:
            task = DoctorTask(
                doctor_id=doctor_id,
                patient_id=patient.id,
                task_type=t_spec.task_type,
                title=t_spec.title,
                content=t_spec.content,
                status="pending",
                due_at=now + timedelta(days=t_spec.due_days),
                source_type=_SEED_SOURCE,
                seed_source=_SEED_SOURCE,
            )
            db.add(task)
            p_result.task_count += 1

        patient_results.append(p_result)

    return SeedResult(
        knowledge_items=kb_results,
        patients=patient_results,
    )


async def _build_existing_result(db: AsyncSession, doctor_id: str) -> SeedResult:
    """Build result from existing seeded data."""
    patients = (await db.execute(
        select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.seed_source == _SEED_SOURCE,
        )
    )).scalars().all()

    kb_items = (await db.execute(
        select(DoctorKnowledgeItem).where(
            DoctorKnowledgeItem.doctor_id == doctor_id,
            DoctorKnowledgeItem.seed_source == _SEED_SOURCE,
        )
    )).scalars().all()

    results = []
    for p in patients:
        results.append(SeedPatientResult(id=p.id, name=p.name))

    return SeedResult(
        already_seeded=True,
        knowledge_items=[{"id": k.id, "title": k.title} for k in kb_items],
        patients=results,
    )
```

- [ ] **Step 2: Verify import**

Run: `.venv/bin/python -c "from channels.web.ui.preseed_service import seed_demo_data, cleanup_seed_data; print('OK')"`

Expected: `OK`

---

### Task 5: Add API endpoints to `doctor_profile_handlers.py`

**Files:**
- Modify: `src/channels/web/ui/doctor_profile_handlers.py`

- [ ] **Step 1: Add the 3 seed-demo endpoints**

At the end of `doctor_profile_handlers.py` (after the existing `ensure_onboarding_examples` endpoint), add:

```python
# ── Preseed Demo Data ─────────────────────────────────────────────────────────

def _require_demo_seed_access():
    if os.environ.get("ALLOW_DEMO_SEED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/api/manage/onboarding/seed-demo", include_in_schema=True)
async def seed_demo(
    body: OnboardingExamplesRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Create preseed demo data (non-destructive). Safe for retry."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    from .preseed_service import seed_demo_data
    async with AsyncSessionLocal() as db:
        result = await seed_demo_data(db, resolved_doctor_id)
        if not result.already_seeded:
            await db.commit()
    return result.model_dump()


@router.post("/api/manage/onboarding/seed-demo/reset", include_in_schema=True)
async def seed_demo_reset(
    body: OnboardingExamplesRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Delete and recreate all preseed demo data."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    from .preseed_service import cleanup_seed_data, seed_demo_data
    async with AsyncSessionLocal() as db:
        await cleanup_seed_data(db, resolved_doctor_id)
        result = await seed_demo_data(db, resolved_doctor_id)
        await db.commit()
    return result.model_dump()


@router.delete("/api/manage/onboarding/seed-demo", include_in_schema=True)
async def seed_demo_delete(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Remove all preseed demo data for a doctor."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    from .preseed_service import cleanup_seed_data
    async with AsyncSessionLocal() as db:
        await cleanup_seed_data(db, resolved_doctor_id)
        await db.commit()
    return {"status": "ok", "deleted": True}
```

- [ ] **Step 2: Verify routes**

Run: `.venv/bin/python -c "from channels.web.ui.doctor_profile_handlers import router; print([r.path for r in router.routes if 'seed' in r.path])"`

Expected: includes `seed-demo`, `seed-demo/reset`

---

### Task 6: Frontend — call seed-demo on onboarding completion

**Files:**
- Modify: `frontend/web/src/api.js`
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Add `seedDemo` to api.js**

In `frontend/web/src/api.js`, add after the existing API functions:

```javascript
export async function seedDemo(doctorId) {
  return post("/api/manage/onboarding/seed-demo", { doctor_id: doctorId });
}
```

- [ ] **Step 2: Call seedDemo in OnboardingWizard on completion**

In `frontend/web/src/pages/doctor/OnboardingWizard.jsx`, in the `handleAdvance` function, when `next > TOTAL_STEPS` (wizard complete), add the seed call before navigating:

Find the block:
```javascript
    if (next > TOTAL_STEPS) {
      markWizardDone(doctorId, "completed");
```

Change to:
```javascript
    if (next > TOTAL_STEPS) {
      markWizardDone(doctorId, "completed");
      // Seed demo data in background — don't block navigation
      import("../../api").then(({ seedDemo }) => seedDemo(doctorId).catch(() => {}));
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend/web && npx vite build --mode development 2>&1 | tail -3`

Expected: build succeeds

---

### Task 7: End-to-end verification

- [ ] **Step 1: Start the server**

Run: `cd /Volumes/ORICO/Code/doctor-ai-agent && ./dev.sh` (in a separate terminal)

- [ ] **Step 2: Test seed-demo endpoint**

Run: `curl -s -X POST http://localhost:8000/api/manage/onboarding/seed-demo -H 'Content-Type: application/json' -d '{"doctor_id":"test_doctor"}' | python3 -m json.tool | head -20`

Expected: JSON with `status: ok`, `already_seeded: false`, 5 patients, 2 knowledge items

- [ ] **Step 3: Test idempotency**

Run the same curl again. Expected: `already_seeded: true`

- [ ] **Step 4: Test reset**

Run: `curl -s -X POST http://localhost:8000/api/manage/onboarding/seed-demo/reset -H 'Content-Type: application/json' -d '{"doctor_id":"test_doctor"}' | python3 -m json.tool | head -5`

Expected: `status: ok`, `already_seeded: false` (fresh data)

- [ ] **Step 5: Test delete**

Run: `curl -s -X DELETE 'http://localhost:8000/api/manage/onboarding/seed-demo?doctor_id=test_doctor' | python3 -m json.tool`

Expected: `{ "status": "ok", "deleted": true }`

---

## Dependency Order

```
Task 1 (seed_source columns) — independent, do first
    ↓
Task 2 (preseed_schema.py) — independent of Task 1
    ↓
Task 3 (preseed_data.json) — depends on Task 2 (validated by schema)
    ↓
Task 4 (preseed_service.py) — depends on Tasks 1, 2, 3
    ↓
Task 5 (API endpoints) — depends on Task 4
    ↓
Task 6 (Frontend trigger) — depends on Task 5
    ↓
Task 7 (E2E verification) — depends on all
```

Tasks 1 and 2 can run in parallel. Task 3 can start after Task 2.
