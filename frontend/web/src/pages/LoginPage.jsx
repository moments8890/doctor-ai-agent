import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Autocomplete,
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

const SPECIALTIES = [
  "内科", "外科", "神经内科", "神经外科", "心内科",
  "骨科", "妇产科", "儿科", "眼科", "耳鼻喉科",
  "口腔科", "皮肤科", "精神科", "肿瘤科", "急诊科",
  "重症医学科", "康复科", "中医科", "全科医学科",
];

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth } = useDoctorStore();
  const [code, setCode] = useState("");
  const [specialty, setSpecialty] = useState("神经外科");
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
      const data = await inviteLogin(c, specialty.trim());
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
          "radial-gradient(1200px 640px at 92% -8%, rgba(7,193,96,0.16), transparent 65%), radial-gradient(900px 520px at -12% 108%, rgba(47,79,111,0.15), transparent 62%), #ededed",
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
                <Autocomplete
                  freeSolo
                  options={SPECIALTIES}
                  value={specialty}
                  onInputChange={(_, val) => setSpecialty(val)}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={t("login.specialty")}
                      size="small"
                      helperText={t("login.specialtyHelper")}
                      inputProps={{ ...params.inputProps, autoComplete: "off" }}
                    />
                  )}
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
