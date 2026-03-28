# Patient Portal Post-Visit Enhancements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the patient portal with treatment plan data, a timeline view, restructured record detail, and doctor info cards — covering P3.4, P3.5, P3.7, P3.8 from the feature parity matrix.

**Architecture:** Two small backend fixes (return real data instead of nulls) + frontend-only changes in PatientPage.jsx (restructure record detail, add timeline toggle, redesign profile tab). One new ~20-line component (DateAvatar). Everything else reuses existing components.

**Tech Stack:** Python/FastAPI (backend), React/MUI (frontend), existing components (ListCard, SectionLabel, StatusBadge, PatientAvatar)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/channels/web/patient_portal_tasks.py` | Modify (~line 250) | Return real diagnosis_status + treatment_plan |
| `src/channels/web/patient_portal.py` | Modify (~line 145) | Add doctor_name + doctor_specialty to /me response |
| `frontend/web/src/components/DateAvatar.jsx` | Create | Date display avatar for timeline |
| `frontend/web/src/pages/patient/PatientPage.jsx` | Modify | Timeline view, record detail restructure, profile tab redesign |

---

### Task 1: Backend — Return treatment plan data in record detail

**Files:**
- Modify: `src/channels/web/patient_portal_tasks.py:229-267`

- [ ] **Step 1: Find the hardcoded nulls**

Open `src/channels/web/patient_portal_tasks.py` and locate the `get_patient_record_detail` function (~line 229). Find lines 251-252 where `diagnosis_status` and `treatment_plan` are hardcoded to `None`.

- [ ] **Step 2: Replace with real data**

Replace the hardcoded None values with actual data from the record. The logic:
- `diagnosis_status`: if `record.status == "pending_review"` → `"completed"`, if `record.status == "completed"` and `record.diagnosis` is non-empty → `"confirmed"`, else `None`
- `treatment_plan`: try to parse `record.treatment_plan` as JSON. If valid dict with expected keys, return it. If free text, wrap as `{"medications": [], "follow_up": text, "lifestyle": None}`. If None, return None.

```python
import json

# Derive diagnosis_status from record state
diagnosis_status = None
if record.status == "pending_review":
    diagnosis_status = "completed"
elif record.status == "completed" and record.diagnosis:
    diagnosis_status = "confirmed"

# Parse treatment_plan
treatment_plan = None
if record.treatment_plan:
    try:
        parsed = json.loads(record.treatment_plan)
        if isinstance(parsed, dict):
            treatment_plan = parsed
        else:
            treatment_plan = {"medications": [], "follow_up": record.treatment_plan, "lifestyle": None}
    except (json.JSONDecodeError, TypeError):
        treatment_plan = {"medications": [], "follow_up": record.treatment_plan, "lifestyle": None}
```

- [ ] **Step 3: Verify the response model accepts these fields**

Check that `PatientRecordDetailOut` (the Pydantic response model in the same file) already has `diagnosis_status: Optional[str]` and `treatment_plan: Optional[Dict[str, Any]]` fields. They should already exist since the frontend expects them — they were just always null.

- [ ] **Step 4: Test manually**

Start the dev server and hit the endpoint with a record that has diagnosis data:
```bash
curl -H "Authorization: Bearer <patient_token>" \
  http://localhost:8000/api/patient/records/<record_id>
```
Verify `diagnosis_status` and `treatment_plan` are non-null in the response.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/patient_portal_tasks.py
git commit -m "fix(patient): return real diagnosis_status and treatment_plan in record detail"
```

---

### Task 2: Backend — Add doctor info to /me endpoint

**Files:**
- Modify: `src/channels/web/patient_portal.py:65-67,145-149`
- Reference: `src/db/models/doctor.py` (Doctor model has `name` and `specialty` fields)

- [ ] **Step 1: Update the response model**

In `src/channels/web/patient_portal.py`, find the `PatientMeResponse` class (~line 65) and add two fields:

```python
class PatientMeResponse(BaseModel):
    patient_id: int
    patient_name: str
    doctor_name: Optional[str] = None
    doctor_specialty: Optional[str] = None
```

- [ ] **Step 2: Update the endpoint to fetch doctor data**

In the `get_patient_me` function (~line 145), after authenticating the patient, look up the doctor's name and specialty. The patient record has a `doctor_id` field. Query the doctors table:

```python
@router.get("/me", response_model=PatientMeResponse)
async def get_patient_me(authorization: Optional[str] = Header(default=None)):
    """Return basic identity info for the current patient token."""
    patient = await _authenticate_patient(authorization)

    doctor_name = None
    doctor_specialty = None
    if patient.doctor_id:
        async with get_session() as session:
            from src.db.models.doctor import Doctor
            doctor = await session.get(Doctor, patient.doctor_id)
            if doctor:
                doctor_name = doctor.name
                doctor_specialty = doctor.specialty

    return PatientMeResponse(
        patient_id=patient.id,
        patient_name=patient.name,
        doctor_name=doctor_name,
        doctor_specialty=doctor_specialty,
    )
```

Note: Check how `get_session` is imported in this file — follow the existing pattern for DB access used by other endpoints in the same file.

- [ ] **Step 3: Test manually**

```bash
curl -H "Authorization: Bearer <patient_token>" \
  http://localhost:8000/api/patient/me
```
Verify response includes `doctor_name` and `doctor_specialty`.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/patient_portal.py
git commit -m "feat(patient): add doctor_name and doctor_specialty to /me endpoint"
```

---

### Task 3: Frontend — Create DateAvatar component

**Files:**
- Create: `frontend/web/src/components/DateAvatar.jsx`

- [ ] **Step 1: Create the component**

Follow the `RecordAvatar` pattern — a small square avatar that shows month + day:

```jsx
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function DateAvatar({ date, size = 36 }) {
  const d = new Date(date);
  const month = `${d.getMonth() + 1}月`;
  const day = `${d.getDate()}日`;

  return (
    <Box sx={{
      width: size, height: size, borderRadius: "4px", bgcolor: COLOR.surface,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, lineHeight: 1.2 }}>{month}</Typography>
      <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, lineHeight: 1.2 }}>{day}</Typography>
    </Box>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/components/DateAvatar.jsx
git commit -m "feat: add DateAvatar component for timeline view"
```

---

### Task 4: Frontend — Add timeline toggle to Records tab

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (Records tab section, ~lines 540-600)
- Reference: `frontend/web/src/components/DateAvatar.jsx`

- [ ] **Step 1: Add timeline state and filter chips**

Find the Records tab rendering in PatientPage.jsx (the section where `tab === "records"` is checked). Add a state variable and filter chips above the record list:

```jsx
const [recordView, setRecordView] = useState("list"); // "list" or "timeline"
```

Add filter chips just below the tab header, above the records list. Follow the pattern from TasksPage.jsx filter chips:

```jsx
<Box sx={{ display: "flex", gap: 0.8, px: 2, py: 1 }}>
  {[{ key: "list", label: "病历" }, { key: "timeline", label: "时间线" }].map(v => (
    <Box
      key={v.key}
      onClick={() => setRecordView(v.key)}
      sx={{
        px: 1.5, py: 0.4, borderRadius: "4px", cursor: "pointer",
        fontSize: TYPE.secondary.fontSize, fontWeight: recordView === v.key ? 600 : 400,
        bgcolor: recordView === v.key ? COLOR.primary : COLOR.white,
        color: recordView === v.key ? COLOR.white : COLOR.text3,
        border: recordView === v.key ? "none" : `0.5px solid ${COLOR.border}`,
      }}
    >
      {v.label}
    </Box>
  ))}
</Box>
```

- [ ] **Step 2: Add timeline rendering**

Below the filter chips, conditionally render either the existing list or the timeline view:

```jsx
{recordView === "list" ? (
  /* existing records.map with RecordAvatar — keep as-is */
) : (
  <Box sx={{ bgcolor: COLOR.white }}>
    {records.map(rec => {
      const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
      const chief = rec.structured?.chief_complaint;
      const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 40) || "";
      const title = preview ? `${typeLabel} · ${preview}` : typeLabel;
      const _DL = { pending: "诊断中", completed: "待审核", confirmed: "已确认", failed: "诊断失败" };
      const _DC = { "诊断中": COLOR.warning, "待审核": COLOR.accent, "已确认": COLOR.success, "诊断失败": COLOR.danger };
      const ds = rec.diagnosis_status;
      const dsLabel = ds ? _DL[ds] : null;
      return (
        <ListCard
          key={rec.id}
          avatar={<DateAvatar date={rec.created_at} />}
          title={title}
          subtitle={dsLabel ? dsLabel : undefined}
          right={dsLabel ? <StatusBadge label={dsLabel} colorMap={_DC} fallbackColor={COLOR.text4} /> : undefined}
          chevron
          onClick={() => navigate(`/patient/records/${rec.id}`)}
        />
      );
    })}
  </Box>
)}
```

Add the import at the top of the file:
```jsx
import DateAvatar from "../../components/DateAvatar";
```

- [ ] **Step 3: Test in browser**

Navigate to `http://localhost:5173/patient/records`. Verify:
1. Filter chips "病历" and "时间线" appear
2. "病历" shows the existing list with RecordAvatar
3. "时间线" shows the list with DateAvatar (month + day)
4. Clicking a record in timeline view opens the detail

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): add timeline view toggle to records tab"
```

---

### Task 5: Frontend — Restructure record detail with action summary

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (RecordDetailView function, ~lines 404-514)

This is the largest change. The current `RecordDetailView` shows all 14 NHC fields first, then diagnosis and treatment plan. We restructure to: action summary first (diagnosis → medications → follow-up → lifestyle), then expandable full record.

- [ ] **Step 1: Add expand state**

Inside `RecordDetailView`, add a state for the full-record toggle:

```jsx
const [showFullRecord, setShowFullRecord] = useState(false);
```

- [ ] **Step 2: Determine if we have summary data**

After the existing `diagStatus` and `treatmentPlan` variables, add:

```jsx
const hasSummary = diagStatus || treatmentPlan;
```

- [ ] **Step 3: Replace the content area**

Replace the content inside the scrollable Box (between the SubpageHeader and the bottom of RecordDetailView). The new structure:

```jsx
<Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
  {loadingDetail ? (
    <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={20} /></Box>
  ) : (
    <>
      {/* Action Summary — only when diagnosis/treatment data exists */}
      {hasSummary && (
        <>
          {/* Diagnosis */}
          {diagStatus && (
            <>
              <SectionLabel>诊断</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white, px: 2, py: 1.5 }}>
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, flex: 1 }}>
                    {detail?.structured?.diagnosis || structured.diagnosis || "—"}
                  </Typography>
                  <StatusBadge label={DIAG_STATUS_LABELS[diagStatus] || diagStatus} colorMap={DIAG_STATUS_COLORS} fallbackColor={COLOR.text4} />
                </Box>
              </Box>
            </>
          )}

          {/* Medications */}
          {treatmentPlan?.medications?.length > 0 && (
            <>
              <SectionLabel>用药方案</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white }}>
                {treatmentPlan.medications.map((med, i) => (
                  <Box key={i} sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", px: 2, py: 1,
                    borderBottom: i < treatmentPlan.medications.length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
                    <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>{med.name || med.drug_class || med}</Typography>
                    {med.dosage && <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>{med.dosage}</Typography>}
                  </Box>
                ))}
              </Box>
            </>
          )}

          {/* Follow-up */}
          {treatmentPlan?.follow_up && (
            <>
              <SectionLabel>随访计划</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white, px: 2, py: 1.5 }}>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  {treatmentPlan.follow_up}
                </Typography>
              </Box>
            </>
          )}

          {/* Lifestyle */}
          {treatmentPlan?.lifestyle && (
            <>
              <SectionLabel>生活建议</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white, px: 2, py: 1.5 }}>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  {treatmentPlan.lifestyle}
                </Typography>
              </Box>
            </>
          )}

          {/* Expand toggle */}
          <Box
            onClick={() => setShowFullRecord(!showFullRecord)}
            sx={{ bgcolor: COLOR.white, py: 1.5, mt: 1, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}
          >
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary }}>
              {showFullRecord ? "收起 ▴" : "查看完整病历 ▾"}
            </Typography>
          </Box>
        </>
      )}

      {/* Full structured record — always shown if no summary, otherwise toggleable */}
      {(!hasSummary || showFullRecord) && (
        <Box sx={{ bgcolor: COLOR.white, px: 1.5, py: 1, mt: hasSummary ? 0 : 0 }}>
          {FIELD_ORDER.map((key) => {
            const val = structured[key];
            if (!val) return null;
            return (
              <Box key={key} sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0", display: "flex", alignItems: "baseline", gap: 0.5 }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", flexShrink: 0 }}>{FIELD_LABELS[key] || key}：</Typography>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", lineHeight: 1.6, flex: 1 }}>{val}</Typography>
              </Box>
            );
          })}
          {!Object.values(structured).some(Boolean) && record.content && (
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#333", lineHeight: 1.8, whiteSpace: "pre-wrap", py: 1 }}>
              {record.content}
            </Typography>
          )}
        </Box>
      )}

      <Box sx={{ height: 24 }} />
    </>
  )}
</Box>
```

- [ ] **Step 4: Add SectionLabel import**

Add to the imports at the top of PatientPage.jsx (if not already imported):
```jsx
import SectionLabel from "../../components/SectionLabel";
```

- [ ] **Step 5: Remove the old treatment plan card**

Delete the old green-background treatment plan card (~lines 479-506) and the old inline diagnosis card (~lines 457-477). These are replaced by the new structured sections above.

- [ ] **Step 6: Test in browser**

Navigate to a patient record detail with diagnosis data. Verify:
1. Action summary shows: diagnosis → medications → follow-up → lifestyle
2. "查看完整病历 ▾" toggle works
3. Records without diagnosis data show full fields directly (fallback)
4. Empty sections are hidden

- [ ] **Step 7: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): restructure record detail with action summary + expandable full record"
```

---

### Task 6: Frontend — Redesign Profile tab with doctor info card

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx` (Profile tab section, ~lines 976-993)
- Reference: `frontend/web/src/api.js` (`getPatientMe`)

- [ ] **Step 1: Update /me API call to capture doctor data**

Find where `getPatientMe` is called (the effect that loads patient identity on mount). The response now includes `doctor_name` and `doctor_specialty`. Store them in state:

```jsx
const [doctorSpecialty, setDoctorSpecialty] = useState("");
```

In the existing effect that calls `getPatientMe`, add:
```jsx
getPatientMe(token).then((data) => {
  setPatientName(data.patient_name);
  setDoctorName(data.doctor_name || "");
  setDoctorSpecialty(data.doctor_specialty || "");
  // ... existing logic
});
```

- [ ] **Step 2: Replace the Profile tab content**

Replace the existing Profile tab section (~lines 976-993) with the new design using ListCard, PatientAvatar, and SectionLabel:

```jsx
{tab === "profile" && (
  <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
    {/* Doctor info card */}
    {doctorName && (
      <>
        <SectionLabel>我的医生</SectionLabel>
        <Box sx={{ bgcolor: COLOR.white }}>
          <ListCard
            avatar={<PatientAvatar name={doctorName} size={42} />}
            title={doctorName}
            subtitle={doctorSpecialty || ""}
          />
        </Box>
      </>
    )}

    {/* Patient info card */}
    <SectionLabel>我的信息</SectionLabel>
    <Box sx={{ bgcolor: COLOR.white }}>
      <ListCard
        avatar={<PatientAvatar name={patientName || "?"} size={42} />}
        title={patientName || "患者"}
        subtitle={doctorId || ""}
      />
    </Box>

    {/* Logout */}
    <Box sx={{ mt: 1 }}>
      <Box onClick={handleLogout}
        sx={{ bgcolor: COLOR.white, py: 1.5, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.danger }}>退出登录</Typography>
      </Box>
    </Box>
  </Box>
)}
```

- [ ] **Step 3: Add imports**

Add to the imports at the top of PatientPage.jsx (if not already present):
```jsx
import ListCard from "../../components/ListCard";
import PatientAvatar from "../../components/PatientAvatar";
```

Note: `SectionLabel` should already be imported from Task 5. `COLOR` should already be imported from theme.

- [ ] **Step 4: Test in browser**

Navigate to `http://localhost:5173/patient/profile`. Verify:
1. Doctor info card shows with avatar + name + specialty
2. Patient info card shows with avatar + name
3. Logout button renders below
4. Cards follow design system (white on `#ededed`, no shadows)

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): redesign profile tab with doctor info card"
```

---

### Task 7: Verify end-to-end

- [ ] **Step 1: Test the full patient flow**

1. Log in as a patient at `http://localhost:5173/patient`
2. Go to Records tab → verify filter chips ("病历" / "时间线") work
3. Switch to timeline view → verify DateAvatar shows month+day
4. Click a record with diagnosis data → verify action summary (diagnosis, meds, follow-up, lifestyle)
5. Click "查看完整病历 ▾" → verify all 14 fields expand
6. Click "收起 ▴" → verify fields collapse
7. Click a record without diagnosis data → verify fallback (full fields shown directly)
8. Go to Profile tab → verify doctor card with name + specialty
9. Verify patient card with name
10. Check console for errors — should be clean

- [ ] **Step 2: Test edge cases**

1. Record with no treatment_plan → medications section should be hidden
2. Record with free-text treatment_plan (not JSON) → should show as follow-up text
3. Record with empty diagnosis → diagnosis section hidden, full record shown
4. Patient with no assigned doctor → "我的医生" section hidden in profile
5. Timeline view with single record → should render correctly

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(patient): address edge cases in post-visit enhancements"
```
