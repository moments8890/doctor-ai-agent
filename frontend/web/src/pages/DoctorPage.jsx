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
  Badge, Box,
  Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Stack, TextField, Typography,
} from "@mui/material";
import BottomNavigationMui from "@mui/material/BottomNavigation";
import BottomNavigationActionMui from "@mui/material/BottomNavigationAction";
import LogoutIcon from "@mui/icons-material/Logout";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import {
  getTasks, getPendingRecord, getReviewQueue,
  getDoctorProfile, updateDoctorProfile, getWorkingContext,
} from "../api";
import { useDoctorStore } from "../store/doctorStore";
import { NAV, DESKTOP_NAV } from "./doctor/constants";
import BriefingSection from "./doctor/BriefingSection";
import ChatSection from "./doctor/ChatSection";
import PatientsSection from "./doctor/PatientsSection";
import TasksSection from "./doctor/TasksSection";
import SettingsSection from "./doctor/SettingsSection";
import WorkingContextHeader from "./doctor/WorkingContextHeader";
import ErrorBoundary from "../components/ErrorBoundary";
import { TYPE, ICON } from "../theme";

function DesktopSidebar({ activeSection, doctorName, doctorId, navBadge, onNav, onLogout }) {
  return (
    <Box sx={{ width: 220, flexShrink: 0, borderRight: "0.5px solid #d9d9d9", backgroundColor: "#f7f7f7", display: "flex", flexDirection: "column", py: 2, px: 0 }}>
      <Box sx={{ mb: 2, px: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "#07C160" }}>医生工作台</Typography>
        <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
      </Box>
      <Box sx={{ flex: 1 }}>
        {DESKTOP_NAV.map((item) => (
          <Box key={item.key} onClick={() => onNav(item.key)}
            sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer",
              bgcolor: activeSection === item.key ? "#07C160" : "transparent",
              color: activeSection === item.key ? "#fff" : "#999999",
              "&:hover": { bgcolor: activeSection === item.key ? "#07C160" : "#f0f0f0" },
              "&:active": { opacity: 0.8 } }}>
            <Box sx={{ "& svg": { fontSize: ICON.lg, color: activeSection === item.key ? "#fff" : "#999999" } }}>
              {navBadge[item.key] > 0 ? <Badge badgeContent={navBadge[item.key]} color="error">{item.icon}</Badge> : item.icon}
            </Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: activeSection === item.key ? 600 : 400, color: "inherit" }}>{item.label}</Typography>
          </Box>
        ))}
      </Box>
      <Box onClick={onLogout} sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer", color: "#999999", "&:hover": { bgcolor: "#f0f0f0" }, "&:active": { opacity: 0.8 } }}>
        <LogoutIcon fontSize="small" sx={{ color: "#999999" }} />
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999999" }}>退出登录</Typography>
      </Box>
    </Box>
  );
}

function MobileBottomNav({ activeSection, pendingTaskCount, pendingRecord, onNav }) {
  // Chat is a subpage of home on mobile — highlight 首页 when in chat
  const navValue = activeSection === "chat" ? "home" : activeSection;
  return (
    <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10, borderTop: "0.5px solid #d9d9d9", bgcolor: "#f7f7f7" }}>
      <BottomNavigationMui value={navValue} onChange={(_, val) => onNav(val)}
        sx={{ height: 64, bgcolor: "#f7f7f7", paddingBottom: "env(safe-area-inset-bottom)", "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: "#999999" }, "& .Mui-selected": { color: "#07C160" }, "& .Mui-selected .MuiBottomNavigationAction-label": { color: "#07C160", fontWeight: 600 } }}>
        {NAV.map((item) => (
          <BottomNavigationActionMui key={item.key} label={item.label} value={item.key} showLabel
            icon={item.key === "tasks" && pendingTaskCount > 0 ? <Badge badgeContent={pendingTaskCount} color="error">{item.icon}</Badge>
              : item.key === "home" && pendingRecord ? <Badge variant="dot" color="warning">{item.icon}</Badge>
              : item.icon}
            sx={{ minWidth: 0, "& .MuiBottomNavigationAction-label": { fontSize: TYPE.micro.fontSize } }} />
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

function SectionContent({ activeSection, doctorId, isMobile, navigate, urlSubpage, urlSubId, chatInsertText, setChatInsertText, chatAutoSendText, setChatAutoSendText, chatAutoSendConsumedRef, patientRefreshKey, setPatientRefreshKey, handleLogout, onContextCleared, triggerInterview, setTriggerInterview }) {
  return (
    <Box sx={{ flex: 1, overflow: "hidden" }}>
      {activeSection === "home" && (
        <ErrorBoundary label="首页">
          <BriefingSection doctorId={doctorId} onNavigateToChat={() => navigate("/doctor/chat")} />
        </ErrorBoundary>
      )}
      {activeSection === "chat" && (
        <ErrorBoundary label="聊天">
          <ChatSection doctorId={doctorId} onMessageCountChange={() => {}}
            externalInput={chatInsertText} onExternalInputConsumed={() => setChatInsertText("")}
            onPatientCreated={() => setPatientRefreshKey((k) => k + 1)}
            autoSendText={chatAutoSendText !== chatAutoSendConsumedRef.current ? chatAutoSendText : ""}
            onAutoSendConsumed={() => { chatAutoSendConsumedRef.current = chatAutoSendText; setChatAutoSendText(""); }}
            onContextCleared={onContextCleared}
            onStartPatientInterview={() => { setTriggerInterview(true); navigate("/doctor/patients"); }}
            onBack={isMobile ? () => navigate("/doctor") : undefined} />
        </ErrorBoundary>
      )}
      {activeSection === "patients" && (
        <ErrorBoundary label="患者">
          <PatientsSection doctorId={doctorId} onNavigateToChat={() => navigate("/doctor/chat")}
            onInsertChatText={(text) => { setChatInsertText(text); navigate("/doctor/chat"); }}
            onAutoSendToChat={(text) => { chatAutoSendConsumedRef.current = ""; setChatAutoSendText(text); navigate("/doctor/chat"); }}
            refreshKey={patientRefreshKey}
            triggerInterview={triggerInterview}
            onTriggerInterviewConsumed={() => setTriggerInterview(false)} />
        </ErrorBoundary>
      )}
      {activeSection === "tasks" && <ErrorBoundary label="任务"><TasksSection doctorId={doctorId} urlSubpage={urlSubpage} urlSubId={urlSubId} /></ErrorBoundary>}
      {activeSection === "settings" && <ErrorBoundary label="设置"><SettingsSection doctorId={doctorId} onLogout={handleLogout} urlSubpage={urlSubpage} urlSubId={urlSubId} /></ErrorBoundary>}
    </Box>
  );
}

function useDoctorPageState({ doctorId, accessToken, setAuth }) {
  const [pendingTaskCount, setPendingTaskCount] = useState(0);
  const [pendingReviewCount, setPendingReviewCount] = useState(0);
  const [pendingRecord, setPendingRecord] = useState(null);
  const [workingContext, setWorkingContext] = useState(null);
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
    getReviewQueue(doctorId, "pending_review", 200)
      .then((d) => setPendingReviewCount((d.items || []).length))
      .catch(() => {});
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
  return { pendingTaskCount, pendingReviewCount, pendingRecord, setPendingRecord, workingContext, setWorkingContext, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit };
}

export default function DoctorPage() {
  const { section, patientId, subpage: urlSubpage, subId: urlSubId } = useParams();
  const navigate = useNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [chatInsertText, setChatInsertText] = useState("");
  const [chatAutoSendText, setChatAutoSendText] = useState("");
  const chatAutoSendConsumedRef = useRef("");
  const [patientRefreshKey, setPatientRefreshKey] = useState(0);
  const [triggerInterview, setTriggerInterview] = useState(false);

  const { pendingTaskCount, pendingReviewCount, pendingRecord, setPendingRecord, workingContext, setWorkingContext, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit } = useDoctorPageState({ doctorId, accessToken, setAuth });

  const activeSection = patientId ? "patients" : (section || "home");

  function handleContextCleared() {
    setPendingRecord(null);
    setWorkingContext(null);
  }
  function handleNav(key) { navigate(key === "home" ? "/doctor" : `/doctor/${key}`); }
  function handleLogout() {
    clearAuth();
    if (window.__wxjs_environment === "miniprogram") wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    navigate("/login");
  }

  return (
    <Box sx={{ display: "flex", height: "100vh", bgcolor: "#f7f7f7" }}>
      {!isMobile && <DesktopSidebar activeSection={activeSection} doctorName={doctorName} doctorId={doctorId} navBadge={{ tasks: pendingTaskCount + pendingReviewCount, home: pendingRecord ? 1 : 0 }} onNav={handleNav} onLogout={handleLogout} />}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: isMobile ? "56px" : 0 }}>
        <WorkingContextHeader context={workingContext} isMobile={isMobile} />
        <SectionContent activeSection={activeSection} doctorId={doctorId} isMobile={isMobile} navigate={navigate} urlSubpage={urlSubpage} urlSubId={urlSubId} chatInsertText={chatInsertText} setChatInsertText={setChatInsertText} chatAutoSendText={chatAutoSendText} setChatAutoSendText={setChatAutoSendText} chatAutoSendConsumedRef={chatAutoSendConsumedRef} patientRefreshKey={patientRefreshKey} setPatientRefreshKey={setPatientRefreshKey} handleLogout={handleLogout} onContextCleared={handleContextCleared} triggerInterview={triggerInterview} setTriggerInterview={setTriggerInterview} />
      </Box>
      {isMobile && <MobileBottomNav activeSection={activeSection} pendingTaskCount={pendingTaskCount + pendingReviewCount} pendingRecord={pendingRecord} onNav={handleNav} />}
      <OnboardingDialog open={showOnboarding} name={onboardName} saving={onboardSaving} onChange={setOnboardName} onSubmit={handleOnboardSubmit} />
    </Box>
  );
}
