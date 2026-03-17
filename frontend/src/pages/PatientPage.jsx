/**
 * 患者门户（ADR 0016）
 *
 * 三个视图：
 * 1. LoginView — 手机 + 出生年份登录，首次注册（含医生选择）
 * 2. HomeView — 患者主页：预问诊、病历、留言
 * 3. InterviewView — 微信风格对话式预问诊
 */

import { useEffect, useState, useCallback, useRef } from "react";
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
  Divider,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SendIcon from "@mui/icons-material/Send";
import AssignmentIcon from "@mui/icons-material/Assignment";
import DescriptionIcon from "@mui/icons-material/Description";
import ChatIcon from "@mui/icons-material/Chat";
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

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  } catch { return iso; }
}

function recordTypeLabel(type) {
  return { visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊" }[type] || type;
}

const FIELD_LABELS = {
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  family_history: "家族史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
};

// ===========================================================================
// LoginView
// ===========================================================================

function LoginView({ onLogin }) {
  const [mode, setMode] = useState("login"); // login | register
  const [phone, setPhone] = useState("");
  const [yob, setYob] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (mode === "register") {
      listDoctors().then(setDoctors).catch(() => {});
    }
  }, [mode]);

  async function handleLogin(e) {
    e.preventDefault();
    if (!phone.trim() || !yob.trim()) { setError("请输入手机号和出生年份"); return; }
    setLoading(true); setError("");
    try {
      const data = await patientLogin(phone.trim(), parseInt(yob), null);
      if (data.needs_doctor_selection) {
        setError("您在多位医生处有记录，请先注册选择医生。");
        setMode("register");
        return;
      }
      onLogin(data.token, data.patient_name, data.doctor_id);
    } catch (err) {
      setError(err.message || "登录失败");
    } finally { setLoading(false); }
  }

  async function handleRegister(e) {
    e.preventDefault();
    if (!doctorId || !name.trim() || !phone.trim() || !yob.trim()) {
      setError("请填写完整信息"); return;
    }
    setLoading(true); setError("");
    try {
      const data = await patientRegister(doctorId, name.trim(), gender || null, parseInt(yob), phone.trim());
      onLogin(data.token, data.patient_name, doctorId);
    } catch (err) {
      setError(err.message || "注册失败");
    } finally { setLoading(false); }
  }

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", px: 2, bgcolor: "#ededed" }}>
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: 48, color: "primary.main" }} />
            <Typography variant="h6" fontWeight={700}>{mode === "login" ? "患者登录" : "患者注册"}</Typography>

            {mode === "login" ? (
              <Box component="form" onSubmit={handleLogin} sx={{ width: "100%" }}>
                <Stack spacing={2}>
                  <TextField label="手机号" value={phone} onChange={e => setPhone(e.target.value)} fullWidth size="small" />
                  <TextField label="出生年份" value={yob} onChange={e => setYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}>
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
                    <MenuItem value="">不填</MenuItem>
                    <MenuItem value="男">男</MenuItem>
                    <MenuItem value="女">女</MenuItem>
                  </TextField>
                  <TextField label="出生年份" value={yob} onChange={e => setYob(e.target.value)} placeholder="例如 1985" fullWidth size="small" />
                  <TextField label="手机号" value={phone} onChange={e => setPhone(e.target.value)} fullWidth size="small" />
                  {error && <Typography variant="body2" color="error">{error}</Typography>}
                  <Button type="submit" variant="contained" fullWidth disabled={loading}>
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
// HomeView
// ===========================================================================

function HomeView({ token, patientName, onLogout, onStartInterview, onViewRecords, onMessage }) {
  const [activeSession, setActiveSession] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    interviewCurrent(token).then(data => {
      setActiveSession(data);
    }).catch(() => {}).finally(() => setChecking(false));
  }, [token]);

  return (
    <Box sx={{ maxWidth: 500, mx: "auto", px: 2, py: 4 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={3}>
        <Stack direction="row" spacing={1} alignItems="center">
          <MedicalServicesOutlinedIcon color="primary" />
          <Typography variant="h6" fontWeight={700}>{patientName}</Typography>
        </Stack>
        <Button size="small" color="inherit" onClick={onLogout}>退出</Button>
      </Stack>

      <Stack spacing={2}>
        {/* Active interview banner */}
        {activeSession && (
          <Card sx={{ bgcolor: "#fff3e0", borderRadius: 2 }}>
            <CardContent>
              <Typography variant="body2" fontWeight={600}>您有一个进行中的预问诊</Typography>
              <Typography variant="caption" color="text.secondary">
                已收集 {activeSession.progress?.filled || 0}/{activeSession.progress?.total || 7} 项
              </Typography>
              <Box mt={1}>
                <Button size="small" variant="contained" onClick={() => onStartInterview(activeSession)}>继续问诊</Button>
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Main actions */}
        <Card sx={{ borderRadius: 2, cursor: "pointer" }} onClick={() => onStartInterview(activeSession)}>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="center">
              <AssignmentIcon color="primary" />
              <Box>
                <Typography variant="body1" fontWeight={600}>
                  {activeSession ? "继续预问诊" : "开始预问诊"}
                </Typography>
                <Typography variant="caption" color="text.secondary">AI 助手帮您整理病情信息</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        <Card sx={{ borderRadius: 2, cursor: "pointer" }} onClick={onViewRecords}>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="center">
              <DescriptionIcon color="primary" />
              <Box>
                <Typography variant="body1" fontWeight={600}>我的病历</Typography>
                <Typography variant="caption" color="text.secondary">查看诊疗记录</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        <Card sx={{ borderRadius: 2, cursor: "pointer" }} onClick={onMessage}>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="center">
              <ChatIcon color="primary" />
              <Box>
                <Typography variant="body1" fontWeight={600}>给医生留言</Typography>
                <Typography variant="caption" color="text.secondary">发送消息给您的医生</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}

// ===========================================================================
// RecordsView
// ===========================================================================

function RecordsView({ token, onBack, onLogout }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPatientRecords(token).then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(err => { if (err.status === 401) onLogout(); })
      .finally(() => setLoading(false));
  }, [token, onLogout]);

  return (
    <Box sx={{ maxWidth: 500, mx: "auto", px: 2, py: 2 }}>
      <Stack direction="row" alignItems="center" mb={2}>
        <IconButton onClick={onBack}><ArrowBackIcon /></IconButton>
        <Typography variant="h6" fontWeight={700}>我的病历</Typography>
      </Stack>
      {loading && <Box display="flex" justifyContent="center" py={4}><CircularProgress size={32} /></Box>}
      {!loading && records.length === 0 && <Typography color="text.secondary" textAlign="center" py={4}>暂无记录</Typography>}
      <Stack spacing={2}>
        {records.map(rec => (
          <Card key={rec.id} variant="outlined" sx={{ borderRadius: 2 }}>
            <CardContent sx={{ pb: "12px !important" }}>
              <Stack direction="row" justifyContent="space-between" mb={0.5}>
                <Typography variant="caption" color="text.secondary">{recordTypeLabel(rec.record_type)}</Typography>
                <Typography variant="caption" color="text.secondary">{formatDate(rec.created_at)}</Typography>
              </Stack>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {rec.content || "（内容为空）"}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Box>
  );
}

// ===========================================================================
// MessageView
// ===========================================================================

function MessageView({ token, onBack, onLogout }) {
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
    <Box sx={{ maxWidth: 500, mx: "auto", px: 2, py: 2 }}>
      <Stack direction="row" alignItems="center" mb={2}>
        <IconButton onClick={onBack}><ArrowBackIcon /></IconButton>
        <Typography variant="h6" fontWeight={700}>给医生留言</Typography>
      </Stack>
      <Box component="form" onSubmit={handleSend}>
        <Stack spacing={2}>
          <TextField multiline minRows={4} maxRows={8} fullWidth placeholder="请输入您的问题或病情描述…" value={message} onChange={e => setMessage(e.target.value)} />
          {reply && <Typography variant="body2" color="success.main">{reply}</Typography>}
          <Button type="submit" variant="contained" disabled={sending || !message.trim()}>
            {sending ? <CircularProgress size={16} /> : "发送"}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}

// ===========================================================================
// InterviewView — WeChat-style chat
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

  // Start or resume session
  useEffect(() => {
    async function init() {
      try {
        const data = await interviewStart(token);
        setSessionId(data.session_id);
        setCollected(data.collected || {});
        setProgress(data.progress);
        setStatus(data.status);
        if (data.resumed && initialSession?.conversation) {
          // Restore conversation from existing session
          const conv = initialSession.conversation.map(m => ({
            role: m.role, content: m.content,
          }));
          setMessages(conv);
        } else {
          setMessages([{ role: "assistant", content: data.reply }]);
        }
      } catch (err) {
        if (err.status === 401) onLogout();
        setMessages([{ role: "assistant", content: "无法启动问诊，请稍后重试。" }]);
      }
    }
    init();
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
    if (abandon) {
      try { await interviewCancel(token, sessionId); } catch {}
    }
    onBack();
  }

  const allFields = ["chief_complaint", "present_illness", "past_history", "allergy_history", "family_history", "personal_history", "marital_reproductive"];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", maxWidth: 500, mx: "auto", bgcolor: "#ededed" }}>
      {/* Top bar */}
      <Box sx={{ display: "flex", alignItems: "center", px: 1, py: 1, bgcolor: "#f5f5f5", borderBottom: "1px solid #ddd" }}>
        <IconButton size="small" onClick={() => status === "confirmed" ? onBack() : setShowExitDialog(true)}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="subtitle1" fontWeight={600} sx={{ flex: 1, textAlign: "center" }}>预问诊</Typography>
        <Chip
          label={`${progress.filled}/${progress.total}`}
          size="small"
          color={status === "reviewing" ? "success" : "default"}
          onClick={() => setShowSummary(true)}
          sx={{ cursor: "pointer" }}
        />
      </Box>

      {/* Chat area */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {messages.map((msg, i) => (
          <Box key={i} sx={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", mb: 1.5 }}>
            <Box sx={{
              maxWidth: "80%", px: 2, py: 1.5, borderRadius: 2,
              bgcolor: msg.role === "user" ? "#95ec69" : "#fff",
              color: "#333", fontSize: "0.9rem", lineHeight: 1.6,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {msg.content}
            </Box>
          </Box>
        ))}
        {sending && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
            <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: "#fff" }}>
              <CircularProgress size={16} />
            </Box>
          </Box>
        )}
        <div ref={chatEndRef} />
      </Box>

      {/* Input bar */}
      {status === "interviewing" && (
        <Box component="form" onSubmit={handleSend} sx={{ display: "flex", gap: 1, px: 2, py: 1.5, bgcolor: "#f5f5f5", borderTop: "1px solid #ddd" }}>
          <TextField
            value={input} onChange={e => setInput(e.target.value)}
            placeholder="请输入…" fullWidth size="small"
            sx={{ bgcolor: "#fff", borderRadius: 1 }}
            autoFocus
          />
          <IconButton type="submit" color="primary" disabled={!input.trim() || sending}><SendIcon /></IconButton>
        </Box>
      )}

      {status === "confirmed" && (
        <Box sx={{ px: 2, py: 2, bgcolor: "#f5f5f5", textAlign: "center" }}>
          <Button variant="contained" onClick={onBack}>返回主页</Button>
        </Box>
      )}

      {/* Summary sheet dialog */}
      <Dialog open={showSummary} onClose={() => setShowSummary(false)} fullWidth maxWidth="xs">
        <DialogTitle>已收集信息</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5}>
            {allFields.map(f => {
              const val = collected[f];
              const label = FIELD_LABELS[f] || f;
              return (
                <Box key={f}>
                  <Typography variant="caption" color="text.secondary">{val ? "✅" : "⬜"} {label}</Typography>
                  {val && <Typography variant="body2" sx={{ ml: 3 }}>{val}</Typography>}
                </Box>
              );
            })}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSummary(false)}>关闭</Button>
          {(status === "reviewing" || progress.filled >= progress.total) && (
            <Button variant="contained" onClick={handleConfirm} disabled={confirming}>
              {confirming ? <CircularProgress size={16} /> : "确认提交"}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Exit dialog */}
      <Dialog open={showExitDialog} onClose={() => setShowExitDialog(false)}>
        <DialogTitle>退出问诊</DialogTitle>
        <DialogContent>
          <Typography variant="body2">您要保存进度还是重新开始？</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => handleExit(false)}>保存退出</Button>
          <Button color="error" onClick={() => handleExit(true)}>放弃重来</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ===========================================================================
// Page root
// ===========================================================================

export default function PatientPage() {
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [view, setView] = useState("home"); // home | records | message | interview
  const [interviewSession, setInterviewSession] = useState(null);

  function handleLogin(newToken, name, doctorId) {
    localStorage.setItem(STORAGE_KEY, newToken);
    localStorage.setItem(STORAGE_NAME_KEY, name);
    if (doctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, doctorId);
    setToken(newToken);
    setPatientName(name);
    setView("home");
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    setToken("");
    setPatientName("");
    setView("home");
  }

  if (!token) return <LoginView onLogin={handleLogin} />;

  switch (view) {
    case "records":
      return <RecordsView token={token} onBack={() => setView("home")} onLogout={handleLogout} />;
    case "message":
      return <MessageView token={token} onBack={() => setView("home")} onLogout={handleLogout} />;
    case "interview":
      return (
        <InterviewView
          token={token}
          initialSession={interviewSession}
          onBack={() => { setView("home"); setInterviewSession(null); }}
          onLogout={handleLogout}
        />
      );
    default:
      return (
        <HomeView
          token={token}
          patientName={patientName}
          onLogout={handleLogout}
          onStartInterview={(session) => { setInterviewSession(session); setView("interview"); }}
          onViewRecords={() => setView("records")}
          onMessage={() => setView("message")}
        />
      );
  }
}
