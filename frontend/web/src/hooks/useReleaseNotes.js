// frontend/web/src/hooks/useReleaseNotes.js
//
// Triggers the "what's new" modal for returning users.
// Waits for backend sync before checking (prevents cross-device race).

import { useState, useEffect, useCallback } from "react";
import { getLatestRelease } from "../config/releases";
import {
  syncSeenReleases,
  hasUnseenRelease,
  markReleaseSeen,
} from "../store/releaseStore";

export function useReleaseNotes(doctorId) {
  const [showDialog, setShowDialog] = useState(false);
  const [release, setRelease] = useState(null);
  const [syncDone, setSyncDone] = useState(false);

  // Step 1: sync seen_releases from backend (merges local + remote)
  // Previously gated on finished_onboarding; that locked out doctors who
  // registered before the wizard existed (most Tencent prod users), so
  // they never saw release notes. Now: any authenticated doctor.
  useEffect(() => {
    if (!doctorId) return;
    syncSeenReleases(doctorId).finally(() => setSyncDone(true));
  }, [doctorId]);

  // Step 2: after sync completes, check for unseen releases
  useEffect(() => {
    if (!syncDone || !doctorId) return;
    const latest = getLatestRelease();
    if (!latest) return;
    if (!hasUnseenRelease(doctorId, latest.version)) return;

    // Short delay so the page paints first
    const timer = setTimeout(() => {
      setRelease(latest);
      setShowDialog(true);
    }, 300);
    return () => clearTimeout(timer);
  }, [syncDone, doctorId]);

  const dismiss = useCallback(() => {
    setShowDialog(false);
    if (release) markReleaseSeen(doctorId, release.version);
  }, [doctorId, release]);

  return { showDialog, release, dismiss };
}
