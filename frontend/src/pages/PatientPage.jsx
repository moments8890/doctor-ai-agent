/**
 * 患者门户（ADR 0016）
 *
 * 布局：单列 + 底部导航（手机和桌面一致）
 * - 预问诊（interview tab / full-screen chat）
 * - 我的病历（records tab）
 * - 给医生留言（message tab）
 * - 登录页（未登录时显示）
 */

import { useEffect, useState, useRef } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SendIcon from "@mui/icons-material/Send";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import {
  patientLogin,
  patientRegister,
  listDoctors,
  getPatientRecords,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
  interviewCurrent,
} from "../api";

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";

const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊",
};

const FIELD_LABELS = {
  chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史",
};

function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }); }
  catch { return iso; }
}

// ===========================================================================
// LoginView (standalone, full-screen)
// ===========================================================================

function LoginView({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [phone, setPhone] = useState("");
  const [yob, setYob] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (mode === "register") listDoctors().then(setDoctors).catch(() => {});
  }, [mode]);

  async function handleLogin(e) {
    e.preventDefault();
    if (!phone.trim() || !yob.trim()) { setError("请输入手机号和出生年份"); return; }
    setLoading(true); setError("");
    try {
      const data = await patientLogin(phone.trim(), parseInt(yob), null);
      if (data.needs_doctor_selection) { setError("您在多位医生处有记录，请先注册选择医生。"); setMode("register"); return; }
      onLogin(data.token, data.patient_name, data.doctor_id);
    } catch (err) { setError(err.message || "登录失败"); }
    finally { setLoading(false); }
  }

  async function handleRegister(e) {
    e.preventDefault();
    if (!doctorId || !name.trim() || !phone.trim() || !yob.trim()) { setError("请填写完整信息"); return; }
    setLoading(true); setError("");
    try {
      const data = await patientRegister(doctorId, name.trim(), gender || null, parseInt(yob), phone.trim());
      onLogin(data.token, data.patient_name, doctorId);
    } catch (err) { setError(err.message || "注册失败"); }
    finally { setLoading(false); }
  }

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", px: 2, bgcolor: "#ededed" }}>
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: 48, color: "#07C160" }} />
            <Typography variant="h6" fontWeight={700}>{mode === "login" ? "患者登录" : "患者注册"}</Typography>
            {mode === "login" ? (
              <Box component="form" onSubmit={handleLogin} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField label="手机号" value={phone} onChange={e => setPhone(e.target.value)} fullWidth size="small" />
                  <TextField label="出生年份" value={yob} onChange={e => setYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading} sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                    {loading ? <CircularProgress size={16} /> : "登录"}
                  </Button>
                  <Button size="small" onClick={() => { setMode("register"); setError(""); }}>首次使用？点击注册</Button>
                </Stack>
              </Box>
            ) : (
              <Box component="form" onSubmit={handleRegister} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField select label="选择医生" value={doctorId} onChange={e => setDoctorId(e.target.value)} fullWidth size="small">
                    {doctors.map(d => <MenuItem key={d.doctor_id} value={d.doctor_id}>{d.name}{d.department ? ` · ${d.department}` : ""}</MenuItem>)}
                  </TextField>
                  <TextField label="您的姓名" value={name} onChange={e => setName(e.target.value)} fullWidth size="small" />
                  <TextField select label="性别" value={gender} onChange={e => setGender(e.target.value)} fullWidth size="small">
                    <MenuItem value="">不填</MenuItem><MenuItem value="男">男</MenuItem><MenuItem value="女">女</MenuItem>
                  </TextField>
                  <TextField label="出生年份" value={yob} onChange={e => setYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                  <TextField label="手机号" value={phone} onChange={e => setPhone(e.target.value)} fullWidth size="small" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading} sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                    {loading ? <CircularProgress size={16} /> : "注册"}
                  </Button>
                  <Button size="small" onClick={() => { setMode("login"); setError(""); }}>已有账号？返回登录</Button>
                </Stack>
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

// ===========================================================================
// InterviewTab — shows active session banner or start button
// ===========================================================================

function InterviewTab({ token, onStartInterview, onLogout }) {
  const [activeSession, setActiveSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    interviewCurrent(token).then(setActiveSession).catch(() => {}).finally(() => setLoading(false));
  }, [token]);

  if (loading) return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={28} /></Box>;

  return (
    <Box sx={{ py: 3, px: 2 }}>
      {activeSession ? (
        <Card sx={{ borderRadius: 2, bgcolor: "#fff3e0" }}>
          <CardContent>
            <Typography fontWeight={600} sx={{ mb: 0.5 }}>您有一个进行中的预问诊</Typography>
            <Typography variant="caption" color="text.secondary">
              已收集 {activeSession.progress?.filled || 0}/{activeSession.progress?.total || 7} 项
            </Typography>
            <Box mt={1.5}>
              <Button variant="contained" onClick={() => onStartInterview(activeSession)}
                sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
                继续问诊
              </Button>
            </Box>
          </CardContent>
        </Card>
      ) : (
        <Card sx={{ borderRadius: 2, cursor: "pointer" }} onClick={() => onStartInterview(null)}>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="center">
              <AssignmentOutlinedIcon sx={{ color: "#07C160", fontSize: 32 }} />
              <Box>
                <Typography fontWeight={600}>开始预问诊</Typography>
                <Typography variant="caption" color="text.secondary">AI 助手帮您整理病情信息</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

// ===========================================================================
// RecordsTab
// ===========================================================================

function RecordsTab({ token, onLogout }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPatientRecords(token).then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(err => { if (err.status === 401) onLogout(); })
      .finally(() => setLoading(false));
  }, [token, onLogout]);

  if (loading) return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={28} /></Box>;
  if (records.length === 0) return <Typography color="text.secondary" textAlign="center" py={6}>暂无记录</Typography>;

  return (
    <Stack spacing={1.5} sx={{ py: 2, px: 2 }}>
      {records.map(rec => (
        <Card key={rec.id} variant="outlined" sx={{ borderRadius: 2 }}>
          <CardContent sx={{ pb: "12px !important" }}>
            <Stack direction="row" justifyContent="space-between" mb={0.5}>
              <Typography variant="caption" color="text.secondary">{RECORD_TYPE_LABEL[rec.record_type] || rec.record_type}</Typography>
              <Typography variant="caption" color="text.secondary">{formatDate(rec.created_at)}</Typography>
            </Stack>
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {rec.content || "（内容为空）"}
            </Typography>
          </CardContent>
        </Card>
      ))}
    </Stack>
  );
}

// ===========================================================================
// MessageTab
// ===========================================================================

function MessageTab({ token, onLogout }) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [reply, setReply] = useState("");

  async function handleSend(e) {
    e.preventDefault();
    if (!message.trim()) return;
    setSending(true); setReply("");
    try {
      const data = await sendPatientMessage(token, message.trim());
      setReply(data.reply || "消息已发送");
      setMessage("");
    } catch (err) {
      if (err.status === 401) { onLogout(); return; }
      setReply("发送失败，请稍后重试");
    } finally { setSending(false); }
  }

  return (
    <Box sx={{ py: 3, px: 2 }}>
      <Box component="form" onSubmit={handleSend}>
        <Stack spacing={2}>
          <TextField multiline minRows={4} maxRows={8} fullWidth placeholder="请输入您的问题或病情描述…"
            value={message} onChange={e => setMessage(e.target.value)} />
          {reply && <Typography variant="body2" color="success.main">{reply}</Typography>}
          <Button type="submit" variant="contained" disabled={sending || !message.trim()}
            sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
            {sending ? <CircularProgress size={16} /> : "发送消息"}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}

// ===========================================================================
// InterviewView — full-screen chat (hides bottom nav)
// ===========================================================================

function InterviewView({ token, initialSession, onBack, onLogout }) {
  const [sessionId, setSessionId] = useState(initialSession?.id || "");
  const [messages, setMessages] = useState([]);
  const [collected, setCollected] = useState(initialSession?.collected || {});
  const [progress, setProgress] = useState(initialSession?.progress || { filled: 0, total: 7 });
  const [status, setStatus] = useState(initialSession?.status || "interviewing");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [showExitDialog, setShowExitDialog] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await interviewStart(token);
        setSessionId(data.session_id);
        setCollected(data.collected || {});
        setProgress(data.progress);
        setStatus(data.status);
        if (data.resumed && initialSession?.conversation) {
          setMessages(initialSession.conversation.map(m => ({ role: m.role, content: m.content })));
        } else {
          setMessages([{ role: "assistant", content: data.reply }]);
        }
      } catch (err) {
        if (err.status === 401) onLogout();
        setMessages([{ role: "assistant", content: "无法启动问诊，请稍后重试。" }]);
      }
    })();
  }, [token]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending || status !== "interviewing") return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const data = await interviewTurn(token, sessionId, text);
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }]);
      setCollected(data.collected || {});
      setProgress(data.progress);
      setStatus(data.status);
      if (data.status === "reviewing") setTimeout(() => setShowSummary(true), 800);
    } catch (err) {
      if (err.status === 401) { onLogout(); return; }
      setMessages(prev => [...prev, { role: "assistant", content: "系统繁忙，请稍后重试。" }]);
    } finally { setSending(false); }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const data = await interviewConfirm(token, sessionId);
      setStatus("confirmed");
      setShowSummary(false);
      setMessages(prev => [...prev, { role: "assistant", content: data.message }]);
    } catch (err) {
      if (err.status === 401) { onLogout(); return; }
      alert("提交失败，请稍后重试。");
    } finally { setConfirming(false); }
  }

  async function handleExit(abandon) {
    setShowExitDialog(false);
    if (abandon) { try { await interviewCancel(token, sessionId); } catch {} }
    onBack();
  }

  const allFields = ["chief_complaint", "present_illness", "past_history", "allergy_history", "family_history", "personal_history", "marital_reproductive"];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", maxWidth: 500, mx: "auto", bgcolor: "#ededed" }}>
      {/* Top bar */}
      <Box sx={{ display: "flex", alignItems: "center", px: 1, py: 1, bgcolor: "#f5f5f5", borderBottom: "1px solid #ddd", flexShrink: 0 }}>
        <IconButton size="small" onClick={() => status === "confirmed" ? onBack() : setShowExitDialog(true)}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="subtitle1" fontWeight={600} sx={{ flex: 1, textAlign: "center" }}>预问诊</Typography>
        <Chip label={`${progress.filled}/${progress.total}`} size="small"
          color={status === "reviewing" ? "success" : "default"}
          onClick={() => setShowSummary(true)} sx={{ cursor: "pointer" }} />
      </Box>

      {/* Chat */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {messages.map((msg, i) => (
          <Box key={i} sx={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", mb: 1.5 }}>
            <Box sx={{
              maxWidth: "80%", px: 2, py: 1.5, borderRadius: 2,
              bgcolor: msg.role === "user" ? "#95ec69" : "#fff",
              color: "#333", fontSize: "0.9rem", lineHeight: 1.6,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
          </Box>
        ))}
        {sending && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
            <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: "#fff" }}><CircularProgress size={16} /></Box>
          </Box>
        )}
        <div ref={chatEndRef} />
      </Box>

      {/* Input */}
      {status === "interviewing" && (
        <Box component="form" onSubmit={handleSend} sx={{ display: "flex", gap: 1, px: 2, py: 1.5, bgcolor: "#f5f5f5", borderTop: "1px solid #ddd", flexShrink: 0 }}>
          <TextField value={input} onChange={e => setInput(e.target.value)} placeholder="请输入…" fullWidth size="small"
            sx={{ bgcolor: "#fff", borderRadius: 1 }} autoFocus />
          <IconButton type="submit" disabled={!input.trim() || sending} sx={{ color: "#07C160" }}><SendIcon /></IconButton>
        </Box>
      )}
      {status === "confirmed" && (
        <Box sx={{ px: 2, py: 2, bgcolor: "#f5f5f5", textAlign: "center", flexShrink: 0 }}>
          <Button variant="contained" onClick={onBack} sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>返回主页</Button>
        </Box>
      )}

      {/* Summary dialog */}
      <Dialog open={showSummary} onClose={() => setShowSummary(false)} fullWidth maxWidth="xs">
        <DialogTitle>已收集信息</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5}>
            {allFields.map(f => {
              const val = collected[f];
              return (
                <Box key={f}>
                  <Typography variant="caption" color="text.secondary">{val ? "✅" : "⬜"} {FIELD_LABELS[f]}</Typography>
                  {val && <Typography variant="body2" sx={{ ml: 3 }}>{val}</Typography>}
                </Box>
              );
            })}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSummary(false)}>关闭</Button>
          {(status === "reviewing" || progress.filled >= progress.total) && (
            <Button variant="contained" onClick={handleConfirm} disabled={confirming}
              sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
              {confirming ? <CircularProgress size={16} /> : "确认提交"}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Exit dialog */}
      <Dialog open={showExitDialog} onClose={() => setShowExitDialog(false)}>
        <DialogTitle>退出问诊</DialogTitle>
        <DialogContent><Typography variant="body2">您要保存进度还是重新开始？</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => handleExit(false)}>保存退出</Button>
          <Button color="error" onClick={() => handleExit(true)}>放弃重来</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ===========================================================================
// Page root — bottom nav layout
// ===========================================================================

const NAV_TABS = [
  { key: "interview", label: "预问诊", icon: <AssignmentOutlinedIcon /> },
  { key: "records", label: "病历", icon: <DescriptionOutlinedIcon /> },
  { key: "message", label: "留言", icon: <ChatOutlinedIcon /> },
];

export default function PatientPage() {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [tab, setTab] = useState("interview");
  const [inInterview, setInInterview] = useState(false);
  const [interviewSession, setInterviewSession] = useState(null);

  function handleLogin(newToken, name, doctorId) {
    localStorage.setItem(STORAGE_KEY, newToken);
    localStorage.setItem(STORAGE_NAME_KEY, name);
    if (doctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, doctorId);
    setToken(newToken);
    setPatientName(name);
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    setToken("");
    setPatientName("");
  }

  if (!token) return <LoginView onLogin={handleLogin} />;

  // Full-screen interview (hides nav)
  if (inInterview) {
    return (
      <InterviewView
        token={token}
        initialSession={interviewSession}
        onBack={() => { setInInterview(false); setInterviewSession(null); }}
        onLogout={handleLogout}
      />
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", maxWidth: 500, mx: "auto", bgcolor: "#ededed" }}>
      {/* Top bar */}
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, bgcolor: "#f5f5f5", borderBottom: "1px solid #ddd", flexShrink: 0 }}>
        <MedicalServicesOutlinedIcon sx={{ color: "#07C160", mr: 1 }} />
        <Typography fontWeight={700} sx={{ flex: 1 }}>患者门户</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>{patientName}</Typography>
        <IconButton size="small" onClick={handleLogout}><LogoutIcon fontSize="small" /></IconButton>
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {tab === "interview" && (
          <InterviewTab token={token} onLogout={handleLogout}
            onStartInterview={(session) => { setInterviewSession(session); setInInterview(true); }} />
        )}
        {tab === "records" && <RecordsTab token={token} onLogout={handleLogout} />}
        {tab === "message" && <MessageTab token={token} onLogout={handleLogout} />}
      </Box>

      {/* Bottom nav */}
      <BottomNavigation value={tab} onChange={(_, v) => setTab(v)} showLabels
        sx={{ borderTop: "1px solid #ddd", flexShrink: 0, bgcolor: "#f5f5f5" }}>
        {NAV_TABS.map(t => (
          <BottomNavigationAction key={t.key} value={t.key} label={t.label} icon={t.icon}
            sx={{ "&.Mui-selected": { color: "#07C160" } }} />
        ))}
      </BottomNavigation>
    </Box>
  );
}
