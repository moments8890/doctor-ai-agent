/**
 * @route /doctor/*
 *
 * v2 DoctorPage shell — antd-mobile TabBar + NavBar.
 * No MUI, no framer-motion, no complex subpage logic.
 * Placeholder content areas; real subpages wired in later tasks.
 *
 * IntakePage overlay: rendered when path is /doctor/patients/new
 */
import { useState, useCallback, useRef, useMemo } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { usePageStack } from "../../usePageStack";
import { NavBar, Popover, Mask, SafeArea, Button, TextArea, Toast } from "antd-mobile";
import { usePatients } from "../../../lib/doctorQueries";
import IntakePage from "./IntakePage";
import MyAIPage from "./MyAIPage";
import PatientsPage from "./PatientsPage";
import PatientDetail from "./PatientDetail";
import PatientChatPage from "./PatientChatPage";
import ReviewPage from "./ReviewPage";
import SettingsPage from "./SettingsPage";
import PersonaSubpage from "./settings/PersonaSubpage";
import KnowledgeSubpage from "./settings/KnowledgeSubpage";
import AddKnowledgeSubpage from "./settings/AddKnowledgeSubpage";
import KnowledgeDetailSubpage from "./settings/KnowledgeDetailSubpage";
import AboutSubpage from "./settings/AboutSubpage";
import TeachByExampleSubpage from "./settings/TeachByExampleSubpage";
import PendingReviewSubpage from "./settings/PendingReviewSubpage";
import PersonaOnboardingSubpage from "./settings/PersonaOnboardingSubpage";
import TemplateSubpage from "./settings/TemplateSubpage";
import QrSubpage from "./settings/QrSubpage";
import AddToHomeScreenOutlinedIcon from "@mui/icons-material/AddToHomeScreenOutlined";
import FeedbackOutlinedIcon from "@mui/icons-material/FeedbackOutlined";
import { submitPlatformFeedback } from "../../../api";
import { APP, FONT, ICON } from "../../theme";
import { useDoctorStore } from "../../../store/doctorStore";

// ── Section detection ──────────────────────────────────────────────

function detectSection() {
  // Single-tab IA: my-ai is always the base section. Other doctor routes
  // (/patients, /review/:id, /settings/*) render via overlayRouteKey.
  return "my-ai";
}

// ── Feedback popover ───────────────────────────────────────────────
// Controlled antd-mobile Popover. Opens on icon tap, closes on submit
// success or outside click. Posts to /api/platform/feedback (auth via
// Authorization header from the existing api.js wrapper).
//
// Category chips are optional — selecting one prefixes the saved content
// with `[bug] ` / `[ui] ` / `[missing] ` so admin grep can pull them
// out without a schema migration. No category = naked content as before.

const FEEDBACK_CATEGORIES = [
  { key: "bug",     label: "Bug" },
  { key: "ui",      label: "UI 体验" },
  { key: "missing", label: "功能缺失" },
];

function CategoryChip({ active, label, onClick }) {
  return (
    <span
      role="button"
      onClick={onClick}
      style={{
        fontSize: FONT.sm,
        padding: "4px 10px",
        borderRadius: 12,
        cursor: "pointer",
        userSelect: "none",
        border: `1px solid ${active ? APP.primary : APP.border}`,
        color: active ? APP.primary : APP.text2,
        background: active ? `${APP.primary}14` : "transparent",
        transition: "all 100ms",
      }}
    >
      {label}
    </span>
  );
}

function FeedbackPopover({ children }) {
  const [visible, setVisible] = useState(false);
  const [category, setCategory] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  // Reset internal state every time the popover closes so a half-typed
  // draft doesn't surprise the user the next time they open it. (We
  // intentionally don't preserve drafts — feedback is small enough that
  // re-typing isn't a real cost.)
  function handleVisibleChange(next) {
    if (!next) {
      setCategory(null);
      setText("");
    }
    setVisible(next);
  }

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const tag = category ? `[${category}] ` : "";
      await submitPlatformFeedback({
        content: tag + trimmed,
        pageUrl: typeof window !== "undefined" ? window.location.href : null,
        userAgent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      });
      Toast.show({ icon: "success", content: "已发送，谢谢你的反馈" });
      setCategory(null);
      setText("");
      setVisible(false);
    } catch (err) {
      Toast.show({
        icon: "fail",
        content: err?.message || "提交失败，请稍后再试",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover
      content={
        <div style={{ width: 280, padding: "4px 2px" }}>
          <div
            style={{
              fontSize: FONT.md,
              fontWeight: 600,
              color: APP.text1,
              marginBottom: 10,
            }}
          >
            反馈给我们
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
            {FEEDBACK_CATEGORIES.map((c) => (
              <CategoryChip
                key={c.key}
                active={category === c.key}
                label={c.label}
                onClick={() => setCategory(category === c.key ? null : c.key)}
              />
            ))}
          </div>
          <TextArea
            value={text}
            onChange={setText}
            placeholder="哪里有问题？想看到什么功能？任何想说的都可以"
            rows={4}
            maxLength={2000}
            autoSize={{ minRows: 4, maxRows: 8 }}
          />
          <Button
            color="primary"
            block
            size="small"
            loading={busy}
            disabled={!text.trim()}
            onClick={handleSubmit}
            style={{ marginTop: 8 }}
          >
            提交
          </Button>
        </div>
      }
      trigger="click"
      placement="bottomRight"
      visible={visible}
      onVisibleChange={handleVisibleChange}
    >
      {children}
    </Popover>
  );
}

// ── Add-to-desktop popover ────────────────────────────────────────
// Controlled popover with a sibling Mask so the rest of the page dims
// while the instructions are visible. Popover portals at z-index 1030,
// Mask at 1000, so the popover stays bright above the dim layer.
// Tapping the mask (or anywhere outside the popover) closes both.

function AddToDesktopPopover() {
  const [visible, setVisible] = useState(false);
  return (
    <>
      <Mask
        visible={visible}
        onMaskClick={() => setVisible(false)}
      />
      <Popover
        trigger="click"
        placement="bottomRight"
        visible={visible}
        onVisibleChange={setVisible}
        content={
          <div style={{ maxWidth: 240, padding: "4px 2px" }}>
            <div
              style={{
                fontSize: FONT.md,
                fontWeight: 600,
                color: APP.text1,
                marginBottom: 8,
              }}
            >
              添加到桌面，下次一键打开
            </div>
            <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.7 }}>
              <div>1. 点击微信右上角「···」</div>
              <div>2. 选择「添加到桌面」</div>
              <div>3. 下次直接从桌面打开</div>
            </div>
          </div>
        }
      >
        <div
          role="button"
          aria-label="添加到桌面"
          style={{
            padding: 8,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
          }}
        >
          <AddToHomeScreenOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
        </div>
      </Popover>
    </>
  );
}

// ── Main shell ─────────────────────────────────────────────────────

export default function DoctorPage({ doctorId: propDoctorId, onLogout }) {
  const { doctorId: storeDoctorId } = useDoctorStore();
  const doctorId = propDoctorId || storeDoctorId;
  const location = useLocation();
  const navigate = useNavigate();

  const activeSection = detectSection();

  // Intake overlay — active when navigated to /doctor/patients/new
  const intakeActive = location.pathname.endsWith("/patients/new");

  // Optional preselected patient passed via ?patient_id=<id> when the user
  // picks an existing patient from the "新建病历" picker on MyAIPage.
  const intakePatientIdParam = new URLSearchParams(location.search).get("patient_id");
  const { data: patientsForIntake } = usePatients();
  const intakePatientContext = useMemo(() => {
    if (!intakeActive || !intakePatientIdParam) return null;
    const list = Array.isArray(patientsForIntake)
      ? patientsForIntake
      : patientsForIntake?.items || [];
    const p = list.find((x) => String(x.id) === String(intakePatientIdParam));
    return p ? { id: p.id, name: p.name } : null;
  }, [intakeActive, intakePatientIdParam, patientsForIntake]);

  // Patient detail subpage — /doctor/patients/:id (any segment after /patients/ that isn't "new")
  const patientDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "patients", ":id"]
    if (parts[2] === "patients" && parts[3] && parts[3] !== "new") {
      return parts[3];
    }
    return null;
  })();

  // Patients list — /doctor/patients (no id, no /new). Pushed as overlay
  // since /my-ai is the only base section after the single-tab IA cut.
  const patientsListMatch = (() => {
    const parts = location.pathname.split("/");
    return parts[2] === "patients" && !parts[3];
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

  // Settings subpage detection
  // /doctor/settings → SettingsPage list
  // /doctor/settings/persona → PersonaSubpage
  // /doctor/settings/knowledge → KnowledgeSubpage
  // /doctor/settings/knowledge/add → AddKnowledgeSubpage
  // /doctor/settings/knowledge/:id → KnowledgeDetailSubpage
  const settingsMatch = (() => {
    const parts = location.pathname.split("/");
    if (parts[2] !== "settings") return null;
    const sub = parts[3]; // persona | knowledge | undefined
    const sub2 = parts[4]; // add | :id | undefined
    return { sub, sub2 };
  })();
  const settingsActive = !!settingsMatch;

  // Derive a unique route key for overlay subpages (null = base only, no overlay)
  const overlayRouteKey = (() => {
    if (intakeActive) return "intake";
    if (patientDetailMatch) {
      // Tab changes within patient detail use ?view= with replace — same overlay key
      return `patient-${patientDetailMatch}`;
    }
    if (reviewDetailMatch) return `review-${reviewDetailMatch}`;
    if (settingsActive) {
      const { sub, sub2 } = settingsMatch;
      return `settings-${sub || "main"}${sub2 ? `-${sub2}` : ""}`;
    }
    if (patientsListMatch) return "patients";
    return null;
  })();

  // Freeze the base tab content when an overlay is active/animating.
  // This prevents the tab underneath from switching (e.g., tasks → patients list)
  // while the overlay page slides in on top.
  const frozenSectionRef = useRef(activeSection);
  if (!overlayRouteKey) {
    frozenSectionRef.current = activeSection;
  }
  const baseSection = frozenSectionRef.current;

  // Render function for page stack — creates content for a given route key.
  // useCallback ensures stable reference so the stack doesn't re-render entries.
  const renderContent = useCallback((key) => {
    if (key === "intake") {
      return (
        <IntakePage
          doctorId={doctorId}
          patientContext={intakePatientContext}
          onComplete={() => navigate("/doctor/patients", { replace: true })}
          onCancel={() => navigate("/doctor/patients", { replace: true })}
        />
      );
    }
    if (key.startsWith("patient-")) {
      const id = key.replace("patient-", "");
      return <PatientDetail patientId={id} />;
    }
    if (key.startsWith("review-")) {
      return <ReviewPage recordId={key.replace("review-", "")} />;
    }
    if (key === "patients") {
      return <PatientsPage />;
    }
    if (key.startsWith("settings-")) {
      const parts = key.replace("settings-", "").split("-");
      const sub = parts[0];
      const sub2 = parts[1];
      if (sub === "persona" && sub2 === "pending") return <PendingReviewSubpage />;
      if (sub === "persona" && sub2 === "teach") return <TeachByExampleSubpage />;
      if (sub === "persona" && sub2 === "onboarding") return <PersonaOnboardingSubpage />;
      if (sub === "persona") return <PersonaSubpage />;
      if (sub === "knowledge" && (sub2 === "add" || sub2 === "new")) return <AddKnowledgeSubpage />;
      // Legacy redirect — pending rules now live inside the Knowledge tab (?tab=pending).
      if (sub === "knowledge" && sub2 === "pending") {
        return <Navigate to="/doctor/settings/knowledge?tab=pending" replace />;
      }
      if (sub === "knowledge" && sub2) return <KnowledgeDetailSubpage itemId={sub2} />;
      if (sub === "knowledge") return <KnowledgeSubpage />;
      if (sub === "about") return <AboutSubpage />;
      if (sub === "teach") return <TeachByExampleSubpage />;
      if (sub === "pending") return <PendingReviewSubpage />;
      // Note: `sub === "review"` was removed — ReviewSubpage is a presentational
      // component that expects props (record + suggestions) and rendered blank
      // when navigated directly. Real review flow goes through /doctor/review/:id.
      if (sub === "template" || sub === "templates") return <TemplateSubpage />;
      if (sub === "qr") return <QrSubpage />;
      return <SettingsPage />;
    }
    return null;
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Page stack — keeps previous pages mounted when navigating deeper
  const { stackEntries } = usePageStack(overlayRouteKey, renderContent);

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

      {/* Top NavBar — feedback on the left, add-to-desktop on the right.
          Subpages render their own NavBar inside the page-stack overlay. */}
      <NavBar
          backArrow={
            <FeedbackPopover>
              <div
                role="button"
                aria-label="反馈"
                style={{
                  padding: 8,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-start",
                }}
              >
                <FeedbackOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
              </div>
            </FeedbackPopover>
          }
          onBack={() => { /* no-op — left slot is feedback, not back nav */ }}
          right={
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-end",
              }}
            >
              <AddToDesktopPopover />
            </div>
          }
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          我的AI
        </NavBar>

      {/* Content area — base section is always MyAIPage in single-tab IA */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
        }}
      >
        <MyAIPage doctorId={doctorId} />
      </div>

      {/* Page stack — positioned over the ENTIRE page */}
      {stackEntries.map((entry) => (
        <div key={entry.key} style={entry.style}>
          {entry.content}
        </div>
      ))}
    </div>
  );
}
