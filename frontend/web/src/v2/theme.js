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
  accent: "#576B95",
  wechatGreen: "#95EC69",
  primaryLight: "#e7f8ee",
  dangerLight: "#fff0f0",
  text1: "#1A1A1A",
  text2: "#333",
  text3: "#666",
  text4: "#999",
  surface: "#fff",
  surfaceAlt: "#f7f7f7",
  border: "#eee",
  borderLight: "#f0f0f0",
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

  // antd-mobile base typography
  r.setProperty("--adm-font-size-main",  `${Math.round(14 * m)}px`);
  r.setProperty("--adm-font-size-xs",    `${Math.round(10 * m)}px`);
  r.setProperty("--adm-font-size-sm",    `${Math.round(12 * m)}px`);
  r.setProperty("--adm-font-size-md",    `${Math.round(15 * m)}px`);
  r.setProperty("--adm-font-size-lg",    `${Math.round(17 * m)}px`);
  r.setProperty("--adm-font-size-xl",    `${Math.round(20 * m)}px`);

  // Component-specific
  r.setProperty("--adm-button-font-size",    `${Math.round(15 * m)}px`);
  r.setProperty("--adm-navbar-font-size",    `${Math.round(17 * m)}px`);
  r.setProperty("--adm-list-item-font-size", `${Math.round(15 * m)}px`);
  r.setProperty("--adm-input-font-size",     `${Math.round(14 * m)}px`);
  r.setProperty("--adm-tabs-font-size",      `${Math.round(14 * m)}px`);
}

// ── Init ───────────────────────────────────────────────────────────
export function initTheme(fontScaleTier = "large") {
  applyThemeColors();
  applyFontScale(fontScaleTier);
}
