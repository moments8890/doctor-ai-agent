import { createTheme } from "@mui/material/styles";

export const appTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#07C160" },
    secondary: { main: "#999999" },
    error: { main: "#FA5151" },
    warning: { main: "#FF9500" },
    background: {
      default: "#ededed",
      paper: "#ffffff",
    },
    text: {
      primary: "#111111",
      secondary: "#999999",
    },
  },
  shape: {
    borderRadius: 4,
  },
  typography: {
    fontFamily: "'Noto Sans SC', 'PingFang SC', 'Helvetica Neue', sans-serif",
    h5: { fontWeight: 500, fontSize: "17px" },
    h6: { fontWeight: 500, fontSize: "17px" },
    subtitle1: { fontWeight: 500, fontSize: "15px" },
    body1: { fontSize: "15px" },
    body2: { fontSize: "14px" },
    caption: { fontSize: "12px" },
    button: { textTransform: "none", fontWeight: 500, fontSize: "14px" },
  },
  shadows: Array(25).fill("none"),
  wechat: {
    userBubble: "#95EC69",
    aiBubble: "#ffffff",
    inputBarBg: "#f5f5f5",
    tabBarBg: "#f7f7f7",
    listDivider: "#f0f0f0",
    borderInput: "#e0e0e0",
    tabBarBorder: "#d9d9d9",
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#ededed",
          borderBottom: "0.5px solid #d9d9d9",
        },
      },
    },
    MuiPaper: {
      defaultProps: {
        elevation: 0,
      },
      styleOverrides: {
        root: {
          boxShadow: "none",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 4,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,
        },
        contained: {
          boxShadow: "none",
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
        },
      },
    },
  },
});
