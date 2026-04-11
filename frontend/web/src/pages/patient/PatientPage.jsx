/**
 * @route /patient, /patient/:tab, /patient/:tab/:subpage
 *
 * Patient portal shell (ADR 0016).
 *
 * Thin orchestrator — all tab content lives in dedicated modules:
 *   ChatTab, RecordsTab, TasksTab, ProfileTab, InterviewPage
 */

import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { Box, Fade } from "@mui/material";
import Badge from "@mui/material/Badge";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import SubpageHeader from "../../components/SubpageHeader";
import { usePatientApi } from "../../api/PatientApiContext";
import {
  NAV_TABS,
  PAGE_LAYOUT,
  STORAGE_KEY,
  STORAGE_NAME_KEY,
  STORAGE_DOCTOR_KEY,
  STORAGE_DOCTOR_NAME_KEY,
  LAST_SEEN_CHAT_KEY,
  ONBOARDING_DONE_KEY_PREFIX,
} from "./constants";
import PatientOnboarding from "./PatientOnboarding";
import ChatTab from "./ChatTab";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import MyPage from "./MyPage";
import InterviewPage from "./InterviewPage";
import { COLOR, TYPE } from "../../theme";

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

export default function PatientPage() {
  const api = usePatientApi();
  const { tab: urlTab, subpage: urlSubpage } = useParams();
  const navigate = useAppNavigate();

  // ---------------------------------------------------------------------------
  // QR code token absorption — must run before state initialization
  // ---------------------------------------------------------------------------
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const qrToken = params.get("token");
    if (qrToken) {
      const qrDoctorId = params.get("doctor_id");
      const qrName = params.get("name");
      localStorage.setItem(STORAGE_KEY, qrToken);
      if (qrName) localStorage.setItem(STORAGE_NAME_KEY, qrName);
      if (qrDoctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, qrDoctorId);
      // Clean URL params
      const cleanUrl = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach(k => cleanUrl.searchParams.delete(k));
      window.history.replaceState({}, "", cleanUrl.toString());
    }
  });

  // ---------------------------------------------------------------------------
  // Identity state — hydrated from localStorage
  // ---------------------------------------------------------------------------
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
  const [doctorSpecialty, setDoctorSpecialty] = useState("");
  const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
  const [unreadCount, setUnreadCount] = useState(0);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // ---------------------------------------------------------------------------
  // Mock mode: auto-set identity when no token
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (api.isMock) {
      setToken("mock-patient-token");
      setPatientName("陈伟强");
      setDoctorName("张医生");
      setDoctorSpecialty("神经外科");
      setDoctorId("mock_doctor");
    }
  }, [api.isMock]);

  // ---------------------------------------------------------------------------
  // Refresh identity from API on mount (real mode only)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!token || api.isMock) return;
    api.getPatientMe(token).then(data => {
      if (data.patient_name) setPatientName(data.patient_name);
      setDoctorName(data.doctor_name || "");
      setDoctorSpecialty(data.doctor_specialty || "");
      if (data.doctor_id) setDoctorId(data.doctor_id);
      if (data.patient_id) localStorage.setItem("patient_portal_patient_id", String(data.patient_id));
    }).catch(() => {});
  }, [token, api]);

  // ---------------------------------------------------------------------------
  // Onboarding check — show once per patient_id
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!token || api.isMock) return;
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId && !localStorage.getItem(ONBOARDING_DONE_KEY_PREFIX + patientId)) {
      setShowOnboarding(true);
    }
  }, [token, api.isMock]);

  // ---------------------------------------------------------------------------
  // URL-driven tab & subpage
  // ---------------------------------------------------------------------------
  const tab = urlTab || "chat";
  const inInterview = urlSubpage === "interview";
  const setTab = useCallback(t => navigate(`/patient/${t}`), [navigate]);
  const startInterview = useCallback(() => navigate("/patient/records/interview"), [navigate]);
  const exitInterview = useCallback(() => navigate("/patient/records"), [navigate]);

  // Clear unread badge when on chat tab
  useEffect(() => {
    if (tab === "chat") {
      localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
      setUnreadCount(0);
    }
  }, [tab]);

  // ---------------------------------------------------------------------------
  // Auth: redirect to /login if no token (non-mock)
  // ---------------------------------------------------------------------------
  const dismissOnboarding = useCallback(() => {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.setItem(ONBOARDING_DONE_KEY_PREFIX + patientId, "1");
    setShowOnboarding(false);
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_NAME_KEY);
    localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
    localStorage.removeItem("patient_portal_patient_id");
    setToken("");
    setPatientName("");
    setDoctorName("");
    setDoctorSpecialty("");
    setDoctorId("");
  }, []);

  if (!token && !api.isMock) {
    window.location.href = "/login";
    return null;
  }

  // ---------------------------------------------------------------------------
  // Full-screen interview — no bottom nav
  // ---------------------------------------------------------------------------
  if (inInterview) {
    return <InterviewPage token={token} onBack={exitInterview} onLogout={handleLogout} />;
  }

  // ---------------------------------------------------------------------------
  // Main layout: header + active tab + bottom nav
  // ---------------------------------------------------------------------------
  return (
    <Box sx={PAGE_LAYOUT}>
      {showOnboarding && (
        <PatientOnboarding
          doctorName={doctorName}
          doctorSpecialty={doctorSpecialty}
          onDismiss={dismissOnboarding}
        />
      )}

      {/* Page header — only for tabs without their own PageSkeleton header */}
      {!urlSubpage && tab !== "records" && tab !== "profile" && (
        <SubpageHeader title={NAV_TABS.find(t => t.key === tab)?.title || "AI 健康助手"} />
      )}

      {/* Content area — Fade transition matches DoctorPage */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        <Fade in={tab === "chat"} timeout={150} unmountOnExit>
          <Box sx={{ position: tab === "chat" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
              onNewInterview={startInterview}
              onViewRecords={() => setTab("records")}
              onUnreadCountChange={setUnreadCount} />
          </Box>
        </Fade>
        <Fade in={tab === "records"} timeout={150} unmountOnExit>
          <Box sx={{ position: tab === "records" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <RecordsTab token={token} onNewRecord={startInterview} urlSubpage={urlSubpage} />
          </Box>
        </Fade>
        <Fade in={tab === "tasks"} timeout={150} unmountOnExit>
          <Box sx={{ position: tab === "tasks" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <TasksTab token={token} />
          </Box>
        </Fade>
        <Fade in={tab === "profile"} timeout={150} unmountOnExit>
          <Box sx={{ position: tab === "profile" ? "relative" : "absolute", inset: 0, display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
            <MyPage patientName={patientName} doctorName={doctorName}
              doctorSpecialty={doctorSpecialty} doctorId={doctorId}
              onLogout={handleLogout} />
          </Box>
        </Fade>
      </Box>

      {/* Bottom navigation */}
      <BottomNavigation value={tab} onChange={(_, v) => setTab(v)} showLabels
        sx={{
          flexShrink: 0, height: 64, bgcolor: COLOR.surface,
          borderTop: `0.5px solid ${COLOR.border}`,
          paddingBottom: "env(safe-area-inset-bottom)",
          "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: COLOR.text4 },
          "& .Mui-selected": { color: COLOR.primary },
          "& .Mui-selected .MuiBottomNavigationAction-label": { color: COLOR.primary, fontWeight: 600 },
        }}>
        {NAV_TABS.map(t => (
          <BottomNavigationAction key={t.key} value={t.key} label={t.label}
            icon={
              t.key === "chat" && unreadCount > 0
                ? <Badge badgeContent={unreadCount} color="error">{t.icon}</Badge>
                : t.icon
            }
            />
        ))}
      </BottomNavigation>
    </Box>
  );
}
