# Diagnosis UI — Design Spec

**Status: ✅ COMPLETED (2026-03-27)**

> Date: 2026-03-25
> Status: Draft
> Depends on: existing `run_diagnosis()` pipeline, existing `DiagnosisSection.jsx` shell

## Problem

The CDS (Clinical Decision Support) pipeline is fully implemented on the backend
(`src/domain/diagnosis.py`) but completely disconnected from the frontend.
`DiagnosisSection.jsx` exists but is never rendered. `ReviewDetail.jsx` returns null.
The doctor's #1 ask — "希望能够有初步的诊断，鉴别诊断以及进一步治疗的建议，
我在里面只要筛选" — is unaddressed.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger | Doctor chooses "保存并诊断" on intake complete | Not every case needs AI; routine follow-ups don't |
| Intake confirm UX | Rename "确认生成" → "完成"; popup with NHC fields + two buttons | Doctor reviews extracted fields before saving |
| Review navigation | Subpage `/doctor/review/:recordId` | Reachable from record tap or task tap |
| Review card layout | Collapsed by default, tap to expand | Mobile-friendly; ~10 items fit on one screen |
| Per-item actions | ✓ confirm, ✗ reject (optional reason), ✎ edit (inline) | Doctor can also add custom entries per section |
| Finalize | "完成审核" sets record status to completed | Each ✓/✗/✎ auto-saves to DB immediately; progress never lost |
| After finalize | Toast "审核完成", return to previous page | Simple, predictable |
| Loading state | "AI 正在分析..." skeleton on review page | Doctor lands on review page immediately after "保存并诊断" |
| DB changes | None — uses existing status, ai_diagnosis, doctor_decisions columns | RecordStatus.pending_review already in enum |
| Visual style | Balanced — thin left border for state, outlined badges, function-first | Minimal color, content-forward |

## User Flow

### Flow 1: Doctor Intake → Diagnosis

```
Doctor conducts intake (chat-style, filling NHC fields)
  → clicks "完成"
  → popup dialog shows extracted NHC fields (主诉、现病史、既往史...)
    ┌──────────────────────────────┐
    │  病历预览                     │
    │  主诉: 头痛3天...             │
    │  现病史: 3天前无明显诱因...    │
    │  既往史: 高血压5年...         │
    │  ...                         │
    │                              │
    │  [保存]     [保存并诊断 →]    │
    └──────────────────────────────┘

  [保存] → record.status = "completed", close popup, back to patients
  [保存并诊断 →] → save record, trigger run_diagnosis() in background,
                   push to /doctor/review/:recordId
```

### Flow 2: Patient Intake → Doctor Review

```
Patient completes pre-consultation intake
  → record saved (status = "completed")
  → review task created for doctor
  → doctor sees task in task list: "李复诊 · 预问诊完成"
  → doctor taps task → push to /doctor/review/:recordId
  → doctor clicks "诊断建议" button on review page to trigger diagnosis
```

Note: patient-submitted records do NOT auto-trigger diagnosis. The doctor
decides after reviewing the patient's input whether AI analysis is needed.

### Flow 3: Doctor Reviews from Patient Detail

```
Doctor opens patient → sees record with status badge
  → taps record row → push to /doctor/review/:recordId
  → if ai_diagnosis exists: shows diagnosis cards
  → if no diagnosis yet: shows record only + "诊断建议" trigger button
```

## Intake Confirm Popup

### Changes to existing intake

1. **Rename button:** "确认生成" → "完成"
2. **Carry-forward section:** Make collapsible (▾/▴ toggle). Auto-collapse
   after user acts on all items (沿用/忽略) or clicks "全部沿用".
   Default expanded on first appearance.
3. **On "完成" click:** Show popup dialog (not navigate away)

### Popup content

- Title: "病历预览"
- Body: NHC fields extracted so far, displayed as label + value pairs
  - Uses existing `RecordFields` component or similar rendering
  - Shows field count: "已提取 7/14 字段"
- Footer: two buttons
  - `保存` — outlined, saves record as completed, closes popup
  - `保存并诊断 →` — green fill, saves record, triggers diagnosis, navigates to review

### Component

Reuse existing `Dialog` from MUI. Content uses `RecordFields`-style rendering.
No new component needed — compose from existing pieces.

## Review Page: `/doctor/review/:recordId`

### Layout

```
┌─────────────────────────────────────┐
│  ← 诊断审核                    完成  │  ← SubpageHeader
├─────────────────────────────────────┤
│  ┌─────────────────────────────┐    │
│  │ 病历摘要 (collapsed)    ▾   │    │  ← NHC fields, collapsible
│  └─────────────────────────────┘    │
│                                     │
│  AI 正在分析...                     │  ← loading skeleton (or cards below)
│  ░░░░░░░░░░░░░░░                    │
│                                     │
│  鉴别诊断                    0/4    │  ← section header + progress
│  ┌─────────────────────────────┐    │
│  │ 蛛网膜下腔出血  [高]    ▾   │    │  ← collapsed card
│  │ 偏头痛          [中]    ▾   │    │
│  │ 脑动脉瘤破裂    [中]    ▾   │    │
│  │ 高血压性脑出血  [中]    ▴   │    │  ← expanded card
│  │   高血压病史合并突发头痛... │    │
│  │   [✓ 确认] [✗ 排除] [✎ 修改]│   │
│  │ + 添加                      │    │
│  └─────────────────────────────┘    │
│                                     │
│  检查建议                    0/3    │
│  ┌─────────────────────────────┐    │
│  │ 头颅CT平扫     [急诊]   ▾   │    │
│  │ CTA脑血管造影  [紧急]   ▾   │    │
│  │ 血常规+凝血    [常规]   ▾   │    │
│  │ + 添加                      │    │
│  └─────────────────────────────┘    │
│                                     │
│  治疗方向                    0/2    │
│  ┌─────────────────────────────┐    │
│  │ 尼莫地平       [药物]   ▾   │    │
│  │ 动脉瘤夹闭     [手术]   ▾   │    │
│  │ + 添加                      │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │ 3/9 已处理       [完成审核] │    │  ← sticky bottom bar
│  └─────────────────────────────┘    │
│  AI建议仅供参考                     │
└─────────────────────────────────────┘
```

### Review Card States

Each card has a thin 3px left border indicating state:

| State | Left border | Right label | Background |
|-------|-------------|-------------|------------|
| Unreviewed | `#ddd` (light gray) | `▾` | `#fff` |
| Confirmed | `COLOR.primary` (#07C160) | `✓ 确认` green | `#fff` |
| Rejected | `#e5e5e5` | `✗ 排除` gray | `#fafafa`, text `#bbb`, strike-through |
| Edited | `COLOR.warning` (#F59E0B) | `✎` amber | `#fff`, `已改` outlined badge |
| Doctor-added | `COLOR.primary` dashed | — | `#fff`, `补充` outlined badge |

### Card Collapsed (default)

Single row: `name` + `[badge]` + `status icon`

- Badge is outlined pill with text: 高/中/低 (confidence), 急诊/紧急/常规 (urgency), 药物/手术/观察/转诊 (intervention)
- Badge color: red for 急诊, amber for 紧急, gray for everything else
- Status icon on right: ▾ (expandable), ✓ (confirmed), ✗ (rejected), ✎ (edited)

### Card Expanded (on tap)

Below the collapsed row, separated by 0.5px hairline:

1. **Reasoning text** — 12px, `COLOR.text3` (#666), line-height 1.5
2. **Action buttons** — full-width row divided by hairlines:
   - `✓ 确认` — `COLOR.primary` text
   - `✗ 排除` — `COLOR.text4` (#999) text
   - `✎ 修改` — `COLOR.accent` (#576B95) text

### Edit Mode (on ✎ tap)

Card expands further with:
- Editable textarea pre-filled with AI text
- "保存修改" / "取消" buttons below
- Original AI text preserved in `ai_suggestions.content` column for audit

### Reject with Reason (on ✗ tap)

- Item immediately shows as rejected (struck-through, dimmed)
- Optional: inline text input appears below for reason
- Reason saved in `ai_suggestions.reason` column

### Add Custom Item (on + 添加 tap)

- Inline form expands: text input for name + text input for description
- "添加" / "取消" buttons
- Saved as new row in `ai_suggestions` with `is_custom=TRUE`

### Bottom Action Bar

Sticky at bottom of scroll area:

- Left: progress text "3/9 已处理"
- Right: `完成审核` (green fill)
- Below: "AI建议仅供参考" in 10px `#ccc`

Each ✓/✗/✎ action auto-saves to `ai_suggestions` via API call.
Doctor can navigate away and come back — progress is always preserved.
完成审核 only sets `record.status = "completed"` and marks review task done.

### "诊断建议" Trigger Button

When a record has no `ai_diagnosis` yet (e.g., patient-submitted record
or doctor chose "保存" without diagnosis):

- Shows a button in place of the diagnosis sections: "诊断建议 — 请AI分析此病历"
- On tap: triggers `run_diagnosis()`, shows loading skeleton, cards appear when done

## Data Model

### New table: `ai_suggestions`

Replaces `ai_diagnosis` and `doctor_decisions` JSON columns on `medical_records`.
One row per AI suggestion item. Doctor decisions update existing rows.
Custom doctor additions insert new rows.

```python
class SuggestionSection(str, Enum):
    differential = "differential"
    workup = "workup"
    treatment = "treatment"

class SuggestionDecision(str, Enum):
    confirmed = "confirmed"
    rejected = "rejected"
    edited = "edited"
    custom = "custom"

class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id:             INT PK
    record_id:      INT FK → medical_records.id
    doctor_id:      VARCHAR

    # Classification
    section:        SuggestionSection     # enum: differential | workup | treatment

    # AI output (written by run_diagnosis)
    content:        TEXT                  # condition name / test name / drug class
    detail:         TEXT                  # reasoning / rationale / description
    confidence:     VARCHAR               # enum: 高/中/低 (differential only, nullable)
    urgency:        VARCHAR               # enum: 急诊/紧急/常规 (workup only, nullable)
    intervention:   VARCHAR               # enum: 手术/药物/观察/转诊 (treatment only, nullable)

    # Doctor response (written during review)
    decision:       SuggestionDecision    # enum, nullable (NULL = unreviewed)
    edited_text:    TEXT                  # doctor's version (if edited or custom)
    reason:         TEXT                  # rejection reason (if rejected)
    decided_at:     DATETIME              # when doctor acted

    is_custom:      BOOLEAN default FALSE # TRUE for doctor-added items

    created_at:     DATETIME
```

### Columns dropped from `medical_records`

- `ai_diagnosis` — replaced by `ai_suggestions` rows
- `doctor_decisions` — replaced by `decision` field on `ai_suggestions` rows

### Columns retained on `medical_records`

- `status` (RecordStatus enum: `intake_active`, `pending_review`, `completed`)
- `diagnosis` (clinical diagnosis text field — doctor's own, separate from AI)
- `final_diagnosis` (outcome tracking — separate concern)

### Status transitions

```
Record created → status = "completed" (if doctor chose "保存")
Record created → status = "pending_review" (if doctor chose "保存并诊断")
                  → run_diagnosis() inserts ai_suggestions rows
                  → creates review task

Doctor finalizes review → status = "completed"
                          → ai_suggestions rows updated with decisions
                          → review task marked done
```

### Analytics queries enabled

```sql
-- Most rejected differentials (tune diagnosis prompt)
SELECT content, COUNT(*) FROM ai_suggestions
WHERE section='differential' AND decision='rejected'
GROUP BY content ORDER BY COUNT(*) DESC;

-- What AI misses (doctor custom additions)
SELECT section, edited_text FROM ai_suggestions
WHERE is_custom=TRUE;

-- Per-doctor confirmation rate
SELECT doctor_id,
  SUM(CASE WHEN decision='confirmed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
FROM ai_suggestions WHERE decision IS NOT NULL
GROUP BY doctor_id;

-- Feed edits back as few-shot examples
SELECT content, edited_text FROM ai_suggestions
WHERE decision='edited' AND section='differential';
```

## API Endpoints

### New endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/doctor/records/:id/diagnose` | Trigger diagnosis for a record |
| GET | `/api/doctor/records/:id/suggestions` | Fetch all ai_suggestions for this record |
| POST | `/api/doctor/suggestions/:id/decide` | Update one suggestion's decision |
| POST | `/api/doctor/records/:id/suggestions` | Add custom suggestion |
| POST | `/api/doctor/records/:id/review/finalize` | Finalize review (status → completed) |

### Modified endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | `/api/doctor/records` | Include `has_suggestions: bool` and `pending_review: bool` |

### POST `/api/doctor/records/:id/diagnose`

Triggers `run_diagnosis()` in background. Returns immediately with `202 Accepted`.

```json
// Response
{"status": "running", "record_id": 42}
```

### GET `/api/doctor/records/:id/suggestions`

Returns all suggestions for this record (AI + custom).

```json
{
  "status": "pending_review",  // record status
  "suggestions": [
    {
      "id": 1,
      "section": "differential",
      "content": "蛛网膜下腔出血",
      "detail": "突发雷击样头痛...",
      "confidence": "高",
      "decision": null,
      "is_custom": false
    },
    ...
  ]
}
```

### POST `/api/doctor/suggestions/:id/decide`

Updates one suggestion row.

```json
// Request
{"decision": "rejected", "reason": "患者否认偏头痛病史"}
// or
{"decision": "edited", "edited_text": "脑动脉瘤破裂导致SAH，需CTA确认"}
// or
{"decision": "confirmed"}
```

### POST `/api/doctor/records/:id/suggestions`

Adds a custom doctor suggestion.

```json
// Request
{
  "section": "differential",
  "content": "颅内静脉窦血栓",
  "detail": "口服避孕药史，需MRV排除"
}
```

### POST `/api/doctor/records/:id/review/finalize`

Sets record status to `completed`, marks review task as done.

```json
// Response
{"status": "completed", "record_id": 42}
```

## Frontend Components

### New

| Component | Path | Purpose |
|-----------|------|---------|
| `ReviewPage.jsx` | `pages/doctor/ReviewPage.jsx` | Full review subpage: record summary + diagnosis cards |
| `DiagnosisCard.jsx` | `pages/doctor/DiagnosisCard.jsx` | Single collapsible review card with actions |
| `IntakeCompleteDialog.jsx` | `pages/doctor/IntakeCompleteDialog.jsx` | NHC fields preview + two-button popup |

### Modified

| Component | Change |
|-----------|--------|
| `IntakeView.jsx` | Rename "确认生成" → "完成"; on click show `IntakeCompleteDialog` |
| `IntakeView.jsx` | Make carry-forward section collapsible |
| `DoctorPage.jsx` / `App.jsx` | Add route `/doctor/review/:recordId` |
| `TasksSection.jsx` | Review tasks navigate to `/doctor/review/:recordId` |
| `PatientDetail.jsx` | Records with `pending_review` show badge; tap navigates to review |
| `api.js` | Add `triggerDiagnosis()`, `getSuggestions()`, `decideSuggestion()`, `addSuggestion()`, `finalizeReview()` |

### Existing (reuse as-is or adapt)

| Component | Usage |
|-----------|-------|
| `DiagnosisSection.jsx` | Reference for rendering logic; may refactor into `DiagnosisCard` |
| `RecordFields.jsx` | NHC field rendering in popup and review page |
| `SubpageHeader.jsx` | Review page header with back button |
| `PageSkeleton.jsx` | Loading state while diagnosis runs |

## UI Inventory

### Design tokens used

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR.primary` | `#07C160` | Confirmed border, 确认 button text, 完成审核 button bg |
| `COLOR.accent` | `#576B95` | ✎ 修改 button text |
| `COLOR.warning` | `#F59E0B` | Edited border, 已改/紧急 badge |
| `COLOR.danger` | `#D65745` | 急诊 badge text |
| `COLOR.text3` | `#666666` | Reasoning text, metadata |
| `COLOR.text4` | `#999999` | Section headers, unreviewed status, ✗ 排除 text |
| `COLOR.border` | `#E5E5E5` | Rejected border, card separators |
| `COLOR.borderLight` | `#f0f0f0` | Hairline dividers inside cards |
| `COLOR.surface` | `#f7f7f7` | Bottom bar background |
| `COLOR.surfaceAlt` | `#ededed` | Page background |
| `TYPE.heading` | 14px/600 | Section headers |
| `TYPE.body` | 14px/400 | Card name text |
| `TYPE.secondary` | 13px/400 | Expanded reasoning, action buttons |
| `TYPE.caption` | 12px/400 | Progress counters, field labels |
| `TYPE.micro` | 11px/500 | Badge text, status labels |

### Existing components reused

- `SubpageHeader` — review page header
- `PageSkeleton` — loading skeleton
- `RecordFields` — NHC field rendering in popup
- `Dialog` (MUI) — intake complete popup
- `AppButton` — 保存/保存并诊断/完成审核 buttons

### New components introduced

- `ReviewPage` — page-level component
- `DiagnosisCard` — collapsible card with confirm/reject/edit
- `IntakeCompleteDialog` — NHC preview + two buttons

## UX Reference

- Design spec: `docs/ux/design-spec.md`
- Theme: `frontend/web/src/theme.js` (COLOR, TYPE, ICON tokens)
- Shared components: `frontend/web/UI-DESIGN.md`
- Visual mockups: `.superpowers/brainstorm/9508-1774478043/review-balanced.html`
