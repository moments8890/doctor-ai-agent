# Patient Portal Post-Visit Enhancements — Design Spec

> **Features:** P3.4 (Treatment Plan), P3.5 (Timeline), P3.7 (Medications), P3.8 (Doctor Info)
> **Scope:** Patient app only. Enrich existing 4 tabs, no new tabs.
> **Date:** 2026-03-26

---

## 1. P3.4 — Treatment Plan Visibility

### Problem
`GET /api/patient/records/{id}` hardcodes `diagnosis_status=None` and `treatment_plan=None` in `patient_portal_tasks.py` (~line 250). The frontend already renders treatment plan cards when data is non-null (PatientPage.jsx lines 418-506).

### Backend Fix
In the patient record detail endpoint, read from the DB record and return:
- `diagnosis_status`: derive from `record.status` — map `pending_review` → `"completed"`, `completed` with diagnosis field populated → `"confirmed"`, else `None`
- `treatment_plan`: parse `record.treatment_plan` text. If it's valid JSON with `{medications, follow_up, lifestyle}`, return as dict. If it's free text, return `{medications: [], follow_up: record.treatment_plan, lifestyle: null}`.

### Frontend
No changes needed — existing rendering code activates when data is non-null.

### Reused Components
- Existing treatment plan card rendering in PatientPage.jsx (diagnosis status badge, medication rows, follow-up text, lifestyle text)

---

## 2. P3.5 — Health Timeline

### Problem
Records tab shows a flat list. No chronological view.

### Design
Add filter chips at the top of Records tab: **"病历"** (default, current list) and **"时间线"** (timeline view).

Timeline view reuses `ListCard` with a **date avatar** instead of `RecordTypeAvatar`:

```
┌────┐
│ 3月│  门诊记录 · 头痛+恶心          ›
│26日│  已确认
└────┘
┌────┐
│ 3月│  预问诊 · 头痛3天伴恶心         ›
│24日│
└────┘
```

### Date Avatar Component: `DateAvatar`

New tiny component (~20 lines). Follows `RecordTypeAvatar` pattern:
- Props: `date: string` (ISO date), `size?: number` (default 36)
- Renders: square rounded box (`borderRadius: "4px"`, `bgcolor: COLOR.surface`)
- Top line: month in `TYPE.micro` (11px), `COLOR.text4`
- Bottom line: day in `TYPE.heading` (14px/600), `COLOR.text1`
- `flexShrink: 0`

### Timeline Entry Rendering

Uses `ListCard` directly:
```jsx
<ListCard
  avatar={<DateAvatar date={record.created_at} />}
  title={`${typeLabel} · ${record.chief_complaint || ""}`}
  subtitle={diagnosisStatus ? <StatusBadge label={statusLabel} colorMap={DIAGNOSIS_STATUS_COLOR} /> : null}
  chevron
  onClick={() => openDetail(record.id)}
/>
```

### Backend
None — reuses `GET /api/patient/records` list data.

### Reused Components
- `ListCard` — avatar + title + subtitle + chevron
- `StatusBadge` — diagnosis status pill
- Filter chip pattern from `TasksPage.jsx`

### New Components
- `DateAvatar` — ~20 lines, follows RecordTypeAvatar pattern

---

## 3. P3.7 — Medications + Record Detail Restructure

### Problem
Patient record detail shows all 14 NHC fields with equal weight. Patients primarily need: diagnosis, medications, follow-up, lifestyle.

### Design: Action Summary + Expandable Full Record

Default view shows **action summary** (collapsed). "查看完整病历 ▾" expands all 14 fields.

```
┌──────────────────────────────────────┐
│  ‹       门诊记录           3月26日  │
├──────────────────────────────────────┤
│  诊断                                │
│  颅内高压（疑似占位性病变）      已确认│
├──────────────────────────────────────┤
│  用药方案                            │
│  甘露醇                 125ml q6-8h  │
│  地塞米松                  4mg q6h   │
├──────────────────────────────────────┤
│  随访计划                            │
│  术后1周复查CT，2周拆线               │
├──────────────────────────────────────┤
│  生活建议                            │
│  避免剧烈运动，清淡饮食               │
├──────────────────────────────────────┤
│         查看完整病历 ▾               │
├──────────────────────────────────────┤
│  (14 NHC fields via RecordFields)    │
└──────────────────────────────────────┘
```

### Sections

**Diagnosis card** (only if `diagnosis_status` is non-null):
- SectionLabel "诊断"
- White card: diagnosis text (`TYPE.body`) + StatusBadge on the right
- Reuses `StatusBadge` with `DIAGNOSIS_STATUS_COLOR` map

**Medications card** (only if `treatment_plan.medications` is non-empty):
- SectionLabel "用药方案"
- White card with rows separated by `#f0f0f0` hairlines
- Per row: medication name (`TYPE.body`, `COLOR.text1`) left, dosage (`TYPE.secondary`, `COLOR.text3`) right
- No new component — simple Box rows

**Follow-up** (only if `treatment_plan.follow_up` is non-empty):
- SectionLabel "随访计划"
- White card with text (`TYPE.body`, `COLOR.text2`, `whiteSpace: pre-wrap`)

**Lifestyle** (only if `treatment_plan.lifestyle` is non-empty):
- SectionLabel "生活建议"
- Same pattern as follow-up

**Expand toggle**:
- Full-width tappable row: "查看完整病历 ▾" / "收起 ▴"
- `TYPE.caption`, `COLOR.primary` (green), centered, `py: 1.5`
- Toggles visibility of the existing inline structured field rendering below

**Full record (expanded)**: Uses the existing `FIELD_ORDER` + `FIELD_LABELS` + `record.structured` rendering already in `RecordDetailView` (PatientPage.jsx lines 440-449). This is the label-value row pattern: label (`TYPE.caption`, 60px, `#999`) + value (`TYPE.secondary`, `#333`), separated by `#f0f0f0` hairlines. No component extraction needed — just wrap the existing map in a collapsible Box.

**Fallback**: If no diagnosis/treatment data exists (record not yet reviewed), skip the summary and show the structured fields expanded directly (current behavior).

### Reused Components
- `SectionLabel` — section headers
- `StatusBadge` — diagnosis status
- Existing inline structured field rendering in RecordDetailView (FIELD_ORDER loop)

### New Components
None. Medications rows are simple Box elements. The expand toggle is a simple state toggle.

---

## 4. P3.8 — Doctor Info Card in Profile Tab

### Problem
Profile tab only shows patient name + doctor name as plain text + logout.

### Design

```
┌──────────────────────────────────────┐
│           设置                        │
├──────────────────────────────────────┤
│  我的医生                            │
│  ┌────┐                              │
│  │ 张 │  张伟医生                     │
│  │    │  神经外科                     │
│  └────┘                              │
│  我的信息                            │
│  ┌────┐                              │
│  │ 李 │  李复诊                       │
│  │    │  test_doctor                  │
│  └────┘                              │
│                                      │
│           退出登录                    │
└──────────────────────────────────────┘
```

Uses `ListCard` for both cards (no chevron, no onClick):
```jsx
<SectionLabel>我的医生</SectionLabel>
<ListCard
  avatar={<NameAvatar name={doctorName} />}
  title={doctorName}
  subtitle={doctorSpecialty || ""}
/>
<SectionLabel>我的信息</SectionLabel>
<ListCard
  avatar={<NameAvatar name={patientName} />}
  title={patientName}
  subtitle={doctorId}
/>
```

### Backend
Add `doctor_name` and `doctor_specialty` to `GET /api/patient/me` response. The endpoint already loads the patient record which has `doctor_id` — just join to the doctors table to get name + specialty.

### Reused Components
- `ListCard` — avatar + title + subtitle (no chevron)
- `NameAvatar` — colored initial circle (works for both doctor and patient names)
- `SectionLabel` — group headers

### New Components
None.

---

## Component Reuse Summary

| Component | Used In | How |
|-----------|---------|-----|
| `ListCard` | P3.5 timeline, P3.8 doctor/patient cards | Avatar + title + subtitle + optional chevron |
| `SectionLabel` | P3.7 sections, P3.8 groups | Section headers |
| `StatusBadge` | P3.5 timeline, P3.7 diagnosis | Diagnosis status pill |
| Inline FIELD_ORDER loop | P3.7 expandable section | Full 14-field NHC display (already in RecordDetailView) |
| `NameAvatar` | P3.8 doctor + patient cards | Colored initial circle |
| `RecordTypeAvatar` | P3.5 "病历" view (existing) | Record type icon |

| New Component | Lines | Purpose |
|---------------|-------|---------|
| `DateAvatar` | ~20 | Date display in avatar slot for timeline |

**Total new components: 1 (~20 lines)**

---

## Backend Changes Summary

| Endpoint | Change |
|----------|--------|
| `GET /api/patient/records/{id}` | Return `diagnosis_status` and `treatment_plan` from DB instead of null |
| `GET /api/patient/me` | Add `doctor_name` and `doctor_specialty` to response |

**Total backend changes: 2 endpoints, both small additions to existing code.**

---

## Design System Compliance

- [x] All `TYPE`/`COLOR`/`ICON` tokens from theme.js
- [x] No shadows, no gradients — flat only
- [x] White cards on `#ededed` background
- [x] Chinese-first labels
- [x] Reuses existing components (ListCard, SectionLabel, StatusBadge, NameAvatar, inline field rendering)
- [x] Mobile-first, 3-component page architecture (top bar + content + bottom nav)
- [x] Empty sections hidden when no data
- [x] Font sizes use only the 7 TYPE tokens
