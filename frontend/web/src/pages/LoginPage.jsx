/**
 * @route /login
 *
 * 登录页 — 医生和患者两个标签页
 *
 * 测试版：使用昵称 + 口令（不收集手机号等个人信息）
 * 登录：昵称 + 口令（两个角色相同）
 * 注册：医生需要邀请码，患者需要选择医生
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Button, Card, CardContent, CircularProgress,
  MenuItem, Stack, Tab, Tabs, TextField, Typography,
} from "@mui/material";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import {
  unifiedLogin, unifiedLoginWithRole,
  unifiedRegisterDoctor, unifiedRegisterPatient,
  unifiedListDoctors, setWebToken,
} from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

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
  const [tab, setTab] = useState(0); // 0=doctor, 1=patient
  const [mode, setMode] = useState("login"); // login | register

  // Login fields (nickname + passcode)
  const [nickname, setNickname] = useState("");
  const [passcode, setPasscode] = useState("");

  // Register common
  const [regNickname, setRegNickname] = useState("");
  const [regPasscode, setRegPasscode] = useState("");

  // Register doctor
  const [inviteCode, setInviteCode] = useState("WELCOME");

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
      localStorage.setItem("patient_portal_token", data.token);
      localStorage.setItem("patient_portal_name", data.name || "");
      localStorage.setItem("patient_portal_doctor_id", data.doctor_id || "");
      navigate("/patient", { replace: true });
    }
  }

  async function handleLogin(e) {
    e.preventDefault();
    if (!nickname.trim() || !passcode.trim()) { setError("请输入昵称和口令"); return; }
    setLoading(true); setError(""); setRoleChoices(null);
    try {
      const data = await unifiedLogin(nickname.trim(), parseInt(passcode));
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
        nickname.trim(), parseInt(passcode), role.role,
        role.doctor_id, role.patient_id,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "登录失败");
    } finally { setLoading(false); }
  }

  async function handleRegisterDoctor(e) {
    e.preventDefault();
    if (!regNickname.trim() || !regPasscode.trim() || !inviteCode.trim()) {
      setError("请填写完整信息"); return;
    }
    setLoading(true); setError("");
    try {
      const data = await unifiedRegisterDoctor(
        regNickname.trim(), regNickname.trim(), parseInt(regPasscode),
        inviteCode.trim(),
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally { setLoading(false); }
  }

  async function handleRegisterPatient(e) {
    e.preventDefault();
    if (!regNickname.trim() || !regPasscode.trim() || !doctorId) {
      setError("请填写完整信息"); return;
    }
    setLoading(true); setError("");
    try {
      const data = await unifiedRegisterPatient(
        regNickname.trim(), regNickname.trim(), parseInt(regPasscode),
        doctorId, gender || undefined,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally { setLoading(false); }
  }

  const isDoctor = tab === 0;

  return (
    <Box sx={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", px: 2,
      bgcolor: COLOR.surface,
    }}>
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: RADIUS.md, boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}>
        <CardContent sx={{ p: 3.5 }}>
          <Stack spacing={2.5} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: ICON.display, color: COLOR.primary }} />
            <Typography sx={{ fontWeight: 700, fontSize: TYPE.title.fontSize }}>AI 医疗助手</Typography>

            {/* Role tabs */}
            <Tabs value={tab} onChange={(_, v) => { setTab(v); setMode("login"); setError(""); setRoleChoices(null); }}
              sx={{ width: "100%", "& .MuiTab-root": { flex: 1, fontSize: TYPE.body.fontSize, color: COLOR.text4 }, "& .Mui-selected": { color: COLOR.primary, fontWeight: 600 }, "& .MuiTabs-indicator": { bgcolor: COLOR.primary, height: 3 } }}>
              <Tab label="医生" />
              <Tab label="患者" />
            </Tabs>

            {/* ==================== LOGIN ==================== */}
            {mode === "login" && !roleChoices && (
              <Box component="form" onSubmit={handleLogin} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField label="昵称" value={nickname} onChange={e => setNickname(e.target.value)}
                    fullWidth size="small" autoFocus />
                  <TextField label="口令" value={passcode} onChange={e => setPasscode(e.target.value)}
                    placeholder="数字口令" fullWidth size="small" type="password" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}
                    sx={{ bgcolor: COLOR.primary, "&:hover": { bgcolor: COLOR.primaryHover }, textTransform: "none", py: 1 }}>
                    {loading ? <CircularProgress size={16} /> : "登录"}
                  </Button>
                  <Typography variant="body2" color="text.secondary" textAlign="center" sx={{ fontSize: TYPE.secondary.fontSize }}>
                    没有账号？
                    <Box component="span" onClick={() => { setMode("register"); setError(""); }}
                      sx={{ color: COLOR.primary, cursor: "pointer", ml: 0.5 }}>
                      {isDoctor ? "医生注册" : "患者注册"}
                    </Box>
                  </Typography>
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
                    sx={{ justifyContent: "flex-start", textTransform: "none", py: 1.5, borderColor: COLOR.border }}>
                    <Stack>
                      <Typography fontWeight={600} sx={{ fontSize: TYPE.heading.fontSize }}>
                        {r.role === "doctor" ? "医生" : "患者"} — {r.name}
                      </Typography>
                    </Stack>
                  </Button>
                ))}
                <Button size="small" onClick={() => setRoleChoices(null)} sx={{ color: COLOR.text4 }}>返回</Button>
              </Stack>
            )}

            {/* ==================== DOCTOR REGISTER ==================== */}
            {mode === "register" && isDoctor && (
              <Box component="form" onSubmit={handleRegisterDoctor} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField label="邀请码" value={inviteCode}
                    fullWidth size="small" disabled
                    helperText="公开测试期间自动填入" />
                  <TextField label="昵称" value={regNickname}
                    onChange={e => setRegNickname(e.target.value)} fullWidth size="small"
                    helperText="用于登录和显示" />
                  <TextField label="口令" value={regPasscode}
                    onChange={e => setRegPasscode(e.target.value)} fullWidth size="small"
                    type="password" placeholder="设置数字口令" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}
                    sx={{ bgcolor: COLOR.primary, "&:hover": { bgcolor: COLOR.primaryHover }, textTransform: "none", py: 1 }}>
                    {loading ? <CircularProgress size={16} /> : "注册"}
                  </Button>
                  <Typography variant="body2" color="text.secondary" textAlign="center" sx={{ fontSize: TYPE.secondary.fontSize }}>
                    已有账号？
                    <Box component="span" onClick={() => { setMode("login"); setError(""); }}
                      sx={{ color: COLOR.primary, cursor: "pointer", ml: 0.5 }}>
                      返回登录
                    </Box>
                  </Typography>
                </Stack>
              </Box>
            )}

            {/* ==================== PATIENT REGISTER ==================== */}
            {mode === "register" && !isDoctor && (
              <Box component="form" onSubmit={handleRegisterPatient} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField select label="选择医生" value={doctorId}
                    onChange={e => setDoctorId(e.target.value)} fullWidth size="small">
                    {doctors.map(d => (
                      <MenuItem key={d.doctor_id} value={d.doctor_id}>
                        {d.name}{d.department ? ` · ${d.department}` : ""}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField label="昵称" value={regNickname}
                    onChange={e => setRegNickname(e.target.value)} fullWidth size="small"
                    helperText="用于登录和显示" />
                  <TextField select label="性别" value={gender}
                    onChange={e => setGender(e.target.value)} fullWidth size="small">
                    <MenuItem value="">不填</MenuItem>
                    <MenuItem value="男">男</MenuItem>
                    <MenuItem value="女">女</MenuItem>
                  </TextField>
                  <TextField label="口令" value={regPasscode}
                    onChange={e => setRegPasscode(e.target.value)} fullWidth size="small"
                    type="password" placeholder="设置数字口令" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}
                    sx={{ bgcolor: COLOR.primary, "&:hover": { bgcolor: COLOR.primaryHover }, textTransform: "none", py: 1 }}>
                    {loading ? <CircularProgress size={16} /> : "注册"}
                  </Button>
                  <Typography variant="body2" color="text.secondary" textAlign="center" sx={{ fontSize: TYPE.secondary.fontSize }}>
                    已有账号？
                    <Box component="span" onClick={() => { setMode("login"); setError(""); }}
                      sx={{ color: COLOR.primary, cursor: "pointer", ml: 0.5 }}>
                      返回登录
                    </Box>
                  </Typography>
                </Stack>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
