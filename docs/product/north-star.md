# North Star — Personal AI Copilot for Specialists

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

## What Makes a Doctor Pay

1. The AI reliably sounds like them, not generic
2. It improves visibly after they teach it
3. It saves real time on daily tasks (replies, diagnosis review)
4. They can see and control what rules it uses
5. It's easier than maintaining their own ChatGPT setup

## Competitive Moat

Not any single feature — the **integrated loop**: personal knowledge → patient context → personalized reasoning → doctor feedback → compounding improvement.

| Need | Current alternatives | Our edge |
|------|---------------------|----------|
| Documentation | Freed, Heidi, Nabla | We personalize to doctor's style |
| Clinical answers | OpenEvidence, Heidi Evidence | We use doctor's own rules + cases |
| Patient comms | Artera, Hippocratic AI | We draft in doctor's voice with citations |
| Personal knowledge | ChatGPT Projects | We integrate into clinical workflow |

## Delivery

- **Doctor:** Web workbench (React SPA) — 4 tabs: 我的AI / 患者 / 审核 / 随访
- **Patient:** WeChat Mini Program + Web portal
- **Architecture:** Plan-and-Act agent, 7 intents, 6-layer prompt composer, feed-all-to-LLM knowledge

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
- ~~Knowledge usage tracking (when/where AI cites doctor's rules)~~ **Done** (cited_rules in API, green tags in UI)
- ~~AI draft replies in doctor's voice with rule citations~~ **Done** (followup_reply prompt, no-draft when no citation, WeChat-style <=100 chars)
- ~~Teaching loop: doctor edits → AI learns preferences~~ **Done** (save-as-rule endpoint)
- AI activity feed: "按你的方法处理了 N 位患者"
- ~~AI-flagged patients based on doctor's own rules~~ **Done** (AI attention items include patient_name)
- ~~Citation visual treatment ("引用了你的规则" vs "未引用个人规则")~~ **Done** (cited_rules clickable tags, undrafted yellow notice)

**Deferred:**
- Structured clinical data extraction (prescriptions, labs, allergies)
- Push notification infrastructure
- Case reference matching (embedding replacement)

## Monetization

¥2,999–6,999/month per doctor. Saves 1+ hour/day of clerical work (~30 hours/month of specialist physician time).

---

*Details: [product-strategy.md](product-strategy.md) (vision) · [requirements-and-gaps.md](requirements-and-gaps.md) (roadmap) · [feature-parity-matrix.md](feature-parity-matrix.md) (build status) · [personal AI redesign spec](../specs/2026-03-27-personal-ai-redesign.md) (next phase UI + backend)*
