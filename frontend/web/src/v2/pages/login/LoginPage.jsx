/**
 * @route /login (v2)
 *
 * 登录页 — 医生和患者两个标签页
 * antd-mobile rewrite, no MUI dependencies.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Form,
  Input,
  Picker,
  SpinLoading,
  Tabs,
  Toast,
} from "antd-mobile";
import {
  unifiedLogin,
  unifiedLoginWithRole,
  unifiedRegisterDoctor,
  unifiedRegisterPatient,
  unifiedListDoctors,
  setWebToken,
} from "../../../api";
import { useDoctorStore } from "../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../theme";

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

// ── Styles ─────────────────────────────────────────────────────────

const styles = {
  page: {
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "0 16px",
    backgroundColor: APP.surfaceAlt,
  },
  card: {
    width: "100%",
    maxWidth: 400,
    backgroundColor: APP.surface,
    borderRadius: RADIUS.lg,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
    padding: "28px 24px",
  },
  header: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 8,
    marginBottom: 20,
  },
  icon: {
    width: 48,
    height: 48,
    borderRadius: RADIUS.circle,
    backgroundColor: APP.primaryLight,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 24,
  },
  title: {
    margin: 0,
    fontWeight: 700,
    fontSize: 18,
    color: APP.text1,
  },
  errorText: {
    color: APP.danger,
    fontSize: FONT.sm,
    textAlign: "center",
    padding: "4px 0",
  },
  switchText: {
    textAlign: "center",
    fontSize: FONT.sm,
    color: APP.text3,
    paddingTop: 4,
  },
  link: {
    color: APP.primary,
    cursor: "pointer",
    marginLeft: 4,
  },
  roleButton: {
    width: "100%",
    marginBottom: 8,
    textAlign: "left",
    justifyContent: "flex-start",
  },
  roleLabel: {
    fontWeight: 600,
    fontSize: FONT.md,
    color: APP.text1,
  },
  helperText: {
    fontSize: FONT.sm,
    color: APP.text4,
    marginTop: 2,
  },
  pickerValue: {
    color: APP.text1,
    fontSize: FONT.main,
  },
  pickerPlaceholder: {
    color: APP.text4,
    fontSize: FONT.main,
  },
};

// ── Doctor icon (inline SVG, no MUI) ────────────────────────────────
function DoctorIcon() {
  return (
    <div style={styles.icon}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={APP.primary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
        <path d="M16 11h2v2h-2v2h-2v-2h-2v-2h2v-2h2v2z" />
      </svg>
    </div>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useDoctorStore();
  const [tab, setTab] = useState("doctor"); // "doctor" | "patient"
  const [mode, setMode] = useState("login"); // "login" | "register"

  // Login fields
  const [nickname, setNickname] = useState("");
  const [passcode, setPasscode] = useState("");

  // Register common
  const [regNickname, setRegNickname] = useState("");
  const [regPasscode, setRegPasscode] = useState("");

  // Register doctor
  const [inviteCode] = useState("WELCOME");

  // Register patient
  const [doctorId, setDoctorId] = useState("");
  const [gender, setGender] = useState("");
  const [doctors, setDoctors] = useState([]);

  // Picker visibility
  const [doctorPickerVisible, setDoctorPickerVisible] = useState(false);
  const [genderPickerVisible, setGenderPickerVisible] = useState(false);

  // Role picker (multi-role login)
  const [roleChoices, setRoleChoices] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    unifiedListDoctors().then(setDoctors).catch(() => {});
  }, []);

  function handleTabChange(key) {
    setTab(key);
    setMode("login");
    setError("");
    setRoleChoices(null);
  }

  function handleLoginSuccess(data) {
    saveSession(data);
    if (data.role === "doctor") {
      setWebToken(data.token);
      setAuth(data.doctor_id, data.name, data.token);
      if (window.__wxjs_environment === "miniprogram") {
        // eslint-disable-next-line no-undef
        wx.miniProgram?.postMessage?.({
          data: {
            action: "login",
            token: data.token,
            doctor_id: data.doctor_id,
            name: data.name || "",
          },
        });
        // eslint-disable-next-line no-undef
        wx.miniProgram?.redirectTo?.({ url: "/pages/doctor/doctor" });
        return;
      }
      navigate("/doctor", { replace: true });
    } else {
      localStorage.setItem("patient_portal_token", data.token);
      localStorage.setItem("patient_portal_name", data.name || "");
      localStorage.setItem("patient_portal_doctor_id", data.doctor_id || "");
      navigate("/patient", { replace: true });
    }
  }

  async function handleLogin(e) {
    e?.preventDefault();
    if (!nickname.trim() || !passcode.trim()) {
      setError("请输入昵称和口令");
      return;
    }
    if (!/^\d+$/.test(passcode.trim())) {
      setError("口令必须为纯数字");
      return;
    }
    setLoading(true);
    setError("");
    setRoleChoices(null);
    try {
      const data = await unifiedLogin(nickname.trim(), parseInt(passcode));
      if (data.needs_role_selection) {
        setRoleChoices(data.roles);
      } else {
        handleLoginSuccess(data);
      }
    } catch (err) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRoleSelect(role) {
    setLoading(true);
    setError("");
    try {
      const data = await unifiedLoginWithRole(
        nickname.trim(),
        parseInt(passcode),
        role.role,
        role.doctor_id,
        role.patient_id,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegisterDoctor(e) {
    e?.preventDefault();
    if (!regNickname.trim() || !regPasscode.trim() || !inviteCode.trim()) {
      setError("请填写完整信息");
      return;
    }
    if (!/^\d+$/.test(regPasscode.trim())) {
      setError("口令必须为纯数字");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await unifiedRegisterDoctor(
        regNickname.trim(),
        regNickname.trim(),
        parseInt(regPasscode),
        inviteCode.trim(),
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegisterPatient(e) {
    e?.preventDefault();
    if (!regNickname.trim() || !regPasscode.trim() || !doctorId) {
      setError("请填写完整信息");
      return;
    }
    if (!/^\d+$/.test(regPasscode.trim())) {
      setError("口令必须为纯数字");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await unifiedRegisterPatient(
        regNickname.trim(),
        regNickname.trim(),
        parseInt(regPasscode),
        doctorId,
        gender || undefined,
      );
      handleLoginSuccess(data);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally {
      setLoading(false);
    }
  }

  const isDoctor = tab === "doctor";

  // Doctor picker columns
  const doctorColumns = [
    doctors.map((d) => ({
      label: d.name + (d.department ? ` · ${d.department}` : ""),
      value: d.doctor_id,
    })),
  ];

  const genderColumns = [
    [
      { label: "不填", value: "" },
      { label: "男", value: "男" },
      { label: "女", value: "女" },
    ],
  ];

  const selectedDoctorLabel =
    doctors.find((d) => d.doctor_id === doctorId)
      ? doctors.find((d) => d.doctor_id === doctorId).name +
        (doctors.find((d) => d.doctor_id === doctorId).department
          ? ` · ${doctors.find((d) => d.doctor_id === doctorId).department}`
          : "")
      : null;

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* Header */}
        <div style={styles.header}>
          <DoctorIcon />
          <h2 style={styles.title}>AI 医疗助手</h2>
        </div>

        {/* Role tabs */}
        <Tabs activeKey={tab} onChange={handleTabChange} style={{ marginBottom: 20 }}>
          <Tabs.Tab title="医生" key="doctor" />
          <Tabs.Tab title="患者" key="patient" />
        </Tabs>

        {/* ==================== LOGIN ==================== */}
        {mode === "login" && !roleChoices && (
          <div>
            <Form layout="vertical">
              <Form.Item label="昵称">
                <Input
                  placeholder="请输入昵称"
                  value={nickname}
                  onChange={setNickname}
                  clearable
                />
              </Form.Item>
              <Form.Item label="口令">
                <Input
                  placeholder="请输入数字口令"
                  value={passcode}
                  onChange={setPasscode}
                  type="number"
                  inputMode="numeric"
                />
              </Form.Item>
            </Form>
            {error && <p style={styles.errorText}>{error}</p>}
            <Button
              block
              color="primary"
              size="large"
              disabled={loading}
              onClick={handleLogin}
              style={{ marginTop: 8 }}
            >
              {loading ? <SpinLoading style={{ "--size": "20px" }} /> : "登录"}
            </Button>
            <p style={styles.switchText}>
              没有账号？
              <span
                style={styles.link}
                onClick={() => {
                  setMode("register");
                  setError("");
                }}
              >
                {isDoctor ? "医生注册" : "患者注册"}
              </span>
            </p>
          </div>
        )}

        {/* ==================== ROLE PICKER ==================== */}
        {mode === "login" && roleChoices && (
          <div>
            <p style={{ ...styles.switchText, marginBottom: 12 }}>
              检测到多个账号，请选择登录身份：
            </p>
            {roleChoices.map((r, i) => (
              <Button
                key={i}
                block
                color="default"
                fill="outline"
                size="large"
                style={{ marginBottom: 8, textAlign: "left", justifyContent: "flex-start" }}
                onClick={() => handleRoleSelect(r)}
                disabled={loading}
              >
                <span style={styles.roleLabel}>
                  {r.role === "doctor" ? "医生" : "患者"} — {r.name}
                </span>
              </Button>
            ))}
            <Button
              block
              color="default"
              fill="none"
              size="small"
              onClick={() => setRoleChoices(null)}
              style={{ color: APP.text4 }}
            >
              返回
            </Button>
          </div>
        )}

        {/* ==================== DOCTOR REGISTER ==================== */}
        {mode === "register" && isDoctor && (
          <div>
            <Form layout="vertical">
              <Form.Item label="邀请码" help="公开测试期间自动填入">
                <Input value={inviteCode} readOnly />
              </Form.Item>
              <Form.Item label="昵称" help="用于登录和显示">
                <Input
                  placeholder="请输入昵称"
                  value={regNickname}
                  onChange={setRegNickname}
                  clearable
                />
              </Form.Item>
              <Form.Item label="口令">
                <Input
                  placeholder="设置数字口令"
                  value={regPasscode}
                  onChange={setRegPasscode}
                  type="password"
                  inputMode="numeric"
                />
              </Form.Item>
            </Form>
            {error && <p style={styles.errorText}>{error}</p>}
            <Button
              block
              color="primary"
              size="large"
              disabled={loading}
              onClick={handleRegisterDoctor}
              style={{ marginTop: 8 }}
            >
              {loading ? <SpinLoading style={{ "--size": "20px" }} /> : "注册"}
            </Button>
            <p style={styles.switchText}>
              已有账号？
              <span
                style={styles.link}
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
              >
                返回登录
              </span>
            </p>
          </div>
        )}

        {/* ==================== PATIENT REGISTER ==================== */}
        {mode === "register" && !isDoctor && (
          <div>
            <Form layout="vertical">
              <Form.Item label="选择医生">
                <div
                  onClick={() => setDoctorPickerVisible(true)}
                  style={{
                    padding: "8px 0",
                    cursor: "pointer",
                    ...(selectedDoctorLabel ? styles.pickerValue : styles.pickerPlaceholder),
                  }}
                >
                  {selectedDoctorLabel || "请选择医生"}
                </div>
              </Form.Item>
              <Form.Item label="昵称" help="用于登录和显示">
                <Input
                  placeholder="请输入昵称"
                  value={regNickname}
                  onChange={setRegNickname}
                  clearable
                />
              </Form.Item>
              <Form.Item label="性别">
                <div
                  onClick={() => setGenderPickerVisible(true)}
                  style={{
                    padding: "8px 0",
                    cursor: "pointer",
                    ...(gender ? styles.pickerValue : styles.pickerPlaceholder),
                  }}
                >
                  {gender || "不填（可选）"}
                </div>
              </Form.Item>
              <Form.Item label="口令">
                <Input
                  placeholder="设置数字口令"
                  value={regPasscode}
                  onChange={setRegPasscode}
                  type="password"
                  inputMode="numeric"
                />
              </Form.Item>
            </Form>

            {/* Doctor picker */}
            <Picker
              columns={doctorColumns}
              visible={doctorPickerVisible}
              onClose={() => setDoctorPickerVisible(false)}
              value={doctorId ? [doctorId] : []}
              onConfirm={(val) => {
                setDoctorId(val[0] || "");
                setDoctorPickerVisible(false);
              }}
              cancelText="取消"
              confirmText="确定"
            />

            {/* Gender picker */}
            <Picker
              columns={genderColumns}
              visible={genderPickerVisible}
              onClose={() => setGenderPickerVisible(false)}
              value={[gender]}
              onConfirm={(val) => {
                setGender(val[0] || "");
                setGenderPickerVisible(false);
              }}
              cancelText="取消"
              confirmText="确定"
            />

            {error && <p style={styles.errorText}>{error}</p>}
            <Button
              block
              color="primary"
              size="large"
              disabled={loading}
              onClick={handleRegisterPatient}
              style={{ marginTop: 8 }}
            >
              {loading ? <SpinLoading style={{ "--size": "20px" }} /> : "注册"}
            </Button>
            <p style={styles.switchText}>
              已有账号？
              <span
                style={styles.link}
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
              >
                返回登录
              </span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
