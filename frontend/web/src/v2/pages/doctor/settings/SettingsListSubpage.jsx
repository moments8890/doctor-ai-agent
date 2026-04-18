/**
 * @route /doctor/settings/preferences
 *
 * SettingsListSubpage v2 — font scale, logout, about.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, List, Popup, Button, Toast, Dialog } from "antd-mobile";
import { CheckOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useFontScaleStore, saveFontScaleToServer } from "../../../../store/fontScaleStore";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

const FONT_SCALE_LEVELS = [
  { key: "standard",   label: "标准",     size: 14 },
  { key: "large",      label: "大字",     size: 17 },
  { key: "extraLarge", label: "特大字",   size: 19 },
];

export default function SettingsListSubpage({ onLogout }) {
  const navigate = useNavigate();
  const { fontScale, setFontScale } = useFontScaleStore();
  const { doctorId, doctorName } = useDoctorStore();
  const [fontScaleOpen, setFontScaleOpen] = useState(false);

  const currentFontLabel = FONT_SCALE_LEVELS.find((f) => f.key === fontScale)?.label || "标准";

  function handleSetFontScale(key) {
    setFontScale(key);
    saveFontScaleToServer(doctorId);
    setFontScaleOpen(false);
  }

  function handleLogout() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      confirmText: "退出",
      cancelText: "取消",
      onConfirm: () => {
        if (onLogout) {
          onLogout();
        } else {
          // Fallback: clear auth and redirect to login
          localStorage.removeItem("doctorAuth");
          window.location.href = "/login";
        }
      },
    });
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        设置
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Account info */}
        <div
          style={{
            padding: "16px",
            backgroundColor: APP.surface,
            borderBottom: `0.5px solid ${APP.border}`,
            marginBottom: 16,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 24,
              backgroundColor: "#576B95",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: APP.surface,
              fontSize: 18,
              fontWeight: 600,
              flexShrink: 0,
            }}
          >
            {(doctorName || doctorId || "?").charAt(0).toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600, color: APP.text1 }}>
              {doctorName || doctorId}
            </div>
            <div style={{ fontSize: 12, color: APP.text4, marginTop: 2 }}>{doctorId}</div>
          </div>
        </div>

        {/* General settings */}
        <List header="通用">
          <List.Item
            arrow
            description={currentFontLabel}
            onClick={() => setFontScaleOpen(true)}
          >
            字体大小
          </List.Item>
        </List>

        {/* About section */}
        <List header="关于" style={{ marginTop: 16 }}>
          <List.Item
            description="医生AI助手"
            arrow={false}
          >
            关于
          </List.Item>
        </List>

        {/* Logout */}
        <div style={{ marginTop: 32, padding: "0 16px" }}>
          <Button
            block
            color="danger"
            fill="outline"
            onClick={handleLogout}
          >
            退出登录
          </Button>
        </div>

        <div style={{ height: 48 }} />
      </div>

      {/* Font scale picker */}
      <Popup
        visible={fontScaleOpen}
        onMaskClick={() => setFontScaleOpen(false)}
        position="bottom"
        bodyStyle={{ borderRadius: "12px 12px 0 0" }}
      >
        <div
          style={{
            padding: "16px 0",
            paddingBottom: "calc(16px + env(safe-area-inset-bottom, 0px))",
          }}
        >
          <div
            style={{
              textAlign: "center",
              fontSize: 16,
              fontWeight: 600,
              color: APP.text1,
              padding: "0 0 12px",
              borderBottom: `0.5px solid ${APP.border}`,
              marginBottom: 4,
            }}
          >
            字体大小
          </div>
          {FONT_SCALE_LEVELS.map((level) => {
            const active = fontScale === level.key;
            return (
              <div
                key={level.key}
                onClick={() => handleSetFontScale(level.key)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 20px",
                  cursor: "pointer",
                  borderBottom: `0.5px solid ${APP.borderLight}`,
                  backgroundColor: active ? APP.primaryLight : "transparent",
                }}
              >
                <span
                  style={{
                    fontSize: level.size,
                    fontWeight: active ? 600 : 400,
                    color: active ? "#07C160" : APP.text1,
                  }}
                >
                  {level.label}
                </span>
                {active && (
                  <CheckOutline style={{ color: "#07C160", fontSize: 18 }} />
                )}
              </div>
            );
          })}
        </div>
      </Popup>
    </div>
  );
}
