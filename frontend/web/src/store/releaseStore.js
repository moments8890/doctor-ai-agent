// frontend/web/src/store/releaseStore.js
//
// Seen-release tracking: localStorage (fast read) + backend preferences (durable).
// Mirrors the pattern in onboardingWizardState.js.

import { getPreferences, updatePreferences } from "../api";
import { RELEASES } from "../config/releases";

const LS_KEY = "seen_releases";

function lsKey(doctorId) {
  return `${LS_KEY}:${doctorId}`;
}

/** Read seen versions from localStorage (fast, offline). */
export function getSeenReleases(doctorId) {
  try {
    return JSON.parse(localStorage.getItem(lsKey(doctorId))) || [];
  } catch {
    return [];
  }
}

/** Check if the latest release version is unseen. */
export function hasUnseenRelease(doctorId, latestVersion) {
  return !getSeenReleases(doctorId).includes(latestVersion);
}

/** Write one version to localStorage + fire-and-forget to backend. */
export function markReleaseSeen(doctorId, version) {
  const seen = getSeenReleases(doctorId);
  if (!seen.includes(version)) {
    seen.push(version);
    localStorage.setItem(lsKey(doctorId), JSON.stringify(seen));
    updatePreferences(doctorId, { seen_releases: seen }).catch(() => {});
  }
}

/**
 * Mark all PREVIOUS releases as seen, leaving the latest unseen so the
 * "what's new" modal still pops once after onboarding. Called when a doctor
 * finishes or skips the onboarding wizard.
 */
export function markPreviousReleasesSeen(doctorId) {
  // RELEASES is newest-first → drop index 0 (the latest)
  const previousVersions = RELEASES.slice(1).map((r) => r.version);
  localStorage.setItem(lsKey(doctorId), JSON.stringify(previousVersions));
  updatePreferences(doctorId, { seen_releases: previousVersions }).catch(() => {});
}

/**
 * Sync from backend — MERGES local + remote (never overwrites).
 * Call after login. Returns a promise so callers can await completion.
 */
export async function syncSeenReleases(doctorId) {
  try {
    const prefs = await getPreferences(doctorId);
    const remote = prefs?.seen_releases || [];
    const local = getSeenReleases(doctorId);
    const merged = [...new Set([...local, ...remote])];
    localStorage.setItem(lsKey(doctorId), JSON.stringify(merged));
    // Write merged back if local had entries the backend missed
    if (merged.length > remote.length) {
      updatePreferences(doctorId, { seen_releases: merged }).catch(() => {});
    }
  } catch {
    // Network error — localStorage value stands
  }
}
