/**
 * PatientPage — patient portal shell (v2, antd-mobile).
 *
 * Ported from src/pages/patient/PatientPage.jsx.
 * Key behaviours preserved:
 *   - QR-code token absorption from URL params
 *   - Identity hydration from localStorage + API refresh
 *   - Onboarding check (once per patient_id)
 *   - URL-driven tab routing (/patient/:tab)
 *   - Full-screen InterviewPage at /patient/records/interview
 *   - Unread badge on 聊天 tab
 *   - SafeArea top + bottom
 *   - Redirect to /login when no token
 *
 * Tabs other than 聊天 render placeholder content — records, tasks, profile
 * are lower priority for v2.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { TabBar, SafeArea, Badge } from "antd-mobile";
import {
  MessageOutline,
  FileOutline,
  UnorderedListOutline,
  UserOutline,
} from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import ChatTab from "./ChatTab";
import InterviewPage from "./InterviewPage";
import PatientOnboarding, { isOnboardingDone, markOnboardingDone } from "./PatientOnboarding";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import MyPage from "./MyPage";
import { APP } from "../../theme";

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

// Tab config
const TABS = [
  { key: "chat",    label: "聊天",  icon: <MessageOutline />      },
  { key: "records", label: "病历",  icon: <FileOutline />          },
  { key: "tasks",   label: "任务",  icon: <UnorderedListOutline /> },
  { key: "profile", label: "我的",  icon: <UserOutline />          },
];

// ---------------------------------------------------------------------------
// Placeholder for unimplemented tabs
// ---------------------------------------------------------------------------

function TabPlaceholder({ name }) {
  return (
    <div style={{ padding: 32, textAlign: "center", color: APP.text4, fontSize: 15 }}>
      {name} — 即将推出
    </div>
  );
}

// ---------------------------------------------------------------------------
// PatientPage
// ---------------------------------------------------------------------------

export default function PatientPage() {
  const api = usePatientApi();
  const { tab: urlTab, subpage: urlSubpage } = useParams();
  const navigate = useNavigate();

  // ---------------------------------------------------------------------------
  // QR code token absorption — runs once before state initialization
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
      const cleanUrl = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => cleanUrl.searchParams.delete(k));
      window.history.replaceState({}, "", cleanUrl.toString());
    }
  });

  // ---------------------------------------------------------------------------
  // Identity state — hydrated from localStorage
  // ---------------------------------------------------------------------------
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(
    () => localStorage.getItem(STORAGE_NAME_KEY) || ""
  );
  const [doctorName, setDoctorName] = useState(
    () => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || ""
  );
  const [doctorId, setDoctorId] = useState(
    () => localStorage.getItem(STORAGE_DOCTOR_KEY) || ""
  );
  const [unreadCount, setUnreadCount] = useState(0);
  const [onboardingDone, setOnboardingDone] = useState(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    return isOnboardingDone(pid);
  });

  // Mock mode: auto-set identity
  useEffect(() => {
    if (api.isMock) {
      setToken("mock-patient-token");
      setPatientName("陈伟强");
      setDoctorName("张医生");
      setDoctorId("mock_doctor");
    }
  }, [api.isMock]);

  // Real mode: refresh identity from API
  useEffect(() => {
    if (!token || api.isMock) return;
    api
      .getPatientMe(token)
      .then((data) => {
        if (data.patient_name) setPatientName(data.patient_name);
        setDoctorName(data.doctor_name || "");
        if (data.doctor_id) setDoctorId(data.doctor_id);
        if (data.patient_id)
          localStorage.setItem("patient_portal_patient_id", String(data.patient_id));
      })
      .catch(() => {});
  }, [token, api]);

  // ---------------------------------------------------------------------------
  // URL-driven tab + subpage
  // ---------------------------------------------------------------------------
  const tab = urlTab || "chat";
  const inInterview = urlSubpage === "interview";

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

  // Clear unread badge when on chat tab
  useEffect(() => {
    if (tab === "chat") {
      localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
      setUnreadCount(0);
    }
  }, [tab]);

  // Onboarding dismiss handler — scoped to current patient_id
  const handleDismissOnboarding = useCallback(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    markOnboardingDone(pid);
    setOnboardingDone(true);
  }, []);

  // Logout helper
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
    setDoctorId("");
  }, []);

  // Auth guard
  if (!token && !api.isMock) {
    window.location.href = "/login";
    return null;
  }

  // ---------------------------------------------------------------------------
  // Full-screen interview — no bottom tab bar
  // ---------------------------------------------------------------------------
  if (inInterview) {
    return (
      <div style={pageStyle}>
        <SafeArea position="top" />
        <InterviewPage token={token} onBack={exitInterview} />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main layout with TabBar
  // ---------------------------------------------------------------------------
  return (
    <div style={pageStyle}>
      <SafeArea position="top" />

      {/* Onboarding overlay — shown once per patient_id */}
      {!onboardingDone && (
        <PatientOnboarding
          doctorName={doctorName}
          onDismiss={handleDismissOnboarding}
        />
      )}

      {/* Active tab content */}
      <div style={contentStyle}>
        {tab === "chat" && (
          <ChatTab
            token={token}
            doctorName={doctorName}
            onNewInterview={startInterview}
            onViewRecords={() => handleTabChange("records")}
            onUnreadCountChange={setUnreadCount}
          />
        )}
        {tab === "records" && (
          <RecordsTab
            token={token}
            onNewRecord={startInterview}
            urlSubpage={urlSubpage}
          />
        )}
        {tab === "tasks" && <TasksTab token={token} />}
        {tab === "profile" && (
          <MyPage
            patientName={patientName}
            doctorName={doctorName}
            doctorId={doctorId}
            onLogout={handleLogout}
          />
        )}
      </div>

      {/* Bottom tab bar */}
      <div style={tabBarWrap}>
        <TabBar activeKey={tab} onChange={handleTabChange} safeArea>
          {TABS.map((t) => (
            <TabBar.Item
              key={t.key}
              title={t.label}
              icon={
                t.key === "chat" && unreadCount > 0 ? (
                  <Badge content={unreadCount} style={{ "--right": "-6px", "--top": "0" }}>
                    {t.icon}
                  </Badge>
                ) : (
                  t.icon
                )
              }
            />
          ))}
        </TabBar>
      </div>
    </div>
  );
}

const pageStyle = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  overflow: "hidden",
  background: APP.surfaceAlt,
};

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
