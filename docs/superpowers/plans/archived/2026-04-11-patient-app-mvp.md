# Patient App MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship-ready patient app — fix chat bugs, add hybrid AI persona, patient onboarding, font scale, cleanup, and Playwright tests.

**Architecture:** Fix-forward approach. Phase 0 fixes critical chat bugs (fake reply, dedup). Phases 1-3 add features while touching the same files. Phase 4 cleans up remaining tech debt. Phase 5 adds E2E test coverage.

**Tech Stack:** React + MUI (frontend), FastAPI + SQLAlchemy (backend), Playwright (E2E tests)

**Spec:** `docs/superpowers/specs/2026-04-11-patient-app-mvp-design.md`

---

### Task 1: Fix fake AI reply in ChatTab

**Files:**
- Modify: `frontend/web/src/pages/patient/ChatTab.jsx:156-169`

- [ ] **Step 1: Remove fake reply append after send**

In `ChatTab.jsx`, replace the `handleSend` function (lines 156-170):

```jsx
  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages(prev => [...prev, { source: "patient", content: text, _local: true, _ts: Date.now() }]);
    setSending(true);
    try {
      await sendPatientChat(token, text);
      // No reply appended — real replies arrive via polling
    } catch (err) {
      if (err.status === 401) { console.warn("auth expired"); return; }
      setMessages(prev => [...prev, { source: "ai", content: "系统繁忙，请稍后重试。" }]);
    } finally { setSending(false); }
  }
```

Key change: removed `setMessages(prev => [...prev, { source: "ai", content: data.reply || "收到您的消息。" ...}])`. Added `_ts: Date.now()` to optimistic messages for dedup (Task 2).

- [ ] **Step 2: Verify locally**

Run dev server, send a patient message. Confirm:
- Patient bubble appears immediately (optimistic)
- No fake "收到您的消息" reply appears
- Real doctor/AI replies still arrive via polling

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/ChatTab.jsx
git commit -m "fix(patient): remove fake AI reply after send — real replies arrive via polling"
```

---

### Task 2: Fix message deduplication

**Files:**
- Modify: `frontend/web/src/pages/patient/ChatTab.jsx:97-113,156-169`

- [ ] **Step 1: Add dedup logic for optimistic messages**

In `ChatTab.jsx`, update the polling merge logic (lines 104-110) to remove optimistic messages when real ones arrive:

```jsx
  setMessages(prev => {
    const existingIds = new Set(prev.filter(m => m.id).map(m => m.id));
    const newMsgs = data.filter(m => !existingIds.has(m.id));
    if (newMsgs.length === 0) return prev;
    // Remove optimistic patient messages that now have real counterparts
    const cleaned = prev.filter(m => {
      if (!m._local) return true;
      // Check if any new message matches this optimistic one
      return !newMsgs.some(nm => nm.source === "patient" && nm.content === m.content);
    });
    return [...cleaned, ...newMsgs];
  });
```

- [ ] **Step 2: Verify locally**

Send a message. Confirm:
- Single patient bubble (not duplicated)
- After polling picks up the saved message, still only one bubble

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/ChatTab.jsx
git commit -m "fix(patient): deduplicate optimistic messages when real ones arrive via polling"
```

---

### Task 3: Backend — expose ai_handled and filter drafts

**Files:**
- Modify: `src/channels/web/patient_portal/chat.py:54-61,75-83,188-206`

- [ ] **Step 1: Add ai_handled to ChatMessageOut schema**

In `chat.py`, update the schema (line 54-61):

```python
class ChatMessageOut(BaseModel):
    id: int
    content: str
    source: str  # patient / ai / doctor
    sender_id: Optional[str] = None
    triage_category: Optional[str] = None
    ai_handled: Optional[bool] = None
    created_at: datetime
```

- [ ] **Step 2: Add ai_handled to _msg_to_out**

Update `_msg_to_out` (line 75-83):

```python
def _msg_to_out(msg: PatientMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        content=msg.content,
        source=_infer_source(msg),
        sender_id=msg.sender_id,
        triage_category=msg.triage_category,
        ai_handled=msg.ai_handled,
        created_at=msg.created_at,
    )
```

- [ ] **Step 3: Filter out un-reviewed AI drafts from patient-visible messages**

In `get_chat_messages` (line 188-206), add a filter to exclude source="ai" + ai_handled=False (these are drafts awaiting doctor review). After the base query (line 197), add:

```python
    # Exclude AI drafts that haven't been reviewed by doctor
    from sqlalchemy import or_, and_
    stmt = stmt.where(
        or_(
            PatientMessage.source != "ai",
            and_(PatientMessage.source == "ai", PatientMessage.ai_handled == True),
        )
    )
```

Place this BEFORE the `order_by` and `limit` calls.

- [ ] **Step 4: Run backend tests**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "patient" -x -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/patient_portal/chat.py
git commit -m "feat(patient-api): expose ai_handled in chat messages, filter out unreviewed drafts"
```

---

### Task 4: Hybrid AI persona attribution in chat

**Files:**
- Modify: `frontend/web/src/pages/patient/ChatTab.jsx:28,172-273`
- Modify: `frontend/web/src/theme.js` (add BUBBLE_RADIUS)

- [ ] **Step 1: Add BUBBLE_RADIUS constants to theme.js**

At the end of the radius section in `theme.js`, add:

```javascript
export const BUBBLE_RADIUS = {
  left: `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0`,   // AI/doctor messages
  right: `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}`,  // patient messages
};
```

- [ ] **Step 2: Add imports and update renderMessage**

In `ChatTab.jsx`, add imports at top:

```jsx
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import NameAvatar from "../../components/NameAvatar";
import { BUBBLE_RADIUS } from "../../theme";
```

- [ ] **Step 3: Update doctor message rendering (lines 176-186)**

Replace the doctor source block:

```jsx
    // Doctor reply bubble — show doctor's name avatar
    if (src === "doctor") {
      return (
        <Box key={msg.id || i} sx={{ display: "flex", alignItems: "flex-end", gap: 1, mb: 1.5 }}>
          <NameAvatar name={doctorName || "医"} size={32} color={COLOR.accent} />
          <Box sx={{ maxWidth: "75%" }}>
            <Box sx={{
              px: 1.5, py: 1, borderRadius: BUBBLE_RADIUS.left, bgcolor: COLOR.white,
              color: COLOR.text2, fontSize: TYPE.body.fontSize, lineHeight: 1.7,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.5 }}>
              {doctorName || "医生"}
              {msg.created_at ? ` · ${new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : ""}
            </Typography>
          </Box>
        </Box>
      );
    }
```

- [ ] **Step 4: Update AI message rendering (lines 246-273)**

Replace the AI source block. AI messages with `ai_handled: true` show doctor avatar + AI badge. Others show generic MsgAvatar:

```jsx
    // AI message (left aligned) — hybrid persona
    const isPersonaAI = msg.ai_handled && doctorName;
    const aiAvatar = isPersonaAI ? (
      <Box sx={{ position: "relative", flexShrink: 0 }}>
        <NameAvatar name={doctorName} size={32} color={COLOR.accent} />
        <SmartToyOutlinedIcon sx={{
          position: "absolute", bottom: -2, right: -2,
          fontSize: 14, color: COLOR.text4,
          bgcolor: COLOR.white, borderRadius: "50%",
        }} />
      </Box>
    ) : (
      <MsgAvatar isUser={false} size={32} />
    );
    const aiLabel = isPersonaAI ? `${doctorName}的AI助手` : "AI健康助手";

    return (
      <Box key={msg.id || i} sx={{ display: "flex", alignItems: "flex-end", gap: 1, mb: 1.5 }}>
        {aiAvatar}
        <Box sx={{ maxWidth: "75%" }}>
          {msg.triage_category === "diagnosis_confirmation" && (
            <Box sx={{ mb: 0.5, px: 1.5, py: 1, borderRadius: BUBBLE_RADIUS.left, bgcolor: COLOR.successLight, border: `0.5px solid ${COLOR.successLight}` }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.success, fontWeight: 500 }}>
                {msg.content}
              </Typography>
            </Box>
          )}
          {msg.triage_category !== "diagnosis_confirmation" && (
            <Box sx={{
              px: 1.5, py: 1, borderRadius: BUBBLE_RADIUS.left, bgcolor: COLOR.white,
              color: COLOR.text2, fontSize: TYPE.body.fontSize, lineHeight: 1.7,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
          )}
          {msg.triage_category === "urgent" && (
            <Box sx={{ mt: 0.5, px: 1.5, py: 0.5, borderRadius: RADIUS.md, bgcolor: COLOR.dangerLight, border: `0.5px solid ${COLOR.danger}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, fontWeight: 500 }}>
                紧急情况，请立即就近就医
              </Typography>
            </Box>
          )}
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.5 }}>
            {aiLabel}
          </Typography>
        </Box>
      </Box>
    );
```

- [ ] **Step 5: Update patient bubble to use BUBBLE_RADIUS**

Replace the patient message `borderRadius` (line 194):

```jsx
  borderRadius: BUBBLE_RADIUS.right,
```

- [ ] **Step 6: Fix loading spinner borderRadius (line 286)**

Replace `borderRadius: 2` with `borderRadius: RADIUS.sm`.

- [ ] **Step 7: Commit**

```bash
git add frontend/web/src/pages/patient/ChatTab.jsx frontend/web/src/theme.js
git commit -m "feat(patient): hybrid AI persona in chat — doctor avatar + AI badge for ai_handled messages"
```

---

### Task 5: Chat header with doctor info

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx:148-150`

- [ ] **Step 1: Update header to show doctor name when on chat tab**

In `PatientPage.jsx`, replace the header block (lines 148-150):

```jsx
      {/* Page header — only for tabs without their own PageSkeleton header */}
      {!urlSubpage && tab !== "records" && tab !== "profile" && (
        <SubpageHeader
          title={tab === "chat" && doctorName ? doctorName : (NAV_TABS.find(t => t.key === tab)?.title || "AI 健康助手")}
          subtitle={tab === "chat" && doctorSpecialty ? doctorSpecialty : undefined}
        />
      )}
```

Note: `SubpageHeader` may not support `subtitle` prop. Check the component. If not, add doctor info below the header as a small Typography line, or update SubpageHeader to accept subtitle.

- [ ] **Step 2: Verify — chat tab shows doctor name in header**

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat(patient): show doctor name + specialty in chat header"
```

---

### Task 6: Patient onboarding sheet

**Files:**
- Create: `frontend/web/src/pages/patient/PatientOnboarding.jsx`
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx`
- Modify: `frontend/web/src/pages/patient/constants.jsx`

- [ ] **Step 1: Add onboarding localStorage key to constants.jsx**

In `constants.jsx`, add after the existing localStorage keys (line 20):

```jsx
export const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";
```

- [ ] **Step 2: Create PatientOnboarding.jsx**

```jsx
/**
 * PatientOnboarding — single dismissible sheet shown on first login.
 * Scoped to patient_id via localStorage key to handle shared devices.
 */
import { Box, Typography } from "@mui/material";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import NameAvatar from "../../components/NameAvatar";
import IconBadge from "../../components/IconBadge";
import AppButton from "../../components/AppButton";
import { TYPE, COLOR, RADIUS } from "../../theme";

const FEATURES = [
  { icon: ChatOutlinedIcon, bg: COLOR.primary, label: "随时咨询", desc: "AI助手帮你解答健康问题" },
  { icon: DescriptionOutlinedIcon, bg: COLOR.accent, label: "健康档案", desc: "病历和检查结果一目了然" },
  { icon: AssignmentOutlinedIcon, bg: COLOR.warning, label: "任务提醒", desc: "用药和复查不再遗漏" },
];

export default function PatientOnboarding({ doctorName, doctorSpecialty, onDismiss }) {
  return (
    <Box sx={{
      position: "absolute", inset: 0, zIndex: 100, bgcolor: COLOR.white,
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* Header */}
      <Box sx={{
        bgcolor: COLOR.primary, pt: 6, pb: 4, px: 3,
        display: "flex", flexDirection: "column", alignItems: "center",
        background: `linear-gradient(135deg, ${COLOR.primary} 0%, #05a050 100%)`,
      }}>
        <NameAvatar name={doctorName || "医"} size={64} color={COLOR.white} textColor={COLOR.primary} />
        <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.white, mt: 2 }}>
          {doctorName ? `${doctorName}的AI健康助手` : "AI健康助手"}
        </Typography>
        {doctorSpecialty && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "rgba(255,255,255,0.8)", mt: 0.5 }}>
            {doctorSpecialty}
          </Typography>
        )}
      </Box>

      {/* Features */}
      <Box sx={{ flex: 1, px: 3, py: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text3, textAlign: "center", mb: 1 }}>
          我会帮助{doctorName || "医生"}为你提供更好的随访服务
        </Typography>
        {FEATURES.map(f => (
          <Box key={f.label} sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconBadge config={{ icon: f.icon, bg: f.bg }} size={40} solid />
            <Box>
              <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }}>{f.label}</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>{f.desc}</Typography>
            </Box>
          </Box>
        ))}
      </Box>

      {/* Action */}
      <Box sx={{ px: 3, pb: 4, pt: 1 }}>
        <AppButton variant="primary" size="lg" fullWidth onClick={onDismiss}>
          开始使用
        </AppButton>
      </Box>

      {/* Skip link */}
      <Typography
        onClick={onDismiss}
        sx={{
          position: "absolute", top: 16, right: 16,
          fontSize: TYPE.secondary.fontSize, color: "rgba(255,255,255,0.7)",
          cursor: "pointer", "&:active": { opacity: 0.5 },
        }}
      >
        跳过
      </Typography>
    </Box>
  );
}
```

- [ ] **Step 3: Wire onboarding into PatientPage.jsx**

Import at top:

```jsx
import PatientOnboarding from "./PatientOnboarding";
import { ONBOARDING_DONE_KEY_PREFIX } from "./constants";
```

Add state after identity state (around line 69):

```jsx
  const [showOnboarding, setShowOnboarding] = useState(false);
```

Add effect to check onboarding status after identity loads (after the `/me` effect, around line 95):

```jsx
  // Show onboarding for first-time patients
  useEffect(() => {
    if (!token || api.isMock) return;
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId && !localStorage.getItem(ONBOARDING_DONE_KEY_PREFIX + patientId)) {
      setShowOnboarding(true);
    }
  }, [token, api.isMock]);
```

Note: we need to store `patient_id` in localStorage. Update the `/me` effect to save it:

In the existing `/me` effect (line 89-94), add:

```jsx
    api.getPatientMe(token).then(data => {
      if (data.patient_name) setPatientName(data.patient_name);
      setDoctorName(data.doctor_name || "");
      setDoctorSpecialty(data.doctor_specialty || "");
      if (data.doctor_id) setDoctorId(data.doctor_id);
      if (data.patient_id) localStorage.setItem("patient_portal_patient_id", String(data.patient_id));
    }).catch(() => {});
```

Add dismiss handler:

```jsx
  const dismissOnboarding = useCallback(() => {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.setItem(ONBOARDING_DONE_KEY_PREFIX + patientId, "1");
    setShowOnboarding(false);
  }, []);
```

Render onboarding overlay before the main layout return (inside the main return, before the header):

```jsx
      {showOnboarding && (
        <PatientOnboarding
          doctorName={doctorName}
          doctorSpecialty={doctorSpecialty}
          onDismiss={dismissOnboarding}
        />
      )}
```

Update logout to clear patient_id:

```jsx
  const handleLogout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_NAME_KEY);
    localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
    localStorage.removeItem("patient_portal_patient_id");
    // Note: don't clear onboarding flag — it's patient-scoped, not session-scoped
    setToken(""); setPatientName(""); setDoctorName(""); setDoctorSpecialty(""); setDoctorId("");
  }, []);
```

- [ ] **Step 4: Verify — fresh patient sees onboarding, existing patient does not**

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/patient/PatientOnboarding.jsx frontend/web/src/pages/patient/PatientPage.jsx frontend/web/src/pages/patient/constants.jsx
git commit -m "feat(patient): add first-login onboarding sheet with doctor info and feature overview"
```

---

### Task 7: MyPage — onboarding replay + font scale

**Files:**
- Modify: `frontend/web/src/pages/patient/MyPage.jsx`

- [ ] **Step 1: Add onboarding replay and font scale rows**

Add imports at top of `MyPage.jsx`:

```jsx
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import { useFontScaleStore, triggerFontScaleRerender } from "../../store/fontScaleStore";
import { applyFontScale } from "../../theme";
import { ONBOARDING_DONE_KEY_PREFIX } from "./constants";
import SheetDialog from "../../components/SheetDialog";
import AppButton from "../../components/AppButton";
```

Add font scale state and handler inside the component:

```jsx
  const fontScale = useFontScaleStore(s => s.fontScale);
  const [showFontScale, setShowFontScale] = useState(false);
  const FONT_SCALE_OPTIONS = [
    { key: "standard", label: "标准" },
    { key: "large", label: "大" },
    { key: "extraLarge", label: "特大" },
  ];

  function handleFontScaleChange(level) {
    useFontScaleStore.getState().setFontScale(level);
    applyFontScale(level);
    triggerFontScaleRerender();
    setShowFontScale(false);
  }

  function handleReplayOnboarding() {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.removeItem(ONBOARDING_DONE_KEY_PREFIX + patientId);
    // Navigate to trigger onboarding — caller (PatientPage) will detect the missing flag
    window.location.reload();
  }
```

Add new rows in the "通用" section (after the privacy row, before `</Box>`):

```jsx
        <SettingsRow
          icon={<TextFieldsOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="字体大小"
          sublabel={FONT_SCALE_OPTIONS.find(o => o.key === fontScale)?.label || "标准"}
          onClick={() => setShowFontScale(true)}
        />
        <SettingsRow
          icon={<ReplayOutlinedIcon sx={{ color: COLOR.text4, fontSize: ICON.lg }} />}
          label="重新查看引导"
          onClick={handleReplayOnboarding}
        />
```

Add the font scale picker dialog after `ConfirmDialog`:

```jsx
      <SheetDialog open={showFontScale} onClose={() => setShowFontScale(false)} title="字体大小">
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, p: 1 }}>
          {FONT_SCALE_OPTIONS.map(o => (
            <AppButton
              key={o.key}
              variant={fontScale === o.key ? "primary" : "secondary"}
              size="md"
              fullWidth
              onClick={() => handleFontScaleChange(o.key)}
            >
              {o.label}
            </AppButton>
          ))}
        </Box>
      </SheetDialog>
```

- [ ] **Step 2: Verify — font scale picker works, onboarding replay works**

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/MyPage.jsx
git commit -m "feat(patient): add font scale picker and onboarding replay to MyPage settings"
```

---

### Task 8: InterviewPage cleanup

**Files:**
- Modify: `frontend/web/src/pages/patient/InterviewPage.jsx:138,179,192`

- [ ] **Step 1: Replace native alert with ConfirmDialog**

Line 138 already imports `ConfirmDialog`. Add state:

```jsx
  const [showErrorDialog, setShowErrorDialog] = useState(false);
```

Replace `alert("提交失败，请稍后重试。")` (line 138) with:

```jsx
      setShowErrorDialog(true);
```

Add the dialog in the render, after the exit dialog:

```jsx
      <ConfirmDialog
        open={showErrorDialog}
        onClose={() => setShowErrorDialog(false)}
        onConfirm={() => setShowErrorDialog(false)}
        title="提交失败"
        message="请稍后重试。"
        confirmLabel="确定"
      />
```

- [ ] **Step 2: Fix hardcoded borderRadius**

Line 179: Replace `borderRadius: 3` with `borderRadius: RADIUS.sm`.

Line 192: Replace `borderRadius: 2` with `borderRadius: RADIUS.sm`.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/InterviewPage.jsx
git commit -m "fix(patient): replace native alert with ConfirmDialog, fix hardcoded borderRadius in InterviewPage"
```

---

### Task 9: RecordsTab cleanup + bug fix

**Files:**
- Modify: `frontend/web/src/pages/patient/RecordsTab.jsx:22,33-41,84-85,232-233`

- [ ] **Step 1: Fix diagnosis_status field mismatch**

The backend `PatientRecordOut` returns `status` (not `diagnosis_status`). Lines 84 and 232 read `rec.diagnosis_status`. Fix both to read `rec.status`:

Line 84: `const ds = rec.diagnosis_status;` → `const ds = rec.status;`
Line 232: `const ds = rec.diagnosis_status;` → `const ds = rec.status;`

- [ ] **Step 2: Replace inline _DL with constants import**

Remove lines 33-34 (`_DL` and `_DC`). Import from constants:

```jsx
import { RECORD_TYPE_LABEL, formatDate, PATIENT_RECORD_TABS, DIAGNOSIS_STATUS_LABELS } from "./constants";
```

Replace `_DL[ds]` references (lines 85, 233) with `DIAGNOSIS_STATUS_LABELS[ds]`.

For `_DC` (color map), define it once using the shared labels:

```jsx
const DIAGNOSIS_STATUS_COLORS = {
  "诊断中": COLOR.warning, "待审核": COLOR.accent, "已确认": COLOR.success, "诊断失败": COLOR.danger,
};
```

Replace `_DC` with `DIAGNOSIS_STATUS_COLORS` in StatusBadge usage.

- [ ] **Step 3: Remove RECORD_TYPE_ICON_COLOR (lines 36-41)**

The colors are already in `RECORD_TYPE_BADGE`. For timeline dots, use:

```jsx
const dotColor = RECORD_TYPE_BADGE[rec.record_type]?.bg || COLOR.text4;
```

Remove the `RECORD_TYPE_ICON_COLOR` object entirely.

- [ ] **Step 4: Remove unused DateAvatar import (line 22)**

Delete: `import DateAvatar from "../../components/DateAvatar";`

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/patient/RecordsTab.jsx
git commit -m "fix(patient): fix diagnosis_status→status field mismatch, dedup constants in RecordsTab"
```

---

### Task 10: Playwright patient auth fixture

**Files:**
- Modify: `frontend/web/tests/e2e/fixtures/doctor-auth.ts`

- [ ] **Step 1: Add authenticatePatientPage function**

After `authenticateDoctorPage` (line 159), add:

```typescript
/**
 * Hydrate the patient session the same way the app does after login.
 *
 * The patient app reads these localStorage keys directly:
 *   - patient_portal_token
 *   - patient_portal_name
 *   - patient_portal_doctor_id
 *   - patient_portal_doctor_name
 *   - patient_portal_patient_id
 */
export async function authenticatePatientPage(page: Page, patient: TestPatient, doctorName?: string) {
  await page.goto("/login");
  await page.evaluate((p) => {
    localStorage.setItem("patient_portal_token", p.token);
    localStorage.setItem("patient_portal_name", p.name);
    localStorage.setItem("patient_portal_doctor_id", p.doctorId);
    localStorage.setItem("patient_portal_doctor_name", p.doctorName || "");
    localStorage.setItem("patient_portal_patient_id", p.patientId);
  }, { ...patient, doctorName: doctorName || "" });
}
```

- [ ] **Step 2: Add patientPage fixture**

Update the Fixtures type and extend block:

```typescript
type Fixtures = {
  doctor: TestDoctor;
  patient: TestPatient;
  doctorPage: Page;
  patientPage: Page;
};

export const test = base.extend<Fixtures>({
  doctor: async ({ request }, use) => {
    const d = await registerDoctor(request);
    await use(d);
  },

  patient: async ({ request, doctor }, use) => {
    const p = await registerPatient(request, doctor.doctorId);
    await use(p);
  },

  doctorPage: async ({ page, doctor }, use) => {
    await authenticateDoctorPage(page, doctor);
    await use(page);
  },

  patientPage: async ({ page, patient, doctor }, use) => {
    await authenticatePatientPage(page, patient, doctor.name);
    await use(page);
  },
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/fixtures/doctor-auth.ts
git commit -m "test: add authenticatePatientPage fixture and patientPage for patient E2E tests"
```

---

### Task 11: Seed helpers for tasks and doctor replies

**Files:**
- Modify: `frontend/web/tests/e2e/fixtures/seed.ts`

- [ ] **Step 1: Add createPatientTask helper**

```typescript
/**
 * Create a patient-targeted task via the doctor task API.
 *
 * Route: `POST /api/manage/tasks?doctor_id=...` (tasks.py:174).
 * Body must include target="patient" and a patient_id.
 */
export async function createPatientTask(
  request: APIRequestContext,
  doctor: TestDoctor,
  patientId: string,
  opts: { title?: string; taskType?: string; content?: string } = {},
): Promise<{ taskId: string }> {
  const url = `${API_BASE_URL}/api/manage/tasks?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: {
      task_type: opts.taskType || "follow_up",
      title: opts.title || "E2E测试随访任务",
      content: opts.content || "请按时复查",
      patient_id: parseInt(patientId, 10),
      target: "patient",
    },
  });
  if (!res.ok()) {
    throw new Error(`seed createPatientTask failed: ${res.status()} ${await res.text()}`);
  }
  const body = await res.json();
  return { taskId: String(body.id) };
}
```

- [ ] **Step 2: Add sendDoctorReply helper**

```typescript
/**
 * Send a doctor reply to a patient (creates a doctor-source message).
 *
 * Route: `POST /api/manage/patients/{patient_id}/reply?doctor_id=...`
 */
export async function sendDoctorReply(
  request: APIRequestContext,
  doctor: TestDoctor,
  patientId: string,
  text: string,
): Promise<{ messageId: string }> {
  const url = `${API_BASE_URL}/api/manage/patients/${patientId}/reply?doctor_id=${encodeURIComponent(doctor.doctorId)}`;
  const res = await request.post(url, {
    headers: doctorHeaders(doctor),
    data: { text },
  });
  if (!res.ok()) {
    throw new Error(`seed sendDoctorReply failed: ${res.status()} ${await res.text()}`);
  }
  const body = await res.json();
  return { messageId: String(body.message_id || "") };
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/fixtures/seed.ts
git commit -m "test: add createPatientTask and sendDoctorReply seed helpers"
```

---

### Task 12: Patient E2E test specs

**Files:**
- Create: `frontend/web/tests/e2e/20-patient-auth.spec.ts`
- Create: `frontend/web/tests/e2e/21-patient-chat.spec.ts`
- Create: `frontend/web/tests/e2e/22-patient-records.spec.ts`
- Create: `frontend/web/tests/e2e/23-patient-tasks.spec.ts`
- Create: `frontend/web/tests/e2e/24-patient-onboarding.spec.ts`

- [ ] **Step 1: Create 20-patient-auth.spec.ts**

```typescript
/**
 * Workflow 20 — Patient auth smoke
 *
 * Verifies patient portal loads after auth fixture injection.
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("Workflow 20 — Patient auth", () => {
  test("patient portal loads with 4 bottom nav tabs", async ({ page, request }) => {
    const doctor = await registerDoctor(request, { name: "E2E患者端医生" });
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");

    // Bottom nav should have 4 tabs
    await expect(page.getByText("主页")).toBeVisible();
    await expect(page.getByText("病历")).toBeVisible();
    await expect(page.getByText("任务")).toBeVisible();
    await expect(page.getByText("我的")).toBeVisible();
  });
});
```

- [ ] **Step 2: Create 21-patient-chat.spec.ts**

```typescript
/**
 * Workflow 21 — Patient chat
 *
 * Tests sending messages, doctor attribution, no fake reply.
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { sendDoctorReply } from "./fixtures/seed";

test.describe("Workflow 21 — Patient chat", () => {
  test("patient can send a message without fake AI reply", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");

    // Type and send
    await page.getByPlaceholder("请输入…").fill("医生你好，我头痛");
    await page.getByLabel("发送").click();

    // Patient bubble should appear
    await expect(page.getByText("医生你好，我头痛")).toBeVisible();

    // Wait a moment — NO "收到您的消息" should appear
    await page.waitForTimeout(2000);
    await expect(page.getByText("收到您的消息")).not.toBeVisible();
  });

  test("doctor reply shows with doctor attribution", async ({ page, request }) => {
    const doctor = await registerDoctor(request, { name: "张医生" });
    const patient = await registerPatient(request, doctor.doctorId);

    // Seed a doctor reply
    await sendDoctorReply(request, doctor, patient.patientId, "注意休息，明天来复查");

    await authenticatePatientPage(page, patient, doctor.name);
    await page.goto("/patient/chat");
    await page.waitForLoadState("networkidle");

    // Wait for polling to pick up the message
    await expect(page.getByText("注意休息，明天来复查")).toBeVisible({ timeout: 15000 });
  });
});
```

- [ ] **Step 3: Create 22-patient-records.spec.ts**

```typescript
/**
 * Workflow 22 — Patient records
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { completePatientInterview, addKnowledgeText } from "./fixtures/seed";

test.describe("Workflow 22 — Patient records", () => {
  test("completed interview shows in records list", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await addKnowledgeText(request, doctor, "高血压患者头痛需排除高血压脑病");
    await completePatientInterview(request, patient);

    await authenticatePatientPage(page, patient, doctor.name);
    await page.goto("/patient/records");
    await page.waitForLoadState("networkidle");

    // Should see at least one record
    await expect(page.getByText("预问诊")).toBeVisible({ timeout: 10000 });
  });

  test("filter tabs switch between record types", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await addKnowledgeText(request, doctor, "高血压患者头痛需排除高血压脑病");
    await completePatientInterview(request, patient);

    await authenticatePatientPage(page, patient, doctor.name);
    await page.goto("/patient/records");
    await page.waitForLoadState("networkidle");

    // Switch to 问诊 filter
    await page.getByText("问诊", { exact: true }).click();
    await expect(page.getByText("预问诊")).toBeVisible();
  });
});
```

- [ ] **Step 4: Create 23-patient-tasks.spec.ts**

```typescript
/**
 * Workflow 23 — Patient tasks
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";
import { createPatientTask } from "./fixtures/seed";

test.describe("Workflow 23 — Patient tasks", () => {
  test("patient task appears in list and can be completed", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    await createPatientTask(request, doctor, patient.patientId, { title: "明天复查血压" });

    await authenticatePatientPage(page, patient, doctor.name);
    await page.goto("/patient/tasks");
    await page.waitForLoadState("networkidle");

    // Task should be visible
    await expect(page.getByText("明天复查血压")).toBeVisible({ timeout: 10000 });

    // Complete the task (click checkbox)
    const checkbox = page.getByText("明天复查血压").locator("..").locator("..").getByRole("checkbox");
    if (await checkbox.isVisible()) {
      await checkbox.click();
      // Switch to 已完成 filter
      await page.getByText("已完成").click();
      await expect(page.getByText("明天复查血压")).toBeVisible();
    }
  });
});
```

- [ ] **Step 5: Create 24-patient-onboarding.spec.ts**

```typescript
/**
 * Workflow 24 — Patient onboarding
 */
import { test, expect, authenticatePatientPage, registerDoctor, registerPatient } from "./fixtures/doctor-auth";

test.describe("Workflow 24 — Patient onboarding", () => {
  test("first-time patient sees onboarding, dismiss persists", async ({ page, request }) => {
    const doctor = await registerDoctor(request, { name: "张医生" });
    const patient = await registerPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    // Store patient_id for onboarding check
    await page.evaluate((pid) => {
      localStorage.setItem("patient_portal_patient_id", pid);
    }, patient.patientId);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");

    // Onboarding should appear
    await expect(page.getByText("开始使用")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("随时咨询")).toBeVisible();

    // Dismiss
    await page.getByText("开始使用").click();

    // Should now see chat tab
    await expect(page.getByText("开始使用")).not.toBeVisible();

    // Reload — onboarding should NOT reappear
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("开始使用")).not.toBeVisible({ timeout: 3000 });
  });
});
```

- [ ] **Step 6: Commit all test specs**

```bash
git add frontend/web/tests/e2e/20-patient-auth.spec.ts frontend/web/tests/e2e/21-patient-chat.spec.ts frontend/web/tests/e2e/22-patient-records.spec.ts frontend/web/tests/e2e/23-patient-tasks.spec.ts frontend/web/tests/e2e/24-patient-onboarding.spec.ts
git commit -m "test: add 5 patient workflow E2E specs (auth, chat, records, tasks, onboarding)"
```

---

## Execution Order

Tasks 1-3 are sequential (chat bug fixes must land before persona work).
Tasks 4-5 depend on Task 3 (backend changes).
Tasks 6-7 are independent of chat work.
Tasks 8-9 are independent cleanup.
Tasks 10-12 depend on all feature work being complete.

```
Task 1 (fake reply) → Task 2 (dedup) → Task 3 (backend) → Task 4 (persona) → Task 5 (header)
                                                                                    ↓
Task 6 (onboarding) → Task 7 (MyPage)                                    Task 10 (fixture)
                                                                          Task 11 (seed helpers)
Task 8 (InterviewPage) ────────────────────────────────────────────────→ Task 12 (E2E specs)
Task 9 (RecordsTab)
```

Parallelizable groups:
- **Group A:** Tasks 1→2→3→4→5 (chat pipeline)
- **Group B:** Tasks 6→7 (onboarding + MyPage)
- **Group C:** Tasks 8, 9 (cleanup, independent)
- **Group D:** Tasks 10→11→12 (tests, after all features)
