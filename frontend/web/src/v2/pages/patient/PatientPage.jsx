/**
 * @route /patient, /patient/:tab, /patient/:tab/:subpage
 *
 * PatientPage — patient portal shell (v2, antd-mobile).
 *
 * Mirrors DoctorPage structure:
 *   - Top NavBar with tab title + optional right action
 *   - Bottom TabBar with 4 tabs (chat / records / tasks / profile)
 *   - Full-screen subpage overlays (hide NavBar + TabBar)
 *   - Pathname-driven section detection (NOT useParams — wildcard route
 *     would make useParams() return only "*")
 *
 * Identity (token + name + doctor_id) hydrated from localStorage; QR-code
 * absorption preserved. Onboarding gate preserved.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { NavBar, TabBar, SafeArea, Badge, Button } from "antd-mobile";
import {
  MessageOutline,
  MessageFill,
  FileOutline,
  UnorderedListOutline,
  UserOutline,
  AddCircleOutline,
} from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import { APP, FONT, ICON } from "../../theme";
import { pageContainer, navBarStyle } from "../../layouts";
import ChatTab from "./ChatTab";
import InterviewPage from "./InterviewPage";
import PatientOnboarding, { isOnboardingDone, markOnboardingDone } from "./PatientOnboarding";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import MyPage from "./MyPage";
import PatientRecordDetailPage from "./PatientRecordDetailPage";
import PatientTaskDetailPage from "./PatientTaskDetailPage";
import PatientAboutSubpage from "./PatientAboutSubpage";
import PatientPrivacySubpage from "./PatientPrivacySubpage";
import {
  detectSection,
  detectRecordDetail,
  detectTaskDetail,
  detectProfileSubpage,
} from "./pathname";

// ── Storage keys ───────────────────────────────────────────────────

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

// ── Tab config ─────────────────────────────────────────────────────

const TABS = [
  { key: "chat",     label: "聊天", title: "聊天",   icon: <MessageOutline />,        activeIcon: <MessageFill />,        path: "/patient/chat" },
  { key: "records",  label: "病历", title: "病历",   icon: <FileOutline />,           activeIcon: <FileOutline />,        path: "/patient/records" },
  { key: "tasks",    label: "任务", title: "任务",   icon: <UnorderedListOutline />,  activeIcon: <UnorderedListOutline/>, path: "/patient/tasks" },
  { key: "profile",  label: "我的", title: "我的",   icon: <UserOutline />,           activeIcon: <UserOutline />,        path: "/patient/profile" },
];
// Note: File/UnorderedList/User have no Fill variant in antd-mobile-icons.
// TabBar conveys active state via color; Outline stays visually.

export default function PatientPage() {
  const api = usePatientApi();
  const location = useLocation();
  const navigate = useNavigate();

  // ── QR code token absorption (must run before state init) ────────
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const qrToken = params.get("token");
    if (qrToken) {
      const qrDoctorId = params.get("doctor_id");
      const qrName = params.get("name");
      localStorage.setItem(STORAGE_KEY, qrToken);
      if (qrName) localStorage.setItem(STORAGE_NAME_KEY, qrName);
      if (qrDoctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, qrDoctorId);
      const cleanUrl = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => cleanUrl.searchParams.delete(k));
      window.history.replaceState({}, "", cleanUrl.toString());
    }
  });

  // ── Identity state ───────────────────────────────────────────────
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
  const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
  const [unreadCount, setUnreadCount] = useState(0);
  const [onboardingDone, setOnboardingDone] = useState(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    return isOnboardingDone(pid);
  });

  // Mock mode
  useEffect(() => {
    if (api.isMock) {
      setToken("mock-patient-token");
      setPatientName("陈伟强");
      setDoctorName("张医生");
      setDoctorId("mock_doctor");
    }
  }, [api.isMock]);

  // Real mode: refresh identity
  useEffect(() => {
    if (!token || api.isMock) return;
    api
      .getPatientMe(token)
      .then((data) => {
        if (data.patient_name) setPatientName(data.patient_name);
        setDoctorName(data.doctor_name || "");
        if (data.doctor_id) setDoctorId(data.doctor_id);
        if (data.patient_id) {
          localStorage.setItem("patient_portal_patient_id", String(data.patient_id));
        }
      })
      .catch(() => {});
  }, [token, api]);

  // ── Pathname-driven overlay/section detection ────────────────────
  const section = detectSection(location.pathname);
  const recordDetailId = detectRecordDetail(location.pathname);
  const taskDetailId = detectTaskDetail(location.pathname);
  const profileSubpage = detectProfileSubpage(location.pathname);
  const inInterview = location.pathname === "/patient/records/interview";

  const fullScreenActive =
    inInterview || !!recordDetailId || !!taskDetailId || !!profileSubpage;

  // ── Tab + navigation handlers ────────────────────────────────────
  const handleTabChange = useCallback(
    (key) => navigate(`/patient/${key}`),
    [navigate]
  );

  const startInterview = useCallback(
    () => navigate("/patient/records/interview"),
    [navigate]
  );

  const exitInterview = useCallback(
    () => navigate("/patient/records"),
    [navigate]
  );

  // Clear unread badge when visiting chat tab
  useEffect(() => {
    if (section === "chat" && !fullScreenActive) {
      localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
      setUnreadCount(0);
    }
  }, [section, fullScreenActive]);

  const handleDismissOnboarding = useCallback(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    markOnboardingDone(pid);
    setOnboardingDone(true);
  }, []);

  const handleLogout = useCallback(() => {
    [
      STORAGE_KEY,
      STORAGE_NAME_KEY,
      STORAGE_DOCTOR_KEY,
      STORAGE_DOCTOR_NAME_KEY,
      PATIENT_CHAT_STORAGE_KEY,
      "patient_portal_patient_id",
    ].forEach((k) => localStorage.removeItem(k));
    setToken("");
    setPatientName("");
    setDoctorName("");
    setDoctorId("");
  }, []);

  // ── Auth guard ────────────────────────────────────────────────────
  if (!token && !api.isMock) {
    window.location.href = "/login";
    return null;
  }

  // ── Full-screen subpages ─────────────────────────────────────────
  if (inInterview) {
    return (
      <div style={pageContainer}>
        <SafeArea position="top" />
        <InterviewPage token={token} onBack={exitInterview} />
      </div>
    );
  }
  if (recordDetailId) {
    return <PatientRecordDetailPage recordId={recordDetailId} token={token} />;
  }
  if (taskDetailId) {
    return <PatientTaskDetailPage taskId={taskDetailId} token={token} />;
  }
  if (profileSubpage === "about") {
    return <PatientAboutSubpage />;
  }
  if (profileSubpage === "privacy") {
    return <PatientPrivacySubpage />;
  }

  // ── Main shell ───────────────────────────────────────────────────
  const activeTab = TABS.find((t) => t.key === section) || TABS[0];

  return (
    <div style={pageContainer}>
      <SafeArea position="top" />

      {/* Top NavBar */}
      <NavBar
        backArrow={false}
        right={
          section === "records" ? (
            <Button
              fill="none"
              color="primary"
              size="small"
              onClick={startInterview}
              aria-label="新问诊"
            >
              <AddCircleOutline style={{ fontSize: ICON.md }} />
            </Button>
          ) : null
        }
        style={navBarStyle}
      >
        {activeTab.title}
      </NavBar>

      {/* Onboarding overlay */}
      {!onboardingDone && (
        <PatientOnboarding
          doctorName={doctorName}
          onDismiss={handleDismissOnboarding}
        />
      )}

      {/* Active tab content */}
      <div style={contentStyle}>
        {section === "chat" && (
          <ChatTab
            token={token}
            doctorName={doctorName}
            onNewInterview={startInterview}
            onViewRecords={() => handleTabChange("records")}
            onUnreadCountChange={setUnreadCount}
          />
        )}
        {section === "records" && (
          <RecordsTab token={token} />
        )}
        {section === "tasks" && <TasksTab token={token} />}
        {section === "profile" && (
          <MyPage
            patientName={patientName}
            doctorName={doctorName}
            doctorId={doctorId}
            onLogout={handleLogout}
          />
        )}
      </div>

      {/* Bottom TabBar */}
      <div style={tabBarWrap}>
        <TabBar activeKey={section} onChange={handleTabChange} safeArea>
          {TABS.map((t) => (
            <TabBar.Item
              key={t.key}
              title={t.label}
              icon={(active) => {
                // Only badge the chat tab, and only when the user is NOT already on it.
                const showBadge =
                  t.key === "chat" && unreadCount > 0 && section !== "chat";
                const glyph = active ? t.activeIcon : t.icon;
                return showBadge ? (
                  <Badge
                    content={unreadCount}
                    style={{ "--right": "-10px", "--top": "-2px" }}
                  >
                    {glyph}
                  </Badge>
                ) : glyph;
              }}
            />
          ))}
        </TabBar>
      </div>
    </div>
  );
}

const contentStyle = {
  flex: 1,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const tabBarWrap = {
  flexShrink: 0,
  borderTop: `0.5px solid ${APP.border}`,
  background: APP.surface,
};
