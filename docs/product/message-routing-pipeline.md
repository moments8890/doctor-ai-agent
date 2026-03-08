# Message Routing Pipeline

> Last updated: 2026-03-08

How a doctor's message travels from WeChat (or the REST API) to the LLM — or bypasses the LLM entirely.

---

## Overview

The system routes ~90% of doctor messages without ever calling an LLM, resolving intent in under 1ms via keyword matching and regex rules. Only ambiguous messages fall through to the LLM (~3–6s).

```
Doctor sends message
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  records.chat()  (routers/records.py)               │
│                                                     │
│  Pre-checks (always run first):                     │
│  1. Rate limit check                                │
│  2. Notify control commands  ("通知"/"提醒" cmds)    │
│  3. Knowledge base commands  ("/加入知识库")          │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  fast_route(text)                                   │
│  services/ai/fast_router.py  — ~1ms, no LLM         │
│                                                     │
│  Tier 0   [PDF:/Word: prefix] → import_history      │
│           Long text (>800 chars) with 2+ dates      │
│           → import_history                          │
│                                                     │
│  Tier 1   Exact keyword sets (hot-reloadable from   │
│           config/fast_router_keywords.json):        │
│           "患者列表" / "所有患者" → list_patients    │
│           "待办任务" / "今天任务" → list_tasks        │
│           Flex regex for variants of the above      │
│                                                     │
│  Tier 2   Regex patterns:                           │
│           "查[NAME]" / "[NAME]的记录" → query_records│
│           "建档[NAME]" → create_patient             │
│           "删除[NAME]" → delete_patient             │
│           "[NAME]改成女" → update_patient            │
│           "刚才写错了" / "上一条更正" → update_record │
│           "完成任务1" → complete_task                │
│           "补充：…" / "加上…" → add_record           │
│                                                     │
│  Tier 2.5 Mined rules (data/mined_rules.json)       │
│           Learned patterns from production logs     │
│                                                     │
│  Tier 3   Clinical keyword detection → add_record   │
│           (see detail below)                        │
│                                                     │
│  Returns: IntentResult  OR  None                    │
└─────────────────────────────────────────────────────┘
        │                        │
   IntentResult (~90%)       None (~10%)
        │                        │
        ▼                        ▼
  Skip LLM entirely      ┌────────────────────────────┐
  Use intent directly     │  agent_dispatch()          │
                          │  services/ai/agent.py      │
                          │  ~3–6s                     │
                          │                            │
                          │  System prompt + history   │
                          │  + tool definitions        │
                          │  → LLM (Claude / DeepSeek) │
                          │                            │
                          │  Returns IntentResult      │
                          │  (may include              │
                          │   structured_fields)       │
                          └────────────────────────────┘
        │                        │
        └──────────┬─────────────┘
                   ▼
       Intent handler in records.chat()
       add_record / query / create / update / etc.
```

---

## Tier 3 — Clinical Keyword Detection (Most Complex)

Tier 3 decides whether a message is a **doctor dictating a clinical note** (→ `add_record`) or a **patient question / exam MCQ / encyclopedia article** (→ LLM fallback).

### Decision flow

```
Message reaches Tier 3
        │
        ▼
Contains a clinical keyword?  ──── No ──→ return None (→ LLM)
  (胸痛, 脑梗, 化疗, 结节, …)
        │ Yes
        ▼
复查-only + reminder command?  ─── Yes ──→ return None (→ LLM)
  ("复查提醒张三")
        │ No
        ▼
MCQ exam ending?               ─── Yes ──→ return None (→ LLM)
  (考虑的是, 可见于, 哪种, …)   [hard block — ignores doctor anchor]
        │ No
        ▼
Patient question pattern?      ─── Yes ──┐
  OR first-person patient voice?          │
  (怎么办, 吗?, 是不是, 我妈…)           │
        │ No                              ▼
        │                    Doctor anchor present?
        │                    (患者/主诉:/ 收入我科…)
        │                         │         │
        │                        Yes        No
        │                         │         │
        │                         ▼         ▼
        │                    return True  return None
        │                    (add_record) (→ LLM)
        │ No patient pattern
        ▼
Pediatric online consult?      ─── Yes ──→ same doctor-anchor check
  (宝宝, 宝贝, 小孩…)
        │ No
        ▼
return True → add_record
```

### Keyword sources

| Source | Count | Location |
|--------|-------|----------|
| Hardcoded baseline | ~80 terms | `_CLINICAL_KW_TIER3` in `fast_router.py` |
| JSON extended (hot-reloadable) | ~110 terms | `config/fast_router_keywords.json` |

Categories: cardinal symptoms, cardiovascular, oncology, respiratory, GI, neurological, metabolic, lab markers, pathology/imaging, clinical admin phrases, English abbreviations (ECG, BNP, HbA1c…).

### FP guard layers (in order)

| Guard | What it blocks | Can be overridden by doctor anchor? |
|-------|---------------|-------------------------------------|
| `_TIER3_EXAM_ENDING_RE` | MCQ question stems (考虑的是, 可见于, 哪种…) | **No** — hard block |
| `_TIER3_QUESTION_RE` | Patient question phrases, knowledge queries, family references | Yes |
| `_TIER3_PATIENT_VOICE_RE` | "我…怎么办", "我头晕" etc. | Yes |
| `_TIER3_CONSULT_RE` | Pediatric online consult language (宝宝, 宝贝…) | Yes |

---

## Benchmark Results (2026-03-08)

### False Negative rate — real clinical notes missed by fast_route (lower is better)

| Dataset | Notes | FN Rate |
|---------|-------|---------|
| Yidu-S4K (CCKS 2019) | 1,379 real EMR discharge records from multiple hospitals | **0.4%** |
| CHIP-CDEE train | 1,587 discharge event sentences | 21.2% |
| CHIP-CDEE dev | 384 discharge event sentences | 19.5% |

> CHIP-CDEE's 21% FN is intentional: those records are short system-review sentences ("食欲正常，神志清醒") that are structurally identical to patient messages. Adding those keywords would create ~3,000 patient false positives.

### False Positive rate — non-clinical messages wrongly routed to add_record (lower is better)

| Dataset | Description | FP Rate |
|---------|-------------|---------|
| CMExam | 54K medical licensing exam MCQs | 3.3% |
| KUAKE-QIC | 6.9K labeled patient search queries | 4.5% |
| Huatuo encyclopedia | 362K medical encyclopedia Q&A | 4.8% |
| MedDG patient turns | 209K gastroenterology dialogue patient turns | 6.0% |
| CHIP-MDCFNPC patient | 113K online consultation patient turns | 6.2% |
| CMID patient queries | 12K intent-labeled patient queries | 6.8% |
| CHIP-STS | 20K disease sentence pairs | 17.3% |
| Huatuo consultation | 32.7M patient health questions | 10.4% |
| webMedQA | 12.6K patient questions from Baidu Doctor | 10.9% |
| MedDialog-CN patient | 5.6M haodf.com consultation patient turns | 18.8% |

### Hard floors

The ~10–19% FP rates on consultation datasets are **irreducible** with keyword/regex rules:

- **~10% floor**: Short symptom descriptions without question markers ("胸闷心慌头晕") are structurally identical to brief clinical dictation. Only semantic understanding can distinguish them.
- **~18–20% floor**: Patients on haodf.com write full clinical histories in medical language when consulting online doctors — indistinguishable from doctor notes without reading intent.

---

## Configuration

### Hot-reload keywords (no restart needed)

Edit `config/fast_router_keywords.json`, then:

```
POST /api/admin/fast-router/keywords/reload
```

### Mined rules

`data/mined_rules.json` — JSON array of learned routing rules. Each rule has `intent`, `patterns` (regex list), `keywords_any`, `min_length`, and `enabled` flag.

---

## Tier-3 Binary Classifier (2026-03-08)

A lightweight **TF-IDF + logistic regression binary classifier** is deployed as the final gate inside `_is_clinical_tier3()`, running only when keyword detection and all FP guards pass but no doctor-voice anchor is present.

### Architecture

- **Vectorizer**: `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4), max_features=100k, sublinear_tf=True)` — character n-grams for Chinese
- **Classifier**: `LogisticRegression(C=1.0, class_weight="balanced")`
- **Inference**: `~0.1ms` (loaded once at module import from `services/ai/tier3_classifier.pkl`)

### Training data

| Split | Source | Count |
|-------|--------|-------|
| Positive | CHIP-CDEE train + dev | 1,971 |
| Positive | Yidu-S4K (all splits) | 1,379 |
| Negative | MedDialog-CN patient turns | 100,000 (sampled) |
| Negative | Huatuo consultation questions | 100,000 (sampled) |
| Negative | webMedQA patient questions | 12,632 |

Class ratio balanced 5:1 negative:positive → 3,350 pos + 16,750 neg = 20,100 total.

### Results

| Dataset | FP Before | FP After | Change |
|---------|-----------|----------|--------|
| Huatuo consultation (hard floor) | 10.4% | **0.3%** | −10.1 pp |
| Yidu-S4K FN (clinical notes missed) | 0.4% | **0.4%** | unchanged |

5-fold CV F1: **0.978 ± 0.002**

### Integration

The classifier is the **final gate** in `_is_clinical_tier3()` — only reached after all keyword and regex guards pass. The doctor-voice anchor (`患者/主诉：/给予/建议观察/NAME+gender+age…`) bypasses it entirely, ensuring short doctor dictation is never blocked by the classifier.

To retrain: `python scripts/train_tier3_classifier.py`
