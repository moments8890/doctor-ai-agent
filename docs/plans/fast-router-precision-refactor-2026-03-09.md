# Fast Router Precision Refactor — 2026-03-09

## Context

This session was a systematic accuracy review of the fast router
(`services/ai/fast_router/`), applied with one governing principle:

> **Prefer LLM over fast-route when intent is ambiguous. A wrong fast-route
> is worse than a 1.5 s LLM call.**

The fast router was originally optimised for hit rate (~90% coverage without
LLM). That optimisation caused accuracy regressions in Tier 3 specifically:
clinical keyword matching routed too many messages to `add_record` that
should have gone to the LLM for proper intent discrimination or been
rejected outright.

Three files were changed: `_keywords.py`, `_tier3.py`, `_patterns.py`.

---

## 1. `_keywords.py` — Keyword bank pruning

### Philosophy

Every keyword in `_CLINICAL_KW_TIER3` is a hard commitment: if a message
contains that term and clears the guards, it is fast-routed to `add_record`
at confidence 0.8 without LLM involvement. The bar for inclusion should be:

> "Would a doctor typing a message containing only this word, with no other
> clinical context, almost certainly be dictating a clinical note rather than
> asking a question, scheduling, or doing something else?"

Broad symptom nouns, common chronic disease names, and everyday words that
happen to have clinical meanings fail that bar.

### Removed from `_CLINICAL_KW_TIER3`

| Term(s) | Reason |
|---|---|
| `疼痛` | Extremely high-frequency generic word; specific compounds (胸痛, 腹痛, 咽痛…) already in set |
| `出血` | Too generic (news, fiction, everyday); specific forms (脑出血, 便血, 呕血, 颅内出血) already present |
| `肿胀`, `红肿` | Generic swelling/redness — common in patient self-reports |
| `头晕` | Too colloquial; Tier-B patient voice guard misses many first-person forms |
| `乏力` | "I'm tired" is universal; not a doctor-note signal |
| `恶心` | Dual meaning in Chinese: nausea (clinical) and disgusting/gross (everyday slang) |
| `阵发性` | Bare modifier/qualifier; any message worth routing via this term already has another keyword |
| `心慌` | Colloquial for nervousness as much as palpitations; was also a duplicate in the frozenset |
| `高血压`, `糖尿病` | Common chronic disease names; appear heavily in patient questions and family summaries; `高血压病史` is retained as the stronger doctor-note signal |
| `白细胞`, `血红蛋白` | Valid clinical terms but frequently appear in patients asking about their own lab results |
| `便秘`, `腹泻`, `胃痛` | Top everyday self-reported complaints; not high-specificity doctor-dictation signals |
| `结节`, `积液`, `钙化`, `梗阻` | Common in report-interpretation requests and patient questions about their own imaging; `占位`, `免疫组化`, `彩超提示` are stronger signals |
| `直肠` | Bare anatomy noun; `直肠癌` already in set |
| `chest` | Single common English word with countless non-clinical uses |
| `介入` | Everyday Chinese verb ("别介入他人的事"); `介入治疗` already in set |
| `鼻炎` | Extremely common self-reported condition; discussed constantly outside clinical notes |
| `咽喉肿痛` | Top everyday self-reported complaint |
| `给予` | Removed from keyword bank (generic Chinese); already handled as a doctor-anchor signal in `_tier3.py` |
| `复查` | Removed from keyword bank; already anchored via `建议…复查` and `^NAME复查,` patterns in `_tier3.py` |

### Removed from `_IMPORT_KEYWORDS`

| Term | Reason |
|---|---|
| `过往记录` | Ambiguous between import_history and query_patient_records; LLM should decide |

### Cleaned up

- Removed duplicate `"所有任务"` entry in `_LIST_TASKS_EXACT` (frozenset
  deduplicated it, but the source was misleading).

### What was kept (and why)

The remaining set is dominated by:
- **High-specificity lab/biomarker abbreviations**: BNP, 肌钙蛋白, HbA1c,
  CEA, ANC, EGFR, HER2, INR — almost never appear outside clinical notes
- **Specific procedures**: STEMI, PCI, 溶栓, 支架, 消融, 化疗, 靶向, 放疗
- **Named neuro/CVD diagnoses**: SAH, TIA, 动脉瘤, 脑出血, 脑疝, 血管痉挛
- **Unambiguous exam findings**: 压痛, 无压痛, 反跳痛 — exclusively physical
  examination language
- **Hospital documentation phrases**: 收入我科, 收治入院, 神志清, 门诊以 —
  never appear outside hospital documentation

---

## 2. `_tier3.py` — Guard and classifier fixes

### 2a. Classifier fail-open → fail-closed

**Before:** When the TF-IDF classifier was absent or failed to load,
`_is_clinical_tier3()` returned `True` after any keyword hit that survived
the guards. This increased false positives precisely when the strongest
disambiguation layer was gone.

**After:** Missing/broken classifier returns `False` — falls through to LLM.
Degrades **recall**, not precision. Correct bias for a precision-first router.

```python
# Before
return True

# After
return False  # missing classifier → LLM handles it
```

### 2b. Blood-pressure pattern removed from both doctor anchors

`\d{2,3}/\d{2,3}` was treated as a doctor-voice anchor, bypassing the
classifier entirely. Patients absolutely write "血压160/100，头晕" or
"今天150/95". The pattern also matches dates, fractions, and dosage ratios.
Removed from both `_TIER3_DOCTOR_ANCHOR_RE` and `_TIER3_STRONG_DOCTOR_ANCHOR_RE`.

### 2c. Bare `^患者|患儿|病人` prefix removed from weak anchor

Any non-question message beginning with 患者/病人 was becoming eligible for
unconditional fast routing once keywords were present. This matched lay
third-person summaries and family-mediated consult text. The strong anchor
variant already excluded this; the weak anchor now matches it.

### 2d. `给予` removed from both anchors

`给予[\u4e00-\u9fff…]` was the weakest "doctor-only" cue in the file.
Removed from both anchor regexes. Messages with `给予` + a clinical keyword
now fall to the classifier (or LLM if classifier is absent).

### 2e. Dead code removed

After removing `复查` from `_CLINICAL_KW_TIER3`, the `_REMINDER_RE`
pattern and the 复查-only reminder guard in `_is_clinical_tier3()` became
dead code and were deleted.

---

## 3. `_patterns.py` — Regex correctness fixes

### 3a. `_EXPORT_RE` / `_OUTPATIENT_REPORT_RE` — domain keyword as name

The lazy `([\u4e00-\u9fff]{2,4}?)` name capture had no guard against
capturing domain keywords. `导出病历` would capture "病历" as the patient
name. Fixed with negative lookahead before the name group:

```python
# Before
r"...\s*([\u4e00-\u9fff]{2,4}?)\s*..."

# After
r"...(?!病历|记录|报告|医疗记录)([\u4e00-\u9fff]{2,4}?)\s*..."
```

### 3b. `_FOLLOWUP_NONAME_RE` — bare keyword match

Every clause (pronoun prefix, verb, time) was optional, meaning bare `随访`
or `复查` matched. Rewritten with two explicit branches — **pronoun branch**
(explicit he/she/this patient reference) and **time branch** (explicit
numeric duration). Neither fires on a bare keyword alone.

### 3c. `_CN_DIGIT_MAP` / `_cn_or_arabic` — duplicate map, silent bad default

Two separate Chinese numeral maps existed (`_CN_DIGIT_MAP` covering 1–10,
`_CN_NUM_MAP` covering 1–20 with two-character compounds). `_cn_or_arabic`
used the smaller map and silently defaulted to `1` for unrecognised tokens
(e.g. "十五" → 1 day follow-up instead of 15 days).

Fixed:
- Removed `_CN_DIGIT_MAP`
- Moved `_CN_NUM_MAP` (the complete map) earlier in the file so both
  functions use it
- `_cn_or_arabic` now raises `ValueError` for unrecognised tokens instead of
  returning a silent wrong value

### 3d. Delete patterns — 4-char names

`_DELETE_LEAD_RE`, `_DELETE_TRAIL_RE`, and `_DELETE_OCCINDEX_RE` used
`_NAME_PAT` (2–3 chars). Compound surnames like 司徒, 欧阳, 上官 produce
4-char names. A wrong match on a destructive action is unacceptable.
Introduced `_NAME_PAT_4 = r"([\u4e00-\u9fff]{2,4})"` used exclusively for
delete operations.

### 3e. `_APPOINTMENT_RE` / `_APPOINTMENT_VERB_FIRST_RE` — optional time

The datetime group was `?` (optional), so `给张三预约` routed as
`schedule_appointment` with no time. This is semantically incomplete and
too close to generic follow-up or task creation. Time expression is now
required in both patterns.

### 3f. `_UPDATE_PATIENT_DEMO_RE` — no guard against domain nouns

Added `(?!病历|记录|情况|病情|状态|诊断|治疗)` before the name capture in
both alternation branches. Domain nouns in the name slot now fall to
downstream `_NON_NAME_KEYWORDS` filtering rather than being silently routed
as `update_patient`.

### 3g. Comments added (no logic change)

- `_SUPPLEMENT_RE`: Mixed anchoring (some branches standalone-only with `$`,
  others prefix triggers without `$`) is intentional. Comment added
  explaining which is which.
- `_TIER3_NAME_RE`: Best-effort only. The following-char set intentionally
  excludes bare Chinese characters to avoid greedy 3-char captures.
  Callers must apply `_TIER3_BAD_NAME` filtering. Comment added.

---

## Architecture — implemented 2026-03-09

### Previous model (three-tier hybrid)

```
Message
  ├── Tier 0: help / import bypass                       ~0ms
  ├── Tier 1: exact keyword match (list, help)           ~0ms
  ├── Tier 2: deterministic regex (task/create/delete/…) ~1ms
  ├── Tier 2.5: correction guard                         ~1ms
  ├── Tier 2.8: session chain continuation               ~1ms
  ├── Tier 3: clinical keyword + TF-IDF → add_record     ~2ms
  └── LLM:   agent.dispatch                              ~1–3s
```

### Accuracy problem with Tier 3

Tier 3 was a one-dimensional gate: keyword hit → `add_record`. It could not
discriminate:
- "李明今天化疗后血常规异常" → `add_record` ✓
- "李明上次化疗后血常规怎么样" → `query_records` ✗ (was mis-routed to add_record)
- "李明化疗方案写错了，应该是紫杉醇" → `update_record` ✗ (was mis-routed to add_record)

### Implemented: LLM-first for all semantic content

**Decision: Option B** — Tier 3 removed. Tier 2.8 (session chain) removed.

```
Message
  ├── Tier 0: help / binary import (PDF/Word/Image prefix)  ~0ms
  ├── Tier 1: exact keyword match (list_patients/tasks/help) ~0ms
  ├── Tier 2: deterministic regex (task ops, create, delete,
  │           followup with name+time, appointment with time,
  │           export, supplement, query, update demographics) ~1ms
  ├── Tier 2.5: correction guard (更正/刚才/写错/改为…)      ~1ms
  │
  └── LLM: Claude Sonnet 4.6 with tool_use                 ~1–2s
        - discriminates add_record / query_records / update_record
        - extracts structured clinical fields (chief_complaint, dx, tx…)
        - uses conversation history for patient context
```

**Key principle:** A wrong fast-route is worse than a 1.5 s LLM call in a
medical record system. Precision is the primary metric; recall is secondary.

### Changes made

| File | Change |
|---|---|
| `_router.py` | Removed Tier 3 block, Tier 2.8 block, `_EMERGENCY_KW` import, `_is_clinical_tier3` / `_extract_tier3_demographics` imports |
| `__init__.py` | Removed `_EMERGENCY_KW`, `_is_clinical_tier3`, `_extract_tier3_demographics` re-exports |
| `_tier3.py` | Added retirement notice; module retained for offline evaluation only |
| `agent.py` | `_SYSTEM_PROMPT` rewritten: query-first, correction-first disambiguation in Chinese |
| `tests/test_fast_router.py` | Updated: 3 Tier 3 parametrize cases → `None`, deleted `test_tier3_clinical_keyword_routes_add_record`, renamed `test_fast_route_label_tier3` → `test_fast_route_label_clinical_falls_to_llm`, updated `_SAMPLE_CLINICAL_INPUTS` |

### UI / DB impact

None. `ChatResponse` model and `structured_fields` on `IntentResult` are
unchanged. `assemble_record()` already handles the existing field set.

---

## What's next

1. **Validate `_cn_or_arabic` callers.** The function now raises `ValueError`
   instead of returning `1`. Any caller that doesn't catch the exception will
   surface a 500 in production. Audit `_time_unit_to_days` call sites.

2. **Gather LLM routing accuracy data.** Sample 200–500 real messages from
   production logs and measure what the LLM routes them to. This validates
   whether the switch from Tier 3 → LLM improved or regressed accuracy in
   practice.

3. **Audit `_NON_NAME_KEYWORDS` and `_TIER3_BAD_NAME`** for completeness.
   Terms removed from `_CLINICAL_KW_TIER3` that could appear in name-slot
   positions may need to be added to the bad-name guards.

4. **Monitor latency.** Removing Tier 3 adds ~1–2 s to messages that
   previously fast-routed as `add_record`. Track p50/p95 chat response time.
