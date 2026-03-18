import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import AdminPanelSettingsOutlinedIcon from "@mui/icons-material/AdminPanelSettingsOutlined";
import { setAdminToken, getAdminRoutingMetrics } from "../api";

const ADMIN_TOKEN_KEY = "adminToken";

export default function AdminLoginPage() {
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const next = location.state?.next || "/admin";
  const initialError = location.state?.error || "";

  // Show server-passed error on first render
  const [serverError] = useState(initialError);

  function handleSubmit(e) {
    e.preventDefault();
    const token = input.trim();
    if (!token) { setError("请输入 Token"); return; }
    setLoading(true);
    setError("");
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
    setAdminToken(token);
    getAdminRoutingMetrics()
      .then(() => navigate(next, { replace: true }))
      .catch(() => {
        localStorage.removeItem(ADMIN_TOKEN_KEY);
        setAdminToken("");
        setError("Token 不正确，请重新输入");
        setLoading(false);
      });
  }

  const displayError = error || serverError;

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background:
          "radial-gradient(900px 500px at 90% -5%, rgba(30,64,175,0.12), transparent 60%), #ededed",
      }}
    >
      <Card sx={{ width: 380, borderRadius: 2, boxShadow: "0 4px 24px rgba(0,0,0,0.08)" }}>
        <CardContent sx={{ p: 3.5 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <AdminPanelSettingsOutlinedIcon color="primary" />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>Admin 登录</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            请输入 UI_ADMIN_TOKEN 以继续
          </Typography>
          <form onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField
                label="Admin Token"
                type="password"
                size="small"
                fullWidth
                autoFocus
                value={input}
                onChange={(e) => { setInput(e.target.value); setError(""); }}
                error={!!displayError}
                helperText={displayError}
                disabled={loading}
              />
              <Button type="submit" variant="contained" fullWidth disabled={loading}>
                {loading ? "验证中…" : "进入"}
              </Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
