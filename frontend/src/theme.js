import { createTheme } from "@mui/material/styles";

export const appTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0b5e55" },
    secondary: { main: "#955f19" },
    background: {
      default: "#eef4f5",
      paper: "#ffffff",
    },
  },
  shape: {
    borderRadius: 14,
  },
  typography: {
    fontFamily: "'IBM Plex Sans', 'Noto Sans', 'Segoe UI', sans-serif",
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          border: "1px solid #d8e1e3",
        },
      },
    },
  },
});
