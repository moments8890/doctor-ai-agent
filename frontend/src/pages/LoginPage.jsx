import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import { webLogin, setWebToken } from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

export default function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useDoctorStore();
  const [doctorId, setDoctorId] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

            <Box component="form" onSubmit={onLogin} sx={{ width: "100%" }}>
              <Stack spacing={2}>
                <TextField
                  label={t("login.doctorId")}
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  autoFocus
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
