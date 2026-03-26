/**
 * @route /patient, /patient/:tab, /patient/:tab/:subpage
 *
 * 患者门户（ADR 0016）
 *
 * 两个 tab：
 * - 💬 对话：AI 健康助手聊天（通用问答）
 * - 📄 病历：病历列表 + 新建病历（启动预问诊）
 *
 * 新建病历 → 全屏预问诊（独立上下文）→ 完成后回到病历 tab
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
  Fab,
  IconButton,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SendIcon from "@mui/icons-material/Send";
import AddIcon from "@mui/icons-material/Add";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import SuggestionChips from "../../components/SuggestionChips";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import RecordAvatar from "../../components/RecordAvatar";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import SubpageHeader from "../../components/SubpageHeader";
import { TYPE, ICON } from "../../theme";
import {
  patientLogin,
  patientRegister,
  listDoctors,
  getPatientRecords,
  getPatientRecordDetail,
  getPatientTasks,
  completePatientTask,
  getPatientChatMessages,
  sendPatientChat,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
  interviewCurrent,
} from "../../api";
import DoctorBubble from "../../components/DoctorBubble";
import TaskChecklist from "../../components/TaskChecklist";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import { COLOR } from "../../theme";

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";

const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊",
};

const FIELD_LABELS = {
  department: "科别", chief_complaint: "主诉", present_illness: "现病史", past_history: "既往史",
  allergy_history: "过敏史", family_history: "家族史", personal_history: "个人史",
  marital_reproductive: "婚育史", physical_exam: "体格检查", specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查", diagnosis: "初步诊断", treatment_plan: "治疗方案",
  orders_followup: "医嘱及随访",
};

const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

// Layout matches DoctorPage — MobileFrame in App.jsx handles the phone container
const PAGE_LAYOUT = {
  display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed",
  position: "relative", overflow: "hidden",
};

function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }); }
  catch { return iso; }
}

// ===========================================================================
// LoginView
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
    listDoctors().then(setDoctors).catch(() => {});
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    if (!phone.trim() || !yob.trim()) { setError("请输入手机号和出生年份"); return; }
    setLoading(true); setError("");
    try {
      const data = await patientLogin(phone.trim(), parseInt(yob), null);
      if (data.needs_doctor_selection) { setError("您在多位医生处有记录，请先注册选择医生。"); setMode("register"); return; }
      // Look up doctor name from list if available
      const docName = doctors.find(d => d.doctor_id === data.doctor_id)?.name || "";
      onLogin(data.token, data.patient_name, data.doctor_id, docName);
    } catch (err) { setError(err.message || "登录失败"); }
    finally { setLoading(false); }
  }

  async function handleRegister(e) {
    e.preventDefault();
    if (!doctorId || !name.trim() || !phone.trim() || !yob.trim()) { setError("请填写完整信息"); return; }
    setLoading(true); setError("");
    try {
      const data = await patientRegister(doctorId, name.trim(), gender || null, parseInt(yob), phone.trim());
      const docName = doctors.find(d => d.doctor_id === doctorId)?.name || "";
      onLogin(data.token, data.patient_name, doctorId, docName);
    } catch (err) { setError(err.message || "注册失败"); }
    finally { setLoading(false); }
  }

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", px: 2, bgcolor: "#ededed" }}>
      <Card sx={{ width: "100%", maxWidth: 400, borderRadius: 2 }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <MedicalServicesOutlinedIcon sx={{ fontSize: ICON.display, color: "#07C160" }} />
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
// ChatTab — AI 健康助手通用对话
// ===========================================================================

function QuickActions({ onNewInterview, onViewRecords }) {
  const actions = [
    { label: "新问诊", subtitle: "AI帮您整理病情", icon: <AddIcon sx={{ fontSize: ICON.xl, color: "#07C160" }} />, onClick: onNewInterview },
    { label: "我的病历", subtitle: "查看历史记录", icon: <DescriptionOutlinedIcon sx={{ fontSize: ICON.xl, color: "#1B6EF3" }} />, onClick: onViewRecords },
  ];
  return (
    <Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5 }}>
      {actions.map(a => (
        <Box key={a.label} onClick={a.onClick}
          sx={{
            flex: 1, bgcolor: "#fff", borderRadius: "8px", p: 1.5,
            display: "flex", alignItems: "center", gap: 1.2,
            cursor: "pointer", userSelect: "none",
            boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
            "&:active": { bgcolor: "#f9f9f9" },
          }}>
          <Box sx={{ width: 36, height: 36, borderRadius: "8px",
            bgcolor: a.label === "新问诊" ? "#e8f5e9" : "#E8F0FE",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            {a.icon}
          </Box>
          <Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: "#1A1A1A" }}>{a.label}</Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>{a.subtitle}</Typography>
          </Box>
        </Box>
      ))}
    </Box>
  );
}

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

function ChatTab({ token, doctorName, onLogout, onNewInterview, onViewRecords }) {
  const welcomeMsg = { source: "ai", content: `您好！我是${doctorName || "医生"}的AI助手。有什么健康问题可以问我。` };

  const [messages, setMessages] = useState([welcomeMsg]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastMsgId, setLastMsgId] = useState(null);
  const chatEndRef = useRef(null);
  const pollingRef = useRef(null);
  const visibleRef = useRef(true);

  // Initial load + polling for new messages
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getPatientChatMessages(token, lastMsgId);
        if (cancelled) return;
        if (Array.isArray(data) && data.length > 0) {
          setMessages(prev => {
            // Merge: append only new messages by id
            const existingIds = new Set(prev.filter(m => m.id).map(m => m.id));
            const newMsgs = data.filter(m => !existingIds.has(m.id));
            return newMsgs.length > 0 ? [...prev, ...newMsgs] : prev;
          });
          const maxId = Math.max(...data.map(m => m.id));
          setLastMsgId(maxId);
        }
      } catch (err) {
        if (err.status === 401) console.warn("auth expired");
      }
    }

    poll();

    function startPolling() {
      if (pollingRef.current) clearInterval(pollingRef.current);
      const interval = visibleRef.current ? 10000 : 60000;
      pollingRef.current = setInterval(poll, interval);
    }

    function handleVisibility() {
      visibleRef.current = !document.hidden;
      startPolling();
    }

    startPolling();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      if (pollingRef.current) clearInterval(pollingRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages(prev => [...prev, { source: "patient", content: text, _local: true }]);
    setSending(true);
    try {
      const data = await sendPatientChat(token, text);
      setMessages(prev => [...prev, { source: "ai", content: data.reply || "收到您的消息。", triage_category: data.triage_category }]);
    } catch (err) {
      if (err.status === 401) { console.warn("auth expired"); return; }
      setMessages(prev => [...prev, { source: "ai", content: "系统繁忙，请稍后重试。" }]);
    } finally { setSending(false); }
  }

  function renderMessage(msg, i) {
    const src = msg.source || (msg.role === "user" ? "patient" : "ai");

    // Doctor reply bubble
    if (src === "doctor") {
      return (
        <Box key={msg.id || i} sx={{ mb: 1.5 }}>
          <DoctorBubble
            doctorName={doctorName || "医生"}
            content={msg.content}
            timestamp={msg.created_at ? new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : null}
          />
        </Box>
      );
    }

    // Patient message (right aligned)
    if (src === "patient") {
      return (
        <Box key={msg.id || i} sx={{ display: "flex", justifyContent: "flex-end", mb: 1.5 }}>
          <Box sx={{
            maxWidth: "80%", px: 2, py: 1.5, borderRadius: 2,
            bgcolor: "#95ec69", color: "#333", fontSize: "0.9rem", lineHeight: 1.6,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>{msg.content}</Box>
        </Box>
      );
    }

    // AI message (left aligned) — with triage enrichment
    return (
      <Box key={msg.id || i} sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
        <Box sx={{ maxWidth: "80%" }}>
          {msg.triage_category === "diagnosis_confirmation" && (
            <Box sx={{ mb: 0.5, px: 1.5, py: 0.8, borderRadius: "8px", bgcolor: "#e8f5e9", border: "0.5px solid #c8e6c9" }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.success, fontWeight: 500 }}>
                {msg.content}
              </Typography>
            </Box>
          )}
          {msg.triage_category !== "diagnosis_confirmation" && (
            <Box sx={{
              px: 2, py: 1.5, borderRadius: 2, bgcolor: "#fff",
              color: "#333", fontSize: "0.9rem", lineHeight: 1.6,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
          )}
          {msg.triage_category === "urgent" && (
            <Box sx={{ mt: 0.5, px: 1.5, py: 0.5, borderRadius: "6px", bgcolor: COLOR.dangerLight, border: `0.5px solid ${COLOR.danger}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, fontWeight: 500 }}>
                紧急情况，请立即就近就医
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Quick actions */}
      <QuickActions onNewInterview={onNewInterview} onViewRecords={onViewRecords} />

      {/* Chat area */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 1 }}>
        {messages.map(renderMessage)}
        {sending && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
            <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: "#fff" }}><CircularProgress size={16} /></Box>
          </Box>
        )}
        <div ref={chatEndRef} />
      </Box>

      {/* Input */}
      <Box component="form" onSubmit={handleSend}
        sx={{ display: "flex", gap: 1, px: 2, py: 1.5, bgcolor: "#f5f5f5", borderTop: "1px solid #ddd", flexShrink: 0 }}>
        <TextField value={input} onChange={e => setInput(e.target.value)} placeholder="请输入…"
          fullWidth size="small" sx={{ bgcolor: "#fff", borderRadius: 1 }} autoFocus />
        <IconButton type="submit" disabled={!input.trim() || sending} sx={{ color: "#07C160" }} aria-label="发送"><SendIcon /></IconButton>
      </Box>
    </Box>
  );
}

// ===========================================================================
// RecordsTab — 病历列表 + 新建病历
// ===========================================================================


function RecordDetailView({ record, token, onBack }) {
  const structured = record.structured || {};
  const typeLabel = RECORD_TYPE_LABEL[record.record_type] || record.record_type;
  const [detail, setDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(true);

  useEffect(() => {
    if (!record.id || !token) { setLoadingDetail(false); return; }
    setLoadingDetail(true);
    getPatientRecordDetail(token, record.id)
      .then(data => setDetail(data))
      .catch(() => {})
      .finally(() => setLoadingDetail(false));
  }, [record.id, token]);

  const diagStatus = detail?.diagnosis_status;
  const treatmentPlan = detail?.treatment_plan;

  const DIAG_STATUS_LABELS = {
    pending: "诊断中",
    completed: "待审核",
    confirmed: "已确认",
    failed: "诊断失败",
  };
  const DIAG_STATUS_COLORS = {
    pending: COLOR.warning,
    completed: COLOR.accent,
    confirmed: COLOR.success,
    failed: COLOR.danger,
  };

  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <SubpageHeader title={typeLabel} onBack={onBack} />
      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#fff", px: 1.5, py: 1 }}>
        {/* Structured fields */}
        {FIELD_ORDER.map((key) => {
          const val = structured[key];
          if (!val) return null;
          return (
            <Box key={key} sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0", display: "flex", alignItems: "baseline", gap: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", flexShrink: 0 }}>{FIELD_LABELS[key] || key}：</Typography>
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", lineHeight: 1.6, flex: 1 }}>{val}</Typography>
            </Box>
          );
        })}
        {/* Raw content fallback if no structured */}
        {!Object.values(structured).some(Boolean) && record.content && (
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#333", lineHeight: 1.8, whiteSpace: "pre-wrap", py: 1 }}>
            {record.content}
          </Typography>
        )}

        {/* Diagnosis status card */}
        {loadingDetail && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}><CircularProgress size={16} /></Box>
        )}
        {!loadingDetail && diagStatus && (
          <Box sx={{ mt: 1.5, p: 1.5, borderRadius: "8px", bgcolor: "#f9f9f9", border: "0.5px solid #e5e5e5" }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mb: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>诊断</Typography>
              <StatusBadge
                label={DIAG_STATUS_LABELS[diagStatus] || diagStatus}
                colorMap={DIAG_STATUS_COLORS}
                fallbackColor={COLOR.text4}
              />
            </Box>
            {(diagStatus === "confirmed" || diagStatus === "completed") && detail?.structured?.diagnosis && (
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, mt: 0.5 }}>
                {detail.structured.diagnosis}
              </Typography>
            )}
          </Box>
        )}

        {/* Treatment plan card */}
        {!loadingDetail && treatmentPlan && (
          <Box sx={{ mt: 1, p: 1.5, borderRadius: "8px", bgcolor: "#f0faf3", border: "0.5px solid #c8e6c9" }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>治疗方案</Typography>
            {treatmentPlan.medications && treatmentPlan.medications.length > 0 && (
              <Box sx={{ mb: 0.5 }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, fontWeight: 500 }}>用药：</Typography>
                {treatmentPlan.medications.map((med, i) => (
                  <Typography key={i} sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, pl: 1 }}>
                    {med.name || med.drug_class || med}{med.dosage ? ` - ${med.dosage}` : ""}
                  </Typography>
                ))}
              </Box>
            )}
            {treatmentPlan.follow_up && (
              <Box>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, fontWeight: 500 }}>随访：</Typography>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, pl: 1 }}>{treatmentPlan.follow_up}</Typography>
              </Box>
            )}
            {treatmentPlan.lifestyle && (
              <Box sx={{ mt: 0.3 }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, fontWeight: 500 }}>生活方式建议：</Typography>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, pl: 1 }}>{treatmentPlan.lifestyle}</Typography>
              </Box>
            )}
          </Box>
        )}

        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#bbb", mt: 2, textAlign: "center" }}>
          {formatDate(record.created_at)}
        </Typography>
      </Box>
    </Box>
  );
}

function RecordsTab({ token, onLogout, onNewRecord, urlSubpage }) {
  const navigate = useNavigate();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadRecords = useCallback(() => {
    setLoading(true);
    getPatientRecords(token).then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, onLogout]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  // URL-driven record detail: /patient/records/:recordId
  if (urlSubpage && urlSubpage !== "interview") {
    const record = records.find(r => String(r.id) === urlSubpage);
    if (record) {
      return <RecordDetailView record={record} token={token} onBack={() => navigate("/patient/records")} />;
    }
    // Record not found yet (still loading) — show spinner
    if (loading) return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={20} /></Box>;
  }

  if (loading) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={20} /></Box>;
  }

  return (
    <Box sx={{ flex: 1, overflowY: "auto", position: "relative" }}>
      {/* New record row */}
      <NewItemCard title="新建病历" subtitle="开始AI预问诊" onClick={onNewRecord} />

      {/* Section label */}
      {records.length > 0 && (
        <Box sx={{ px: 2, py: 1 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>
            最近 · {records.length}份病历
          </Typography>
        </Box>
      )}

      {/* Record list */}
      {records.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <Typography color="text.secondary">暂无病历记录</Typography>
          <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: "block" }}>
            点击上方「新建病历」开始预问诊
          </Typography>
        </Box>
      ) : (
        <Box sx={{ bgcolor: "#fff" }}>
          {records.map(rec => {
            const typeLabel = RECORD_TYPE_LABEL[rec.record_type] || rec.record_type;
            const chief = rec.structured?.chief_complaint;
            const preview = chief || (rec.content || "").replace(/\n/g, " ").slice(0, 40) || "（内容为空）";
            const _DL = { pending: "诊断中", completed: "待审核", confirmed: "已确认", failed: "诊断失败" };
            const _DC = { "诊断中": COLOR.warning, "待审核": COLOR.accent, "已确认": COLOR.success, "诊断失败": COLOR.danger };
            const ds = rec.diagnosis_status;
            const dsLabel = ds ? _DL[ds] : null;
            return (
              <ListCard
                key={rec.id}
                avatar={<RecordAvatar type={rec.record_type} />}
                title={typeLabel}
                subtitle={preview}
                right={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                    {dsLabel && (
                      <StatusBadge label={dsLabel} colorMap={_DC} fallbackColor={COLOR.text4} />
                    )}
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{formatDate(rec.created_at)}</Typography>
                  </Box>
                }
                onClick={() => navigate(`/patient/records/${rec.id}`)}
              />
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// ===========================================================================
// TasksTab — 患者任务（ADR 0020）
// ===========================================================================

function TasksTab({ token }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadTasks = useCallback(() => {
    setLoading(true);
    getPatientTasks(token)
      .then(data => setTasks(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  async function handleComplete(taskId) {
    try {
      await completePatientTask(token, taskId);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: "completed" } : t));
    } catch {}
  }

  if (loading) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={20} /></Box>;
  }

  if (tasks.length === 0) {
    return (
      <Box sx={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <Typography sx={{ fontSize: ICON.display, color: "#ccc", mb: 1 }}>📋</Typography>
        <Typography color="text.disabled" sx={{ fontWeight: 500 }}>暂无任务</Typography>
        <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5 }}>
          医生安排的复查、用药提醒将显示在这里
        </Typography>
      </Box>
    );
  }

  const pending = tasks.filter(t => t.status === "pending" || t.status === "notified");
  const completed = tasks.filter(t => t.status === "completed");

  return (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {pending.length > 0 && (
        <>
          <SectionLabel>待完成 · {pending.length}</SectionLabel>
          <TaskChecklist tasks={pending} onComplete={handleComplete} />
        </>
      )}
      {completed.length > 0 && (
        <>
          <SectionLabel sx={{ mt: 1 }}>已完成 · {completed.length}</SectionLabel>
          <TaskChecklist tasks={completed} />
        </>
      )}
    </Box>
  );
}

// ===========================================================================
// InterviewPage — 全屏预问诊（独立上下文）
// ===========================================================================

function InterviewPage({ token, onBack, onLogout }) {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [collected, setCollected] = useState({});
  const [progress, setProgress] = useState({ filled: 0, total: 7 });
  const [status, setStatus] = useState("interviewing");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [showExitDialog, setShowExitDialog] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const chatEndRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await interviewStart(token);
        setSessionId(data.session_id);
        setCollected(data.collected || {});
        setProgress(data.progress);
        setStatus(data.status);
        setMessages([{ role: "assistant", content: data.reply }]);
      } catch (err) {
        if (err.status === 401) console.warn("auth expired");
        setMessages([{ role: "assistant", content: "无法启动问诊，请稍后重试。" }]);
      }
    })();
  }, [token]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  function handleToggleSuggestion(text) {
    setSelectedSuggestions(prev =>
      prev.includes(text) ? prev.filter(s => s !== text) : [...prev, text]
    );
  }

  async function handleSend(e) {
    if (e && e.preventDefault) e.preventDefault();
    const parts = [...selectedSuggestions];
    if (input.trim()) parts.push(input.trim());
    const text = parts.join("，");
    if (!text || sending || status !== "interviewing") return;
    setInput("");
    setSuggestions([]);
    setSelectedSuggestions([]);
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const data = await interviewTurn(token, sessionId, text);
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }]);
      setCollected(data.collected || {});
      setProgress(data.progress);
      setStatus(data.status);
      setSuggestions(data.suggestions || []);
      setSelectedSuggestions([]);
      if (data.status === "reviewing") setTimeout(() => setShowSummary(true), 800);
    } catch (err) {
      if (err.status === 401) { console.warn("auth expired"); return; }
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
      if (err.status === 401) { console.warn("auth expired"); return; }
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
    <Box sx={PAGE_LAYOUT}>
      <SubpageHeader title="新建病历" onBack={() => status === "confirmed" ? onBack() : setShowExitDialog(true)}
        right={
          <Chip label={`${progress.total ? Math.round((progress.filled / progress.total) * 100) : 0}%`} size="small"
            color={status === "reviewing" ? "success" : "default"}
            onClick={() => setShowSummary(true)} sx={{ cursor: "pointer" }} />
        }
      />

      {/* Progress bar */}
      <Box sx={{ px: 2, py: 0.5, bgcolor: "#fff", borderBottom: "1px solid #f0f0f0" }}>
        <LinearProgress variant="determinate"
          value={progress.total ? (progress.filled / progress.total) * 100 : 0}
          sx={{ height: 6, borderRadius: 3, bgcolor: "#e0e0e0",
            "& .MuiLinearProgress-bar": { bgcolor: "#07C160", borderRadius: 3 } }} />
        <Typography variant="caption" sx={{ color: "#999", mt: 0.3, display: "block" }}>
          {progress.total ? Math.round((progress.filled / progress.total) * 100) : 0}%
        </Typography>
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

      {/* Suggestion chips — floating above input */}
      {status === "interviewing" && !sending && suggestions.length > 0 && (
        <SuggestionChips
          items={suggestions}
          selected={selectedSuggestions}
          onToggle={handleToggleSuggestion}
          onDismiss={() => setSuggestions([])}
          disabled={sending}
        />
      )}

      {/* Input with selected chips */}
      {status === "interviewing" && (
        <Box component="form" onSubmit={handleSend}
          sx={{ display: "flex", alignItems: "flex-end", gap: 1, px: 2, py: 1, bgcolor: "#f5f5f5",
            borderTop: suggestions.length > 0 ? "none" : "1px solid #ddd", flexShrink: 0 }}>
          <Box sx={{ flex: 1, bgcolor: "#fff", borderRadius: "6px", border: "1px solid #e0e0e0",
            px: 1, py: 0.5, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5, minHeight: 36 }}>
            {selectedSuggestions.map((s, i) => (
              <Box key={i} sx={{
                display: "inline-flex", alignItems: "center", gap: 0.3,
                px: 1, py: 0.2, borderRadius: "12px", fontSize: TYPE.secondary.fontSize,
                bgcolor: "#e8f5e9", color: "#07C160", fontWeight: 500,
                flexShrink: 0,
              }}>
                {s}
                <Box component="span"
                  onClick={(e) => { e.stopPropagation(); setSelectedSuggestions(prev => prev.filter(x => x !== s)); }}
                  sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, ml: 0.2, "&:active": { opacity: 0.5 } }}>
                  ×
                </Box>
              </Box>
            ))}
            <Box component="input" value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={selectedSuggestions.length > 0 ? "" : "请输入…"}
              autoFocus
              sx={{ flex: 1, minWidth: 60, border: "none", outline: "none",
                fontSize: TYPE.body.fontSize, fontFamily: "inherit", bgcolor: "transparent", p: 0.3 }}
            />
          </Box>
          <IconButton type="submit" disabled={(!input.trim() && selectedSuggestions.length === 0) || sending}
            sx={{ color: "#07C160", flexShrink: 0 }}>
            <SendIcon />
          </IconButton>
        </Box>
      )}
      {status === "confirmed" && (
        <Box sx={{ px: 2, py: 2, bgcolor: "#f5f5f5", textAlign: "center", flexShrink: 0 }}>
          <Button variant="contained" onClick={onBack} sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>返回病历</Button>
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
          {(status === "reviewing" || progress.filled >= 2) && (
            <Button variant="contained" onClick={handleConfirm} disabled={confirming}
              sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" } }}>
              {confirming ? <CircularProgress size={16} /> : progress.filled >= progress.total ? "确认提交" : `提交 (${progress.filled}/${progress.total})`}
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
// Page root — two-tab layout
// ===========================================================================

const NAV_TABS = [
  { key: "chat", label: "主页", icon: <ChatOutlinedIcon />, title: "AI 健康助手" },
  { key: "records", label: "病历", icon: <DescriptionOutlinedIcon />, title: "病历" },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon />, title: "任务" },
  { key: "profile", label: "设置", icon: <SettingsOutlinedIcon />, title: "设置" },
];

export default function PatientPage() {
  const { tab: urlTab, subpage: urlSubpage } = useParams();
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");

  // URL-driven tab and subpage
  const tab = urlTab || "chat";
  const inInterview = urlSubpage === "interview";
  function setTab(t) { navigate(`/patient/${t}`); }
  function startInterview() { navigate("/patient/records/interview"); }
  function exitInterview() { navigate("/patient/records"); }

  function handleLogin(newToken, name, doctorId, docName) {
    localStorage.setItem(STORAGE_KEY, newToken);
    localStorage.setItem(STORAGE_NAME_KEY, name);
    if (doctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, doctorId);
    if (docName) localStorage.setItem(STORAGE_DOCTOR_NAME_KEY, docName);
    setToken(newToken);
    setPatientName(name);
    setDoctorName(docName || "");
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_NAME_KEY);
    localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
    setToken("");
    setPatientName("");
    setDoctorName("");
  }

  if (!token) {
    window.location.href = "/login";
    return null;
  }

  // Full-screen interview (hides everything)
  if (inInterview) {
    return (
      <InterviewPage token={token}
        onBack={exitInterview}
        onLogout={handleLogout} />
    );
  }

  return (
    <Box sx={PAGE_LAYOUT}>
      {/* Hide page header when a subpage has its own header */}
      {!urlSubpage && <SubpageHeader title={NAV_TABS.find(t => t.key === tab)?.title || "AI 健康助手"} />}

      {/* Content — flex:1 scrollable area with bottom nav padding */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: "56px" }}>
        {tab === "chat" && <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
          onNewInterview={() => { startInterview(); }}
          onViewRecords={() => setTab("records")} />}
        {tab === "records" && (
          <RecordsTab token={token} onLogout={handleLogout} onNewRecord={() => startInterview()} urlSubpage={urlSubpage} />
        )}
        {tab === "tasks" && <TasksTab token={token} />}
        {tab === "profile" && (
          <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#ededed" }}>
            <Box sx={{ bgcolor: "#fff", px: 2, py: 2, mb: 1, display: "flex", alignItems: "center", gap: 1.5 }}>
              <Box sx={{ width: 44, height: 44, borderRadius: "50%", bgcolor: "#07C160",
                display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Typography sx={{ color: "#fff", fontSize: ICON.md, fontWeight: 600 }}>{(patientName || "?")[0]}</Typography>
              </Box>
              <Box>
                <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>{patientName || "患者"}</Typography>
                {doctorName && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>主治医生：{doctorName}</Typography>}
              </Box>
            </Box>
            <Box onClick={handleLogout}
              sx={{ bgcolor: "#fff", py: 1.5, textAlign: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
              <Typography sx={{ fontSize: TYPE.action.fontSize, color: "#FA5151" }}>退出登录</Typography>
            </Box>
          </Box>
        )}
      </Box>

      {/* Bottom nav — fixed at bottom like DoctorPage */}
      <BottomNavigation value={tab} onChange={(_, v) => setTab(v)} showLabels
        sx={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 56,
          borderTop: "1px solid #ddd", bgcolor: "#f5f5f5",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}>
        {NAV_TABS.map(t => (
          <BottomNavigationAction key={t.key} value={t.key} label={t.label} icon={t.icon}
            sx={{ "&.Mui-selected": { color: "#07C160" } }} />
        ))}
      </BottomNavigation>
    </Box>
  );
}
