/**
 * @route /doctor/settings
 *
 * SettingsPage v2 — antd-mobile List navigation to settings subpages.
 * No MUI. Delegates subpage rendering to DoctorPage routing.
 */
import { List, NavBar } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { APP } from "../../theme";

export default function SettingsPage() {
  const navigate = useNavigate();

  const items = [
    { label: "AI人设", sublabel: "配置AI助手的沟通风格", path: "/doctor/settings/persona" },
    { label: "知识库", sublabel: "管理AI助手参考规则", path: "/doctor/settings/knowledge" },
    { label: "设置", sublabel: "字体、退出登录", path: "/doctor/settings/preferences" },
  ];

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
        <div style={{ height: 16 }} />
        <List>
          {items.map((item) => (
            <List.Item
              key={item.path}
              description={item.sublabel}
              arrow
              onClick={() => navigate(item.path)}
            >
              {item.label}
            </List.Item>
          ))}
        </List>
      </div>
    </div>
  );
}
