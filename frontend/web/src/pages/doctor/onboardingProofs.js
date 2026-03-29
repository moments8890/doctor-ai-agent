import { ONBOARDING_EXAMPLES, getOnboardingState } from "./constants";

function findDiagnosisQueueItem(queue, preferredRuleTitle) {
  return (queue?.pending || []).find((row) => row.rule_cited === preferredRuleTitle)
    || (queue?.pending || []).find((row) => ONBOARDING_EXAMPLES.ruleTitles.includes(row.rule_cited))
    || (queue?.pending || []).find((row) => ONBOARDING_EXAMPLES.diagnosisPatientNames.includes(row.patient_name))
    || null;
}

function findReplyDraftItem(items, preferredRuleTitle) {
  const activeDrafts = items.filter((row) => row.status !== "sent");
  return activeDrafts.find((row) => row.rule_cited === preferredRuleTitle)
    || activeDrafts.find((row) => (row.cited_rules || []).some((rule) => rule.title === preferredRuleTitle))
    || activeDrafts.find((row) => ONBOARDING_EXAMPLES.ruleTitles.includes(row.rule_cited))
    || activeDrafts.find((row) => ONBOARDING_EXAMPLES.replyPatientNames.includes(row.patient_name))
    || null;
}

async function ensureExamples(api, doctorId, preferredRuleId) {
  if (typeof api.ensureOnboardingExamples !== "function") return null;
  try {
    return await api.ensureOnboardingExamples(doctorId, { knowledgeItemId: preferredRuleId || undefined });
  } catch {
    return null;
  }
}

export async function resolveDiagnosisProofDestination(api, doctorId, { preferredRuleId, preferredRuleTitle } = {}) {
  const queue = await (api.getReviewQueue || (() => Promise.resolve({ pending: [] })))(doctorId);
  const existingItem = findDiagnosisQueueItem(queue, preferredRuleTitle || "");
  if (existingItem?.record_id) {
    return `/doctor/review/${existingItem.record_id}?source=knowledge_proof&highlight_record=${existingItem.record_id}`;
  }

  const ensured = await ensureExamples(api, doctorId, preferredRuleId);
  if (ensured?.diagnosis_record_id) {
    return `/doctor/review/${ensured.diagnosis_record_id}?source=knowledge_proof&highlight_record=${ensured.diagnosis_record_id}`;
  }

  const fallbackItem = (queue?.pending || []).find((row) => row.rule_cited) || (queue?.pending || [])[0];
  if (fallbackItem?.record_id) {
    return `/doctor/review/${fallbackItem.record_id}?source=knowledge_proof&highlight_record=${fallbackItem.record_id}`;
  }

  return "/doctor/review?tab=pending&source=knowledge_proof";
}

export async function resolveReplyProofDestination(api, doctorId, { preferredRuleId, preferredRuleTitle } = {}) {
  const drafts = await (api.fetchDrafts || (() => Promise.resolve({ pending_messages: [] })))(doctorId, { includeSent: true });
  const items = Array.isArray(drafts) ? drafts : (drafts?.pending_messages || []);
  const existingItem = findReplyDraftItem(items, preferredRuleTitle || "");
  if (existingItem?.id) {
    return `/doctor/review?tab=replies&source=reply_proof&highlight_draft=${existingItem.id}`;
  }

  const ensured = await ensureExamples(api, doctorId, preferredRuleId);
  if (ensured?.reply_draft_id) {
    return `/doctor/review?tab=replies&source=reply_proof&highlight_draft=${ensured.reply_draft_id}`;
  }

  const fallbackItem = items.find((row) => row.status !== "sent" && row.draft_text) || items.find((row) => row.status !== "sent");
  if (fallbackItem?.id) {
    return `/doctor/review?tab=replies&source=reply_proof&highlight_draft=${fallbackItem.id}`;
  }

  return "/doctor/review?tab=replies&source=reply_proof";
}

export function getPreferredOnboardingRule(doctorId, explicit = {}) {
  const onboarding = getOnboardingState(doctorId);
  return {
    preferredRuleId: explicit.preferredRuleId ?? onboarding.lastSavedRuleId ?? null,
    preferredRuleTitle: explicit.preferredRuleTitle ?? onboarding.lastSavedRuleTitle ?? "",
  };
}
