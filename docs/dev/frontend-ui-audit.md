# Frontend UI Audit Procedure

> Standard procedure for verifying that frontend features are complete,
> usable, and fit real doctor/patient workflows. Run after any major
> frontend milestone or before release.

## Prerequisites

- Backend running on port 8000 (`./cli.py start`)
- Frontend running on port 5173 (`cd frontend/web && npm run dev`)
- At least 1 doctor account with patients and records in the database
- At least 1 patient account linked to that doctor

## Three-Level Audit

### Level 1: Functional (Does it work?)

For every feature marked "Done" in the feature parity matrix:

- [ ] Route loads without console errors
- [ ] Data fetches and displays correctly
- [ ] All interactive elements respond (buttons, links, tabs, dialogs)
- [ ] Error states handled (empty lists, network failure, loading spinners)
- [ ] Mobile viewport (375px) renders correctly
- [ ] Desktop viewport (1280px) renders correctly

**Tool:** `/qa-only` for automated sweep, or `/browse` for manual walkthrough.

**Output:** Pass/fail per feature with screenshot evidence.

### Level 2: Usability (Is it human-friendly?)

Walk each feature as a real user. Score each on:

| Criterion | Question | Score |
|-----------|----------|-------|
| **Clarity** | Can the user understand what to do without instructions? | 0-3 |
| **Speed** | Can the task be completed in <30 seconds? | 0-3 |
| **Mobile** | Can it be done with one thumb on a phone? | 0-3 |
| **Language** | Are Chinese medical terms correct and natural? | 0-3 |
| **Feedback** | Does the UI confirm success/failure clearly? | 0-3 |

Score guide: 0 = broken, 1 = confusing, 2 = workable, 3 = smooth.

**Threshold:** Features scoring <8/15 need redesign. Features scoring 8-11 need polish. Features scoring 12+ are ship-ready.

### Level 3: Workflow Fit (Does it match real life?)

Walk through 4 complete user journeys end-to-end. These represent a
typical day for the doctor and patient:

#### Journey 1: Patient Pre-Consultation (患者预问诊)
```
Patient opens portal → logs in → starts interview →
answers AI questions (demographics, chief complaint, history) →
reviews summary → confirms → doctor gets notification
```

Verify:
- [ ] Patient can complete without getting stuck
- [ ] Interview asks medically appropriate questions
- [ ] Generated record is structured and readable
- [ ] Doctor sees the completed record in their workbench

#### Journey 2: Doctor Reviews Patient (医生查房)
```
Doctor opens workbench → sees briefing with pending reviews →
opens patient → reads structured record → checks history →
(future: reviews AI diagnosis) → creates follow-up task
```

Verify:
- [ ] Briefing shows actionable summary
- [ ] Patient detail loads quickly with full record
- [ ] Records are readable in SOAP structure
- [ ] Task creation works from patient context

#### Journey 3: Doctor Dictates Record (医生口述病历)
```
Doctor opens chat → dictates patient case (voice or text) →
AI structures into 14-field record → doctor reviews →
confirms or edits → record saved to patient
```

Verify:
- [ ] Voice input works (if implemented)
- [ ] AI correctly structures dictation into SOAP fields
- [ ] Doctor can review before saving
- [ ] Record appears in patient's history

#### Journey 4: Doctor Manages Day (日常管理)
```
Doctor checks briefing → sees today's tasks →
completes tasks → reviews patient list →
exports PDF for a patient → checks settings
```

Verify:
- [ ] Briefing provides useful daily overview
- [ ] Task list is clear with correct dates and status
- [ ] PDF export produces valid document
- [ ] Settings are discoverable and functional

## Scoring Template

For each journey, score:

| Journey | Completable? | Friction points | Time to complete | Verdict |
|---------|-------------|-----------------|------------------|---------|
| 1. Patient pre-consult | yes/no/partial | list blockers | minutes | ship/fix/redesign |
| 2. Doctor reviews patient | yes/no/partial | list blockers | minutes | ship/fix/redesign |
| 3. Doctor dictates record | yes/no/partial | list blockers | minutes | ship/fix/redesign |
| 4. Doctor manages day | yes/no/partial | list blockers | minutes | ship/fix/redesign |

## How to Run

### Option A: Automated + Manual (recommended)

1. Run `/qa-only` for Level 1 (functional sweep)
2. Use `/browse` to walk each Level 3 journey manually
3. Fill in the scoring template
4. Save report to `docs/qa/ui-audit-YYYY-MM-DD.md`

### Option B: Full Manual

1. Open app in browser
2. Walk each journey with devtools console open
3. Screenshot every step
4. Fill in scoring template

### Option C: Parallel Agents

Dispatch subagents for each journey in parallel using `/browse`:
- Agent 1: Patient pre-consultation journey
- Agent 2: Doctor review journey
- Agent 3: Doctor dictation journey
- Agent 4: Doctor daily management journey

Each agent produces its own section of the report.

## After the Audit

1. **Blockers (score 0-1):** Fix before any new features
2. **Friction (score 2):** File as tasks, fix in next sprint
3. **Ship-ready (score 3):** No action needed
4. **Missing features found:** Add to feature parity matrix

Save the report to `docs/qa/ui-audit-YYYY-MM-DD.md` and update the
feature parity matrix if any "Done" features turn out to be incomplete.

## Frequency

- **Before release:** Full 3-level audit
- **After major frontend changes:** Level 1 + affected journeys from Level 3
- **Weekly during active development:** Level 1 only (`/qa-only`)
