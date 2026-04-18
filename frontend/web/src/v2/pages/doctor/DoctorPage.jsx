/**
 * @route /doctor/*
 *
 * v2 DoctorPage shell — antd-mobile TabBar + NavBar.
 * No MUI, no framer-motion, no complex subpage logic.
 * Placeholder content areas; real subpages wired in later tasks.
 *
 * InterviewPage overlay: rendered when path is /doctor/patients/new
 */
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { NavBar, SafeArea, TabBar } from "antd-mobile";
import InterviewPage from "./InterviewPage";
import MyAIPage from "./MyAIPage";
import PatientsPage from "./PatientsPage";
import PatientDetail from "./PatientDetail";
import PatientChatPage from "./PatientChatPage";
import TaskPage from "./TaskPage";
import ReviewQueuePage from "./ReviewQueuePage";
import ReviewPage from "./ReviewPage";
import SettingsPage from "./SettingsPage";
import PersonaSubpage from "./settings/PersonaSubpage";
import KnowledgeSubpage from "./settings/KnowledgeSubpage";
import AddKnowledgeSubpage from "./settings/AddKnowledgeSubpage";
import KnowledgeDetailSubpage from "./settings/KnowledgeDetailSubpage";
import SettingsListSubpage from "./settings/SettingsListSubpage";
import KbPendingSubpage from "./settings/KbPendingSubpage";
import TaskDetailSubpage from "./settings/TaskDetailSubpage";
import AboutSubpage from "./settings/AboutSubpage";
import TeachByExampleSubpage from "./settings/TeachByExampleSubpage";
import ReviewSubpage from "./settings/ReviewSubpage";
import PendingReviewSubpage from "./settings/PendingReviewSubpage";
import PersonaOnboardingSubpage from "./settings/PersonaOnboardingSubpage";
import TemplateSubpage from "./settings/TemplateSubpage";
import {
  MessageOutline,
  TeamOutline,
  CheckShieldOutline,
  FileOutline,
} from "antd-mobile-icons";
import { APP } from "../../theme";

// ── Tab config ─────────────────────────────────────────────────────

const TABS = [
  {
    key: "my-ai",
    label: "我的AI",
    icon: <MessageOutline />,
    path: "/doctor/my-ai",
    title: "我的AI",
  },
  {
    key: "patients",
    label: "患者",
    icon: <TeamOutline />,
    path: "/doctor/patients",
    title: "患者",
    badgeKey: "patients",
  },
  {
    key: "review",
    label: "审核",
    icon: <CheckShieldOutline />,
    path: "/doctor/review",
    title: "审核",
    badgeKey: "review",
  },
  {
    key: "tasks",
    label: "随访",
    icon: <FileOutline />,
    path: "/doctor/tasks",
    title: "随访",
    badgeKey: "tasks",
  },
];

// ── Section detection ──────────────────────────────────────────────

function detectSection(pathname) {
  // /doctor or /doctor/ → my-ai
  if (pathname === "/doctor" || pathname === "/doctor/") return "my-ai";
  const segment = pathname.split("/")[2]; // e.g. "my-ai", "patients", "review", "tasks", "settings"
  if (TABS.some((t) => t.key === segment)) return segment;
  if (segment === "settings") return "settings";
  return "my-ai";
}

// ── Placeholder content ────────────────────────────────────────────

function SectionPlaceholder({ name }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 12,
        color: APP.text4,
        fontFamily: "system-ui, sans-serif",
        fontSize: 15,
      }}
    >
      <span style={{ fontSize: 32 }}>🚧</span>
      <span>{name} — 即将上线</span>
    </div>
  );
}

// ── Main shell ─────────────────────────────────────────────────────

export default function DoctorPage({ doctorId, onLogout }) {
  const location = useLocation();
  const navigate = useNavigate();

  const activeSection = detectSection(location.pathname);
  const activeTab = TABS.find((t) => t.key === activeSection) || TABS[0];

  // Badge counts — placeholder zeros; real data wired in later
  const [badges] = useState({ review: 0, tasks: 0, patients: 0 });

  // Interview overlay — active when navigated to /doctor/patients/new
  const interviewActive = location.pathname.endsWith("/patients/new");

  // Patient detail subpage — /doctor/patients/:id (any segment after /patients/ that isn't "new")
  const patientDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "patients", ":id"]
    if (parts[2] === "patients" && parts[3] && parts[3] !== "new") {
      return parts[3];
    }
    return null;
  })();

  // Review detail subpage — /doctor/review/:recordId
  const reviewDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "review", ":recordId"]
    if (parts[2] === "review" && parts[3]) {
      return parts[3];
    }
    return null;
  })();

  // Task detail subpage — /doctor/tasks/:taskId
  const taskDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "tasks", ":taskId"]
    if (parts[2] === "tasks" && parts[3]) {
      return parts[3];
    }
    return null;
  })();

  // Settings subpage detection
  // /doctor/settings → SettingsPage list
  // /doctor/settings/persona → PersonaSubpage
  // /doctor/settings/knowledge → KnowledgeSubpage
  // /doctor/settings/knowledge/add → AddKnowledgeSubpage
  // /doctor/settings/knowledge/:id → KnowledgeDetailSubpage
  // /doctor/settings/preferences → SettingsListSubpage
  const settingsMatch = (() => {
    const parts = location.pathname.split("/");
    if (parts[2] !== "settings") return null;
    const sub = parts[3]; // persona | knowledge | preferences | undefined
    const sub2 = parts[4]; // add | :id | undefined
    return { sub, sub2 };
  })();
  const settingsActive = !!settingsMatch;

  // Full-screen overlays hide NavBar/TabBar
  const fullScreenActive =
    interviewActive ||
    !!patientDetailMatch ||
    !!reviewDetailMatch ||
    !!taskDetailMatch ||
    settingsActive;

  function handleTabChange(key) {
    const tab = TABS.find((t) => t.key === key);
    if (tab) navigate(tab.path, { replace: true });
  }

  function handleInterviewComplete() {
    navigate("/doctor/patients", { replace: true });
  }

  function handleInterviewCancel() {
    navigate("/doctor/patients", { replace: true });
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Safe area top */}
      <SafeArea position="top" />

      {/* Top NavBar — hidden when full-screen overlays are active */}
      {!fullScreenActive && (
        <NavBar
          backArrow={false}
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          {activeTab.title}
        </NavBar>
      )}

      {/* Content area */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {interviewActive ? (
          /* Full-screen interview overlay (keyboard-aware, no TabBar) */
          <InterviewPage
            doctorId={doctorId}
            onComplete={handleInterviewComplete}
            onCancel={handleInterviewCancel}
          />
        ) : patientDetailMatch ? (
          /* Full-screen patient detail or chat subpage (no TabBar) */
          new URLSearchParams(location.search).get("view") === "chat" ? (
            <PatientChatPage patientId={patientDetailMatch} />
          ) : (
            <PatientDetail patientId={patientDetailMatch} />
          )
        ) : reviewDetailMatch ? (
          /* Full-screen review detail (no TabBar) */
          <ReviewPage recordId={reviewDetailMatch} />
        ) : taskDetailMatch ? (
          /* Full-screen task detail (no TabBar) */
          <TaskDetailSubpage taskId={taskDetailMatch} />
        ) : settingsActive ? (
          /* Settings subpages — full-screen, hide TabBar */
          (() => {
            const { sub, sub2 } = settingsMatch;
            if (sub === "persona") return <PersonaSubpage />;
            if (sub === "knowledge" && sub2 === "add") return <AddKnowledgeSubpage />;
            if (sub === "knowledge" && sub2 === "pending") return <KbPendingSubpage />;
            if (sub === "knowledge" && sub2) return <KnowledgeDetailSubpage itemId={sub2} />;
            if (sub === "knowledge") return <KnowledgeSubpage />;
            if (sub === "preferences") return <SettingsListSubpage onLogout={onLogout} />;
            if (sub === "about") return <AboutSubpage />;
            if (sub === "teach") return <TeachByExampleSubpage />;
            if (sub === "review") return <ReviewSubpage />;
            if (sub === "pending-review") return <PendingReviewSubpage />;
            if (sub === "persona-onboarding") return <PersonaOnboardingSubpage />;
            if (sub === "templates") return <TemplateSubpage />;
            // /doctor/settings → main list
            return <SettingsPage />;
          })()
        ) : activeSection === "my-ai" ? (
          <MyAIPage doctorId={doctorId} />
        ) : activeSection === "patients" ? (
          <PatientsPage />
        ) : activeSection === "review" ? (
          <ReviewQueuePage />
        ) : activeSection === "tasks" ? (
          <TaskPage doctorId={doctorId} />
        ) : (
          <SectionPlaceholder name={activeTab.title} />
        )}
      </div>

      {/* Bottom TabBar — hidden when full-screen overlays are active */}
      {!fullScreenActive && (
        <TabBar
          activeKey={activeSection}
          onChange={handleTabChange}
          style={{
            borderTop: `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
            "--adm-color-primary": "#07C160",
          }}
        >
          {TABS.map((tab) => {
            const badgeCount = tab.badgeKey ? (badges[tab.badgeKey] || 0) : 0;
            return (
              <TabBar.Item
                key={tab.key}
                icon={tab.icon}
                title={tab.label}
                badge={badgeCount > 0 ? badgeCount : undefined}
              />
            );
          })}
        </TabBar>
      )}

      {/* Safe area bottom — always present (TabBar has its own) */}
      {fullScreenActive && <SafeArea position="bottom" />}
      {!fullScreenActive && <SafeArea position="bottom" />}
    </div>
  );
}
