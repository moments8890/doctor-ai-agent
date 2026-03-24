# Patient Interview System — Actionable Improvements

**Source:** QA testing + 10-persona simulation (2026-03-24)
**Baseline:** DB 10/10 PASS, Extraction avg 1.9/4 fields, Quality avg 7.6/10, 26 anomalies (14 high)

## Evidence Index

| Evidence | Path | What it shows |
|----------|------|---------------|
| 10-persona simulation (pre-context-fix) | [sim-20260324T055635Z.html](../../reports/patient_sim/sim-20260324T055635Z.html) | All anomalies, duplication, extraction misses |
| 10-persona simulation JSON | [sim-20260324T055635Z.json](../../reports/patient_sim/sim-20260324T055635Z.json) | Machine-readable: per-persona tier1-4 results |
| P1 post-fix simulation | [sim-20260324T062804Z.html](../../reports/patient_sim/sim-20260324T062804Z.html) | Proves context injection eliminates duplication |
| P1 post-fix JSON | [sim-20260324T062804Z.json](../../reports/patient_sim/sim-20260324T062804Z.json) | ext=4/4, quality=8/10, clean extraction |
| 3-persona report (with DB records) | [sim-20260324T060958Z.html](../../reports/patient_sim/sim-20260324T060958Z.html) | Medical records linked in report |
| Pre-fix LLM debug (Turn 1 input) | [interview.patient_061852_830628.json](../../src/logs/llm_debug/interview.patient_061852_830628.json) | System prompt has NO collected context |
| Pre-fix LLM debug (Turn 3 output) | [interview.patient_061854_632618_output.json](../../src/logs/llm_debug/interview.patient_061854_632618_output.json) | LLM re-extracts all 4 fields despite no new info |
| QA report (frontend bugs) | [qa-report-localhost-5173-2026-03-24.md](../../.gstack/qa-reports/qa-report-localhost-5173-2026-03-24.md) | 422, [object Object], 404, ARIA issues |
| QA screenshots | [screenshots/](../../.gstack/qa-reports/screenshots/) | 84 screenshots of UI state before/after |

---

## Critical (blocks production quality)

### 1. Content duplication in SOAP fields — FIXED THIS SESSION

**Evidence:**
- [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html) → P2, P6, P8, P9, P10 anomaly sections show "内容重复" flagged by 3 LLM judges
- [Pre-fix LLM debug Turn 1](../../src/logs/llm_debug/interview.patient_061852_830628.json) → system prompt `messages[0].content` contains NO `当前已采集` or `已收集` — the LLM has zero visibility into what's already extracted
- [Pre-fix LLM debug Turn 3 output](../../src/logs/llm_debug/interview.patient_061854_632618_output.json) → LLM returns `past_history: "高血压5年，服用氨氯地平5mg/天"` again on Turn 3, even though it was already extracted in Turn 1. Patient said nothing new about hypertension in Turn 3.
- [Post-fix P1 report](../../reports/patient_sim/sim-20260324T062804Z.html) → After injecting collected context, Turn 2 only extracts new headache details, Turn 3 only extracts `allergy_history: "无"`. No re-extraction.

**Root cause (proven):** `interview_turn.py:186-188` popped the user message containing `<patient_context>` before the LLM call. The prompt composer also never substituted `{collected_json}` placeholders. The LLM saw only conversation history + static rules.

**Fix applied:**
- `interview_turn.py`: Appended `## 当前问诊状态` block (with collected JSON) directly to system prompt after composition
- `patient-interview.md` / `doctor-interview.md`: Added delta-only extraction rules (17-23)

**Verify:** Rerun full 10-persona simulation. Expect "内容重复" anomalies to drop from 5 to 0-1.

---

### 2. Extraction misses — 提取遗漏 (8 instances, most common anomaly)

**Evidence:** [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html) → anomaly review sections:
- P2 李秀兰: "患者提到每天进行康复训练，但在个人史中没有详细描述" (high)
- P4 赵小红: "患者提到曾经尝试过深呼吸和散步，但效果不明显，这些信息未出现在结构化字段中" (high)
- P6 刘芳: "患者提到最近半年睡眠质量不好，但这信息未出现在结构化字段中" (medium)
- P7 王淑芬: "患者提到最近出现的瘀青和牙龈出血，但未出现在结构化字段的present_illness中" (high)
- P9 孙丽: "患者提到有几次是坐着没动的时候突然发黑" (medium)
- P10 何静: "患者提到精神紧张和睡眠质量差，但未出现在结构化字段中" (high)

**Root cause:** The prompt's 7 SOAP field definitions don't cover: sleep quality, rehabilitation, coping strategies, medication side effects, functional status, psychological state. These are clinically relevant but fall through the cracks.

**Recommended fix:**
- Add to prompt extraction rules: "如果患者提到以下内容但不属于其他字段，追加到 present_illness：睡眠质量、康复训练、用药副作用、情绪心理、日常活动功能"
- Add example: "患者说'最近睡不好，经常半夜醒' → present_illness 追加 '睡眠质量差，夜间易醒'"

---

### 3. Hallucinated extractions — 提取错误 (5 instances)

**Evidence:** [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html) → anomaly review sections:
- P4 赵小红: "结构化字段中出现患者从未提到的信息，例如'患者对AVM破裂高度焦虑，影响睡眠和情绪'" — patient said "有点担心会不会破", system inflated to "高度焦虑，影响睡眠和情绪" (medium, anomaly type: 提取错误)
- P6 刘芳: "结构化字段中出现了患者从未提到的信息：'高血压6-7年，服用硝苯地平；糖尿病3年，服用二甲双胍'" — medication names may not match what patient actually said (high, anomaly type: 提取错误)
- P2 李秀兰: "高血压8年，服用氨氯地平；高脂血症，服用阿托伐他汀20mg/天（第二次出现）" — duplicated extraction with added detail (medium)
- P9 孙丽: "数据库中记录的高血压7年和高血脂2-3年似乎是重复的信息" (low)

**Root cause:** The LLM paraphrases and elaborates beyond what the patient literally said. Constraint "不捏造信息" is too vague — the LLM thinks summarizing/interpreting is acceptable.

**Recommended fix:**
- Add to extraction rules: "extracted 字段只能包含患者原话中明确表达的信息。不可以：推断情绪程度、补充药物剂量/品牌、扩展简短表述"
- Add negative example in prompt: "✗ 患者说'有点担心' → extracted: '高度焦虑，影响睡眠和情绪' (过度推断，患者未提及睡眠和情绪)"
- Add negative example: "✗ 患者说'吃降压药' → extracted: '服用硝苯地平' (患者未说药名，不要猜测)"

---

## High (degrades user experience)

### 4. Interview doesn't know when to stop — 对话质量 (5 instances)

**Evidence:** [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html) → anomaly review sections:
- P2 李秀兰: "AI助手在收集完信息后仍继续提问" (low)
- P4 赵小红: "AI助手在收集完信息后仍继续提问，例如'您平时有没有尝试过一些放松的方法？'" (low)
- P6 刘芳: "AI助手在收集完信息后仍继续提问" (low)
- P9 孙丽: "AI助手在收集完信息后仍继续提问，例如关于抽烟、喝酒、长期熬夜、压力比较大的情况" (medium)
- P10 何静: "AI助手在收集完信息后仍继续提问" (medium)

**Root cause:** The `complete: true` flag depends on the LLM voluntarily setting it. Even when `待收集: 无（可进入确认）` is in the context, the LLM keeps conversing.

**Recommended fix:**
- Strengthen prompt rule: "当 待收集 显示'无（可进入确认）'时，你**必须**设置 complete: true 并结束问诊。不要再提问。"
- Server-side hard stop in `interview_turn.py`: if `check_completeness(collected)` returns empty list, force `complete=True` in the response regardless of what LLM returns

---

### 5. Premature truncation with messy patients — 截断/不完整 (3 instances)

**Evidence:** [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html):
- P4 赵小红 (anxious): "对话被过早结束导致信息收集不完整，例如患者提到曾经尝试过的治疗方法和效果" (high)
- P5 陈大海 (minimal): only 4 turns, quality=5/10 (lowest of all 10 personas)
- P9 孙丽: "对话被过早结束，导致信息收集不完整，例如关于家族史的进一步询问" (high)
- P10 何静: "对话结束时患者仍有疑问未被回答" (low)

**Root cause:** Messy patients (anxious, minimal, vague) need more guided turns. The system uses open-ended questions that get non-informative responses, then gives up.

**Recommended fix:**
- Add prompt strategy: "如果患者连续两轮给出简短回答（少于10字），改用具体选择题：'您的头痛是左边、右边还是两边都有？' 而不是 '还有什么要补充的？'"
- Add prompt strategy for anxious patients: "如果患者表达焦虑，先简短安抚（一句话），然后回到临床问题。不要被情绪对话带偏。"

---

### 6. chief_complaint / present_illness field confusion

**Evidence:** [10-persona report](../../reports/patient_sim/sim-20260324T055635Z.html):
- P6 刘芳 anomaly: "患者在chief_complaint和present_illness中重复提到了头痛的症状和加重因素" (high, type: 内容重复)
- P1 王明: chief_complaint = "体检发现脑动脉瘤，间歇性轻微头痛几个月" — contains symptoms + duration + description mixed together

**Root cause:** When patients dump everything in first message, the LLM doesn't cleanly separate the brief chief complaint from the detailed present illness.

**Recommended fix:**
- Reinforce existing prompt rule with stronger wording: "chief_complaint **严格**只放：[症状名称] + [持续时间]，最多10个字。所有描述、特点、检查结果、诱因全部放入 present_illness"
- Add example: "✓ chief_complaint: '头痛3个月'  ✗ chief_complaint: '头痛3个月，间歇性，与血压相关'"

---

## Medium (polish)

### 7. Log infrastructure was writing to wrong directory — FIXED THIS SESSION

**Evidence:** `ls src/logs/` showed app.log, diagnosis_llm.jsonl, observability_*.jsonl, scheduler.log, tasks.log — all in `src/logs/` instead of project root `logs/`.

**Fix applied:** Migrated 6 files: `runtime_config.py`, `app_config.py`, `diagnosis.py`, `observability.py`, `turn_log.py`, `debug_handlers.py`. Added [lint script](../../scripts/lint_log_paths.sh) + pre-commit hook.

---

### 8. Review-queue API 422 on every page load — FIXED THIS SESSION

**Evidence:** [QA report](../../.gstack/qa-reports/qa-report-localhost-5173-2026-03-24.md) → ISSUE-001. Network tab showed `GET /api/manage/review-queue` → 422 on every page navigation. Response body: `{"detail":[{"type":"missing","loc":["query","kwargs"],"msg":"Field required"}]}`.

**Fix applied:** `src/channels/web/ui/review_handlers.py` — replaced `**kwargs` with explicit `doctor_id`, `status`, `limit` query parameters.

---

### 9. Chat error shows [object Object] — FIXED THIS SESSION

**Evidence:** [QA report](../../.gstack/qa-reports/qa-report-localhost-5173-2026-03-24.md) → ISSUE-002. Screenshot: [issue-001-object-error.png](../../.gstack/qa-reports/screenshots/issue-001-object-error.png). Clicking "今日摘要" chip showed "请求失败：[object Object]" in the chat bubble.

**Fix applied:** `frontend/web/src/api.js` `readError()` — now type-checks `json.detail`: handles string, array (FastAPI validation errors with `.msg`), and object (JSON.stringify fallback).

---

### 10. Sidebar nav lacks accessibility — FIXED THIS SESSION

**Evidence:** [QA report](../../.gstack/qa-reports/qa-report-localhost-5173-2026-03-24.md) → ISSUE-004. `snapshot -i` returned "no interactive elements" — nav items were `<Box>` divs with `cursor:pointer`, invisible to screen readers. Screenshot: [initial.png](../../.gstack/qa-reports/screenshots/initial.png).

**Fix applied:** `frontend/web/src/pages/DoctorPage.jsx` — nav items changed to `<Box component="button">` inside `<Box component="nav" aria-label="主导航">`, with `aria-current="page"` and `focus-visible` outlines. Post-fix: `snapshot -i` shows 6 button elements.

---

## Metrics to track

| Metric | Current (pre-fix) | Target | How to measure |
|--------|-------------------|--------|----------------|
| Duplication rate | 5/10 personas | 0/10 | Anomaly "内容重复" in [sim report](../../reports/patient_sim/) |
| Extraction accuracy | 1.9/4 fields avg | 3.5/4 | Tier 2 semantic match in sim report |
| Quality score | 7.6/10 avg | 8.5/10 | Tier 3 median in sim report |
| Anomalies per persona | 2.6 avg (1.4 high) | <1 avg (<0.5 high) | Tier 4 count in sim report |
| Hallucination rate | 5/10 personas | 0/10 | "提取错误" count in sim report |
| Interview completion | 3/10 stop properly | 10/10 | "对话质量" anomaly count = 0 |

---

## Priority order for next session

1. **Verify duplication fix** — rerun full 10-persona simulation, confirm 内容重复 drops to 0
2. **Fix hallucination** — add anti-inference extraction rules + negative examples to prompts
3. **Fix stop condition** — server-side hard stop when completeness check passes
4. **Fix messy patient handling** — specific follow-up strategy for minimal/vague responders
5. **Fix extraction coverage** — expand present_illness guidance for sleep/rehab/side effects
6. **Fix chief_complaint boundary** — reinforce the split rule with more examples
