import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import { inviteLogin, setWebToken } from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth } = useDoctorStore();
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const err = searchParams.get("error");
    if (err) setError(err);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onLogin(e) {
    e.preventDefault();
    const c = code.trim();
    if (!c) {
      setError(t("login.codeRequired"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await inviteLogin(c);
      setWebToken(data.access_token);
      setAuth(data.doctor_id, data.doctor_id, data.access_token);
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
                  label={t("login.inviteCode")}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoFocus
                  fullWidth
                  size="small"
                  helperText={t("login.inviteCodeHelper")}
                  inputProps={{ autoComplete: "off" }}
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
