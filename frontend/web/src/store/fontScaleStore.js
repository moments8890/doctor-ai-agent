import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useSyncExternalStore } from "react";
import { getPreferences, updatePreferences } from "../api";

/**
 * Font scale preference store — persisted to localStorage (instant) + backend (cross-device).
 * Values: "standard" | "large" | "extraLarge"
 */
export const useFontScaleStore = create(
  persist(
    (set) => ({
      fontScale: "large",
      setFontScale: (level) => set({ fontScale: level }),
    }),
    { name: "doctor-font-scale" }
  )
);

/** Load preferences from backend and apply to store (call after login). */
export async function syncFontScaleFromServer(doctorId) {
  try {
    const prefs = await getPreferences(doctorId);
    if (prefs?.font_scale) {
      useFontScaleStore.getState().setFontScale(prefs.font_scale);
    }
  } catch {
    // Offline or table not yet created — localStorage value stands
  }
}

/** Save current font scale to backend (fire-and-forget). */
export function saveFontScaleToServer(doctorId) {
  const { fontScale } = useFontScaleStore.getState();
  updatePreferences(doctorId, { font_scale: fontScale }).catch(() => {});
}

// ── Re-render trigger ──────────────────────────────────────────────
// useSyncExternalStore-based mechanism to force the root component tree
// to re-render when font scale changes (so TYPE Proxy values are re-read).
let _version = 0;
const _listeners = new Set();

function subscribe(cb) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}
function getSnapshot() { return _version; }

/** Call after applyFontScale() to force all subscribed components to re-render. */
export function triggerFontScaleRerender() {
  _version++;
  _listeners.forEach((cb) => cb());
}

/** Hook — subscribe the calling component to font scale changes. */
export function useFontScaleRerender() {
  useSyncExternalStore(subscribe, getSnapshot);
}
