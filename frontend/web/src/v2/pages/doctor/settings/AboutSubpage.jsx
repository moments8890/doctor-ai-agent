/**
 * @route /doctor/settings/about
 *
 * AboutSubpage v2 — static about page.
 * antd-mobile only, no MUI.
 */
import { NavBar, List } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { APP } from "../../../theme";

export default function AboutSubpage() {
  const navigate = useNavigate();

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
        关于
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* App icon + branding */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "40px 24px 32px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 18,
              backgroundColor: "#07C160",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 16,
              fontSize: 36,
              color: "#fff",
              fontWeight: 700,
            }}
          >
            医
          </div>
          <div
            style={{ fontSize: 20, fontWeight: 700, color: APP.text1, marginBottom: 6 }}
          >
            AI 医疗助手
          </div>
          <div style={{ fontSize: 13, color: APP.text4, marginBottom: 20 }}>
            版本 1.0.0
          </div>
          <div
            style={{
              fontSize: 14,
              color: APP.text3,
              lineHeight: 1.8,
              maxWidth: 300,
            }}
          >
            智能医疗助手为医生提供 AI 辅助病历记录、患者管理和任务跟踪功能，帮助提升诊疗效率。
          </div>
        </div>

        {/* App info list */}
        <List header="应用信息">
          <List.Item extra="1.0.0" arrow={false}>
            版本号
          </List.Item>
          <List.Item extra="医生AI助手" arrow={false}>
            产品名称
          </List.Item>
          <List.Item extra="Anthropic" arrow={false}>
            AI 提供商
          </List.Item>
        </List>

        <div style={{ height: 48 }} />
      </div>
    </div>
  );
}
