/**
 * @route /doctor/*
 *
 * 鲸鱼随行主页：composer-first workbench with one visible working context.
 *
 * Default route is the AI chat composer.
 * Admin/management surfaces are reachable but secondary.
 */
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge, Box, Stack, TextField, Typography,
} from "@mui/material";
import BottomNavigationMui from "@mui/material/BottomNavigation";
import BottomNavigationActionMui from "@mui/material/BottomNavigationAction";
import LogoutIcon from "@mui/icons-material/Logout";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useDoctorStore } from "../../store/doctorStore";
import { NAV, DESKTOP_NAV } from "./constants";
import MyAIPage from "./MyAIPage";
import ChatPage from "./ChatPage";
import PatientsPage from "./PatientsPage";
import SettingsPage from "./SettingsPage";
import ReviewPage from "./ReviewPage";
import ReviewQueuePage from "./ReviewQueuePage";
import TaskPage from "./TaskPage";
import ErrorBoundary from "../../components/ErrorBoundary";
import SheetDialog from "../../components/SheetDialog";
import AppButton from "../../components/AppButton";
import { TYPE, ICON } from "../../theme";

function DesktopSidebar({ activeSection, doctorName, doctorId, navBadge, onNav, onLogout }) {
  return (
    <Box sx={{ width: 220, flexShrink: 0, borderRight: "0.5px solid #d9d9d9", backgroundColor: "#f7f7f7", display: "flex", flexDirection: "column", py: 2, px: 0 }}>
      <Box sx={{ mb: 2, px: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "#07C160" }}>鲸鱼随行</Typography>
        <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
      </Box>
      <Box component="nav" aria-label="主导航" sx={{ flex: 1 }}>
        {DESKTOP_NAV.map((item) => (
          <Box key={item.key} component="button" type="button" onClick={() => onNav(item.key)}
            aria-current={activeSection === item.key ? "page" : undefined}
            sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer", width: "100%", border: "none", textAlign: "left",
              bgcolor: activeSection === item.key ? "#07C160" : "transparent",
              color: activeSection === item.key ? "#fff" : "#999999",
              "&:hover": { bgcolor: activeSection === item.key ? "#07C160" : "#f0f0f0" },
              "&:focus-visible": { outline: "2px solid #07C160", outlineOffset: -2 },
              "&:active": { opacity: 0.8 } }}>
            <Box sx={{ "& svg": { fontSize: ICON.lg, color: activeSection === item.key ? "#fff" : "#999999" } }}>
              {item.badgeKey && navBadge[item.badgeKey] > 0 ? <Badge badgeContent={navBadge[item.badgeKey]} color="error">{item.icon}</Badge> : item.icon}
            </Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: activeSection === item.key ? 600 : 400, color: "inherit" }}>{item.label}</Typography>
          </Box>
        ))}
      </Box>
      <Box component="button" type="button" onClick={onLogout} sx={{ display: "flex", alignItems: "center", gap: 1.2, px: 2, py: 1.2, cursor: "pointer", width: "100%", border: "none", textAlign: "left", bgcolor: "transparent", color: "#999999", "&:hover": { bgcolor: "#f0f0f0" }, "&:focus-visible": { outline: "2px solid #07C160", outlineOffset: -2 }, "&:active": { opacity: 0.8 } }}>
        <LogoutIcon fontSize="small" sx={{ color: "#999999" }} />
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#999999" }}>退出登录</Typography>
      </Box>
    </Box>
  );
}

function MobileBottomNav({ activeSection, navBadge, onNav }) {
  // Chat is a subpage of my-ai on mobile — highlight 我的AI when in chat
  const navValue = activeSection === "chat" ? "my-ai" : activeSection;
  return (
    <Box sx={{ flexShrink: 0, borderTop: "0.5px solid #d9d9d9", bgcolor: "#f7f7f7" }}>
      <BottomNavigationMui value={navValue} onChange={(_, val) => onNav(val)}
        sx={{ height: 64, bgcolor: "#f7f7f7", paddingBottom: "env(safe-area-inset-bottom)", "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: "#999999" }, "& .Mui-selected": { color: "#07C160" }, "& .Mui-selected .MuiBottomNavigationAction-label": { color: "#07C160", fontWeight: 600 } }}>
        {NAV.map((item) => {
          const badgeCount = item.badgeKey ? (navBadge[item.badgeKey] || 0) : 0;
          return (
            <BottomNavigationActionMui key={item.key} label={item.label} value={item.key} showLabel
              icon={badgeCount > 0 ? <Badge badgeContent={badgeCount} color="error">{item.icon}</Badge> : item.icon}
              sx={{ minWidth: 0, "& .MuiBottomNavigationAction-label": { fontSize: TYPE.micro.fontSize } }} />
          );
        })}
      </BottomNavigationMui>
    </Box>
  );
}

function OnboardingDialog({ open, name, saving, onChange, onSubmit, onClose }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="欢迎，请完成初始设置"
      desktopMaxWidth={360}
      footer={
        <Box sx={{ display: "grid", gap: 0.5, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>
            取消
          </AppButton>
          <AppButton variant="primary" size="md" fullWidth disabled={!name.trim() || saving} loading={saving} loadingLabel="保存中..." onClick={onSubmit}>
            完成设置
          </AppButton>
        </Box>
      }
    >
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="您的姓名" value={name} onChange={(e) => onChange(e.target.value)} fullWidth autoFocus required />
        </Stack>
    </SheetDialog>
  );
}

function SectionContent({ activeSection, doctorId, isMobile, navigate, urlSubpage, urlSubId, chatInsertText, setChatInsertText, chatAutoSendText, setChatAutoSendText, chatAutoSendConsumedRef, patientRefreshKey, setPatientRefreshKey, handleLogout, onContextCleared, triggerInterview, setTriggerInterview, chatInterviewSessionId, setChatInterviewSessionId, chatInterviewPrePopulated, setChatInterviewPrePopulated }) {
  return (
    <Box sx={{ flex: 1, overflow: "hidden" }}>
      {activeSection === "my-ai" && (
        <ErrorBoundary label="我的AI">
          <MyAIPage doctorId={doctorId} />
        </ErrorBoundary>
      )}
      {activeSection === "chat" && (
        <ErrorBoundary label="聊天">
          <ChatPage doctorId={doctorId} onMessageCountChange={() => {}}
            externalInput={chatInsertText} onExternalInputConsumed={() => setChatInsertText("")}
            onPatientCreated={() => setPatientRefreshKey((k) => k + 1)}
            autoSendText={chatAutoSendText !== chatAutoSendConsumedRef.current ? chatAutoSendText : ""}
            onAutoSendConsumed={() => { chatAutoSendConsumedRef.current = chatAutoSendText; setChatAutoSendText(""); }}
            onContextCleared={onContextCleared}
            onStartPatientInterview={(sessionId, prePopulated) => { setChatInterviewSessionId(sessionId || null); setChatInterviewPrePopulated(prePopulated || null); setTriggerInterview(true); navigate("/doctor/patients"); }}
            onBack={isMobile ? () => navigate("/doctor") : undefined} />
        </ErrorBoundary>
      )}
      {activeSection === "patients" && (
        <ErrorBoundary label="患者">
          <PatientsPage doctorId={doctorId} onNavigateToChat={() => navigate("/doctor/chat")}
            onInsertChatText={(text) => { setChatInsertText(text); navigate("/doctor/chat"); }}
            onAutoSendToChat={(text) => { chatAutoSendConsumedRef.current = ""; setChatAutoSendText(text); navigate("/doctor/chat"); }}
            refreshKey={patientRefreshKey}
            triggerInterview={triggerInterview}
            onTriggerInterviewConsumed={() => setTriggerInterview(false)}
            chatInterviewSessionId={chatInterviewSessionId}
            onChatInterviewSessionConsumed={() => { setChatInterviewSessionId(null); setChatInterviewPrePopulated(null); }}
            chatInterviewPrePopulated={chatInterviewPrePopulated} />
        </ErrorBoundary>
      )}
      {activeSection === "review" && <ErrorBoundary label="审核"><ReviewQueuePage doctorId={doctorId} /></ErrorBoundary>}
      {activeSection === "tasks" && <ErrorBoundary label="任务"><TaskPage doctorId={doctorId} /></ErrorBoundary>}
      {activeSection === "settings" && <ErrorBoundary label="设置"><SettingsPage doctorId={doctorId} onLogout={handleLogout} urlSubpage={urlSubpage} urlSubId={urlSubId} /></ErrorBoundary>}
    </Box>
  );
}

function useDoctorPageState({ doctorId, accessToken, setAuth }) {
  const { getTasks, getDoctorProfile, updateDoctorProfile, fetchDraftSummary: fetchDraftSummaryApi } = useApi();
  const [pendingTaskCount, setPendingTaskCount] = useState(0);
  const [reviewCount, setReviewCount] = useState(0);
  const [followupCount, setFollowupCount] = useState(0);
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

  // Fetch review + followup badge counts
  useEffect(() => {
    if (!doctorId) return;
    // Try fetching draft summary for badge counts; fall back to task count
    if (typeof fetchDraftSummaryApi === "function") {
      fetchDraftSummaryApi(doctorId)
        .then((d) => {
          // review badge = pending AI diagnosis suggestions (review queue)
          setReviewCount(d?.review_pending_count ?? 0);
          // followup badge = pending draft replies needing doctor attention
          setFollowupCount(d?.pending ?? 0);
        })
        .catch(() => {
          // Fall back: use pending task count for review badge
          setReviewCount(pendingTaskCount);
        });
    } else {
      setReviewCount(pendingTaskCount);
    }
  }, [doctorId, pendingTaskCount]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleOnboardSubmit() {
    if (!onboardName.trim() || onboardSaving) return;
    setOnboardSaving(true);
    try { await updateDoctorProfile(doctorId, { name: onboardName.trim() }); setAuth(doctorId, onboardName.trim(), accessToken); setShowOnboarding(false); }
    catch {} finally { setOnboardSaving(false); }
  }
  return { pendingTaskCount, reviewCount, followupCount, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit };
}

export default function DoctorPage() {
  const { section, patientId, recordId, subpage: urlSubpage, subId: urlSubId } = useParams();
  const navigate = useAppNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [chatInsertText, setChatInsertText] = useState("");
  const [chatAutoSendText, setChatAutoSendText] = useState("");
  const chatAutoSendConsumedRef = useRef("");
  const [patientRefreshKey, setPatientRefreshKey] = useState(0);
  const [triggerInterview, setTriggerInterview] = useState(false);
  const [chatInterviewSessionId, setChatInterviewSessionId] = useState(null);
  const [chatInterviewPrePopulated, setChatInterviewPrePopulated] = useState(null);

  const { pendingTaskCount, reviewCount, followupCount, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit } = useDoctorPageState({ doctorId, accessToken, setAuth });

  const navBadge = { tasks: followupCount, review: reviewCount };

  const isReviewPage = !!recordId;
  const activeSection = patientId ? "patients" : (section || "my-ai");

  // Main tabs show bottom nav; subpages hide it and show ‹ back in top bar.
  // WeChat pattern: bottom nav only on root tab views.
  const MAIN_TABS = new Set(["my-ai", "patients", "review", "tasks"]);
  const isSubpage = isReviewPage || !MAIN_TABS.has(activeSection) || !!patientId;

  function handleNav(key) { navigate(key === "my-ai" ? "/doctor" : `/doctor/${key}`); }
  function handleLogout() {
    clearAuth();
    if (window.__wxjs_environment === "miniprogram") wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    navigate("/login");
  }

  return (
    <Box sx={{ display: "flex", flexDirection: isMobile ? "column" : "row", height: "100%", position: "relative", bgcolor: "#f7f7f7" }}>
      {!isMobile && <DesktopSidebar activeSection={activeSection} doctorName={doctorName} doctorId={doctorId} navBadge={navBadge} onNav={handleNav} onLogout={handleLogout} />}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        {isReviewPage ? (
          <ErrorBoundary label="诊断审核">
            <ReviewPage recordId={recordId} />
          </ErrorBoundary>
        ) : (
          <SectionContent activeSection={activeSection} doctorId={doctorId} isMobile={isMobile} navigate={navigate} urlSubpage={urlSubpage} urlSubId={urlSubId} chatInsertText={chatInsertText} setChatInsertText={setChatInsertText} chatAutoSendText={chatAutoSendText} setChatAutoSendText={setChatAutoSendText} chatAutoSendConsumedRef={chatAutoSendConsumedRef} patientRefreshKey={patientRefreshKey} setPatientRefreshKey={setPatientRefreshKey} handleLogout={handleLogout} onContextCleared={undefined} triggerInterview={triggerInterview} setTriggerInterview={setTriggerInterview} chatInterviewSessionId={chatInterviewSessionId} setChatInterviewSessionId={setChatInterviewSessionId} chatInterviewPrePopulated={chatInterviewPrePopulated} setChatInterviewPrePopulated={setChatInterviewPrePopulated} />
        )}
      </Box>
      {isMobile && !isSubpage && <MobileBottomNav activeSection={activeSection} navBadge={navBadge} onNav={handleNav} />}
      <OnboardingDialog open={showOnboarding} name={onboardName} saving={onboardSaving} onChange={setOnboardName} onSubmit={handleOnboardSubmit} onClose={() => setShowOnboarding(false)} />
    </Box>
  );
}
