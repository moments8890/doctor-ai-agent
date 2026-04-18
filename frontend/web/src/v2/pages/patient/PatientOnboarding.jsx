/**
 * PatientOnboarding v2 — single dismissible screen shown on first login.
 * Scoped to patient_id via localStorage key to handle shared devices.
 * antd-mobile only, no MUI.
 */
import { Button } from "antd-mobile";
import { ContentOutline, FlagOutline } from "antd-mobile-icons";
import { APP, FONT, RADIUS } from "../../theme";

const FEATURES = [
  { bg: APP.primary, label: "随时咨询", desc: "AI助手帮你解答健康问题", icon: <ContentOutline style={{ fontSize: 20, color: APP.white }} /> },
  { bg: APP.accent, label: "健康档案", desc: "病历和检查结果一目了然", icon: <ContentOutline style={{ fontSize: 20, color: APP.white }} /> },
  { bg: APP.warning, label: "任务提醒", desc: "用药和复查不再遗漏", icon: <FlagOutline style={{ fontSize: 20, color: APP.white }} /> },
];

/** Returns the localStorage key scoped to a patient id. */
export function patientOnboardingDoneKey(patientId) {
  return `patient_onboarding_done_${patientId || ""}`;
}

/** Returns true if onboarding has been dismissed for this patient. */
export function isOnboardingDone(patientId) {
  return !!localStorage.getItem(patientOnboardingDoneKey(patientId));
}

/** Marks onboarding as done in localStorage. */
export function markOnboardingDone(patientId) {
  localStorage.setItem(patientOnboardingDoneKey(patientId), "1");
}

export default function PatientOnboarding({ doctorName, doctorSpecialty, onDismiss }) {
  return (
    <div style={{
      position: "absolute",
      inset: 0,
      zIndex: 100,
      background: APP.surface,
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        background: `linear-gradient(135deg, ${APP.primary} 0%, ${APP.primaryHover} 100%)`,
        paddingTop: 48,
        paddingBottom: 32,
        paddingLeft: 24,
        paddingRight: 24,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
      }}>
        {/* Avatar */}
        <div style={{
          width: 64,
          height: 64,
          borderRadius: RADIUS.circle,
          background: APP.white,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 28,
          fontWeight: 700,
          color: APP.primary,
          marginBottom: 16,
          flexShrink: 0,
        }}>
          {doctorName ? doctorName[0] : "医"}
        </div>

        <div style={{ fontSize: 18, fontWeight: 600, color: APP.white, marginBottom: 4 }}>
          {doctorName ? `${doctorName}的AI健康助手` : "AI健康助手"}
        </div>

        {doctorSpecialty && (
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.8)" }}>
            {doctorSpecialty}
          </div>
        )}
      </div>

      {/* Features */}
      <div style={{ flex: 1, padding: "24px 24px 16px", display: "flex", flexDirection: "column", gap: 20, overflowY: "auto" }}>
        <div style={{ fontSize: FONT.main, color: APP.text3, textAlign: "center" }}>
          我会帮助{doctorName || "医生"}为你提供更好的随访服务
        </div>

        {FEATURES.map((f) => (
          <div key={f.label} style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{
              width: 44,
              height: 44,
              borderRadius: RADIUS.lg,
              background: f.bg,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
              flexShrink: 0,
            }}>
              {f.icon}
            </div>
            <div>
              <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>{f.label}</div>
              <div style={{ fontSize: FONT.sm, color: APP.text3, marginTop: 2 }}>{f.desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div style={{ padding: "8px 24px 32px" }}>
        <Button
          color="primary"
          block
          size="large"
          onClick={onDismiss}
          style={{ "--border-radius": `${RADIUS.lg}px` }}
        >
          开始使用
        </Button>
      </div>

      {/* Skip */}
      <div
        onClick={onDismiss}
        style={{
          position: "absolute",
          top: 16,
          right: 16,
          fontSize: FONT.sm,
          color: "rgba(255,255,255,0.7)",
          cursor: "pointer",
          padding: "4px 8px",
        }}
      >
        跳过
      </div>
    </div>
  );
}
