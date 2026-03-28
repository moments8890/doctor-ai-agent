# North Star — Doctor AI Agent

**Last verified: 2026-03-27 against code on `main`**

---

## What We're Building

AI assistant for specialist doctors: asks questions like a junior doctor, writes medical records, gives preliminary diagnostic suggestions, manages patient follow-up — **doctors only make final decisions.**

## For Whom

Large-hospital specialist doctors (neurosurgery) with significant private patient bases who manage 200+ WeChat patient messages daily and lack quality records before consultations.

## Core Value

| Stage | AI Does | Doctor Does |
|-------|---------|-------------|
| **诊前** (Pre-visit) | Structured patient interview → quality medical record | Reviews, edits record |
| **诊中** (During visit) | Differential diagnosis + workup + treatment suggestions | Confirms, rejects, edits suggestions |
| **诊后** (Post-visit) | Auto-triage patient messages, follow-up task tracking | Reviews escalations, makes clinical decisions |

## Delivery

- **Doctor:** Web workbench (React SPA)
- **Patient:** WeChat Mini Program + Web portal
- **Architecture:** Plan-and-Act agent pipeline, 7 intent types, 6-layer prompt composer, feed-all-to-LLM knowledge strategy

## Current Status (78% feature complete)

**Done (51/65):**
- Doctor workbench: chat, patients, tasks, settings, knowledge management
- Diagnosis pipeline: AI suggestions → doctor review → confirm/reject/edit
- Patient portal: pre-consultation interview, record viewing, messaging, task checklist
- Document upload with LLM processing and citation in diagnosis
- QR code login, bulk data export, voice input
- Regression test infrastructure (86+ scenarios)

**Remaining (14/65):**
- Structured clinical data extraction (prescriptions, labs, allergies) — blocks patient medications view
- Clinical safety & emergency handling (red flag rules)
- Push notification infrastructure (WeChat template messages / web push)
- Case reference matching (needs new approach after embedding removal)

## Monetization

¥2,999–6,999/month per doctor. Rationale: saves 1+ hour/day of clerical work (~30 hours/month of specialist physician time).

## Competitive Moat

1. **Physician data sovereignty** — doctors own and can export all data
2. **Specialty depth over breadth** — deep neurosurgery first, then expand
3. **No platform lock-in** — unlike 好大夫/京东健康, doctors keep their patients

---

*For details: [product-strategy.md](product-strategy.md) (vision) · [requirements-and-gaps.md](requirements-and-gaps.md) (roadmap) · [feature-parity-matrix.md](feature-parity-matrix.md) (build status)*
