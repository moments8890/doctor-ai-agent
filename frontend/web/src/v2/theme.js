/**
 * v2 theme — antd-mobile CSS variable configuration + font/icon scaling.
 *
 * Sizing is tuned for WeChat-style ease-of-use with a slight bump toward
 * 40+ readability (WCAG AA 16px body, iOS HIG 44pt touch targets).
 * See CLAUDE.md § "UI Design System — Tokens" for the rules.
 *
 * antd-mobile uses px values (not rem), so root font-size multiplier does
 * NOT cascade. We override CSS variables per font scale tier.
 */

// ── Color mapping ──────────────────────────────────────────────────
export function applyThemeColors() {
  const r = document.documentElement.style;
  r.setProperty("--adm-color-primary", "#07C160");
  r.setProperty("--adm-color-danger", "#FA5151");
  r.setProperty("--adm-color-warning", "#FFC300");
  r.setProperty("--adm-color-success", "#07C160");
  r.setProperty("--adm-border-color", "#eee");
  r.setProperty("--adm-color-background", "#ffffff");
  r.setProperty("--adm-color-text", "#1A1A1A");
  r.setProperty("--adm-color-text-secondary", "#666");
  r.setProperty("--adm-color-weak", "#999");
  r.setProperty("--adm-color-light", "#ccc");
  r.setProperty("--adm-color-white", "#fff");
  r.setProperty("--adm-color-box", "#f7f7f7");
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

/**
 * Font size tokens (inline-style references).
 *
 * Base values below are in the "standard" tier (1.0×). Tiers scale all
 * values proportionally (compact 0.9× / standard 1.0× / large 1.15× /
 * extraLarge 1.3×). Values picked for 40+ readability while staying
 * close to WeChat's look:
 *   xs 11 → badges / micro meta
 *   sm 13 → tab labels, captions, timestamps
 *   base 15 → body text
 *   md 17 → list-item titles, emphasized body (WeChat body standard)
 *   lg 19 → section headings
 *   xl 22 → page titles / hero
 */
export const FONT = {
  xs:   "var(--adm-font-size-xs)",     // 11px standard
  sm:   "var(--adm-font-size-sm)",     // 13px
  base: "var(--adm-font-size-main)",   // 15px
  md:   "var(--adm-font-size-md)",     // 17px
  lg:   "var(--adm-font-size-lg)",     // 19px
  xl:   "var(--adm-font-size-xl)",     // 22px
  main: "var(--adm-font-size-main)",   // alias for base
};

/**
 * Icon size tokens (inline-style references).
 *
 * Tier-scaled. Use for MUI-style / antd-mobile icon `fontSize` props.
 *   xs 16 → inline meta (timestamps w/ icon)
 *   sm 20 → list-item prefix / NavBar action
 *   md 24 → primary action button inside a list row
 *   lg 28 → bottom TabBar
 *   xl 32 → hero / empty-state
 */
export const ICON = {
  xs: "var(--icon-size-xs)",
  sm: "var(--icon-size-sm)",
  md: "var(--icon-size-md)",
  lg: "var(--icon-size-lg)",
  xl: "var(--icon-size-xl)",
};

// Category color palettes (knowledge, records, etc.)
export const CATEGORY_COLORS = {
  diagnosis:  { bg: APP.primaryLight,  text: APP.primary },
  medication: { bg: "#e8f0fe",         text: "#1B6EF3" },  // blue — no APP token
  followup:   { bg: "#fff3e0",         text: "#E67E22" },  // orange — no APP token
  custom:     { bg: "#f3f0ff",         text: "#7C3AED" },  // purple — no APP token
};

// ── Font / icon scaling ─────────────────────────────────────────────
const FONT_SCALES = {
  compact:    0.9,
  standard:   1.0,
  large:      1.15,
  extraLarge: 1.3,
};

export function applyFontScale(tier) {
  const m = FONT_SCALES[tier] ?? 1.0;
  const r = document.documentElement.style;
  const px = (base) => `${Math.round(base * m)}px`;

  // App semantic tokens (standard-tier base values)
  r.setProperty("--adm-font-size-xs",   px(11));  // badges
  r.setProperty("--adm-font-size-sm",   px(13));  // captions, tab labels
  r.setProperty("--adm-font-size-main", px(15));  // body
  r.setProperty("--adm-font-size-md",   px(17));  // list titles
  r.setProperty("--adm-font-size-lg",   px(19));  // section headings
  r.setProperty("--adm-font-size-xl",   px(22));  // page titles

  // antd-mobile numbered scale — components use these internally.
  // TabBar title → --adm-font-size-2, List item → --adm-font-size-9, etc.
  // Values aligned to our semantic scale, bumped from the library defaults.
  r.setProperty("--adm-font-size-1",  px(10));
  r.setProperty("--adm-font-size-2",  px(13));  // TabBar label (lib default 10)
  r.setProperty("--adm-font-size-3",  px(12));
  r.setProperty("--adm-font-size-4",  px(13));
  r.setProperty("--adm-font-size-5",  px(14));
  r.setProperty("--adm-font-size-6",  px(15));
  r.setProperty("--adm-font-size-7",  px(15));
  r.setProperty("--adm-font-size-8",  px(16));
  r.setProperty("--adm-font-size-9",  px(15));
  r.setProperty("--adm-font-size-10", px(18));

  // Component-specific
  r.setProperty("--adm-button-font-size",    px(17));
  r.setProperty("--adm-navbar-font-size",    px(18));
  r.setProperty("--adm-list-item-font-size", px(15));
  r.setProperty("--adm-input-font-size",     px(15));
  r.setProperty("--adm-tabs-font-size",      px(15));

  // Icon sizes — scale with tier too
  r.setProperty("--icon-size-xs", px(16));
  r.setProperty("--icon-size-sm", px(20));
  r.setProperty("--icon-size-md", px(24));
  r.setProperty("--icon-size-lg", px(28));
  r.setProperty("--icon-size-xl", px(32));
}

/**
 * Inject CSS overrides for antd-mobile class rules that don't expose a
 * CSS variable. Currently: TabBar icon size (hardcoded 24px in library).
 * Idempotent — guarded by a stable id.
 */
function injectComponentOverrides() {
  const id = "v2-theme-component-overrides";
  if (document.getElementById(id)) return;
  const styleEl = document.createElement("style");
  styleEl.id = id;
  styleEl.textContent = `
    .adm-tab-bar-item-icon {
      font-size: var(--icon-size-lg);
      height: var(--icon-size-lg);
    }
    .adm-tab-bar-item-title {
      line-height: 1.2;
    }
  `;
  document.head.appendChild(styleEl);
}

// ── Init ───────────────────────────────────────────────────────────
export function initTheme(fontScaleTier = "standard") {
  applyThemeColors();
  applyFontScale(fontScaleTier);
  injectComponentOverrides();
}
