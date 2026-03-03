import { createTheme } from "@mui/material/styles";

export const appTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0f766e" },
    secondary: { main: "#2f4f6f" },
    background: {
      default: "#f3f7f8",
      paper: "#ffffff",
    },
    text: {
      primary: "#102a35",
      secondary: "#5b7281",
    },
  },
  shape: {
    borderRadius: 16,
  },
  typography: {
    fontFamily: "'Noto Sans SC', 'IBM Plex Sans', 'Segoe UI', sans-serif",
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  shadows: [
    "none",
    "0 2px 6px rgba(16,42,53,0.06)",
    "0 4px 12px rgba(16,42,53,0.08)",
    "0 8px 20px rgba(16,42,53,0.10)",
    "0 10px 24px rgba(16,42,53,0.12)",
    ...Array(20).fill("0 12px 28px rgba(16,42,53,0.14)"),
  ],
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(8px)",
          backgroundColor: "rgba(255,255,255,0.72)",
          borderBottom: "1px solid #d6e2e5",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          border: "1px solid #d8e3e8",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid #d8e3e8",
          boxShadow: "0 10px 24px rgba(16,42,53,0.08)",
        },
      },
    },
  },
});
