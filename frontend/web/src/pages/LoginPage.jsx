/**
 * 统一登录页 — 医生和患者共用
 *
 * 登录：手机号 + 出生年份 → 自动检测角色 → 路由到对应 UI
 * 注册：医生（需要邀请码）/ 患者（选择医生）
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import {
  unifiedLogin,
  unifiedLoginWithRole,
  unifiedRegisterDoctor,
  unifiedRegisterPatient,
  unifiedListDoctors,
  setWebToken,
} from "../api";
import { useDoctorStore } from "../store/doctorStore";

const STORAGE_KEY = "unified_auth_token";
const STORAGE_ROLE_KEY = "unified_auth_role";
const STORAGE_NAME_KEY = "unified_auth_name";
const STORAGE_DOCTOR_ID_KEY = "unified_auth_doctor_id";
const STORAGE_PATIENT_ID_KEY = "unified_auth_patient_id";

function saveSession(data) {
  localStorage.setItem(STORAGE_KEY, data.token);
  localStorage.setItem(STORAGE_ROLE_KEY, data.role);
  localStorage.setItem(STORAGE_NAME_KEY, data.name || "");
  if (data.doctor_id) localStorage.setItem(STORAGE_DOCTOR_ID_KEY, data.doctor_id);
  if (data.patient_id) localStorage.setItem(STORAGE_PATIENT_ID_KEY, String(data.patient_id));
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useDoctorStore();
  const [mode, setMode] = useState("login"); // login | register
  const [registerTab, setRegisterTab] = useState(0); // 0=patient, 1=doctor

  // Login fields
  const [phone, setPhone] = useState("");
  const [yob, setYob] = useState("");

  // Register common
  const [regPhone, setRegPhone] = useState("");
  const [regName, setRegName] = useState("");
  const [regYob, setRegYob] = useState("");

  // Register doctor
  const [inviteCode, setInviteCode] = useState("");
  const [specialty, setSpecialty] = useState("");

  // Register patient
  const [doctorId, setDoctorId] = useState("");
  const [gender, setGender] = useState("");
  const [doctors, setDoctors] = useState([]);

  // Role picker
  const [roleChoices, setRoleChoices] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    unifiedListDoctors().then(setDoctors).catch(() => {});
  }, []);

  function handleLoginSuccess(data) {
    saveSession(data);
    if (data.role === "doctor") {
      setWebToken(data.token);
      setAuth(data.doctor_id, data.name, data.token);
      navigate("/doctor", { replace: true });
    } else {
      // Store patient token for PatientPage
      localStorage.setItem("patient_portal_token", data.token);
      localStorage.setItem("patient_portal_name", data.name || "");
      localStorage.setItem("patient_portal_doctor_id", data.doctor_id || "");
      navigate("/patient", { replace: true });
    }
  }

  async function handleLogin(e) {
    e.preventDefault();
    if (!phone.trim() || !yob.trim()) { setError("请输入手机号和出生年份"); return; }
    setLoading(true); setError(""); setRoleChoices(null);
    try {
      const data = await unifiedLogin(phone.trim(), parseInt(yob));
      if (data.needs_role_selection) {
        setRoleChoices(data.roles);
      } else {
        handleLoginSuccess(data);
      }
    } catch (err) {
      setError(err.message || "登录失败");
    } finally { setLoading(false); }
  }

  async function handleRoleSelect(role) {
    setLoading(true); setError("");
    try {
      const data = await unifiedLoginWithRole(
        phone.trim(), parseInt(yob), role.role,
        role.doctor_id, role.patient_id,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "登录失败");
    } finally { setLoading(false); }
  }

  async function handleRegisterDoctor(e) {
    e.preventDefault();
    if (!regPhone.trim() || !regName.trim() || !regYob.trim() || !inviteCode.trim()) {
      setError("请填写完整信息"); return;
    }
    setLoading(true); setError("");
    try {
      const data = await unifiedRegisterDoctor(
        regPhone.trim(), regName.trim(), parseInt(regYob),
        inviteCode.trim(), specialty.trim() || undefined,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally { setLoading(false); }
  }

  async function handleRegisterPatient(e) {
    e.preventDefault();
    if (!regPhone.trim() || !regName.trim() || !regYob.trim() || !doctorId) {
      setError("请填写完整信息"); return;
    }
    setLoading(true); setError("");
    try {
      const data = await unifiedRegisterPatient(
        regPhone.trim(), regName.trim(), parseInt(regYob),
        doctorId, gender || undefined,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally { setLoading(false); }
  }

  return (
    <Box sx={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", px: 2,
      background: "radial-gradient(1200px 640px at 92% -8%, rgba(7,193,96,0.16), transparent 65%), #ededed",
    }}>
      <Card sx={{ width: "100%", maxWidth: 420, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: 48, color: "#07C160" }} />
            <Typography variant="h6" fontWeight={700}>
              {mode === "login" ? "登录" : "注册"}
            </Typography>

            {/* ==================== LOGIN ==================== */}
            {mode === "login" && !roleChoices && (
              <Box component="form" onSubmit={handleLogin} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField label="手机号" value={phone} onChange={e => setPhone(e.target.value)}
                    fullWidth size="small" autoFocus />
                  <TextField label="出生年份" value={yob} onChange={e => setYob(e.target.value)}
                    placeholder="例如 1985" fullWidth size="small" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}
                    sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                    {loading ? <CircularProgress size={16} /> : "登录"}
                  </Button>
                  <Button size="small" onClick={() => { setMode("register"); setError(""); }}>
                    没有账号？注册
                  </Button>
                </Stack>
              </Box>
            )}

            {/* ==================== ROLE PICKER ==================== */}
            {mode === "login" && roleChoices && (
              <Stack spacing={2} sx={{ width: "100%" }}>
                <Typography variant="body2" color="text.secondary" textAlign="center">
                  检测到多个账号，请选择登录身份：
                </Typography>
                {roleChoices.map((r, i) => (
                  <Button key={i} variant="outlined" fullWidth onClick={() => handleRoleSelect(r)}
                    sx={{ justifyContent: "flex-start", textTransform: "none", py: 1.5 }}>
                    <Stack>
                      <Typography fontWeight={600}>
                        {r.role === "doctor" ? "医生" : "患者"} — {r.name}
                      </Typography>
                      {r.role === "patient" && (
                        <Typography variant="caption" color="text.secondary">
                          {r.doctor_id}
                        </Typography>
                      )}
                    </Stack>
                  </Button>
                ))}
                <Button size="small" onClick={() => setRoleChoices(null)}>返回</Button>
              </Stack>
            )}

            {/* ==================== REGISTER ==================== */}
            {mode === "register" && (
              <Box sx={{ width: "100%" }}>
                <Tabs value={registerTab} onChange={(_, v) => { setRegisterTab(v); setError(""); }}
                  centered sx={{ mb: 2 }}>
                  <Tab label="患者注册" />
                  <Tab label="医生注册" />
                </Tabs>

                {/* Patient register */}
                {registerTab === 0 && (
                  <Box component="form" onSubmit={handleRegisterPatient}>
                    <Stack spacing={2}>
                      <TextField select label="选择医生" value={doctorId}
                        onChange={e => setDoctorId(e.target.value)} fullWidth size="small">
                        {doctors.map(d => (
                          <MenuItem key={d.doctor_id} value={d.doctor_id}>
                            {d.name}{d.department ? ` · ${d.department}` : ""}
                          </MenuItem>
                        ))}
                      </TextField>
                      <TextField label="您的姓名" value={regName}
                        onChange={e => setRegName(e.target.value)} fullWidth size="small" />
                      <TextField select label="性别" value={gender}
                        onChange={e => setGender(e.target.value)} fullWidth size="small">
                        <MenuItem value="">不填</MenuItem>
                        <MenuItem value="男">男</MenuItem>
                        <MenuItem value="女">女</MenuItem>
                      </TextField>
                      <TextField label="出生年份" value={regYob}
                        onChange={e => setRegYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                      <TextField label="手机号" value={regPhone}
                        onChange={e => setRegPhone(e.target.value)} fullWidth size="small" />
                      {error && <Typography variant="body2" color="error">{error}</Typography>}
                      <Button type="submit" variant="contained" fullWidth disabled={loading}
                        sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                        {loading ? <CircularProgress size={16} /> : "注册"}
                      </Button>
                    </Stack>
                  </Box>
                )}

                {/* Doctor register */}
                {registerTab === 1 && (
                  <Box component="form" onSubmit={handleRegisterDoctor}>
                    <Stack spacing={2}>
                      <TextField label="邀请码" value={inviteCode}
                        onChange={e => setInviteCode(e.target.value)} fullWidth size="small"
                        helperText="请向管理员获取邀请码" />
                      <TextField label="您的姓名" value={regName}
                        onChange={e => setRegName(e.target.value)} fullWidth size="small" />
                      <TextField label="科室/专科" value={specialty}
                        onChange={e => setSpecialty(e.target.value)} placeholder="例如 神经外科" fullWidth size="small" />
                      <TextField label="出生年份" value={regYob}
                        onChange={e => setRegYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                      <TextField label="手机号" value={regPhone}
                        onChange={e => setRegPhone(e.target.value)} fullWidth size="small" />
                      {error && <Typography variant="body2" color="error">{error}</Typography>}
                      <Button type="submit" variant="contained" fullWidth disabled={loading}
                        sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                        {loading ? <CircularProgress size={16} /> : "注册"}
                      </Button>
                    </Stack>
                  </Box>
                )}

                <Box textAlign="center" mt={2}>
                  <Button size="small" onClick={() => { setMode("login"); setError(""); }}>
                    已有账号？返回登录
                  </Button>
                </Box>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
