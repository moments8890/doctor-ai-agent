import { createTheme } from "@mui/material/styles";
import { getDialogContainer } from "./utils/dialogContainer";

// ── Font scale system ────────────────────────────────────────────────
// Three accessibility levels for elderly/low-vision users.
// Components read TYPE.body.fontSize etc. — values auto-scale via Proxy.
const FONT_SCALE_LEVELS = {
  standard:    { label: "标准", multiplier: 1.0 },
  large:       { label: "大字", multiplier: 1.2 },
  extraLarge:  { label: "超大", multiplier: 1.35 },
};

let _fontScaleMultiplier = 1.0;

/** Apply a font scale level. Call this then trigger a React re-render. */
function applyFontScale(level) {
  const entry = FONT_SCALE_LEVELS[level];
  if (entry) _fontScaleMultiplier = entry.multiplier;
}

/** Get current multiplier (for MUI theme recreation). */
function getFontScaleMultiplier() { return _fontScaleMultiplier; }

// ── Typography scale (7 levels) ─────────────────────────────────────
// Change here → affects all pages. Do not use hardcoded fontSize in components.
const BASE_TYPE = {
  title:     { fontSize: 16, fontWeight: 600 },  // top bar title, page title
  action:    { fontSize: 15, fontWeight: 400 },  // top bar actions (BarButton)
  heading:   { fontSize: 14, fontWeight: 600 },  // section titles, card headers, form labels
  body:      { fontSize: 14, fontWeight: 400 },  // primary content, field values
  secondary: { fontSize: 13, fontWeight: 400 },  // list subtitles, descriptions
  caption:   { fontSize: 12, fontWeight: 400 },  // metadata, timestamps
  micro:     { fontSize: 11, fontWeight: 500 },  // badges, tags, source labels
};

// Proxy returns scaled fontSize values. Components read TYPE.body.fontSize
// and automatically get the scaled value without any code changes.
const TYPE = new Proxy(BASE_TYPE, {
  get(target, prop) {
    const base = target[prop];
    if (base && typeof base === "object" && "fontSize" in base) {
      return { ...base, fontSize: Math.round(base.fontSize * _fontScaleMultiplier) };
    }
    return base;
  },
});

// ── Icon scale (8 levels) ────────────────────────────────────────────
// Change here → affects all icon sizes globally.
const ICON = {
  xs:      13,  // inline tiny (sort arrows, inline delete/edit)
  sm:      16,  // inline icons (chevrons, close, action bar)
  md:      18,  // list item icons, avatar inner, expand/collapse
  lg:      20,  // nav icons, settings row icons, primary actions
  xl:      22,  // quick action cards, avatar initials
  xxl:     24,  // detail header icons
  hero:    28,  // SubpageHeader back chevron, action panel
  display: 48,  // empty state, about page, login splash
};

// ── Border-radius scale (4 levels) ──────────────────────────────────
// Change here → affects all corner rounding. Do not use hardcoded borderRadius.
const RADIUS = {
  sm:   "4px",   // buttons, cards, avatars, inputs, badges
  md:   "8px",   // containers, bubbles, icon boxes
  lg:   "12px",  // dialog paper, bottom sheets
  pill: "16px",  // pills, chips, MobileFrame
};

const BUBBLE_RADIUS = {
  left: `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0`,
  right: `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}`,
};

const BUTTON = {
  compactHeight: 36,
  get compactFontSize() { return TYPE.body.fontSize; },
  compactLineHeight: 1.2,
  compactPaddingX: "16px",
  compactPaddingY: "0px",
  compactRadius: "4px",
  largeHeight: 48,
};

// ── Color tokens ────────────────────────────────────────────────────
const COLOR = {
  primary:      "#07C160",
  primaryLight: "#E7F7EE",
  accent:       "#576B95",
  accentLight:  "#EEF1F6",
  success:      "#07C160",
  successLight: "#E7F7EE",
  danger:       "#D65745",
  dangerLight:  "#FDF0EE",
  warning:      "#F59E0B",
  warningLight: "#FFF7E6",
  text1:        "#1A1A1A",
  text2:        "#333333",
  text3:        "#666666",
  text4:        "#999999",
  border:       "#E5E5E5",
  borderLight:  "#f0f0f0",
  surface:      "#f7f7f7",
  surfaceAlt:   "#ededed",
  white:        "#ffffff",
  // Record type groups (minimal 3-color palette)
  recordDoc:    "#8993a4",   // document records: dictation, import
  // Interaction states
  primaryHover: "#06a050",   // button hover/active
  link:         "#1565c0",   // citation badges, knowledge references
  // Chat bubbles
  wechatGreen:  "#95EC69",   // user message bubble (WeChat standard)
  // Highlight
  highlightBg:  "#fffef5",   // highlighted row background (URL-driven)
  // Semantic accent colors
  orange:       "#e8833a",   // import/file/medium urgency
  recordBlue:   "#5b9bd5",   // dictation/gallery/patient-side blue
  purple:       "#9b59b6",   // patient archive action
  // Amber tones (draft indicators, no-draft notices)
  amberLight:   "#fff8e1",   // warm amber background
  amberText:    "#b28704",   // dark amber label text
  amberBorder:  "#ffcc02",   // amber border for notices
  // Deep variants for text on light backgrounds
  successText:  "#2e7d32",   // dark green text on successLight bg
};

// ── Shared sx presets ──────────────────────────────────────────────
const HIGHLIGHT_ROW_SX = {
  bgcolor: COLOR.highlightBg,
  borderLeft: `3px solid ${COLOR.primary}`,
};

export { TYPE, BASE_TYPE, ICON, BUTTON, COLOR, RADIUS, BUBBLE_RADIUS, HIGHLIGHT_ROW_SX, FONT_SCALE_LEVELS, applyFontScale, getFontScaleMultiplier };

// Shared theme options (palette, typography, components) — used by both app and admin themes.
// Returns fresh options reading current TYPE values (which reflect font scale).
function buildSharedThemeOptions() {
  return {
    palette: {
      mode: "light",
      primary: { main: COLOR.primary },
      secondary: { main: COLOR.text4 },
      error: { main: COLOR.danger },
      warning: { main: COLOR.warning },
      background: {
        default: COLOR.surfaceAlt,
        paper: COLOR.white,
      },
      text: {
        primary: COLOR.text1,
        secondary: COLOR.text4,
      },
    },
    shape: {
      borderRadius: parseInt(RADIUS.sm),
    },
    wechat: {
      userBubble: COLOR.wechatGreen,
      aiBubble: COLOR.white,
      inputBarBg: "#f5f5f5",
      tabBarBg: COLOR.surface,
      listDivider: COLOR.borderLight,
      borderInput: "#e0e0e0",
      tabBarBorder: "#d9d9d9",
    },
    typography: {
      fontFamily: "'Noto Sans SC', 'IBM Plex Sans', 'Segoe UI', sans-serif",
      // MUI variant mapping to our type scale (reads scaled TYPE values)
      h5:       { fontWeight: TYPE.title.fontWeight,   fontSize: TYPE.title.fontSize },
      h6:       { fontWeight: TYPE.title.fontWeight,   fontSize: TYPE.title.fontSize },
      subtitle1:{ fontWeight: 500,                     fontSize: TYPE.action.fontSize },
      body1:    { fontWeight: TYPE.body.fontWeight,     fontSize: TYPE.body.fontSize },
      body2:    { fontWeight: TYPE.body.fontWeight,     fontSize: TYPE.body.fontSize },
      caption:  { fontWeight: TYPE.caption.fontWeight,  fontSize: TYPE.caption.fontSize },
      button:   { textTransform: "none", fontWeight: 500, fontSize: TYPE.body.fontSize },
    },
    shadows: Array(25).fill("none"),
    components: {
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: COLOR.surfaceAlt,
            borderBottom: `0.5px solid #d9d9d9`,
          },
        },
      },
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: { root: { boxShadow: "none" } },
      },
      MuiCard: {
        styleOverrides: { root: { borderRadius: parseInt(RADIUS.sm) } },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: RADIUS.sm,
            minHeight: BUTTON.compactHeight,
            padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
            fontSize: TYPE.body.fontSize,
            lineHeight: BUTTON.compactLineHeight,
          },
          sizeSmall: {
            minHeight: BUTTON.compactHeight,
            padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
            fontSize: TYPE.body.fontSize,
            lineHeight: BUTTON.compactLineHeight,
          },
          sizeMedium: {
            minHeight: BUTTON.compactHeight,
            padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
            fontSize: TYPE.body.fontSize,
            lineHeight: BUTTON.compactLineHeight,
          },
          sizeLarge: {
            minHeight: BUTTON.largeHeight,
            padding: "0 20px",
            fontSize: TYPE.action.fontSize,
            lineHeight: 1.25,
          },
          contained: { boxShadow: "none", "&:hover": { boxShadow: "none" } },
        },
      },
      MuiDialog: {
        defaultProps: { container: getDialogContainer },
        styleOverrides: { paper: { borderRadius: parseInt(RADIUS.lg) } },
      },
    },
  };
}

/** Create the mobile app theme with current font scale applied. */
export function createAppThemeScaled() {
  return createTheme({
    ...buildSharedThemeOptions(),
    breakpoints: {
      values: { xs: 0, sm: 9999, md: 9999, lg: 9999, xl: 9999 },
    },
  });
}

// Default theme instances (for backward compat / initial render)
export const appTheme = createAppThemeScaled();

// `adminTheme` / `createAdminThemeScaled` were removed alongside the
// legacy GitHub-Dark v1 admin (2026-04-27). v3 admin uses inline-styled
// tokens from src/pages/admin/v3/tokens.js instead of MUI's ThemeProvider.
