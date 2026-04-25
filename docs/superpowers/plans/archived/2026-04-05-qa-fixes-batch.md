# QA Fixes Batch — Ship-Blockers + Dogfood Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 highest-priority issues from the QA/dogfood backlog, ordered by Codex's recommended priority: review finalize gating (ship-blocker), knowledge onboarding bug, interview error resilience, onboarding completion semantics, and diagnosis proof data cleanup.

**Architecture:** Each fix is isolated to 1-2 files. No cross-task dependencies except Task 5 (proof data) depends on Task 2 (onboarding state) sharing the same state shape. All fixes are backend+frontend pairs or frontend-only.

**Tech Stack:** FastAPI (Python), React (JSX), SQLAlchemy async, MUI, localStorage state machine

---

## Task 1: `完成审核` Gating — Frontend + Backend (SHIP-BLOCKER)

**Problem:** Doctors can finalize reviews without deciding on all suggestions. The button is always enabled if suggestions exist. The backend accepts incomplete reviews silently.

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/ReviewSubpage.jsx:187-244`
- Modify: `src/channels/web/doctor_dashboard/diagnosis_handlers.py:287-428`

### Frontend: Disable button until all suggestions decided

- [ ] **Step 1: Add decision-completeness check to ReviewSubpage**

In `ReviewSubpage.jsx`, add a computed variable after `hasSuggestions` (line 199) and use it to disable the button:

```jsx
// After line 199:
const hasSuggestions = suggestions.length > 0;

// Add this:
const allDecided = hasSuggestions && suggestions.every(
  (s) => s.decision === "confirmed" || s.decision === "rejected" || s.decision === "edited" || s.decision === "custom"
);
const undecidedCount = suggestions.filter(
  (s) => !s.decision || s.decision === null
).length;
```

Then update the button (lines 236-242) to:

```jsx
{hasSuggestions && (
  <Box sx={{ position: "absolute", bottom: 0, left: 0, right: 0, px: 2, pt: 1.5, pb: "calc(12px + env(safe-area-inset-bottom))", bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}` }}>
    <AppButton variant="primary" size="lg" fullWidth onClick={onFinalize} loading={finalizing} loadingLabel="提交中..." disabled={!allDecided}>
      {allDecided ? "完成审核" : `还有 ${undecidedCount} 项未处理`}
    </AppButton>
  </Box>
)}
```

- [ ] **Step 2: Verify button renders disabled state**

Open `/doctor/review/{id}` in browser. With undecided suggestions, the button should show "还有 N 项未处理" and be disabled. Decide all suggestions, button should change to "完成审核" and become enabled.

### Backend: Reject finalize with unresolved suggestions

- [ ] **Step 3: Add validation to finalize_review endpoint**

In `diagnosis_handlers.py`, after line 319 (`rows = await get_suggestions_for_record(db, record_id)`), add:

```python
    # Gate: all suggestions must have a decision before finalizing
    undecided = [r for r in rows if r.decision is None]
    if undecided:
        raise HTTPException(
            status_code=422,
            detail=f"还有 {len(undecided)} 条建议未处理，请先完成审核",
        )
```

- [ ] **Step 4: Verify backend rejects incomplete finalize**

```bash
# Assuming a record with undecided suggestions exists:
curl -s -X POST "http://127.0.0.1:8000/api/doctor/records/{RECORD_ID}/review/finalize" \
  -H "Content-Type: application/json" \
  -d '{"doctor_id":"test_doctor"}' | python3 -m json.tool
# Expected: 422 with detail message
```

---

## Task 2: Knowledge Onboarding — Fix savedRuleIds Bug

**Problem:** `OnboardingWizard.jsx` reads from `progress.savedRuleIds` (an array in the default state), but the save logic writes IDs to `progress.savedIds` (an object keyed by source type). So `lastRuleId` is always undefined, and `ensureOnboardingExamples` gets no knowledge item ID.

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx:247-278`

- [ ] **Step 1: Fix the savedRuleIds reference**

In `OnboardingWizard.jsx`, lines 272-274, replace:

```javascript
    const lastRuleId = progress.savedRuleIds?.[progress.savedRuleIds.length - 1];
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
```

with:

```javascript
    const lastRuleId = Object.values(progress.savedIds || {}).filter(Boolean).pop();
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
```

This reads from `savedIds` (the object that actually gets populated) and picks the last non-null value.

- [ ] **Step 2: Also update the save logic to populate savedRuleIds for consistency**

In `OnboardingWizard.jsx`, lines 247-252, the `updateProgress` call. Add `savedRuleIds` population so the state shape stays consistent with `DEFAULT_PROGRESS`:

```javascript
      updateProgress((prev) => ({
        savedSources: [...new Set([...prev.savedSources, savedSource])],
        savedTitles: { ...(prev.savedTitles || {}), [savedSource]: savedTitle || "已添加" },
        savedIds: { ...(prev.savedIds || {}), ...(savedId ? { [savedSource]: savedId } : {}) },
        savedRuleTitle: savedTitle || prev.savedRuleTitle,
        ...(savedId ? { savedRuleIds: [...new Set([...(prev.savedRuleIds || []), savedId])] } : {}),
      }));
```

- [ ] **Step 3: Verify onboarding requires all 3 sources**

Open as clean doctor. Go through onboarding step 2. Confirm:
- Adding from one source shows "已完成" for that source, "待添加" for others
- "下一步" button is NOT enabled until all 3 sources added
- After all 3, backend `ensureOnboardingExamples` receives a valid knowledge item ID

---

## Task 3: Interview "系统繁忙" — Add Retry Hint + Better Error

**Problem:** After 3 LLM failures, the patient sees "系统暂时繁忙，请稍后再试" with no way to retry. The frontend also has its own generic fallback. This is a transient error that usually resolves on retry.

**Files:**
- Modify: `src/domain/patients/interview_turn.py:263-275`
- Modify: `frontend/web/src/pages/patient/InterviewPage.jsx:124` (error handler)

- [ ] **Step 1: Backend — return a retryable status in the response**

In `interview_turn.py`, update the error branch (lines 263-275). Replace:

```python
    if llm_response is None:
        if isinstance(last_error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
            reply = "抱歉，我没有理解，请再说一次。"
        else:
            log(f"[interview] LLM call failed after 3 attempts: {last_error}", level="error")
            reply = "系统暂时繁忙，请稍后再试。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            ready_to_review=session.status == InterviewStatus.reviewing,
        )
```

with:

```python
    if llm_response is None:
        if isinstance(last_error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
            reply = "抱歉，我没有理解，请再说一次。"
            is_retryable = False
        else:
            log(f"[interview] LLM call failed after 3 attempts: {last_error}", level="error")
            reply = "系统暂时繁忙，请重新发送您的回答。"
            is_retryable = True
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            ready_to_review=session.status == InterviewStatus.reviewing,
            retryable=is_retryable,
        )
```

- [ ] **Step 2: Add retryable field to InterviewResponse if not present**

Check `InterviewResponse` model. If `retryable` field doesn't exist, add it:

```python
class InterviewResponse(BaseModel):
    # ... existing fields ...
    retryable: bool = False
```

- [ ] **Step 3: Frontend — show retry button on transient errors**

In `InterviewPage.jsx`, update the catch block (around line 124). Replace the generic error:

```javascript
setMessages(prev => [...prev, { role: "assistant", content: "系统繁忙，请稍后重试。" }]);
```

with:

```javascript
setMessages(prev => [...prev, {
  role: "assistant",
  content: "系统暂时繁忙，请重新发送您的回答。",
  retryable: true,
}]);
```

And if there's a retry button mechanism, wire `retryable` messages to re-send the last user message on tap. If not, just the improved copy is sufficient for now.

---

## Task 4: Onboarding Completion Semantics

**Problem:** Onboarding completion is marked by button click/navigation, not by actual task verification. A doctor can click through without actually completing tasks.

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx` (step advancement logic)
- Modify: `frontend/web/src/pages/doctor/onboardingWizardState.js` (state shape)

- [ ] **Step 1: Gate step advancement on actual task completion**

The wizard uses `canAdvance` state per step. The fix is to ensure each step correctly sets `canAdvance` based on real completion, not just navigation. Review each step's `setCanAdvance` call:

- **Step 1 (Knowledge):** Already correct — `setCanAdvance(false)` until `allDone` is true (all 3 sources). No change needed.
- **Step 2 (Diagnosis proof):** Should set `canAdvance` only after the doctor has actually reviewed at least one suggestion. Check if `proofData` alone is sufficient or if we need review evidence.
- **Step 5 (Patient preview):** Should set `canAdvance` only after patient interview reaches review state.

For each step that's currently click-gated, find the `setCanAdvance(true)` call and add the actual completion condition.

- [ ] **Step 2: Verify canAdvance is tied to real completion for Step 2**

Read the Step 2 component in OnboardingWizard.jsx. If `canAdvance` is set to `true` just from loading proof data (without the doctor actually reviewing), add a condition:

The doctor should at minimum view the proof data before advancing. The simplest gate: `setCanAdvance(true)` only after the user has scrolled to or interacted with the proof suggestions.

For MVP: `setCanAdvance(true)` after proof data loads is acceptable since the step's purpose is to show the doctor what AI diagnosis looks like, not to complete a real review. Document this decision.

- [ ] **Step 3: Mark completion with verification token**

In `onboardingWizardState.js`, update `markWizardDone` to include a completion summary:

```javascript
export function markWizardDone(doctorId, status = "completed") {
  if (!doctorId) return;
  localStorage.setItem(doneKey(doctorId), JSON.stringify({
    status,
    completedAt: new Date().toISOString(),
  }));
  clearWizardProgress(doctorId);
  localStorage.removeItem(`doctor_onboarding_state:v1:${doctorId}`);
  localStorage.removeItem(`onboarding_setup_done:${doctorId}`);
}
```

Update `isWizardDone` to handle both old string format and new JSON format:

```javascript
export function isWizardDone(doctorId) {
  if (!doctorId) return false;
  const flag = localStorage.getItem(doneKey(doctorId));
  if (flag) return true;  // Works for both "completed" string and JSON object
  // ... rest of migration logic ...
}
```

---

## Task 5: Diagnosis Proof Data Cleanup

**Problem:** The proof data screen creates hardcoded suggestions with destructive reset every time it's called. Multiple calls create duplicate patient records, and the data quality is noisy.

**Files:**
- Modify: `src/channels/web/doctor_dashboard/onboarding_handlers.py:153-257`

- [ ] **Step 1: Make suggestion reset idempotent instead of destructive**

In `onboarding_handlers.py`, the `_ensure_diagnosis_example` function (lines 220-254) deletes all suggestions and recreates 3 new ones every call. Change to only recreate if the suggestions don't already match:

Replace lines 220-254:

```python
    # Always reset to exactly 3 clean onboarding suggestions
    if suggestions:
        for s in suggestions:
            await db.delete(s)
        await db.flush()
```

with:

```python
    # Reuse existing suggestions if they match the expected onboarding set
    expected_contents = {"术后迟发性血肿", "尽快完成头颅CT平扫", "必要时急诊评估并处理"}
    existing_contents = {s.content for s in suggestions}
    if suggestions and existing_contents == expected_contents:
        # Already has the right suggestions, just reset decisions for re-review
        for s in suggestions:
            s.decision = None
            s.edited_text = None
        await db.commit()
        return record.id
    # Otherwise, clean slate
    if suggestions:
        for s in suggestions:
            await db.delete(s)
        await db.flush()
```

- [ ] **Step 2: Verify idempotency**

```bash
# Call the endpoint twice — should not create duplicate suggestions
curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/examples" \
  -H "Content-Type: application/json" \
  -d '{"doctor_id":"test_doctor"}' | python3 -m json.tool
# Second call:
curl -s -X POST "http://127.0.0.1:8000/api/manage/onboarding/examples" \
  -H "Content-Type: application/json" \
  -d '{"doctor_id":"test_doctor"}' | python3 -m json.tool
# Check suggestion count is still 3, not 6
```

---

## Verification

After all tasks, run the core E2E regression to confirm nothing broke:

```bash
# Start dev server
./dev.sh

# Run core checklist TC-1 through TC-4
# Then specifically verify:
# - TC-4.3: 完成审核 with undecided suggestions should be blocked
# - Onboarding wizard requires 3 knowledge sources
# - Patient interview transient errors show retry-friendly message
```

---

## Not In Scope

These items are deferred per Codex's recommendation:
- **Section 6 triage QA** — needs running app, separate QA session
- **§7 Draft & Reply rerun** — needs running app, separate QA session
- **Onboarding visual hierarchy** (dogfood #1) — cosmetic, lowest priority
- **Playwright automation** — wait for feature churn to stabilize
