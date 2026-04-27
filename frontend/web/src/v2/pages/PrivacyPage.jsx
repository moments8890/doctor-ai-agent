/**
 * @route /privacy
 *
 * PrivacyPage v2 — static privacy policy.
 * antd-mobile only, no MUI.
 */
import { SafeArea, NavBar } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { APP } from "../theme";
import PrivacyContent from "./PrivacyContent";

export default function PrivacyPage() {
  const navigate = useNavigate();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: APP.surfaceAlt, overflow: "hidden" }}>
      <SafeArea position="top" />
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        隐私政策
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        <PrivacyContent />
      </div>
    </div>
  );
}
