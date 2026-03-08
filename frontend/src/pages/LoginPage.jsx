import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import { webLogin, getWecomLoginUrl, setWebToken } from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth } = useDoctorStore();
  const [doctorId, setDoctorId] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [wecomLoading, setWecomLoading] = useState(false);
  const [error, setError] = useState("");

  // Handle redirect back from WeCom OAuth callback: /login?token=...&doctor_id=...&name=...
  useEffect(() => {
    const token = searchParams.get("token");
    const id = searchParams.get("doctor_id");
    const displayName = searchParams.get("name");
    const err = searchParams.get("error");

    if (err) {
      setError(t("login.wecomFailed", { message: err }));
      return;
    }
    if (token && id) {
      setWebToken(token);
      setAuth(id, displayName || id, token);
      navigate("/", { replace: true });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onLogin(e) {
    e.preventDefault();
    const id = doctorId.trim();
    if (!id) {
      setError(t("login.doctorIdRequired"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await webLogin(id, name.trim() || undefined);
      setWebToken(data.access_token);
      setAuth(data.doctor_id, name.trim() || data.doctor_id, data.access_token);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  async function onWecomLogin() {
    setWecomLoading(true);
    setError("");
    try {
      const data = await getWecomLoginUrl();
      window.location.href = data.url;
    } catch (err) {
      setError(err.message || t("login.wecomUnavailable"));
      setWecomLoading(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background:
          "radial-gradient(1200px 640px at 92% -8%, rgba(15,118,110,0.16), transparent 65%), radial-gradient(900px 520px at -12% 108%, rgba(47,79,111,0.15), transparent 62%), #f3f7f8",
      }}
    >
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: 48, color: "primary.main" }} />
            <Typography variant="h6" fontWeight={700}>
              {t("login.title")}
            </Typography>

            {/* WeCom QR scan login */}
            <Button
              variant="outlined"
              fullWidth
              onClick={onWecomLogin}
              disabled={wecomLoading}
              startIcon={wecomLoading ? <CircularProgress size={16} color="inherit" /> : null}
              sx={{ borderColor: "#07c160", color: "#07c160", "&:hover": { borderColor: "#06ad56", bgcolor: "rgba(7,193,96,0.04)" } }}
            >
              {t("login.wecomLogin")}
            </Button>

            <Divider sx={{ width: "100%" }}>
              <Typography variant="caption" color="text.secondary">
                {t("login.orDivider")}
              </Typography>
            </Divider>

            {/* Manual ID login (dev / fallback) */}
            <Box component="form" onSubmit={onLogin} sx={{ width: "100%" }}>
              <Stack spacing={2}>
                <TextField
                  label={t("login.doctorId")}
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  fullWidth
                  size="small"
                  inputProps={{ autoComplete: "username" }}
                />
                <TextField
                  label={t("login.name")}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  fullWidth
                  size="small"
                  inputProps={{ autoComplete: "name" }}
                  helperText={t("login.nameHelper")}
                />
                {error && (
                  <Typography variant="body2" color="error">
                    {error}
                  </Typography>
                )}
                <Button
                  type="submit"
                  variant="contained"
                  fullWidth
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={16} color="inherit" /> : null}
                >
                  {t("login.submit")}
                </Button>
              </Stack>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
