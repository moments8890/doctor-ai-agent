# Deferred Work — Doctor AI Agent

> Generated from /plan-eng-review on 2026-03-20. Review these when picking up new work.

## Deferred from Eng Review (2026-03-20)

### 1. F2.4 External Model Integration (ADR 0019)
**What:** API bridge to external diagnostic services (华佗GPT, specialized medical LLMs).
**Why deferred:** PHI risk — free-text clinical narratives are identifying even after name removal. No legal framework (data processing agreements, 《健康医疗大数据安全管理办法》 compliance, cross-border data flow) exists yet.
**Trigger to revisit:** When legal counsel reviews PHI requirements for external API calls.
**Depends on:** Legal review, P2 internal diagnosis pipeline proven.

### 2. Specific Drug Dosing in Treatment Suggestions
**What:** Output specific medication doses (e.g., "Dexamethasone 4mg IV q6h") instead of drug classes.
**Why deferred:** Interview doesn't collect allergy history in structured form, current medications, weight, renal/hepatic function, or pregnancy status. Outputting specific doses without this data is a clinical safety risk.
**Trigger to revisit:** When interview collects medication list + allergy data in structured form, or when doctor-side input form exists for these fields.
**Depends on:** Extended interview fields or doctor-side data entry.

### 3. Structured Medical Domain Model (Path A)
**What:** Replace LLM-first approach with structured domain entities: Disease (ICD-10), Symptom (coded), Medication (with interactions), deterministic rule engine for red flags.
**Why deferred:** Path B (LLM-first + structured overlay) chosen for speed to market. Path A is the right 3-year architecture but delays first doctor use by weeks.
**Trigger to revisit:** After product-market fit validated with real doctors (1+ month of daily use). If diagnosis quality is insufficient with LLM-only approach.
**Depends on:** Product validation, revenue signal.

### 4. Vector DB for Case History Matching
**What:** Replace in-memory cosine similarity with pgvector or ChromaDB for case matching.
**Why deferred:** At current scale (<1,000 cases per doctor), in-memory embedding search is <10ms. Vector DB adds infrastructure dependency.
**Trigger to revisit:** When any doctor's case history exceeds 1,000 entries.
**Depends on:** P2 diagnosis pipeline operational + case growth loop running.

### 5. Multi-Specialty Expansion (F4.3)
**What:** Extend knowledge base + diagnosis prompts to cardiology, endocrinology, orthopedics, etc.
**Why deferred:** Neurosurgery-only for initial validation. Architecture supports expansion (specialty-scoped skills/).
**Trigger to revisit:** After neurology validation complete + second specialty doctor interested.
**Depends on:** Neurology fully validated in production.

### 6. Unit Test Coverage for Non-Critical Modules
**What:** Add unit tests for CRUD operations, record structuring, patient portal, etc.
**Why deferred:** User preference — trust AI code, integration tests for critical paths only.
**Trigger to revisit:** If bugs in non-critical modules become frequent.
**Depends on:** Nothing — can be done anytime.
