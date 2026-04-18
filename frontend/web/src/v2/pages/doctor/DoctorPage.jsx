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
  const segment = pathname.split("/")[2]; // e.g. "my-ai", "patients", "review", "tasks"
  if (TABS.some((t) => t.key === segment)) return segment;
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

export default function DoctorPage({ doctorId }) {
  const location = useLocation();
  const navigate = useNavigate();

  const activeSection = detectSection(location.pathname);
  const activeTab = TABS.find((t) => t.key === activeSection) || TABS[0];

  // Badge counts — placeholder zeros; real data wired in later
  const [badges] = useState({ review: 0, tasks: 0, patients: 0 });

  // Interview overlay — active when navigated to /doctor/patients/new
  const interviewActive = location.pathname.endsWith("/patients/new");

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

      {/* Top NavBar — hidden when interview overlay is active */}
      {!interviewActive && (
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
        ) : (
          <SectionPlaceholder name={activeTab.title} />
        )}
      </div>

      {/* Bottom TabBar — hidden when interview overlay is active */}
      {!interviewActive && (
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

      {/* Safe area bottom — shown when TabBar is hidden */}
      {interviewActive && <SafeArea position="bottom" />}
      {!interviewActive && <SafeArea position="bottom" />}
    </div>
  );
}
