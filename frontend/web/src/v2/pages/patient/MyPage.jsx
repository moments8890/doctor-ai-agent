/**
 * MyPage — patient "我的" settings page (v2, antd-mobile, doctor-card-pattern).
 *
 * Mirrors doctor SettingsPage visual structure: profile card, section headers
 * (icon + label) above each Card, TintedIconRow rows inside Cards, danger-
 * outlined logout button, security footer. The local SectionHeader stays local
 * — patient app is the only second consumer right now and the abstraction
 * isn't earned yet (different from doctor SettingsPage's local SectionHeader,
 * which has the same {Icon, iconColor, title} signature).
 */
import { useState } from "react";
import { Button, Dialog, Popup, Radio, Space } from "antd-mobile";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import FormatSizeOutlinedIcon from "@mui/icons-material/FormatSizeOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import LogoutOutlinedIcon from "@mui/icons-material/LogoutOutlined";
import SecurityOutlinedIcon from "@mui/icons-material/SecurityOutlined";
import { useNavigate } from "react-router-dom";

import { APP, FONT, ICON, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { Card, NameAvatar, TintedIconRow } from "../../components";
import {
  FONT_SCALE_OPTIONS,
  getFontScale,
  setFontScale as persistFontScale,
  getFontScaleLabel,
} from "../../lib/patientFontScale";

const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";

// Local section header (icon + label, sits OUTSIDE Card on the gray bg).
// Same visual pattern as doctor/SettingsPage's local SectionHeader.
function SectionHeader({ Icon, iconColor, title }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "0 20px",
        margin: "16px 0 8px",
      }}
    >
      <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      <span style={{ fontSize: FONT.base, color: APP.text3, fontWeight: 500 }}>
        {title}
      </span>
    </div>
  );
}

export default function MyPage({ patientName, doctorName, doctorSpecialty, onLogout }) {
  const navigate = useNavigate();
  const [fontScale, setFontScaleState] = useState(getFontScale);
  const [showFontPopup, setShowFontPopup] = useState(false);

  function handleFontScaleChange(tier) {
    setFontScaleState(tier);
    persistFontScale(tier);
    setShowFontPopup(false);
  }

  function handleReplayOnboarding() {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.removeItem(ONBOARDING_DONE_KEY_PREFIX + patientId);
    window.location.reload();
  }

  function handleLogoutTap() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      cancelText: "取消",
      confirmText: "退出",
      onConfirm: onLogout,
    });
  }

  return (
    <div style={pageContainer}>
      <div style={{ ...scrollable, paddingTop: 12, paddingBottom: 24 }}>
        {/* Profile card — display only */}
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
            <NameAvatar name={patientName || "患"} size={48} color={APP.primary} charPosition="last" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: FONT.lg, fontWeight: 700, color: APP.text1 }}>
                {patientName || "患者"}
              </div>
              <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                患者
              </div>
            </div>
          </div>
        </Card>

        {/* My doctor */}
        {doctorName && (
          <>
            <SectionHeader Icon={LocalHospitalOutlinedIcon} iconColor={APP.accent} title="我的医生" />
            <Card>
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
                <NameAvatar name={doctorName} size={44} color={APP.accent} charPosition="last" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
                    {doctorName}
                  </div>
                  {doctorSpecialty && (
                    <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                      {doctorSpecialty}
                    </div>
                  )}
                </div>
              </div>
            </Card>
          </>
        )}

        {/* General */}
        <SectionHeader Icon={SettingsOutlinedIcon} iconColor={APP.accent} title="通用" />
        <Card>
          <TintedIconRow
            Icon={InfoOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="关于"
            subtitle="版本信息"
            onClick={() => navigate("/patient/profile/about")}
            isFirst
          />
          <TintedIconRow
            Icon={LockOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="隐私政策"
            subtitle="数据使用与保护"
            onClick={() => navigate("/patient/profile/privacy")}
          />
          <TintedIconRow
            Icon={FormatSizeOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="字体大小"
            subtitle={getFontScaleLabel(fontScale)}
            onClick={() => setShowFontPopup(true)}
          />
          <TintedIconRow
            Icon={RefreshOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="重新查看引导"
            onClick={handleReplayOnboarding}
          />
        </Card>

        {/* Logout */}
        <div style={{ margin: "24px 12px 8px" }}>
          <Button
            block
            color="danger"
            fill="outline"
            onClick={handleLogoutTap}
            style={{
              "--border-radius": `${RADIUS.lg}px`,
              padding: "14px 0",
              fontSize: FONT.md,
              fontWeight: 600,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <LogoutOutlinedIcon sx={{ fontSize: ICON.sm }} />
              退出登录
            </span>
          </Button>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            padding: "8px 16px",
            fontSize: FONT.sm,
            color: APP.text4,
          }}
        >
          <SecurityOutlinedIcon sx={{ fontSize: ICON.xs, color: APP.text4 }} />
          <span>退出后将清除本地缓存，确保账号安全</span>
        </div>

        {/* Font-size Popup (3 options preserved — patient audience needs 特大) */}
        <Popup
          visible={showFontPopup}
          onMaskClick={() => setShowFontPopup(false)}
          position="bottom"
          bodyStyle={{ borderRadius: `${RADIUS.xl}px ${RADIUS.xl}px 0 0`, padding: "16px 16px 32px" }}
        >
          <div style={{ textAlign: "center", fontSize: FONT.md, fontWeight: 600, color: APP.text1, marginBottom: 16 }}>
            字体大小
          </div>
          <Radio.Group value={fontScale} onChange={handleFontScaleChange}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {FONT_SCALE_OPTIONS.map((o) => (
                <Radio key={o.key} value={o.key} style={{ width: "100%", fontSize: FONT.md }}>
                  {o.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
          <Button
            block
            color="default"
            style={{ marginTop: 16, borderRadius: RADIUS.md }}
            onClick={() => setShowFontPopup(false)}
          >
            取消
          </Button>
        </Popup>
      </div>
    </div>
  );
}
