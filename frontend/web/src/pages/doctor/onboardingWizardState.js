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
  localStorage.setItem(doneKey(doctorId), JSON.stringify({
    status,
    completedAt: new Date().toISOString(),
  }));
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
