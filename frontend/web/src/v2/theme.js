/**
 * v2 theme — antd-mobile CSS variable configuration + font scaling.
 *
 * antd-mobile uses px values internally (not rem), so root font-size
 * multiplier does NOT cascade. We override specific CSS variables per
 * font scale tier.
 */

// ── Color mapping ──────────────────────────────────────────────────
export function applyThemeColors() {
  const r = document.documentElement.style;
  r.setProperty("--adm-color-primary", "#07C160");
  r.setProperty("--adm-color-danger", "#FA5151");
  r.setProperty("--adm-color-warning", "#FFC300");
  r.setProperty("--adm-color-success", "#07C160");
  r.setProperty("--adm-border-color", "#eee");
  r.setProperty("--adm-color-background", "#f7f7f7");
  r.setProperty("--adm-color-text", "#1A1A1A");
  r.setProperty("--adm-color-text-secondary", "#666");
  r.setProperty("--adm-color-weak", "#999");
  r.setProperty("--adm-color-light", "#ccc");
  r.setProperty("--adm-color-white", "#fff");
  r.setProperty("--adm-color-box", "#f5f5f5");
}

// App-specific tokens not covered by antd-mobile
export const APP = {
  // Colors
  primary: "#07C160",
  primaryHover: "#06ad56",
  accent: "#576B95",
  accentLight: "#eef1f6",
  wechatGreen: "#95EC69",
  primaryLight: "#e7f8ee",
  danger: "#FA5151",
  dangerLight: "#fff0f0",
  warning: "#FFC300",
  warningLight: "#fff8e0",
  success: "#07C160",
  successLight: "#e7f8ee",
  text1: "#1A1A1A",
  text2: "#333",
  text3: "#666",
  text4: "#999",
  surface: "#fff",
  surfaceAlt: "#f7f7f7",
  border: "#eee",
  borderLight: "#f0f0f0",
  white: "#fff",
  black: "#000",
};

// Border radius tokens
export const RADIUS = {
  xs: 4,
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  pill: 999,
  circle: "50%",
};

// Font size CSS variable references (use in inline styles)
// Hierarchy: xs < sm < base < md < lg < xl (clear visual steps)
export const FONT = {
  xs: "var(--adm-font-size-xs)",     // 10px base — micro labels, badges
  sm: "var(--adm-font-size-sm)",     // 12px base — captions, timestamps
  base: "var(--adm-font-size-main)", // 14px base — body text
  md: "var(--adm-font-size-md)",     // 16px base — emphasized body, list titles
  lg: "var(--adm-font-size-lg)",     // 18px base — section headings
  xl: "var(--adm-font-size-xl)",     // 22px base — page titles, hero text
  // Aliases for backward compat (agents may have used "main")
  main: "var(--adm-font-size-main)", // = base
};

// Category color palettes (knowledge, records, etc.)
export const CATEGORY_COLORS = {
  diagnosis:  { bg: APP.primaryLight,  text: APP.primary },
  medication: { bg: "#e8f0fe",         text: "#1B6EF3" },  // blue — no APP token
  followup:   { bg: "#fff3e0",         text: "#E67E22" },  // orange — no APP token
  custom:     { bg: "#f3f0ff",         text: "#7C3AED" },  // purple — no APP token
};

// ── Font scaling ───────────────────────────────────────────────────
const FONT_SCALES = {
  standard:   1.0,
  large:      1.2,
  extraLarge: 1.35,
};

export function applyFontScale(tier) {
  const m = FONT_SCALES[tier] || 1.0;
  const r = document.documentElement.style;

  // antd-mobile base typography — clear visual steps between each tier
  r.setProperty("--adm-font-size-xs",    `${Math.round(10 * m)}px`);  // micro
  r.setProperty("--adm-font-size-sm",    `${Math.round(12 * m)}px`);  // caption
  r.setProperty("--adm-font-size-main",  `${Math.round(14 * m)}px`);  // body (base)
  r.setProperty("--adm-font-size-md",    `${Math.round(16 * m)}px`);  // emphasized
  r.setProperty("--adm-font-size-lg",    `${Math.round(18 * m)}px`);  // heading
  r.setProperty("--adm-font-size-xl",    `${Math.round(22 * m)}px`);  // title

  // Component-specific
  r.setProperty("--adm-button-font-size",    `${Math.round(16 * m)}px`);
  r.setProperty("--adm-navbar-font-size",    `${Math.round(18 * m)}px`);
  r.setProperty("--adm-list-item-font-size", `${Math.round(16 * m)}px`);
  r.setProperty("--adm-input-font-size",     `${Math.round(14 * m)}px`);
  r.setProperty("--adm-tabs-font-size",      `${Math.round(14 * m)}px`);
}

// ── Init ───────────────────────────────────────────────────────────
export function initTheme(fontScaleTier = "large") {
  applyThemeColors();
  applyFontScale(fontScaleTier);
}
