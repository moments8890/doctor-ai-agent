/**
 * Patient font scale — local-only (no server sync, unlike the doctor store).
 *
 * Default tier: "large" (1.15×). The patient audience skews older / less
 * tech-comfortable, so the larger default and the 3-option selector
 * (standard / large / extraLarge) are deliberately preserved here.
 *
 * The doctor app uses a separate store (store/fontScaleStore) keyed under
 * "doctor-font-scale" and auto-syncs to the doctor backend. Patient must NOT
 * use that store — it would cross-contaminate doctor preferences in shared-
 * browser scenarios.
 */
import { applyFontScale } from "../theme";

const FONT_SCALE_KEY = "v2_patient_font_scale";

export const FONT_SCALE_OPTIONS = [
  { key: "standard",   label: "标准" },
  { key: "large",      label: "大" },
  { key: "extraLarge", label: "特大" },
];

export function getFontScale() {
  return localStorage.getItem(FONT_SCALE_KEY) || "large";
}

export function setFontScale(tier) {
  localStorage.setItem(FONT_SCALE_KEY, tier);
  applyFontScale(tier);
}

export function getFontScaleLabel(tier) {
  return FONT_SCALE_OPTIONS.find((o) => o.key === tier)?.label || "标准";
}

// One-shot migration from the legacy v2_font_scale key (used by MyPage before
// extraction). Idempotent: only runs if the new key is empty AND the legacy
// key has a value.
(function migrate() {
  if (typeof localStorage === "undefined") return;
  if (localStorage.getItem(FONT_SCALE_KEY)) return;
  const legacy = localStorage.getItem("v2_font_scale");
  if (!legacy) return;
  localStorage.setItem(FONT_SCALE_KEY, legacy);
  localStorage.removeItem("v2_font_scale");
})();
