/**
 * Design tokens for admin v3 — see docs/specs/2026-04-24-admin-modern-mockup-v3.html
 *
 * Theme proposal author: codex (consult mode, 2026-04-24).
 * Anchored to the mobile v2 design language (frontend/web/src/v2/theme.js)
 * so admin and mobile feel like the same product family.
 *
 * Usage rules:
 *   - Import what you need: `import { COLOR, FONT, RADIUS } from "../tokens"`
 *   - Never hardcode hex values in v3 components — every color comes from COLOR.*
 *   - Green (COLOR.brand) is reserved for: primary CTA, active nav/tab,
 *     accepted/done states, and the doctor's outbound reply bubble.
 *     Use COLOR.info for AI surfaces and secondary emphasis.
 */

// ── Colors ────────────────────────────────────────────────────────────────
export const COLOR = {
  // Background hierarchy — neutral gray-white only
  bgPage:    "#F5F7F8",
  bgCanvas:  "#EEF2F3",
  bgCard:    "#FFFFFF",
  bgCardAlt: "#FAFBFB",

  // Borders
  borderSubtle:  "#E9EEF0",
  borderDefault: "#DDE4E7",
  borderStrong:  "#C6D0D5",

  // Text — bumped contrast vs v2 for cream-bg-friendly tones
  text1: "#1A1A1A",
  text2: "#5F6B76",
  text3: "#8B98A5",
  text4: "#B0BAC2",

  // Brand — same #07C160 as mobile primary, used sparingly
  brand:      "#07C160",
  brandHover: "#06AD56",
  brandTint:  "#E7F8EE",

  // Info accent (WeChat-style indigo-blue) — AI surfaces, secondary emphasis
  info:     "#576B95",
  infoTint: "#EEF1F6",

  // Semantic — exact mobile values (matches v2/theme.js APP.danger / APP.warning)
  danger:       "#FA5151",
  dangerTint:   "#FFF1F1",
  dangerStrong: "#E03A3A",

  // warning text-on-white needs a darker variant; warningBg is the mobile fill
  warning:     "#B07A1C",
  warningBg:   "#FFC300",
  warningTint: "#FFF8E0",
};

// ── Typography ────────────────────────────────────────────────────────────
export const FONT_STACK = {
  sans:
    '"PingFang SC","Noto Sans SC","HarmonyOS Sans SC",-apple-system,' +
    'BlinkMacSystemFont,"Segoe UI",sans-serif',
  mono:
    '"SF Mono","JetBrains Mono","Roboto Mono",ui-monospace,Menlo,monospace',
};

// Font sizes (px). body=14 per codex density spec; xl=22 reserved for the
// page title in the topbar (the only >17px sans element in v3).
export const FONT = {
  xs:   11,
  sm:   12,
  base: 13,
  body: 14,
  md:   15,
  lg:   17,
  xl:   22,
};

// ── Radius / spacing / shadow ─────────────────────────────────────────────
export const RADIUS = { sm: 6, md: 8, lg: 12, pill: 999 };

export const SPACE = {
  control:    36, // button / nav-item / search input height
  cardPad:    16,
  pageGutter: 20,
  sectionGap: 16,
};

export const SHADOW = {
  s1: "0 1px 1px rgba(15, 23, 28, 0.04)",
  s2: "0 1px 2px rgba(15, 23, 28, 0.05), 0 6px 16px -8px rgba(15, 23, 28, 0.06)",
};
