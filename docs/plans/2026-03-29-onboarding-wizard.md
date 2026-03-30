# Onboarding Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 6-step guided onboarding wizard at `/doctor/onboarding` that replaces the current inline onboarding checklist on 我的AI.

**Architecture:** Single `OnboardingWizard.jsx` component with step-by-step navigation. Backend `ensureOnboardingExamples` extended to seed auto-handled messages. Old onboarding state machine replaced by wizard localStorage flags. Real app components reused for consistent look.

**Tech Stack:** React + MUI (existing), FastAPI + SQLAlchemy (existing), localStorage for wizard state.

**Spec:** `docs/specs/2026-03-29-onboarding-wizard-design.md`

---

## File Map

### New files
- `frontend/web/src/pages/doctor/OnboardingWizard.jsx` — wizard shell + all 6 step renderers
- `frontend/web/src/pages/doctor/onboardingWizardState.js` — localStorage persistence for wizard progress

### Modified files
- `frontend/web/src/App.jsx` — add `/doctor/onboarding` route
- `frontend/web/src/pages/doctor/DoctorPage.jsx` — redirect to wizard on first login, remove old welcome dialog logic
- `frontend/web/src/pages/doctor/MyAIPage.jsx` — replace `OnboardingChecklist` with "重新体验引导" link when wizard is done
- `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx` — onboarding return flow to wizard
- `frontend/web/src/pages/doctor/ReviewPage.jsx` — remove `knowledge_proof` onboarding branch
- `frontend/web/src/pages/doctor/ReviewQueuePage.jsx` — remove `reply_proof` onboarding branch
- `frontend/web/src/pages/doctor/constants.jsx` — keep `ONBOARDING_STEP` (still used by wizard)
- `frontend/web/src/api/mockApi.js` — extend mock `ensureOnboardingExamples` with `auto_handled_messages`
- `src/channels/web/ui/doctor_profile_handlers.py` — extend `ensureOnboardingExamples` endpoint + response model

### Deleted files
- `frontend/web/src/pages/doctor/onboardingProofs.js` — proof resolution logic moves into wizard

---

## Task 1: Wizard State Module

**Files:**
- Create: `frontend/web/src/pages/doctor/onboardingWizardState.js`
- Modify: `frontend/web/src/pages/doctor/constants.jsx`

This module replaces the old `doctor_onboarding_state:v1` system with two localStorage keys: a "done" flag and a "progress" blob.

- [ ] **Step 1: Create `onboardingWizardState.js`**

```javascript
// frontend/web/src/pages/doctor/onboardingWizardState.js

const WIZARD_DONE_KEY = "onboarding_wizard_done";
const WIZARD_PROGRESS_KEY = "onboarding_wizard_progress";

function doneKey(doctorId) { return `${WIZARD_DONE_KEY}:${doctorId}`; }
function progressKey(doctorId) { return `${WIZARD_PROGRESS_KEY}:${doctorId}`; }

/**
 * Check if the wizard has been completed or skipped.
 * Also migrates from old `doctor_onboarding_state:v1` if all steps were done.
 */
export function isWizardDone(doctorId) {
  if (!doctorId) return false;
  const flag = localStorage.getItem(doneKey(doctorId));
  if (flag) return true;

  // Migrate from old state machine
  const oldKey = `doctor_onboarding_state:v1:${doctorId}`;
  try {
    const raw = localStorage.getItem(oldKey);
    if (raw) {
      const old = JSON.parse(raw);
      const steps = old.steps || {};
      const allDone = steps.knowledge && steps.diagnosis && steps.reply
        && steps.patient_preview && steps.followup_task;
      if (allDone) {
        localStorage.setItem(doneKey(doctorId), "completed");
        localStorage.removeItem(oldKey);
        return true;
      }
    }
  } catch { /* ignore parse errors */ }
  return false;
}

export function markWizardDone(doctorId, status = "completed") {
  if (!doctorId) return;
  localStorage.setItem(doneKey(doctorId), status);
  clearWizardProgress(doctorId);
  // Clean up old key
  localStorage.removeItem(`doctor_onboarding_state:v1:${doctorId}`);
  localStorage.removeItem(`onboarding_setup_done:${doctorId}`);
}

export function clearWizardDone(doctorId) {
  if (!doctorId) return;
  localStorage.removeItem(doneKey(doctorId));
}

/**
 * Wizard progress: tracks current step, completed steps, and proof data IDs.
 */
const DEFAULT_PROGRESS = {
  currentStep: 1,
  completedSteps: [],
  savedSources: [],           // Step 1: ["file", "url", "text"]
  savedRuleIds: [],            // Step 1: knowledge item IDs
  savedRuleTitle: "",          // Step 1: title of last saved rule
  proofData: null,             // ensureOnboardingExamples response
  followUpTaskIds: [],         // from Step 2 finalize
  previewPatientId: null,      // from Step 5
  previewPatientName: "",      // from Step 5
};

export function getWizardProgress(doctorId) {
  if (!doctorId) return { ...DEFAULT_PROGRESS };
  try {
    const raw = localStorage.getItem(progressKey(doctorId));
    if (!raw) return { ...DEFAULT_PROGRESS };
    return { ...DEFAULT_PROGRESS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_PROGRESS };
  }
}

export function setWizardProgress(doctorId, patch) {
  if (!doctorId) return;
  const prev = getWizardProgress(doctorId);
  const next = { ...prev, ...(typeof patch === "function" ? patch(prev) : patch) };
  localStorage.setItem(progressKey(doctorId), JSON.stringify(next));
  return next;
}

export function clearWizardProgress(doctorId) {
  if (!doctorId) return;
  localStorage.removeItem(progressKey(doctorId));
}
```

- [ ] **Step 2: Verify file saves correctly**

Run: `cat frontend/web/src/pages/doctor/onboardingWizardState.js | head -5`
Expected: First 5 lines match.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/onboardingWizardState.js
git commit -m "feat(onboarding): add wizard state module with localStorage persistence"
```

---

## Task 2: Backend — Extend `ensureOnboardingExamples` with Auto-Handled Messages

**Files:**
- Modify: `src/channels/web/ui/doctor_profile_handlers.py:59-69` (response model)
- Modify: `src/channels/web/ui/doctor_profile_handlers.py:444-487` (endpoint handler)

- [ ] **Step 1: Extend the response model**

In `src/channels/web/ui/doctor_profile_handlers.py`, replace the `OnboardingExamplesResponse` class:

```python
class AutoHandledMessageItem(BaseModel):
    id: int
    patient_name: str
    content: str
    ai_reply: str
    triage: str  # "routine" | "info" | "urgent"
    status: str  # "sent" | "pending_doctor"
    draft_id: Optional[int] = None


class OnboardingExamplesResponse(BaseModel):
    status: str
    knowledge_item_id: int
    diagnosis_record_id: int
    reply_draft_id: int
    reply_message_id: int
    auto_handled_messages: list[AutoHandledMessageItem] = []
```

- [ ] **Step 2: Add `_ensure_auto_handled_messages` function**

Add this function after `_ensure_reply_example` (around line 340):

```python
_ONBOARDING_AUTO_TRIAGE = "onboarding_auto_handled"


async def _ensure_auto_handled_messages(
    db,
    *,
    doctor_id: str,
    patient_id: int,
    knowledge_item_id: int,
) -> list[dict]:
    """Create 3 seeded messages: 2 auto-handled + 1 escalated with draft."""
    # Check if we already have auto-handled onboarding messages
    existing = (
        await db.execute(
            select(PatientMessage)
            .where(
                PatientMessage.doctor_id == doctor_id,
                PatientMessage.patient_id == patient_id,
                PatientMessage.triage_category == _ONBOARDING_AUTO_TRIAGE,
            )
        )
    ).scalars().all()

    if existing:
        # Delete existing and recreate
        for msg in existing:
            # Also delete any drafts linked to this message
            await db.execute(
                delete(MessageDraft).where(MessageDraft.source_message_id == msg.id)
            )
            # Delete any outbound reply linked via reference_id
            await db.execute(
                delete(PatientMessage).where(PatientMessage.reference_id == msg.id)
            )
            await db.delete(msg)
        await db.flush()

    messages_spec = [
        {
            "content": "药还需要继续吃吗？",
            "ai_reply": "请继续按原方案服药，下次复诊时再评估。如有不适请随时联系。",
            "triage": "routine",
            "auto_send": True,
        },
        {
            "content": "复查报告出来了，一切正常",
            "ai_reply": "好的，结果已记录。如有不适随时联系。",
            "triage": "info",
            "auto_send": True,
        },
        {
            "content": "头痛又加重了，还吐了一次",
            "ai_reply": (
                "您术后头痛加重伴呕吐需要高度重视。请您尽快到医院急诊做头颅CT检查，"
                "排除术后出血可能。如果出现剧烈头痛、频繁呕吐或意识不清，请立即拨打120。"
                f" [KB-{knowledge_item_id}]"
            ),
            "triage": "urgent",
            "auto_send": False,
        },
    ]

    result = []
    for spec in messages_spec:
        inbound = PatientMessage(
            patient_id=patient_id,
            doctor_id=doctor_id,
            content=spec["content"],
            direction="inbound",
            source="patient",
            triage_category=_ONBOARDING_AUTO_TRIAGE,
            ai_handled=spec["auto_send"],
        )
        db.add(inbound)
        await db.flush()

        item = {
            "id": inbound.id,
            "patient_name": "陈伟强",
            "content": spec["content"],
            "ai_reply": spec["ai_reply"],
            "triage": spec["triage"],
        }

        if spec["auto_send"]:
            # Create outbound auto-reply
            outbound = PatientMessage(
                patient_id=patient_id,
                doctor_id=doctor_id,
                content=spec["ai_reply"],
                direction="outbound",
                source="ai",
                reference_id=inbound.id,
                triage_category=_ONBOARDING_AUTO_TRIAGE,
            )
            db.add(outbound)
            item["status"] = "sent"
        else:
            # Create pending draft for doctor review
            draft = MessageDraft(
                doctor_id=doctor_id,
                patient_id=str(patient_id),
                source_message_id=inbound.id,
                draft_text=spec["ai_reply"],
                cited_knowledge_ids=f"[{knowledge_item_id}]",
                status=DraftStatus.generated.value,
            )
            db.add(draft)
            await db.flush()
            item["status"] = "pending_doctor"
            item["draft_id"] = draft.id

        result.append(item)

    return result
```

- [ ] **Step 3: Add missing imports at top of file**

Add `delete` import if not present:

```python
from sqlalchemy import delete  # add to existing import line
```

Check existing imports and add only what's missing. The `DraftStatus` import should already exist from `_ensure_reply_example`.

- [ ] **Step 4: Wire into the endpoint handler**

In the `ensure_onboarding_examples` function (around line 465), add the auto-handled messages call after `_ensure_reply_example`:

```python
        reply_draft_id, reply_message_id = await _ensure_reply_example(
            db,
            doctor_id=resolved_doctor_id,
            patient_id=patient.id,
            knowledge_item_id=item.id,
        )
        auto_handled = await _ensure_auto_handled_messages(
            db,
            doctor_id=resolved_doctor_id,
            patient_id=patient.id,
            knowledge_item_id=item.id,
        )

    return OnboardingExamplesResponse(
        status="ok",
        knowledge_item_id=item.id,
        diagnosis_record_id=diagnosis_record_id,
        reply_draft_id=reply_draft_id,
        reply_message_id=reply_message_id,
        auto_handled_messages=auto_handled,
    )
```

- [ ] **Step 5: Verify Python compiles**

Run: `python -m py_compile src/channels/web/ui/doctor_profile_handlers.py`
Expected: No output (clean compile).

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/ui/doctor_profile_handlers.py
git commit -m "feat(onboarding): extend ensureOnboardingExamples with auto-handled messages"
```

---

## Task 3: Mock API Parity

**Files:**
- Modify: `frontend/web/src/api/mockApi.js:371-379`

- [ ] **Step 1: Update mock `ensureOnboardingExamples`**

Replace the current mock at line 371:

```javascript
export async function ensureOnboardingExamples() {
  return {
    status: "ok",
    knowledge_item_id: 7,
    diagnosis_record_id: 102,
    reply_draft_id: 101,
    reply_message_id: 201,
    auto_handled_messages: [
      {
        id: 301,
        patient_name: "陈伟强",
        content: "药还需要继续吃吗？",
        ai_reply: "请继续按原方案服药，下次复诊时再评估。如有不适请随时联系。",
        triage: "routine",
        status: "sent",
      },
      {
        id: 302,
        patient_name: "陈伟强",
        content: "复查报告出来了，一切正常",
        ai_reply: "好的，结果已记录。如有不适随时联系。",
        triage: "info",
        status: "sent",
      },
      {
        id: 303,
        patient_name: "陈伟强",
        content: "头痛又加重了，还吐了一次",
        ai_reply: "您术后头痛加重伴呕吐需要高度重视。请您尽快到医院急诊做头颅CT检查，排除术后出血可能。如果出现剧烈头痛、频繁呕吐或意识不清，请立即拨打120。",
        triage: "urgent",
        status: "pending_doctor",
        draft_id: 150,
      },
    ],
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/api/mockApi.js
git commit -m "feat(onboarding): update mock ensureOnboardingExamples with auto_handled_messages"
```

---

## Task 4: Route Registration

**Files:**
- Modify: `frontend/web/src/App.jsx`

- [ ] **Step 1: Add the onboarding route**

The wizard must be rendered outside `DoctorPage` since it hides bottom nav. Add a new `Route` alongside the existing doctor routes (around line 191).

Find the `doctorRoutes` call and add above it:

```javascript
{/* Onboarding wizard — outside DoctorPage shell (no bottom nav) */}
<Route path="/doctor/onboarding" element={
  <MobileFrame><RequireAuth><ApiProvider><OnboardingWizard /></ApiProvider></RequireAuth></MobileFrame>
} />
{doctorRoutes("/doctor", ApiProvider)}
```

Add the import at top of file:

```javascript
import OnboardingWizard from "./pages/doctor/OnboardingWizard";
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/App.jsx
git commit -m "feat(onboarding): register /doctor/onboarding route"
```

---

## Task 5: Wizard Shell Component

**Files:**
- Create: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

This is the main component. It manages step navigation, persists progress, and renders each step's content. The shell is built first with placeholder step content. Tasks 6-11 replace each placeholder with the real step implementation.

- [ ] **Step 1: Create the wizard shell**

```javascript
// frontend/web/src/pages/doctor/OnboardingWizard.jsx
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Box, Typography, LinearProgress } from "@mui/material";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useApi } from "../../api/ApiContext";
import { useDoctorStore } from "../../store/doctorStore";
import SubpageHeader from "../../components/SubpageHeader";
import AppButton from "../../components/AppButton";
import { TYPE, COLOR, RADIUS } from "../../theme";
import {
  getWizardProgress,
  setWizardProgress,
  markWizardDone,
  clearWizardProgress,
} from "./onboardingWizardState";

const TOTAL_STEPS = 6;

const STEP_TITLES = {
  1: "教 AI 你的方法",
  2: "看诊断审核",
  3: "看患者回复",
  4: "看 AI 自动处理",
  5: "体验患者预问诊",
  6: "查看生成任务",
};

function ProgressBar({ step }) {
  return (
    <Box sx={{ px: 2, py: 1, bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          步骤 {step}/{TOTAL_STEPS}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          {STEP_TITLES[step]}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={(step / TOTAL_STEPS) * 100}
        sx={{
          height: 4,
          borderRadius: 2,
          bgcolor: "#d9eeda",
          "& .MuiLinearProgress-bar": { bgcolor: COLOR.primary, borderRadius: 2 },
        }}
      />
    </Box>
  );
}

function ContextCard({ children }) {
  return (
    <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: "#f0fdf4", border: `1px solid #bbf7d0`, borderRadius: RADIUS.lg }}>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
        {children}
      </Typography>
    </Box>
  );
}

function WizardFooter({ canAdvance, onAdvance, onSkip, advanceLabel = "下一步", isLast = false }) {
  return (
    <Box sx={{
      p: 2,
      borderTop: `0.5px solid ${COLOR.border}`,
      bgcolor: COLOR.white,
      display: "flex",
      flexDirection: "column",
      gap: 1,
    }}>
      <AppButton
        variant="primary" size="md" fullWidth
        disabled={!canAdvance}
        onClick={onAdvance}
      >
        {isLast ? "完成引导" : advanceLabel}
      </AppButton>
      <Typography
        onClick={onSkip}
        sx={{
          fontSize: TYPE.caption.fontSize,
          color: COLOR.text4,
          textAlign: "center",
          cursor: "pointer",
          py: 0.5,
          "&:active": { color: COLOR.text3 },
        }}
      >
        跳过引导
      </Typography>
    </Box>
  );
}

// Step placeholder — each step will be implemented in Tasks 6-11
function StepPlaceholder({ step }) {
  return (
    <Box sx={{ p: 3, textAlign: "center" }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, color: COLOR.text3 }}>
        Step {step}: {STEP_TITLES[step]}
      </Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 1 }}>
        (Implementation pending)
      </Typography>
    </Box>
  );
}

function CompletionScreen() {
  const navigate = useAppNavigate();
  useEffect(() => {
    const timer = setTimeout(() => navigate("/doctor"), 3000);
    return () => clearTimeout(timer);
  }, [navigate]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", p: 3 }}>
      <Typography sx={{ fontSize: 48, mb: 2 }}>✓</Typography>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
        设置完成，开始使用
      </Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 1, textAlign: "center", lineHeight: 1.6 }}>
        你的 AI 已学会你的诊疗方法，可以开始处理患者消息了
      </Typography>
      <AppButton
        variant="primary" size="md"
        onClick={() => navigate("/doctor")}
        sx={{ mt: 3, minWidth: 200 }}
      >
        进入工作台
      </AppButton>
    </Box>
  );
}

export default function OnboardingWizard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useAppNavigate();
  const { doctorId } = useDoctorStore();
  const api = useApi();

  const stepParam = parseInt(searchParams.get("step") || "1", 10);
  const isDone = searchParams.get("step") === "done";

  // Load persisted progress
  const [progress, setProgress] = useState(() => getWizardProgress(doctorId));
  const [canAdvance, setCanAdvance] = useState(false);

  // Current step: use URL param, but don't go below persisted progress
  const step = isDone ? 0 : Math.max(1, Math.min(stepParam, TOTAL_STEPS));

  // Persist progress changes
  const updateProgress = useCallback((patch) => {
    const updated = setWizardProgress(doctorId, patch);
    setProgress(updated);
    return updated;
  }, [doctorId]);

  function goToStep(n) {
    setCanAdvance(false);
    setSearchParams({ step: String(n) }, { replace: true });
  }

  function handleAdvance() {
    const next = step + 1;
    const completedSteps = [...new Set([...(progress.completedSteps || []), step])];
    updateProgress({ completedSteps, currentStep: next });
    if (next > TOTAL_STEPS) {
      markWizardDone(doctorId, "completed");
      setSearchParams({ step: "done" }, { replace: true });
    } else {
      goToStep(next);
    }
  }

  function handleSkip() {
    markWizardDone(doctorId, "skipped");
    navigate("/doctor");
  }

  function handleBack() {
    if (step > 1) goToStep(step - 1);
  }

  if (isDone) {
    return <CompletionScreen />;
  }

  // Step content renderer — placeholder for now, each task below fills these in
  function renderStep() {
    switch (step) {
      case 1: return <StepPlaceholder step={1} />;
      case 2: return <StepPlaceholder step={2} />;
      case 3: return <StepPlaceholder step={3} />;
      case 4: return <StepPlaceholder step={4} />;
      case 5: return <StepPlaceholder step={5} />;
      case 6: return <StepPlaceholder step={6} />;
      default: return <StepPlaceholder step={1} />;
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader
        title={STEP_TITLES[step] || "引导"}
        onBack={step > 1 ? handleBack : undefined}
      />
      <ProgressBar step={step} />
      <Box sx={{ flex: 1, overflow: "auto" }}>
        {renderStep()}
      </Box>
      <WizardFooter
        canAdvance={canAdvance}
        onAdvance={handleAdvance}
        onSkip={handleSkip}
        isLast={step === TOTAL_STEPS}
      />
    </Box>
  );
}

// Exported for use by step implementations
export { ContextCard, STEP_TITLES };
```

- [ ] **Step 2: Verify it renders**

Start the app (`npm run dev`) and navigate to `http://localhost:5173/doctor/onboarding?step=1`. Should show the shell with placeholder content, progress bar, and footer buttons.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): wizard shell with step navigation and progress persistence"
```

---

## Task 6: Step 1 — 教 AI 三种来源的知识

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx` (replace StepPlaceholder for step 1)
- Modify: `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx` (return to wizard after save)

- [ ] **Step 1: Implement Step1Content in OnboardingWizard.jsx**

Add this component inside `OnboardingWizard.jsx`, before the `export default`:

```javascript
function Step1Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const navigate = useAppNavigate();
  const [searchParams] = useSearchParams();

  // Check for return from AddKnowledgeSubpage
  const savedSource = searchParams.get("saved");
  useEffect(() => {
    if (savedSource && !progress.savedSources.includes(savedSource)) {
      const updated = updateProgress((prev) => ({
        savedSources: [...new Set([...prev.savedSources, savedSource])],
      }));
      // Clean the URL param
      const params = new URLSearchParams(window.location.search);
      params.delete("saved");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, [savedSource]); // eslint-disable-line react-hooks/exhaustive-deps

  const savedSources = progress.savedSources || [];
  const allDone = savedSources.includes("file") && savedSources.includes("url") && savedSources.includes("text");

  // When all 3 done, call ensureOnboardingExamples and enable advance
  useEffect(() => {
    if (!allDone) { setCanAdvance(false); return; }
    if (progress.proofData) { setCanAdvance(true); return; }
    // Call backend to create proof data
    const lastRuleId = progress.savedRuleIds?.[progress.savedRuleIds.length - 1];
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
    }).then((data) => {
      if (data) {
        updateProgress({ proofData: data });
        setCanAdvance(true);
      }
    }).catch(() => {});
  }, [allDone]); // eslint-disable-line react-hooks/exhaustive-deps

  const sources = [
    { key: "file", label: "文件上传", subtitle: "PDF、Word、图片", icon: ICON_BADGES.kb_upload },
    { key: "url", label: "网址导入", subtitle: "粘贴网页链接", icon: ICON_BADGES.kb_url },
    { key: "text", label: "手动输入", subtitle: "直接输入规则文本", icon: ICON_BADGES.kb_doctor },
  ];

  return (
    <>
      <ContextCard>
        让 AI 学会你的诊疗方法 — 从三种来源各添加一条知识
      </ContextCard>
      <Box sx={{ mt: 2, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        {sources.map((s, i) => (
          <ListCard
            key={s.key}
            avatar={<IconBadge config={s.icon} />}
            title={s.label}
            subtitle={s.subtitle}
            right={
              savedSources.includes(s.key)
                ? <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600 }}>已完成</Typography>
                : <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>待添加</Typography>
            }
            chevron={!savedSources.includes(s.key)}
            onClick={savedSources.includes(s.key) ? undefined : () => {
              navigate(`/doctor/settings/knowledge/add?onboarding=1&source=${s.key}&wizard=1`);
            }}
            sx={i === sources.length - 1 ? { borderBottom: "none" } : undefined}
          />
        ))}
      </Box>
      <Box sx={{ px: 2, mt: 2 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "center" }}>
          {savedSources.length}/3 完成
        </Typography>
      </Box>
    </>
  );
}
```

Add the necessary imports at the top of the file:

```javascript
import ListCard from "../../components/ListCard";
import IconBadge from "../../components/IconBadge";
import { ICON_BADGES } from "./constants";
```

Replace the step 1 case in `renderStep()`:

```javascript
case 1: return <Step1Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Modify AddKnowledgeSubpage to return to wizard**

In `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx`, find the `handleKnowledgeSaved` function (line 95). Modify the onboarding branch:

```javascript
function handleKnowledgeSaved(text, knowledgeItemId = null) {
  const title = deriveRuleTitle(text);
  const params = new URLSearchParams(window.location.search);
  const wizardMode = params.get("wizard") === "1";
  const sourceType = params.get("source") || "text";

  if (wizardMode) {
    // Return to wizard with saved source info
    navigate(`/doctor/onboarding?step=1&saved=${sourceType}`);
    return;
  }

  // Existing onboarding mode (non-wizard) — keep for backward compat
  markOnboardingStep(doctorId, ONBOARDING_STEP.knowledge, {
    lastSavedRuleTitle: title,
    lastSavedRuleId: knowledgeItemId,
    lastSavedRuleAt: new Date().toISOString(),
  });
  if (onboardingMode) {
    setSavedRuleTitle(title);
    setNextStepOpen(true);
    return;
  }
  onBack();
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx
git commit -m "feat(onboarding): implement Step 1 — add knowledge from 3 sources"
```

---

## Task 7: Step 2 — 看 AI 如何用于诊断审核

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Implement Step2Content**

Add this component in `OnboardingWizard.jsx`:

```javascript
function Step2Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const proofData = progress.proofData;
  const [suggestion, setSuggestion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const { getSuggestions, decideSuggestion, finalizeReview } = api;

  // Fetch the first suggestion from the proof record
  useEffect(() => {
    if (!proofData?.diagnosis_record_id) return;
    getSuggestions(proofData.diagnosis_record_id, doctorId)
      .then((data) => {
        const items = Array.isArray(data) ? data : (data.suggestions || data.items || []);
        const first = items.find((s) => s.section === "differential") || items[0];
        setSuggestion(first || null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [proofData?.diagnosis_record_id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleConfirm() {
    if (!suggestion || confirming) return;
    setConfirming(true);
    try {
      // Confirm this suggestion
      await decideSuggestion(suggestion.id, "accept");
      // Auto-confirm remaining suggestions + finalize
      const allData = await getSuggestions(proofData.diagnosis_record_id, doctorId);
      const allItems = Array.isArray(allData) ? allData : (allData.suggestions || allData.items || []);
      for (const item of allItems) {
        if (item.id !== suggestion.id && !item.decision) {
          await decideSuggestion(item.id, "accept").catch(() => {});
        }
      }
      const result = await finalizeReview(proofData.diagnosis_record_id, doctorId);
      const taskIds = result?.follow_up_task_ids || [];
      updateProgress({ followUpTaskIds: taskIds });
      setConfirmed(true);
      setCanAdvance(true);
    } catch {
      // Allow advance even on error — proof was shown
      setConfirmed(true);
      setCanAdvance(true);
    } finally {
      setConfirming(false);
    }
  }

  if (loading) {
    return <Box sx={{ p: 3, textAlign: "center" }}><Typography sx={{ color: COLOR.text4 }}>加载中...</Typography></Box>;
  }

  return (
    <>
      <ContextCard>
        你刚保存的规则会在诊断审核中被引用
        {progress.savedRuleTitle ? (
          <Box component="span" sx={{ display: "inline-block", ml: 0.5, px: 1, py: 0.25, bgcolor: "#d1fae5", color: "#065f46", borderRadius: "999px", fontSize: TYPE.caption.fontSize, fontWeight: 600 }}>
            {progress.savedRuleTitle}
          </Box>
        ) : null}
      </ContextCard>

      {/* Patient case summary */}
      <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
          陈伟强 · 男 · 42岁
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
          主诉：术后头痛加剧伴恶心1天。脑膜瘤术后第7天，今日晨起头痛较昨日明显加重，伴恶心，无发热。
        </Typography>
      </Box>

      {/* Diagnosis suggestion card */}
      {suggestion && (
        <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              {suggestion.content}
            </Typography>
            <Box sx={{ px: 1, py: 0.25, bgcolor: "#fef3c7", color: "#92400e", borderRadius: "999px", fontSize: 11, fontWeight: 600 }}>
              {suggestion.confidence || "高"}
            </Box>
          </Box>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.6, mb: 1.5 }}>
            {(suggestion.detail || "").replace(/\[KB-\d+\]/g, "").trim()}
          </Typography>
          {/* Cited rule */}
          <Box sx={{ px: 1.5, py: 1, bgcolor: "#f0fdf4", borderRadius: RADIUS.md, border: "1px solid #bbf7d0" }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#065f46", lineHeight: 1.5 }}>
              引用规则: {progress.savedRuleTitle || "你保存的临床规则"}
            </Typography>
          </Box>
          {/* Action */}
          {!confirmed && (
            <Box sx={{ display: "flex", gap: 1, mt: 2 }}>
              <AppButton variant="primary" size="md" fullWidth onClick={handleConfirm} disabled={confirming} loading={confirming} loadingLabel="确认中...">
                确认建议
              </AppButton>
            </Box>
          )}
          {confirmed && (
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 600, mt: 2, textAlign: "center" }}>
              ✓ 已确认
            </Typography>
          )}
        </Box>
      )}
    </>
  );
}
```

Replace step 2 case in `renderStep()`:

```javascript
case 2: return <Step2Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): implement Step 2 — diagnosis review proof"
```

---

## Task 8: Step 3 — 看 AI 如何起草患者回复

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Implement Step3Content**

```javascript
function Step3Content({ doctorId, progress, setCanAdvance, api }) {
  const proofData = progress.proofData;
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  const { fetchDrafts, sendDraft } = api;

  useEffect(() => {
    if (!proofData?.reply_draft_id) return;
    fetchDrafts(doctorId, { includeSent: true })
      .then((data) => {
        const items = Array.isArray(data) ? data : (data.pending_messages || []);
        const match = items.find((d) => d.id === proofData.reply_draft_id) || items[0];
        setDraft(match || null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [proofData?.reply_draft_id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSend() {
    if (!draft || sending) return;
    setSending(true);
    try {
      await sendDraft(draft.id, doctorId);
      setSent(true);
      setCanAdvance(true);
    } catch {
      setSent(true);
      setCanAdvance(true);
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <Box sx={{ p: 3, textAlign: "center" }}><Typography sx={{ color: COLOR.text4 }}>加载中...</Typography></Box>;
  }

  return (
    <>
      <ContextCard>同一条规则也影响患者沟通草稿</ContextCard>

      {/* Patient message */}
      <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: "#95ec69", borderRadius: RADIUS.lg, maxWidth: "85%", ml: "auto", mr: 2 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.6 }}>
          {draft?.patient_message || "张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？"}
        </Typography>
      </Box>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "right", mr: 2, mt: 0.5 }}>
        陈伟强
      </Typography>

      {/* AI draft */}
      <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600, mb: 1 }}>
          AI按你的话术起草
        </Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.7, whiteSpace: "pre-line" }}>
          {draft?.draft_text || ""}
        </Typography>
        {/* Cited rule */}
        <Box sx={{ mt: 1.5, px: 1.5, py: 1, bgcolor: "#f0fdf4", borderRadius: RADIUS.md, border: "1px solid #bbf7d0" }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#065f46", lineHeight: 1.5 }}>
            引用: {progress.savedRuleTitle || "你保存的临床规则"}
          </Typography>
        </Box>
        {!sent && (
          <Box sx={{ display: "flex", gap: 1, mt: 2 }}>
            <AppButton variant="primary" size="md" fullWidth onClick={handleSend} disabled={sending} loading={sending} loadingLabel="发送中...">
              发送
            </AppButton>
          </Box>
        )}
        {sent && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 600, mt: 2, textAlign: "center" }}>
            ✓ 已发送
          </Typography>
        )}
      </Box>
    </>
  );
}
```

Replace step 3 case in `renderStep()`:

```javascript
case 3: return <Step3Content doctorId={doctorId} progress={progress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): implement Step 3 — reply draft proof"
```

---

## Task 9: Step 4 — 看 AI 如何自动处理患者消息

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Implement Step4Content**

```javascript
function Step4Content({ doctorId, progress, setCanAdvance, api }) {
  const autoMessages = progress.proofData?.auto_handled_messages || [];
  const [confirmed, setConfirmed] = useState(false);
  const [sending, setSending] = useState(false);

  const escalated = autoMessages.find((m) => m.status === "pending_doctor");
  const handled = autoMessages.filter((m) => m.status === "sent");

  async function handleConfirmEscalation() {
    if (!escalated?.draft_id || sending) return;
    setSending(true);
    try {
      await api.sendDraft(escalated.draft_id, doctorId);
    } catch { /* allow advance on error */ }
    setConfirmed(true);
    setCanAdvance(true);
    setSending(false);
  }

  // If no auto messages (mock or backend didn't return them), auto-advance
  useEffect(() => {
    if (autoMessages.length === 0) setCanAdvance(true);
  }, [autoMessages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  function MessageCard({ msg, isEscalated }) {
    const tagColor = isEscalated ? "#f59e0b" : COLOR.primary;
    const tagBg = isEscalated ? "#fef3c7" : "#d1fae5";
    const tagText = isEscalated ? "需医生确认" : "已自动回复";

    return (
      <Box sx={{ mx: 2, mt: 1.5, p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text1 }}>
            {msg.patient_name}
          </Typography>
          <Box sx={{ px: 1, py: 0.25, bgcolor: tagBg, color: tagColor, borderRadius: "999px", fontSize: 11, fontWeight: 600 }}>
            {tagText}
          </Box>
        </Box>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
          {msg.content}
        </Typography>
        <Box sx={{ mt: 1, pl: 1.5, borderLeft: `2px solid ${isEscalated ? "#f59e0b" : COLOR.primary}` }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.6 }}>
            AI: {msg.ai_reply?.replace(/\[KB-\d+\]/g, "").trim()}
          </Typography>
        </Box>
        {isEscalated && !confirmed && (
          <Box sx={{ display: "flex", gap: 1, mt: 1.5 }}>
            <AppButton variant="primary" size="sm" fullWidth onClick={handleConfirmEscalation} disabled={sending} loading={sending} loadingLabel="发送中...">
              确认发送
            </AppButton>
          </Box>
        )}
        {isEscalated && confirmed && (
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600, mt: 1.5, textAlign: "center" }}>
            ✓ 已确认发送
          </Typography>
        )}
      </Box>
    );
  }

  return (
    <>
      <ContextCard>患者发来消息后，AI 会自动判断并处理</ContextCard>
      {handled.map((msg) => (
        <MessageCard key={msg.id} msg={msg} isEscalated={false} />
      ))}
      {escalated && <MessageCard msg={escalated} isEscalated={true} />}
    </>
  );
}
```

Replace step 4 case in `renderStep()`:

```javascript
case 4: return <Step4Content doctorId={doctorId} progress={progress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): implement Step 4 — AI auto-handling proof"
```

---

## Task 10: Step 5 — 体验患者预问诊

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Implement Step5Content**

```javascript
function Step5Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const [patientName, setPatientName] = useState("");
  const [qrData, setQrData] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [previewSubmitted, setPreviewSubmitted] = useState(false);

  const { createOnboardingPatientEntry } = api;

  async function handleGenerate() {
    if (!patientName.trim() || generating) return;
    setGenerating(true);
    try {
      const data = await createOnboardingPatientEntry(doctorId, { patientName: patientName.trim() });
      setQrData(data);
      updateProgress({
        previewPatientId: data.patient_id,
        previewPatientName: patientName.trim(),
      });
    } catch { /* show error */ }
    setGenerating(false);
  }

  function handlePreview() {
    if (!qrData) return;
    const previewUrl = `/doctor/preview/${qrData.patient_id}?patient_token=${encodeURIComponent(qrData.token)}&patient_name=${encodeURIComponent(patientName)}&wizard_return=1`;
    window.location.href = previewUrl;
  }

  // Check if returning from preview with submission done
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("preview_done") === "1") {
      setPreviewSubmitted(true);
      setCanAdvance(true);
      // Clean URL
      params.delete("preview_done");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <ContextCard>为患者生成预问诊入口，预览患者体验</ContextCard>

      <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `0.5px solid ${COLOR.border}` }}>
        {!qrData ? (
          <>
            <TextField
              label="患者姓名"
              placeholder="请输入患者姓名，例如：李阿姨"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              fullWidth
              sx={{ mb: 2 }}
            />
            <AppButton variant="primary" size="md" fullWidth onClick={handleGenerate} disabled={!patientName.trim() || generating} loading={generating} loadingLabel="生成中...">
              生成入口
            </AppButton>
          </>
        ) : (
          <>
            {/* QR display */}
            <Box sx={{ textAlign: "center", py: 2 }}>
              {qrData.qr_url && <Box component="img" src={qrData.qr_url} sx={{ width: 200, height: 200, mx: "auto" }} />}
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, mt: 1 }}>
                {patientName} 预问诊码
              </Typography>
            </Box>
            <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
              <AppButton variant="primary" size="md" fullWidth onClick={handlePreview}>
                预览患者端
              </AppButton>
              <AppButton variant="secondary" size="md" fullWidth onClick={() => navigator.clipboard?.writeText(qrData.link || "")}>
                复制链接
              </AppButton>
            </Box>
            {previewSubmitted && (
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 600, mt: 2, textAlign: "center" }}>
                ✓ 患者预问诊已提交
              </Typography>
            )}
          </>
        )}
      </Box>
    </>
  );
}
```

Add `TextField` to the MUI imports at the top:

```javascript
import { Box, Typography, LinearProgress, TextField } from "@mui/material";
```

Replace step 5 case in `renderStep()`:

```javascript
case 5: return <Step5Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): implement Step 5 — patient pre-interview"
```

---

## Task 11: Step 6 — 查看生成任务

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Implement Step6Content**

```javascript
function Step6Content({ doctorId, progress, setCanAdvance, api }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setCanAdvance(true); // View-only step — always advanceable
    const { getTasks } = api;
    if (!getTasks) { setLoading(false); return; }
    getTasks(doctorId, "pending")
      .then((data) => {
        const items = Array.isArray(data) ? data : (data.items || []);
        setTasks(items);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  const followUpTaskIds = progress.followUpTaskIds || [];
  const reviewTasks = tasks.filter((t) => t.task_type === "review" || t.title?.includes("审阅"));
  const followUpTasks = tasks.filter((t) => followUpTaskIds.includes(t.id));
  // If we can't match by ID, show all non-review tasks
  const displayFollowUp = followUpTasks.length > 0 ? followUpTasks : tasks.filter((t) => !reviewTasks.includes(t)).slice(0, 3);

  if (loading) {
    return <Box sx={{ p: 3, textAlign: "center" }}><Typography sx={{ color: COLOR.text4 }}>加载中...</Typography></Box>;
  }

  function TaskItem({ task, tagLabel, tagColor, tagBg }) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
            {task.title}
          </Typography>
          {task.patient_name && (
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.25 }}>
              患者: {task.patient_name}
            </Typography>
          )}
        </Box>
        <Box sx={{ px: 1, py: 0.25, bgcolor: tagBg, color: tagColor, borderRadius: "999px", fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
          {tagLabel}
        </Box>
      </Box>
    );
  }

  return (
    <>
      <ContextCard>系统会在两个时刻自动创建任务</ContextCard>

      {reviewTasks.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Box sx={{ px: 2, py: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 600, color: COLOR.text3 }}>
              审核任务（患者提交后创建）
            </Typography>
          </Box>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            {reviewTasks.map((t) => (
              <TaskItem key={t.id} task={t} tagLabel="审核任务" tagColor="#1d4ed8" tagBg="#eff6ff" />
            ))}
          </Box>
        </Box>
      )}

      {displayFollowUp.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Box sx={{ px: 2, py: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 600, color: COLOR.text3 }}>
              随访任务（审核完成后创建）
            </Typography>
          </Box>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            {displayFollowUp.map((t) => (
              <TaskItem key={t.id} task={t} tagLabel="来自诊断审核" tagColor="#065f46" tagBg="#d1fae5" />
            ))}
          </Box>
        </Box>
      )}

      {reviewTasks.length === 0 && displayFollowUp.length === 0 && (
        <Box sx={{ p: 3, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
            暂无任务数据
          </Typography>
        </Box>
      )}
    </>
  );
}
```

Replace step 6 case in `renderStep()`:

```javascript
case 6: return <Step6Content doctorId={doctorId} progress={progress} setCanAdvance={setCanAdvance} api={api} />;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/doctor/OnboardingWizard.jsx
git commit -m "feat(onboarding): implement Step 6 — view generated tasks"
```

---

## Task 12: Entry/Exit Logic — DoctorPage Redirect + MyAI Cleanup

**Files:**
- Modify: `frontend/web/src/pages/doctor/DoctorPage.jsx`
- Modify: `frontend/web/src/pages/doctor/MyAIPage.jsx`

- [ ] **Step 1: Add wizard redirect in DoctorPage**

In `DoctorPage.jsx`, in the `useDoctorPageState` hook, add a redirect check after the existing setup dialog logic. Find the `useEffect` with `getDoctorProfile` (around line 712) and add below it:

```javascript
  // Redirect to onboarding wizard on first login
  useEffect(() => {
    if (!doctorId) return;
    if (!isWizardDone(doctorId)) {
      navigate("/doctor/onboarding");
    }
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
```

Add import at top:

```javascript
import { isWizardDone } from "./onboardingWizardState";
```

Also remove the old `onboarding_setup_done` localStorage check and the `OnboardingDialog` component usage, since the wizard now handles initial setup. The welcome name dialog can be the first thing in the wizard or removed entirely.

- [ ] **Step 2: Simplify MyAIPage onboarding section**

In `MyAIPage.jsx`, replace the `OnboardingChecklist` usage with a simple replay link. Find where `<OnboardingChecklist>` is rendered (around line 411) and replace:

```javascript
{isWizardDone(doctorId) ? (
  <Box sx={{ px: 2, py: 1.5 }}>
    <Typography
      onClick={() => navigate("/doctor/onboarding?step=1")}
      sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, cursor: "pointer", textDecoration: "underline" }}
    >
      重新体验引导
    </Typography>
  </Box>
) : (
  <OnboardingChecklist rows={checklistRows} completedCount={completedChecklistCount} />
)}
```

Add import:

```javascript
import { isWizardDone } from "./onboardingWizardState";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/doctor/DoctorPage.jsx frontend/web/src/pages/doctor/MyAIPage.jsx
git commit -m "feat(onboarding): add wizard redirect + replace MyAI checklist with replay link"
```

---

## Task 13: Remove Old Onboarding Branches from Production Pages

**Files:**
- Modify: `frontend/web/src/pages/doctor/ReviewPage.jsx`
- Modify: `frontend/web/src/pages/doctor/ReviewQueuePage.jsx`
- Delete: `frontend/web/src/pages/doctor/onboardingProofs.js`

- [ ] **Step 1: Remove `knowledge_proof` source handling from ReviewPage**

In `ReviewPage.jsx`, remove the onboarding-specific comment (around line 240):

```javascript
  // Step 2 onboarding: mark complete only when doctor finalizes review (not on page visit)
```

And in `handleFinalize`, remove the `knowledge_proof` block:

```javascript
      // Remove this block:
      if (source === "knowledge_proof") {
        markOnboardingStep(doctorId, ONBOARDING_STEP.diagnosis);
      }
```

Also remove the import of `markOnboardingStep` and `ONBOARDING_STEP` if they're no longer used elsewhere in the file. Check for other references first.

- [ ] **Step 2: Remove `reply_proof` source handling from ReviewQueuePage**

In `ReviewQueuePage.jsx`, remove the onboarding-specific comment (around line 290):

```javascript
  // Step 3 onboarding: mark complete only when doctor sends a reply (not on page visit)
```

And in `handleSendDraft`, remove the `reply_proof` block:

```javascript
      // Remove this block:
      if (source === "reply_proof") {
        markOnboardingStep(doctorId, ONBOARDING_STEP.reply);
      }
```

Also remove the reply_proof banner (around lines 357-376) if it exists.

Remove unused imports of `markOnboardingStep` and `ONBOARDING_STEP`.

- [ ] **Step 3: Delete `onboardingProofs.js`**

```bash
git rm frontend/web/src/pages/doctor/onboardingProofs.js
```

Remove imports of this file from `MyAIPage.jsx` and `AddKnowledgeSubpage.jsx` if present. The wizard resolves proof destinations directly from its own state.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor(onboarding): remove old proof branches from production pages"
```

---

## Task 14: Smoke Test

- [ ] **Step 1: Verify wizard flow**

1. Clear localStorage: `localStorage.clear()` in browser console
2. Navigate to `http://localhost:5173/doctor` — should redirect to `/doctor/onboarding?step=1`
3. Walk through Steps 1-6
4. After completion, should land on `/doctor` with no onboarding checklist
5. "重新体验引导" link should be visible on 我的AI

- [ ] **Step 2: Verify skip flow**

1. Clear localStorage
2. Navigate to `/doctor` → redirected to wizard
3. Click "跳过引导"
4. Should land on `/doctor` with normal dashboard
5. Next navigation to `/doctor` should NOT redirect to wizard again

- [ ] **Step 3: Verify refresh persistence**

1. Clear localStorage
2. Start wizard, complete Step 1 (add 3 knowledge sources)
3. Refresh the page
4. Should resume at step 2, not restart from step 1
5. Proof data should still be available

- [ ] **Step 4: Verify production pages are clean**

1. Navigate to `/doctor/review/{recordId}` directly
2. No onboarding banners or "下一步" links should appear
3. Navigate to `/doctor/review?tab=replies` directly
4. No "reply_proof" banners should appear

---

## Task 15: Documentation Updates

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/product/feature-parity-matrix.md`

- [ ] **Step 1: Update architecture.md**

Add the onboarding wizard to the frontend routes section:

```markdown
### Onboarding Wizard

- Route: `/doctor/onboarding?step=1-6`
- Dedicated step-by-step guided flow for new doctors
- Reuses real app components (FieldReviewCard, ReplyCard, ActionRow)
- State persisted in localStorage (`onboarding_wizard_done`, `onboarding_wizard_progress`)
- Backend proof data via `POST /api/manage/onboarding/examples`
- Auto-redirects on first login, skippable, replayable via 我的AI
```

- [ ] **Step 2: Update feature-parity-matrix.md**

Add onboarding wizard row:

```markdown
| Onboarding wizard | 6-step guided flow | ✅ Web | ❌ WeChat | `/doctor/onboarding` |
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md docs/product/feature-parity-matrix.md
git commit -m "docs: add onboarding wizard to architecture and feature matrix"
```
