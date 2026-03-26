import { createTheme } from "@mui/material/styles";
import { getDialogContainer } from "./utils/dialogContainer";

// ── Typography scale (7 levels) ─────────────────────────────────────
// Change here → affects all pages. Do not use hardcoded fontSize in components.
const TYPE = {
  title:     { fontSize: 16, fontWeight: 600 },  // top bar title, page title
  action:    { fontSize: 15, fontWeight: 400 },  // top bar actions (BarButton)
  heading:   { fontSize: 14, fontWeight: 600 },  // section titles, card headers, form labels
  body:      { fontSize: 14, fontWeight: 400 },  // primary content, field values
  secondary: { fontSize: 13, fontWeight: 400 },  // list subtitles, descriptions
  caption:   { fontSize: 12, fontWeight: 400 },  // metadata, timestamps
  micro:     { fontSize: 11, fontWeight: 500 },  // badges, tags, source labels
};

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

const BUTTON = {
  compactHeight: 36,
  compactFontSize: TYPE.body.fontSize,
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
};

export { TYPE, ICON, BUTTON, COLOR };

// Shared theme options (palette, typography, components) — used by both app and admin themes
const sharedThemeOptions = {
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
    borderRadius: 4,
  },
  wechat: {
    userBubble: "#95EC69",
    aiBubble: COLOR.white,
    inputBarBg: "#f5f5f5",
    tabBarBg: COLOR.surface,
    listDivider: COLOR.borderLight,
    borderInput: "#e0e0e0",
    tabBarBorder: "#d9d9d9",
  },
  typography: {
    fontFamily: "'Noto Sans SC', 'IBM Plex Sans', 'Segoe UI', sans-serif",
    // MUI variant mapping to our type scale
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
      styleOverrides: { root: { borderRadius: 4 } },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: BUTTON.compactRadius,
          minHeight: BUTTON.compactHeight,
          padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
          fontSize: BUTTON.compactFontSize,
          lineHeight: BUTTON.compactLineHeight,
        },
        sizeSmall: {
          minHeight: BUTTON.compactHeight,
          padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
          fontSize: BUTTON.compactFontSize,
          lineHeight: BUTTON.compactLineHeight,
        },
        sizeMedium: {
          minHeight: BUTTON.compactHeight,
          padding: `${BUTTON.compactPaddingY} ${BUTTON.compactPaddingX}`,
          fontSize: BUTTON.compactFontSize,
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
      styleOverrides: { paper: { borderRadius: 12 } },
    },
  },
};

// Mobile-forced theme for doctor/patient pages (breakpoints pinned to force mobile)
export const appTheme = createTheme({
  ...sharedThemeOptions,
  breakpoints: {
    values: { xs: 0, sm: 9999, md: 9999, lg: 9999, xl: 9999 },
  },
});

// Desktop theme for admin pages (standard MUI breakpoints)
export const adminTheme = createTheme({
  ...sharedThemeOptions,
  // Default MUI breakpoints: xs:0, sm:600, md:900, lg:1200, xl:1536
});
