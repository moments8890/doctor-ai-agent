# Roadmap

**Status: 82% feature complete** (53/65 items done) as of 2026-03-28

---

## Remaining Work

### Partial (1)

| ID | Feature | What's missing |
|----|---------|---------------|
| P3.4 | Treatment plan visibility | Patient sees task checklist but no dedicated medication schedule view |

### Backend Only (1)

| ID | Feature | What's missing |
|----|---------|---------------|
| D5.3 | Task notifications | Backend sends WeChat notifications; no doctor preference UI |

### Not Started (1)

| ID | Feature | Notes |
|----|---------|-------|
| — | AI activity feed | "按你的方法处理了 N 位患者" — surface on 我的AI tab |

---

## Deferred (3 groups, 8 items)

### Group 1: Structured Clinical Data (D3.5, D3.6, D3.7, P3.7)

Extract detailed fields for prescriptions, lab results, allergies from NHC flat text. Currently stored as unstructured text in `orders_followup`, `auxiliary_exam`, `allergy_history`.

- D3.5 — Prescription records (dedicated view)
- D3.6 — Lab results (structured display)
- D3.7 — Allergy information (dedicated CRUD)
- P3.7 — Patient current medications (blocked by D3.5)

### Group 2: Clinical Safety & Emergency (D4.5, D4.7)

- D4.5 — Red flag detection with doctor-curated specialty rules
- D4.7 — Case reference matching (embedding.py removed; needs lightweight replacement — Ollama embeddings, LLM-based, or keyword matching)

### Group 3: Active Notifications (D6.6, P4.1, P4.2)

Needs push infrastructure (WeChat template msg / web push / SMS). Notifications stay passive (in-app badges, polling) for now.

- D6.6 — Doctor notification preferences UI
- P4.1 — Patient notification capability
- P4.2 — Patient follow-up reminders

---

## Open ADRs

| ADR | Feature | Status | Blocker |
|-----|---------|--------|---------|
| 0019 | External clinical AI integration | Not started | PHI risk, needs legal framework |
| 0020 | Bidirectional doctor-patient communication | Partial | Post-visit portal exists but limited |
| 0021 | Patient outcome tracking | Not started | Needs treatment plan + communication loop first |

---

## Success Criteria (unchecked)

- [ ] E2E pipeline (intake → record → diagnosis) completes within 30 seconds
- [ ] Patient self-onboards via QR in <60 seconds
- [ ] Doctor reviews and finalizes a case in <3 minutes
- [ ] One neurosurgeon uses the system for 1 week with real patients
- [ ] Doctor reports time savings vs. manual workflow
- [ ] Patient completion rate >80%

---

## Long-term Deferred

1. External model integration (ADR 0019) — PHI risk
2. Specific drug dosing — needs allergy/medication/renal data
3. Structured medical ontology — revisit after PMF validation
4. Vector DB for case matching — when case count exceeds 1,000
5. Multi-specialty expansion — neuro-only for now (architecture supports multi)
6. Knowledge auto-categorization — currently assigns "custom" by default

---

*Strategy and positioning: [product-strategy.md](product-strategy.md)*
*Architecture: [../architecture.md](../architecture.md)*
