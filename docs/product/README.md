# Product — Personal AI Copilot for Specialists

**Last verified: 2026-03-28 against code on `main`**

---

## What We Are

A **personal AI follow-up copilot** for specialists managing recurring patients. The doctor's clinical expertise, guidelines, communication style, and treatment preferences shape every AI output. The AI learns from the doctor's edits and decisions, getting smarter with use.

**"This AI thinks like me."**

## What We Are Not

- Not a hospital EMR/HIS/PMS
- Not an appointment/billing/prescription system
- Not an autonomous diagnostic or prescribing system
- Not a generic medical chatbot
- Not a replacement for the physician's clinical judgment

## For Whom

Large-hospital specialist doctors (neurosurgery) with significant private patient bases who manage 200+ WeChat messages daily. They need a copilot that handles follow-up, documentation, and preliminary review — so they only make final decisions.

## Core Value Loop

| Stage | AI Does | Doctor Does |
|-------|---------|-------------|
| **诊前** | Structured patient interview → quality record | Reviews, edits record |
| **诊中** | Differential diagnosis + workup + treatment suggestions, citing doctor's own rules | Confirms, rejects, edits — AI learns from edits |
| **诊后** | Drafts follow-up replies in doctor's voice, triages patient messages, tracks tasks | Reviews drafts, sends with one tap, teaches AI new rules |

## Delivery

- **Doctor:** Web workbench (React SPA) — 4 tabs: 我的AI / 患者 / 审核 / 随访
- **Patient:** WeChat Mini Program + Web portal
- **Architecture:** Plan-and-Act agent, 7 intents, 7-layer prompt composer, feed-all-to-LLM knowledge

## Current Status (82% feature complete)

**Done (53/65):**
- Doctor workbench: chat, patients, tasks, settings, knowledge management
- Diagnosis pipeline: AI suggestions → doctor review → confirm/reject/edit with KB citations
- Patient portal: pre-consultation interview, records, messaging, tasks, voice input
- Document upload with LLM processing and citation in diagnosis
- QR code login, bulk data export, regression tests (75 promptfoo cases)
- AI draft replies with KB citation tracking, teaching loop, triage color dots
- Demo simulation engine for product showcases

**Next Phase — Personal AI Features:**
- AI activity feed: "按你的方法处理了 N 位患者"

**Deferred:**
- Structured clinical data extraction (prescriptions, labs, allergies)
- Push notification infrastructure
- Case reference matching (embedding replacement)

## Monetization

¥2,999–6,999/month per doctor. Saves 1+ hour/day of clerical work (~30 hours/month of specialist physician time).

---

## Docs

| Doc | Covers |
|-----|--------|
| [roadmap.md](roadmap.md) | Remaining work, deferred items, open ADRs, success criteria |
| [product-strategy.md](product-strategy.md) | Vision, positioning, competitive context, monetization |

### Reference

- [competitive-analysis-abc-2026-03-20.md](competitive-analysis-abc-2026-03-20.md) — competitive analysis
- [clinical-decision-support-test-plan.md](clinical-decision-support-test-plan.md) — QA checklist for CDS pipeline

### Archived

- [requirements-and-gaps.md](requirements-and-gaps.md) — historical phase roadmap (mostly implemented)
- [feature-parity-matrix.md](feature-parity-matrix.md) — detailed per-item tracking (consolidated into roadmap.md)
- [clinical-decision-support-design.md](clinical-decision-support-design.md) — historical CDS design doc

Technical architecture lives in [docs/architecture.md](../architecture.md).
