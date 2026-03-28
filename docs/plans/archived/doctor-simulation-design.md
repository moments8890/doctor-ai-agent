# Doctor Simulation Pipeline — Design

**Status:** Planned (Codex-reviewed)
**Date:** 2026-03-25
**Depends on:** Patient sim pipeline (done), hybrid extraction (done)

## Goal

Test doctor interview extraction accuracy — does the system correctly extract
structured clinical fields from dense clinical input with abbreviations, mixed
languages, OCR artifacts, and multi-turn dictation?

## 8 Doctor Personas

| ID | Style | Turns | What it tests |
|----|-------|-------|---------------|
| D1 | 详细主治医师 | 1 | Full sentences, well-structured, baseline accuracy |
| D2 | 简洁外科/急诊 | 1 | Terse fragments, heavy abbreviations (STEMI, PCI, EF, LAD) |
| D3 | OCR粘贴 | 1 | Broken lines, OCR artifacts, formatting noise |
| D4 | 多轮口述 | 3 | Incremental turns with addenda, merge quality |
| D5 | 中英混合 | 1 | Chinese/English mix with labs, drugs, units |
| D6 | 否定为主随访 | 1 | Many "无/否认" statements, 阴性症状集群 ("无发热咳嗽咳痰...") |
| D7 | 复制粘贴冲突 | 1 | Copy-pasted content with duplicates/contradictions from prior visit |
| D8 | 模板填空 | 1 | Semi-structured template input ("主诉：____ 现病史：____") |

## Clinical Shorthand the System Must Handle

### English abbreviations (common in Chinese EMR)
```
BP, HR, EF, LAD, RCA, LCX, PCI, DES, BMS, TIMI, STEMI, NSTEMI,
TIA, SAH, ICH, AVM, DSA, CTA, MRA, CEA, CAS, mRS, NIHSS,
CHD, HFrEF, HFpEF, AF, VT, VF, IABP, ECMO, CRRT
```

### Lab values
```
hs-cTnI 3.2 ng/mL, BNP 168 pg/mL, HbA1c 7.2%, Cr 1.1 mg/dL,
ALT 45 U/L, WBC 12.3×10⁹/L, PLT 180, INR 1.2, PT 12.5s,
CK-MB 25 U/L, TSH 2.5 mIU/L, LDL-C 3.2 mmol/L, HGB 120 g/L,
CrCl 60 mL/min, FT3, FT4, Hcy 15 μmol/L, D-dimer 0.5 mg/L
```

### Drug names — brand → generic mapping (critical for Chinese EMR)
```
波立维 → 氯吡格雷 (clopidogrel)
拜新同 → 硝苯地平控释片 (nifedipine CR)
立普妥 → 阿托伐他汀 (atorvastatin)
可定 → 瑞舒伐他汀 (rosuvastatin)
倍他乐克 → 美托洛尔 (metoprolol)
代文 → 缬沙坦 (valsartan)
安博维 → 厄贝沙坦 (irbesartan)
格华止 → 二甲双胍 (metformin)
拜阿司匹林 → 阿司匹林肠溶片 (enteric-coated aspirin)
泰嘉 → 氯吡格雷 (another brand)
ASA / 阿司匹林, 替格瑞洛 / ticagrelor, 氨氯地平 / amlodipine,
肝素 / heparin, 华法林 / warfarin, 依诺肝素 / enoxaparin
```

The system should recognize both brand and generic names as equivalent.

### Dosing notation
```
5mg qd, 0.5 bid, 300mg ld (loading dose), 8000u iv,
75mg po qd, 20mg qn, 100mg/d, 0.4ml ih q12h
```

### Negation patterns (单项)
```
否认, 无, (-), 未见, 不详, 无殊, 无特殊, 未诉, 否认烟酒,
无药物过敏, 无家族遗传病史, 无手术外伤史
```

### 阴性症状集群 (negative symptom clusters — common in Chinese EMR)
Doctors often list multiple negatives in one breath. System must extract each:
```
"无发热咳嗽咳痰" → 分别提取：无发热、无咳嗽、无咳痰
"否认头晕头痛恶心呕吐" → 分别提取4项否认
"无胸闷气短心悸" → 3项否认
"否认肝炎结核等传染病史" → 否认传染病
"无烟酒嗜好" → 无吸烟、无饮酒
"双瞳等大等圆，对光反射灵敏" → 阴性神经体征
```

### Time shorthands
```
90min, 10y, 2h, 3d, 6m, 术后3月, 病程2周, 反复发作5年
```

## Persona Format

Different from patient sim — uses `turn_plan` (scripted text) + `gold_soap` (expected output):

```json
{
  "id": "D2",
  "name": "简洁外科急诊",
  "style": "telegraphic",
  "description": "急诊科医生，用语极简，大量缩写",
  "turn_plan": [
    {
      "turn": 1,
      "text": "张三 男 61 急诊 胸痛90min伴大汗 下壁STEMI hs-cTnI 3.2 BNP 168 EF 45% LAD 90%闭塞 PCI+DES×1 术后TIMI 3级 ASA 300mg ld 替格瑞洛180mg ld 肝素8000u iv\n既往HTN 10y 氨氯地平5mg qd DM 2y 二甲双胍0.5 bid\n青霉素过敏 否认烟酒"
    }
  ],
  "gold_soap": {
    "chief_complaint": "胸痛90min伴大汗",
    "present_illness": "下壁STEMI，hs-cTnI 3.2 ng/mL，BNP 168 pg/mL，EF 45%，LAD 90%闭塞，行PCI+DES×1，术后TIMI 3级",
    "past_history": "HTN 10y，氨氯地平5mg qd；DM 2y，二甲双胍0.5 bid",
    "allergy_history": "青霉素过敏",
    "personal_history": "否认烟酒",
    "diagnosis": "下壁STEMI",
    "treatment_plan": "ASA 300mg ld，替格瑞洛180mg ld，肝素8000u iv",
    "physical_exam": "",
    "family_history": "",
    "auxiliary_exam": "hs-cTnI 3.2，BNP 168，EF 45%"
  },
  "fact_catalog": [
    {"id": "cc_chest_pain", "field": "chief_complaint", "text": "胸痛90min伴大汗", "importance": "critical"},
    {"id": "pi_stemi", "field": "present_illness", "text": "下壁STEMI", "importance": "critical"},
    {"id": "pi_troponin", "field": "present_illness", "text": "hs-cTnI 3.2", "importance": "critical"},
    {"id": "pi_pci", "field": "present_illness", "text": "PCI+DES", "importance": "critical"},
    {"id": "ph_htn", "field": "past_history", "text": "HTN 10y 氨氯地平", "importance": "critical"},
    {"id": "ph_dm", "field": "past_history", "text": "DM 2y 二甲双胍", "importance": "critical"},
    {"id": "al_pcn", "field": "allergy_history", "text": "青霉素过敏", "importance": "critical"},
    {"id": "tp_asa", "field": "treatment_plan", "text": "ASA 300mg", "importance": "important"},
    {"id": "tp_tica", "field": "treatment_plan", "text": "替格瑞洛180mg", "importance": "important"},
    {"id": "sh_neg", "field": "personal_history", "text": "否认烟酒", "importance": "important"}
  ]
}
```

## Evaluation Dimensions (3, not 4)

| Dimension | Weight | What | How |
|-----------|--------|------|-----|
| **事实提取召回率** | 40% | Of gold_soap facts, how many captured? | 3 LLM judges vs DB fields |
| **字段归类准确率** | 30% | Facts in the correct clinical field? | Check field routing |
| **记录质量** | 30% | No hallucinations, abbreviations preserved, no duplication | Deterministic + 1 LLM |

No elicitation/disclosure/conversation quality — doctor provides all facts directly.

## Reuse from patient_sim

| Component | Reuse? |
|-----------|--------|
| `_pick_judges`, `_llm_call`, `_parse_json_response` | ✓ Copy or import |
| `_load_fields_from_db`, `CLINICAL_FIELDS` | ✓ Copy or import |
| Tier 1 DB checks | ✓ Reuse `validate_tier1` |
| Report HTML shell + CSS | ✓ Reuse, new scorecard panels |
| AI expert analysis | ✓ Reuse `analyze_results` |
| Engine loop | New — different auth, scripted turns, no patient registration |
| Validator dimensions | New — extraction-focused |
| Persona format | New — `turn_plan` + `gold_soap` |

## File Structure

```
scripts/
  run_doctor_sim.py
  doctor_sim/
    __init__.py
    engine.py          # scripted turns, doctor auth, confirm
    validator.py       # 3-dimension extraction evaluation
    report.py          # HTML report (reuse patient_sim shell)
tests/fixtures/
  doctor_sim/
    personas/
      d1_verbose_attending.json
      d2_telegraphic_surgeon.json
      d3_ocr_paste.json
      d4_multi_turn.json
      d5_bilingual_mix.json
      d6_negation_cluster.json
      d7_copy_paste_conflict.json
      d8_template_fill.json
```

## Planned: Additional Multi-Turn Personas

| ID | Style | Turns | What it tests |
|----|-------|-------|---------------|
| D11 | 分段补充 | 4-5 | Doctor enters CC first, adds fields piece by piece based on agent's missing-field guidance |
| D12 | 口述+修正 | 3 | Doctor dictates then corrects ("上面血压写错了，应该是150/95") |
| D13 | 急诊快录 | 3 | Rapid abbreviation-heavy entries ("STEMI LAD PCI" → "HTN DM" → "ASA 替格") |
| D14 | 查房记录 | 2 | Ward round style with references to prior notes ("同前" "较前好转") |

Note: D10 (复诊+历史预填) removed — returning patient history pre-population is a UI feature, not testable via the interview API alone.

## No Server Changes Needed

The doctor interview endpoints already exist and work.
Batch extraction at confirm is already implemented.
