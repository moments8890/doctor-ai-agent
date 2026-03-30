# Patient Sim — Test Coverage Matrix

Status as of 2026-03-29. Tracks which interview pipeline scenarios have E2E sim coverage.

## A. Context Layers

| # | Scenario | Prior Records | Doctor KB | Mode | Status |
|---|----------|:---:|:---:|:---:|:---:|
| A1 | First-visit, no KB, no history | — | — | patient | ✅ 10 personas |
| A2 | Returning patient — confirm/update history | past_history, allergy, etc | — | patient | ❌ Not tested |
| A3 | Returning patient — new complaint, old history | prior CC + diagnosis | — | patient | ❌ Not tested |
| A4 | Doctor KB loaded — interview shaped by rules | — | KB rules | patient | ❌ Not tested |
| A5 | Doctor KB + prior records combined | prior records | KB rules | patient | ❌ Not tested |
| A6 | Doctor mode (full 14-field extraction) | — | — | doctor | ❌ Not tested |

### What each tests

- **A2**: `_load_previous_history()` injects prior records into prompt. AI should reference them: "上次记录您有高血压10年，在吃氨氯地平，现在还是这样吗？" Needs: seed `medical_records` rows with `status='completed'` before `/start`.
- **A3**: Same as A2 but patient comes with a different chief complaint. Tests whether AI correctly reuses stable fields (past_history, allergy) while collecting new present_illness.
- **A4**: `load_knowledge()` injects doctor KB (L4 Doctor Rules). Tests whether doctor-specific rules shape the interview. Example: KB says "动脉瘤患者必须问是否服用抗凝药" → AI should ask about anticoagulants. Needs: seed `doctor_knowledge_items` rows.
- **A5**: Both A2 and A4 active simultaneously. Tests interaction between prior records and KB rules.
- **A6**: Doctor-mode interview uses `create_record` intent with 14 fields (adds physical exam, diagnosis, treatment plan). Entirely different completeness gate.

## B. Interview Quality

| # | Scenario | Status |
|---|----------|:---:|
| B1 | Standard comorbidity elicitation (HTN/DM/surgery/anticoagulants) | ✅ Fixed — checklist in interview prompt |
| B2 | Patient gives brief answers → AI follows up for details | ⚠️ Implicit (P5 minimal talker) |
| B3 | Patient contradicts prior record | ❌ Not tested |
| B4 | Patient says "没变化" → AI confirms specifics | ❌ Not tested |
| B5 | Phase transition: chief complaint → history | ✅ Implicit |

### What each tests

- **B2**: When patient says "有高血压" without details, AI should follow up: "持续多久？吃什么药？控制得怎么样？" Rule 15 in interview prompt covers this but no dedicated persona tests it.
- **B3**: Prior record says "高血压10年" but patient says "我没有高血压". AI must handle the contradiction (prompt rule: 以最后一次表述为准). Needs: A2 seeded records + persona that denies a prior condition.
- **B4**: Patient says "都没变" or "跟上次一样". AI must restate the specific values for confirmation (prompt rules 17-18). Needs: A2 seeded records + persona that confirms without change.

## C. Edge Cases

| # | Scenario | Status |
|---|----------|:---:|
| C1 | Patient goes off-topic midway | ✅ Implicit (P4 anxious) |
| C2 | Max turns (30) reached without completion | ❌ Not tested |
| C3 | Multi-field extraction from single message | ✅ Implicit (P1 first message) |
| C4 | "不知道"/"不记得" handling → "不详" | ⚠️ Implicit (P5) |

## D. Sim Infrastructure

| # | Scenario | Status |
|---|----------|:---:|
| D1 | volunteer=false facts disclosed on general questions | ✅ Fixed — sim prompt + LLM disclosure filter |
| D2 | Tiered judge matching (exact/partial/missed) | ✅ Fixed — dialog-based judge |

## E. Product Flow

| # | Scenario | Status |
|---|----------|:---:|
| E1 | `/chat` endpoint (real mini-program path, not `/turn`) | ❌ Not tested |
| E2 | Same-session correction ("青霉素过敏" → "不是，是造影剂") | ❌ Not tested |
| E3 | Premature confirm (only CC, no history collected) | ❌ Not tested |
| E4 | Review-state reopen ("我还想补充华法林") | ❌ Not tested |
| E5 | Resume after app restart (session in review, user returns later) | ❌ Not tested |

## F. Data Integrity & Concurrency

| # | Scenario | Status |
|---|----------|:---:|
| F1 | Pending-review history leakage into new interview | ❌ Not tested |
| F2 | Double-submit confirm (duplicate records/tasks) | ❌ Not tested |
| F3 | Concurrent turns on same session | ❌ Not tested |

## G. Security & Safety

| # | Scenario | Status |
|---|----------|:---:|
| G1 | Cross-patient session hijack (Patient B tries A's session_id) | ❌ Not tested |
| G2 | Adversarial patient (asks for diagnosis, tries to expose prompt/rules) | ❌ Not tested |

## H. Resilience & Real-World Input

| # | Scenario | Status |
|---|----------|:---:|
| H1 | LLM outage mid-interview → "系统繁忙" → patient retries | ❌ Not tested |
| H2 | Voice/ASR noisy input ("嗯那个左眼前一阵阵发黑哈") | ❌ Not tested |
| H3 | Oversized pasted report (>2000 chars) | ❌ Not tested |
| H4 | Downstream notification failure on confirm | ❌ Not tested |

## Priority for next implementation

### Tier 1 — Highest value
1. **A2 — Returning patient**: Tests prior history confirmation. Seed DB rows in sim engine.
2. **A4 — Doctor KB**: Tests "AI thinks like me" north star. Seed KB rules.
3. **E1 — `/chat` endpoint**: The real production path has zero sim coverage.

### Tier 2 — High value
4. **B3 — Contradiction**: Patient denies prior record. Builds on A2.
5. **E2 — Same-session correction**: Tests correction handling in extraction.
6. **E4 — Review-state reopen**: Common mobile behavior.
7. **G2 — Adversarial patient**: Safety boundary test.

### Tier 3 — Medium value
8. **A6 — Doctor mode**: Different extraction scope, zero coverage.
9. **H2 — ASR noisy input**: Real-world input quality.
10. **F1 — Pending-review leakage**: Code/doc mismatch in `_load_previous_history`.
11. **F2 — Double-submit**: Idempotency test.

### Tier 4 — Lower priority (unit test may suffice)
12. **F3 — Concurrent turns**: Session lock already exists, unit test may cover.
13. **G1 — Session hijack**: Auth boundary, unit test preferred.
14. **H3 — Oversized input**: Input validation, unit test preferred.
15. **H4 — Notification failure**: Side-effect isolation, unit test preferred.
16. **E3 — Premature confirm**: Guard check, unit test preferred.
17. **E5 — Resume after restart**: Session persistence, integration test preferred.

## How to add a new scenario

1. Create persona JSON in `tests/fixtures/patient_sim/personas/`
2. If scenario needs prior records: modify `engine.py` to seed `medical_records` before `/start`
3. If scenario needs KB: modify `engine.py` to seed `doctor_knowledge_items`
4. Add persona ID to `_PERSONA_FILES` in `run_patient_sim.py`
5. Run sim and verify with review HTML (`sim-{ts}-review.html`)

## Notes

- Tier 4 scenarios may be better served by deterministic unit/integration tests rather than LLM-based E2E sim
- E1 (`/chat` endpoint) requires sim engine changes to use the agent chat path instead of `/turn`
- F1 (pending-review leakage) is a known code/doc mismatch: `_load_previous_history()` includes `pending_review` rows despite docstring saying it skips them
