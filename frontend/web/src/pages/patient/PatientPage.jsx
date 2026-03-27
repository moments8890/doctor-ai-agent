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
import { Box } from "@mui/material";
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
} from "./constants";
import ChatTab from "./ChatTab";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import ProfileTab from "./ProfileTab";
import InterviewPage from "./InterviewPage";

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

export default function PatientPage() {
  const api = usePatientApi();
  const { tab: urlTab, subpage: urlSubpage } = useParams();
  const navigate = useAppNavigate();

  // ---------------------------------------------------------------------------
  // Identity state — hydrated from localStorage
  // ---------------------------------------------------------------------------
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
  const [doctorSpecialty, setDoctorSpecialty] = useState("");
  const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
  const [unreadCount, setUnreadCount] = useState(0);

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
    }).catch(() => {});
  }, [token, api]);

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
  const handleLogout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_NAME_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_KEY);
    localStorage.removeItem(STORAGE_DOCTOR_NAME_KEY);
    localStorage.removeItem(PATIENT_CHAT_STORAGE_KEY);
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
      {/* Page header — hidden when a subpage renders its own */}
      {!urlSubpage && <SubpageHeader title={NAV_TABS.find(t => t.key === tab)?.title || "AI 健康助手"} />}

      {/* Content area */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        {tab === "chat" && (
          <ChatTab token={token} doctorName={doctorName} onLogout={handleLogout}
            onNewInterview={startInterview}
            onViewRecords={() => setTab("records")}
            onUnreadCountChange={setUnreadCount} />
        )}
        {tab === "records" && (
          <RecordsTab token={token} onNewRecord={startInterview} urlSubpage={urlSubpage} />
        )}
        {tab === "tasks" && <TasksTab token={token} />}
        {tab === "profile" && (
          <ProfileTab patientName={patientName} doctorName={doctorName}
            doctorSpecialty={doctorSpecialty} doctorId={doctorId}
            onLogout={handleLogout} />
        )}
      </Box>

      {/* Bottom navigation */}
      <BottomNavigation value={tab} onChange={(_, v) => setTab(v)} showLabels
        sx={{
          flexShrink: 0, height: 56,
          borderTop: "1px solid #ddd", bgcolor: "#f5f5f5",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}>
        {NAV_TABS.map(t => (
          <BottomNavigationAction key={t.key} value={t.key} label={t.label}
            icon={
              t.key === "chat" && unreadCount > 0
                ? <Badge badgeContent={unreadCount} color="error">{t.icon}</Badge>
                : t.icon
            }
            sx={{ "&.Mui-selected": { color: "#07C160" } }} />
        ))}
      </BottomNavigation>
    </Box>
  );
}
