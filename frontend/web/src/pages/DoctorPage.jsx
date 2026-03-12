/**
 * 医生工作台主页：composer-first workbench with one visible working context.
 *
 * Default route is the AI chat composer. The working-context header shows
 * current patient, pending draft, and next-step guidance at a glance.
 * Admin/management surfaces are reachable but secondary.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert, Badge, Box,
  Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Snackbar, Stack, TextField, Typography,
} from "@mui/material";
import BottomNavigationMui from "@mui/material/BottomNavigation";
import BottomNavigationActionMui from "@mui/material/BottomNavigationAction";
import LogoutIcon from "@mui/icons-material/Logout";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import {
  getTasks, getPendingRecord, confirmPendingRecord, abandonPendingRecord,
  getDoctorProfile, updateDoctorProfile, getWorkingContext,
} from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { NAV } from "./doctor/constants";
import ChatSection from "./doctor/ChatSection";
import PatientsSection from "./doctor/PatientsSection";
import TasksSection from "./doctor/TasksSection";
import SettingsSection from "./doctor/SettingsSection";
import WorkingContextHeader from "./doctor/WorkingContextHeader";
import ErrorBoundary from "../components/ErrorBoundary";

function PendingRecordBanner({ isMobile, pendingRecord, onConfirm, onAbandon }) {
  if (!pendingRecord) return null;
  const preview = pendingRecord.content_preview || "";
  const expiry = pendingRecord.expires_at
    ? (() => { const mins = Math.max(0, Math.round((new Date(pendingRecord.expires_at) - Date.now()) / 60000)); return { mins, urgent: mins <= 2 }; })()
    : null;

  if (isMobile) {
    return (
      <Box sx={{ px: 2, py: 1.2, backgroundColor: "#fff7e6", borderBottom: "1px solid #ffd666", display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontSize: 13, color: "#d46b08", flex: 1 }}>
          待确认：{pendingRecord.patient_name || "未关联"} — {preview.slice(0, 20)}{preview.length > 20 ? "…" : ""}
          {expiry && <span style={{ marginLeft: 4, fontWeight: 700, color: expiry.urgent ? "#cf1322" : "#d46b08" }}>({expiry.mins}分钟)</span>}
        </Typography>
        <Box onClick={onConfirm} sx={{ px: 1.5, py: 0.4, borderRadius: "12px", bgcolor: "#07C160", cursor: "pointer", "&:active": { opacity: 0.8 } }}>
          <Typography sx={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>确认</Typography>
        </Box>
        <Box onClick={onAbandon} sx={{ px: 1.5, py: 0.4, borderRadius: "12px", bgcolor: "#f2f2f2", cursor: "pointer", "&:active": { opacity: 0.8 } }}>
          <Typography sx={{ color: "#555", fontSize: 12 }}>撤销</Typography>
        </Box>
      </Box>
    );
  }
  return (
    <Box sx={{ mx: 2, mt: 1, px: 2, py: 1, backgroundColor: "#fff7e6", border: "1px solid #ffd666", borderRadius: 1.5, display: "flex", alignItems: "center", gap: 1.5 }}>
      <Typography sx={{ fontSize: 13, color: "#d46b08", flex: 1 }}>
        <strong>待确认病历</strong>：{pendingRecord.patient_name || "未关联"} — {preview}
        {expiry && <span style={{ marginLeft: 8, fontWeight: 700, color: expiry.urgent ? "#cf1322" : "#d46b08" }}>{expiry.mins <= 0 ? "即将过期" : `${expiry.mins}分钟后过期`}</span>}
      </Typography>
      <Box onClick={onConfirm} sx={{ px: 2, py: 0.6, borderRadius: "12px", bgcolor: "#07C160", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
        <Typography sx={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>确认保存</Typography>
      </Box>
      <Box onClick={onAbandon} sx={{ px: 2, py: 0.6, borderRadius: "12px", bgcolor: "#f2f2f2", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
        <Typography sx={{ color: "#555", fontSize: 13 }}>撤销</Typography>
      </Box>
    </Box>
  );
}

function DesktopSidebar({ activeSection, doctorName, doctorId, navBadge, onNav, onLogout }) {
  return (
    <Box sx={{ width: 220, flexShrink: 0, borderRight: "1px solid #e5e5e5", backgroundColor: "#f7f7f7", display: "flex", flexDirection: "column", py: 2, px: 0 }}>
      <Box sx={{ mb: 2, px: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "#07C160" }}>医生工作台</Typography>
        <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
      </Box>
      <Box sx={{ flex: 1 }}>
        {NAV.map((item) => (
          <Box key={item.key} onClick={() => onNav(item.key)}
            sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer",
              bgcolor: activeSection === item.key ? "#07C160" : "transparent",
              color: activeSection === item.key ? "#fff" : "#555",
              "&:hover": { bgcolor: activeSection === item.key ? "#07C160" : "rgba(0,0,0,0.05)" },
              "&:active": { opacity: 0.8 } }}>
            <Box sx={{ "& svg": { fontSize: 20, color: activeSection === item.key ? "#fff" : "#555" } }}>
              {navBadge[item.key] > 0 ? <Badge badgeContent={navBadge[item.key]} color="error">{item.icon}</Badge> : item.icon}
            </Box>
            <Typography sx={{ fontSize: 14, fontWeight: activeSection === item.key ? 600 : 400, color: "inherit" }}>{item.label}</Typography>
          </Box>
        ))}
      </Box>
      <Box onClick={onLogout} sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer", color: "#888", "&:hover": { bgcolor: "rgba(0,0,0,0.05)" }, "&:active": { opacity: 0.8 } }}>
        <LogoutIcon fontSize="small" sx={{ color: "#888" }} />
        <Typography sx={{ fontSize: 14, color: "#888" }}>退出登录</Typography>
      </Box>
    </Box>
  );
}

function MobileBottomNav({ activeSection, pendingTaskCount, pendingRecord, onNav }) {
  return (
    <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10, borderTop: "1px solid #e2e8f0" }}>
      <BottomNavigationMui value={activeSection} onChange={(_, val) => onNav(val)}
        sx={{ height: 64, "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: "#888" }, "& .Mui-selected": { color: "#07C160" }, "& .Mui-selected .MuiBottomNavigationAction-label": { color: "#07C160", fontWeight: 600 } }}>
        {NAV.map((item) => (
          <BottomNavigationActionMui key={item.key} label={item.label} value={item.key} showLabel
            icon={item.key === "tasks" && pendingTaskCount > 0 ? <Badge badgeContent={pendingTaskCount} color="error">{item.icon}</Badge>
              : item.key === "chat" && pendingRecord ? <Badge variant="dot" color="warning">{item.icon}</Badge>
              : item.icon}
            sx={{ minWidth: 0, "& .MuiBottomNavigationAction-label": { fontSize: 11 } }} />
        ))}
      </BottomNavigationMui>
    </Box>
  );
}

function OnboardingDialog({ open, name, saving, onChange, onSubmit }) {
  return (
    <Dialog open={open} maxWidth="xs" fullWidth>
      <DialogTitle>欢迎，请完成初始设置</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="您的姓名" value={name} onChange={(e) => onChange(e.target.value)} fullWidth autoFocus required />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="contained" disabled={!name.trim() || saving} onClick={onSubmit}>
          {saving ? "保存中..." : "完成设置"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function SectionContent({ activeSection, doctorId, navigate, chatInsertText, setChatInsertText, chatAutoSendText, setChatAutoSendText, chatAutoSendConsumedRef, patientRefreshKey, setPatientRefreshKey, handleLogout }) {
  return (
    <Box sx={{ flex: 1, overflow: "hidden" }}>
      {activeSection === "chat" && (
        <ErrorBoundary label="聊天">
          <ChatSection doctorId={doctorId} onMessageCountChange={() => {}}
            externalInput={chatInsertText} onExternalInputConsumed={() => setChatInsertText("")}
            onPatientCreated={() => setPatientRefreshKey((k) => k + 1)}
            autoSendText={chatAutoSendText !== chatAutoSendConsumedRef.current ? chatAutoSendText : ""}
            onAutoSendConsumed={() => { chatAutoSendConsumedRef.current = chatAutoSendText; setChatAutoSendText(""); }} />
        </ErrorBoundary>
      )}
      {activeSection === "patients" && (
        <ErrorBoundary label="患者">
          <PatientsSection doctorId={doctorId} onNavigateToChat={() => navigate("/doctor/chat")}
            onInsertChatText={(text) => { setChatInsertText(text); navigate("/doctor/chat"); }}
            onAutoSendToChat={(text) => { chatAutoSendConsumedRef.current = ""; setChatAutoSendText(text); navigate("/doctor/chat"); }}
            refreshKey={patientRefreshKey} />
        </ErrorBoundary>
      )}
      {activeSection === "tasks" && <ErrorBoundary label="任务"><TasksSection doctorId={doctorId} /></ErrorBoundary>}
      {activeSection === "settings" && <ErrorBoundary label="设置"><SettingsSection doctorId={doctorId} onLogout={handleLogout} /></ErrorBoundary>}
    </Box>
  );
}

function useDoctorPageState({ doctorId, accessToken, setAuth }) {
  const [pendingTaskCount, setPendingTaskCount] = useState(0);
  const [pendingRecord, setPendingRecord] = useState(null);
  const [workingContext, setWorkingContext] = useState(null);
  const [confirmSnackbar, setConfirmSnackbar] = useState(false);
  const [pendingError, setPendingError] = useState("");
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardName, setOnboardName] = useState("");
  const [onboardSaving, setOnboardSaving] = useState(false);

  useEffect(() => {
    if (!doctorId) return;
    getDoctorProfile(doctorId).then((p) => { if (!p.onboarded) { setOnboardName(p.name || ""); setShowOnboarding(true); } }).catch(() => {});
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!doctorId) return;
    getTasks(doctorId, "pending").then((d) => setPendingTaskCount((Array.isArray(d) ? d : (d.items || [])).length)).catch(() => {});
  }, [doctorId]);
  useEffect(() => {
    if (!doctorId) return;
    const fetch = () => getPendingRecord(doctorId).then((d) => setPendingRecord(d || null)).catch(() => {});
    fetch(); const id = setInterval(fetch, 30000); return () => clearInterval(id);
  }, [doctorId]);

  // Working context: poll every 15 seconds for header state
  useEffect(() => {
    if (!doctorId) return;
    const fetch = () => getWorkingContext(doctorId).then((d) => setWorkingContext(d || null)).catch(() => {});
    fetch();
    const id = setInterval(fetch, 15000);
    return () => clearInterval(id);
  }, [doctorId]);

  async function handleOnboardSubmit() {
    if (!onboardName.trim() || onboardSaving) return;
    setOnboardSaving(true);
    try { await updateDoctorProfile(doctorId, { name: onboardName.trim() }); setAuth(doctorId, onboardName.trim(), accessToken); setShowOnboarding(false); }
    catch {} finally { setOnboardSaving(false); }
  }
  async function handleConfirmPending() {
    try { await confirmPendingRecord(doctorId); setPendingRecord(null); setConfirmSnackbar(true); } catch {}
  }
  async function handleAbandonPending() {
    try { await abandonPendingRecord(doctorId); setPendingRecord(null); setPendingError(""); }
    catch (e) { setPendingError(e.message || "操作失败，请重试"); }
  }

  return { pendingTaskCount, pendingRecord, workingContext, confirmSnackbar, setConfirmSnackbar, pendingError, setPendingError, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit, handleConfirmPending, handleAbandonPending };
}

export default function DoctorPage() {
  const { section, patientId } = useParams();
  const navigate = useNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [chatInsertText, setChatInsertText] = useState("");
  const [chatAutoSendText, setChatAutoSendText] = useState("");
  const chatAutoSendConsumedRef = useRef("");
  const [patientRefreshKey, setPatientRefreshKey] = useState(0);

  const { pendingTaskCount, pendingRecord, workingContext, confirmSnackbar, setConfirmSnackbar, pendingError, setPendingError, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit, handleConfirmPending, handleAbandonPending } = useDoctorPageState({ doctorId, accessToken, setAuth });

  // Default to chat (composer-first). "home" section removed from primary nav.
  const activeSection = patientId ? "patients" : (section || "chat");

  function handleNav(key) { navigate(key === "chat" ? "/doctor/chat" : `/doctor/${key}`); }
  function handleLogout() {
    clearAuth();
    if (window.__wxjs_environment === "miniprogram") wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    navigate("/login");
  }

  return (
    <Box sx={{ display: "flex", height: "100vh", bgcolor: "#f7f7f7" }}>
      {!isMobile && <DesktopSidebar activeSection={activeSection} doctorName={doctorName} doctorId={doctorId} navBadge={{ tasks: pendingTaskCount, chat: pendingRecord ? 1 : 0 }} onNav={handleNav} onLogout={handleLogout} />}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: isMobile ? "56px" : 0 }}>
        <WorkingContextHeader context={workingContext} isMobile={isMobile} />
        {pendingError && <Alert severity="error" sx={{ mx: 2, mt: 1.5, borderRadius: 1.5 }} onClose={() => setPendingError("")}>{pendingError}</Alert>}
        <PendingRecordBanner isMobile={isMobile} pendingRecord={pendingRecord} onConfirm={handleConfirmPending} onAbandon={handleAbandonPending} />
        <SectionContent activeSection={activeSection} doctorId={doctorId} navigate={navigate} chatInsertText={chatInsertText} setChatInsertText={setChatInsertText} chatAutoSendText={chatAutoSendText} setChatAutoSendText={setChatAutoSendText} chatAutoSendConsumedRef={chatAutoSendConsumedRef} patientRefreshKey={patientRefreshKey} setPatientRefreshKey={setPatientRefreshKey} handleLogout={handleLogout} />
      </Box>
      {isMobile && <MobileBottomNav activeSection={activeSection} pendingTaskCount={pendingTaskCount} pendingRecord={pendingRecord} onNav={handleNav} />}
      <Snackbar open={confirmSnackbar} autoHideDuration={3000} onClose={() => setConfirmSnackbar(false)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert onClose={() => setConfirmSnackbar(false)} severity="success" sx={{ width: "100%" }}>病历已保存</Alert>
      </Snackbar>
      <OnboardingDialog open={showOnboarding} name={onboardName} saving={onboardSaving} onChange={setOnboardName} onSubmit={handleOnboardSubmit} />
    </Box>
  );
}
